# SPDX-License-Identifier: BSD-2-Clause
"""Separate bounded BAR relocation/restore seam, never endpoint decode or DMA.

The callback verifies current owner/thread/phase and exact owned source objects
on EVERY core use. The actual config transport keeps its per-access guards.
This module does not build a loader, publish a package or authorize hardware.
"""
from tools.rpi5 import rp1_bars_root_profile as util
ROOT=util.ROOT
FROZEN=ROOT/'build/rpi5/pcie-guard-composition-kernel-20261013-v1/overlay'
PROFILE='rp1-all-bar-relocation-restore-no-decode-v1'
FIELDS='CALL=%u RC=%d STATE=%u SLOT=%u TXNS=%u WRITES=%u ASSIGNED=%02x RESTORED=%02x'


def header(text):
    text=util.once(text,'#include "rp1_bars_plan.h"','#include "rp1_bars_plan.h"\n#include "rp1_bars_assign.h"')
    text=util.once(text,'    struct rpi5_rp1_bars_plan barsPlan;',
        '    struct rpi5_rp1_bars_plan barsPlan;\n'
        '    struct rpi5_rp1_assignment_observation assigned,restored;\n'
        '    struct rpi5_rp1_mapping_candidate mapping;')
    text=util.once(text,'    struct rpi5_rp1_bars_probe barsProbe={};',
        '    struct rpi5_rp1_bars_probe barsProbe={};\n'
        '    struct rpi5_rp1_assignment assignment={};\n'
        '    struct rpi5_rp1_bars_size assignmentSizes={};\n'
        '    bool assignmentActive=false;unsigned diagAssignCall=0;int diagAssignRC=0;\n'
        '    static int assignmentSource(void *,const struct rpi5_pcie_config *,const struct rpi5_pcie_fdt *,\n'
        '        const struct rpi5_rp1_bars_probe *,const struct rpi5_rp1_bars_size *);\n'
        '    static int assignmentAuthorize(void *,const struct rpi5_pcie_config_request *);\n'
        '    static int assignmentWrite(void *,uint32_t,uint32_t,uint32_t);')
    return util.once(text,'    unsigned traceBarsCall() const { return diagBarsCall; }',
        '\n'.join('    '+kind+' traceAssign'+name+'() const { return '+value+'; }' for kind,name,value in (
            ('unsigned','Call','diagAssignCall'),('int','RC','diagAssignRC'),('unsigned','State','assignment.state'),
            ('unsigned','Slot','assignment.selected'),('unsigned','Transactions','assignment.transactions'),
            ('unsigned','Writes','assignment.writes_started'),('unsigned','Assigned','assignment.assigned_mask'),
            ('unsigned','Restored','assignment.restored_mask')))+'\n'
        '    unsigned traceBarsCall() const { return diagBarsCall; }')


def diagnostic_calls():
    args=['transport?transport->traceAssign'+name+'():0' for name in
        ('Call','RC','State','Slot','Transactions','Writes','Assigned','Restored')]
    rows=['    kprintf("RPI5XNU:PCIEID:ASSIGN '+FIELDS+'\\n",\n        '+',\n        '.join(args)+');']
    for name,member in (('ASSIGNED_BARS','assigned'),('RESTORED_BARS','restored')):
        args=['observed.'+member+'.bar['+str(i)+']' for i in range(6)]
        rows.append('    kprintf("RPI5XNU:PCIEID:'+name+' '+
            ' '.join('BAR'+str(i)+'=%08x' for i in range(6))+'\\n",\n        '+',\n        '.join(args)+');')
    fields=('BAR1_START','BAR1_END','GEM_START','GEM_END','CLOCK_START','CLOCK_END')
    args=['(unsigned long long)observed.mapping.'+region+'.'+edge for region in ('bar1_cpu','gem_pages','clock_pages') for edge in ('start','end')]
    rows.append('    kprintf("RPI5XNU:PCIEID:MAPPING '+' '.join(k+'=%llu' for k in fields)+
        '\\n",\n        '+',\n        '.join(args)+');')
    return '\n'.join(rows)+'\n'


def trial(text):
    return util.once(text,'    kprintf("RPI5XNU:PCIEID:END ',diagnostic_calls()+'    kprintf("RPI5XNU:PCIEID:END ')


def transport(text):
    text=util.once(text,'rp1BarsAuthorize,rp1Read,rp1BarsWrite,order',
        'assignmentAuthorize,rp1Read,assignmentWrite,order')
    # Declare before any goto target so all failure paths remain legal C++.
    text=util.once(text,'    struct bcm2712_rp1_observation result = {};',
        '    struct bcm2712_rp1_observation result = {};\n'
        '    const struct rpi5_rp1_assignment_source source={this,assignmentSource};')
    return util.once(text,'    diagBarsCall=5;\n    setPhase(BCM2712_PHY_COMPLETE);',
        '''    diagBarsCall=5;
    assignmentSizes=result.bars;assignmentActive=true;
    diagAssignCall=1;diagAssignRC=rpi5_rp1_bars_assign(&assignment,&rp1Config,&binding,
        &barsProbe,&assignmentSizes,&source,&result.assigned);
    if(diagAssignRC)goto rp1_failed;
    diagAssignCall=2;
    if(!guard())goto rp1_failed;
    diagAssignCall=3;diagAssignRC=rpi5_rp1_bars_mapping_candidate(&assignment,&binding,&result.mapping);
    if(diagAssignRC)goto rp1_failed;
    /* This geometry is not mapped or dereferenced. A future Device-map owner
     * must revoke its mappings before the following restoration operation. */
    diagAssignCall=4;diagAssignRC=rpi5_rp1_bars_restore(&assignment,&result.restored);
    if(diagAssignRC)goto rp1_failed;
    diagAssignCall=5;
    if(!guard())goto rp1_failed;
    assignmentActive=false;diagAssignCall=6;
    setPhase(BCM2712_PHY_COMPLETE);''')


ADAPTER=r'''
/* In-memory provenance only: all real PM/IRQ/FW and lifecycle checks remain
 * in the unchanged config transport. No SMC/MMIO/clock read here. */
int BCM2712PCIePHYTransport::assignmentSource(void *context,
    const struct rpi5_pcie_config *config,const struct rpi5_pcie_fdt *binding,
    const struct rpi5_rp1_bars_probe *probe,const struct rpi5_rp1_bars_size *sizes)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !self->onOwnerThread() || !self->trialMode || !self->controllerMode ||
        !self->assignmentActive || self->getPhase()!=BCM2712_PHY_RP1_INSPECTING ||
        self->lifecyclePhase!=BCM2712_CONTROLLER_RELEASED ||
        __atomic_load_n(&phyOwner,__ATOMIC_ACQUIRE)!=self || !self->providerOpened ||
        !self->ownerProvider || !self->ownerProvider->isOpen(self) || !self->claimAttempted ||
        !self->irqClaimed || !self->fwClaimed || self->claimingIRQ || self->claimingFW ||
        self->checkingLifecycle || config!=&self->rp1Config || binding!=&self->binding ||
        probe!=&self->barsProbe || sizes!=&self->assignmentSizes ||
        (config->state!=RPI5_PCIE_CONFIG_READY && config->state!=RPI5_PCIE_CONFIG_BUSY))return -1;
    return 0;
}
int BCM2712PCIePHYTransport::assignmentAuthorize(void *context,
    const struct rpi5_pcie_config_request *request)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self)return -1;
    if(!self->assignmentActive)return rp1BarsAuthorize(context,request);
    if(!self->rp1Locked || self->rp1Config.state!=RPI5_PCIE_CONFIG_BUSY ||
        !rpi5_rp1_assignment_write_allowed(&self->assignment,request))return -1;
    return self->guard()?0:-1;
}
int BCM2712PCIePHYTransport::assignmentWrite(void *context,uint32_t offset,uint32_t width,uint32_t value)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self)return -1;
    if(!self->assignmentActive)return rp1BarsWrite(context,offset,width,value);
    if(offset==0x9000)return rp1Write(context,offset,width,value);
    if(!self->onOwnerThread())return -1;
    self->diagIOBank=BCM2712_PHY_BRIDGE;self->diagIOOffset=offset;
    self->diagIODirection=1;self->diagIOStage=1;self->diagIOValue=value;
    if(offset<0x8010 || offset>0x8024 || (offset&3) || width!=4)return -1;
    const struct rpi5_pcie_config_request request={1,0,0,offset-0x8000,4,1,value};
    if(assignmentAuthorize(context,&request))return -1;
    self->diagIOStage=2;
    __asm__ volatile("dmb osh" ::: "memory");
    *reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=value;
    __asm__ volatile("dsb sy" ::: "memory");
    self->diagIOStage=3;
    if(!self->guard())return -1;
    self->diagIOStage=4;return 0;
}
'''


def emit(folder):
    folder.mkdir(exist_ok=False)
    for path in FROZEN.iterdir():
        if path.is_file():(folder/path.name).write_bytes(path.read_bytes())
    for name,adapt in (('BCM2712PCIePHYTransport.h',header),('BCM2712RP1ConfigTransport.inc',transport),
        ('BCM2712PCIeIDTrialProgress.inc',trial)):
        path=folder/name;path.write_text(adapt(path.read_text()))
    (folder/'BCM2712RP1AssignmentTransport.inc').write_text(ADAPTER)
    path=folder/'BCM2712PCIePHYTransport.cpp'
    path.write_text(path.read_text()+'\n#include "BCM2712RP1AssignmentTransport.inc"\n')
    for suffix in ('h','c'):
        source=ROOT/'loader/rpi5'/('rp1_bars_assign.'+suffix)
        (folder/source.name).write_bytes(source.read_bytes())
    return path,folder/'rp1_bars_assign.c'
