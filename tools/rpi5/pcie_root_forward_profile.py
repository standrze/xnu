# SPDX-License-Identifier: BSD-2-Clause
"""Distinct root MEM/window cycle around the frozen read-only GEM callback."""
from tools.rpi5 import rp1_gem_known_clock_profile as prior
ROOT,util=prior.ROOT,prior.util
FROZEN=ROOT/'build/rpi5/pcie-gem-identify-kernel-20261013-v2/overlay'
PROFILE='pcie-root-mem-forwarding-around-gem-v1'
FIELDS=prior.FIELDS


def header(text):
    text=util.once(text,'#include "rp1_gem_identify.h"','#include "rp1_gem_identify.h"\n#include "pcie_root_forward.h"')
    text=util.once(text,'    struct rpi5_gem_observation gem;',
        '    struct rpi5_gem_observation gem;\n    struct rpi5_root_forward_observation rootForward;')
    text=util.once(text,'    struct rpi5_gem_identify gemSession={};',
        '''    struct rpi5_gem_identify gemSession={};
    struct rpi5_root_forward rootForward={};
    struct rpi5_root_forward_observation rootForwardObserved={};
    int diagRootForwardRC=0;unsigned diagRootForwardCall=0;
    static int gemIdentifyUnderRoot(void *,const struct rpi5_rp1_decode_cycle *);
    static int rootForwardSource(void *,const struct rpi5_root_forward *,const struct rpi5_rp1_decode_cycle *);
    static int rootForwardRead(void *,uint32_t,unsigned,uint32_t *);
    static int rootForwardWrite(void *,uint32_t,unsigned,uint32_t);''')
    return util.once(text,'    int traceGemRC()',
        '''    int traceRootForwardRC() const { return diagRootForwardRC; }
    unsigned traceRootForwardCall() const { return diagRootForwardCall; }
    const struct rpi5_root_forward *traceRootForward() const { return &rootForward; }
    int traceGemRC()''')


def gem_adapter(text):
    text=util.once(text,'int BCM2712PCIePHYTransport::gemIdentify(',
        'int BCM2712PCIePHYTransport::gemIdentifyUnderRoot(')
    return util.once(text,'    if(!self || s!=&self->gemSession',
        '    if(!self || self->rootForward.state!=RPI5_ROOT_FORWARD_LIVE || s!=&self->gemSession')


def caller(text):
    return util.once(text,'    result.gem=gemObserved;',
        '    result.rootForward=rootForwardObserved;\n    result.gem=gemObserved;')


ADAPTER=r'''
int BCM2712PCIePHYTransport::rootForwardSource(void *context,const struct rpi5_root_forward *s,
    const struct rpi5_rp1_decode_cycle *d)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || s!=&self->rootForward || d!=&self->decodeCycle ||
        d->state!=RPI5_RP1_DECODE_MAPPED || d->mapped!=3 || d->unmapped ||
        d->pending_write || d->pending_map || decodeSource(context,d,&self->assignment) ||
        !self->decodeMapValid(0,d->geometry.gem_pages) ||
        !self->decodeMapValid(1,d->geometry.clock_pages))return -1;
    return 0;
}
int BCM2712PCIePHYTransport::rootForwardRead(void *context,uint32_t offset,unsigned width,uint32_t *out)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !out || !rpi5_root_forward_access_allowed(&self->rootForward,offset,width,0,0) ||
        !self->guard())return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    uint32_t value=width==2?*reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset):
        *reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset);
    __asm__ volatile("dsb sy" ::: "memory");
    if(!self->guard() || rootForwardSource(context,&self->rootForward,&self->decodeCycle))return -1;
    *out=value;return 0;
}
int BCM2712PCIePHYTransport::rootForwardWrite(void *context,uint32_t offset,unsigned width,uint32_t value)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !rpi5_root_forward_access_allowed(&self->rootForward,offset,width,1,value) ||
        !self->guard())return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    if(width==2)*reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=(uint16_t)value;
    else *reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=value;
    __asm__ volatile("dsb sy" ::: "memory");
    return self->guard() && !rootForwardSource(context,&self->rootForward,&self->decodeCycle)?0:-1;
}
int BCM2712PCIePHYTransport::gemIdentify(void *context,const struct rpi5_rp1_decode_cycle *d)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || rootForwardSource(context,&self->rootForward,d))return -3;
    const struct rpi5_root_forward_io io={self,rootForwardSource,rootForwardRead,rootForwardWrite,gemIdentifyUnderRoot};
    self->diagRootForwardCall=1;
    self->diagRootForwardRC=rpi5_root_forward_run(&self->rootForward,d,&io,&self->rootForwardObserved);
    if(self->diagRootForwardRC)return self->diagRootForwardRC;
    self->diagRootForwardCall=2;return 0;
}
'''


def diagnostic_calls():
    lines=['    const struct rpi5_root_forward emptyRootForward={};',
        '    const struct rpi5_root_forward *rf=transport?transport->traceRootForward():&emptyRootForward;',
        '    kprintf("RPI5XNU:PCIEID:ROOT_MEM CALL=%u RC=%d STAGE=%u READS=%u WRITES=%u PENDING=%u\\n",',
        '        transport?transport->traceRootForwardCall():0,transport?transport->traceRootForwardRC():0,',
        '        rf->state,rf->reads,rf->writes,rf->pending);',
        '    kprintf("RPI5XNU:PCIEID:ROOT_MEM_COMMAND BEFORE=%04x LIVE=%04x AFTER=%04x\\n",rf->before.command,rf->live.command,rf->after.command);',
        '    kprintf("RPI5XNU:PCIEID:ROOT_MEM_WINDOW BEFORE=%08x WANTED=%08x LIVE=%08x AFTER=%08x\\n",',
        '        rf->before.window,rf->wanted_window,rf->live.window,rf->after.window);',
        '    kprintf("RPI5XNU:PCIEID:ROOT_MEM_CONFIG ID=%08x HDR=%08x BUS=%08x\\n",rf->before.id,rf->before.header,rf->before.buses);',
        '    kprintf("RPI5XNU:PCIEID:ROOT_MEM_IO OFFSET=%08x WIDTH=%u WRITE=%u VALUE=%08x\\n",rf->offset,rf->width,rf->write,rf->value);']
    for i in range(2):
        args=','.join(f'rf->outbound[{i*5+n}]' for n in range(5))
        lines.append(f'    kprintf("RPI5XNU:PCIEID:ROOT_MEM_OUT{i} LO=%08x HI=%08x BASELIMIT=%08x BASEHI=%08x LIMITHI=%08x\\n",{args});')
    return '\n'.join(lines)+'\n'


def emit(folder):
    folder.mkdir(exist_ok=False)
    for path in FROZEN.iterdir():
        if path.is_file():(folder/path.name).write_bytes(path.read_bytes())
    for name,adapt in (('BCM2712PCIePHYTransport.h',header),('BCM2712RP1GEMIdentifyTransport.inc',gem_adapter),
        ('BCM2712RP1ConfigTransport.inc',caller)):
        path=folder/name;path.write_text(adapt(path.read_text()))
    path=folder/'BCM2712PCIeIDTrialProgress.inc'
    path.write_text(util.once(path.read_text(),'    kprintf("RPI5XNU:PCIEID:END ',diagnostic_calls()+'    kprintf("RPI5XNU:PCIEID:END '))
    (folder/'BCM2712RootForwardTransport.inc').write_text(ADAPTER)
    path=folder/'BCM2712PCIePHYTransport.cpp';path.write_text(path.read_text()+'\n#include "BCM2712RootForwardTransport.inc"\n')
    for suffix in ('c','h'):
        source=ROOT/'loader/rpi5'/('pcie_root_forward.'+suffix);(folder/source.name).write_bytes(source.read_bytes())
    return path,folder/'pcie_root_forward.c'
