# SPDX-License-Identifier: BSD-2-Clause
"""Private reset + timed MDIO successor, not an observer or packet driver.

The old GPIO/MDIO artifacts stay byte-for-byte unchanged. This copies their
exact mapping/owner implementations, replaces the twelve raw observer reads
with one held-map action, and retains every actual MMIO pre/post guard. The
action admits fresh no-ASPM root LINK_CONTROL under the sole pre-IOKit owner,
executes a GPIO32-only five-ms pulse, a fresh bounded C22 read sequence, and
restores known original GPIO fields. Any failure quarantines without cleanup.
F_M is admitted only as zero or documented reset encoding0x80 and is preserved
throughout. No IRQ/reset/unknown CTRL bits are written back. No owner limit,
deadline, PHY command, DMA/IRQ/packet activation policy is relaxed.
"""
from tools.rpi5 import rp1_phy_gpio_observe_profile as gpio
from tools.rpi5 import rp1_gem_mdio_timed_profile as timed
ROOT,util=gpio.ROOT,gpio.util
FROZEN=ROOT/'build/rpi5/pcie-phy-gpio-kernel-20261014-v1/overlay'
PROFILE='rp1-phy-reset-timed-mdio-held-maps-v1'


def gpio_header(text):
    text=util.once(text,'    int (*read)(void *,unsigned,uint32_t,uint32_t *);',
        '    /* One bounded action while all three maps remain held. */\n    int (*action)(void *);')
    start=text.index('/* Read-only observer, not a PHY admission/reset routine.')
    end=text.index('int rpi5_phy_gpio_map_allowed',start)
    text=text[:start]+'''/* Private successor map-holder: zero raw observer reads. One action must
 * complete before reverse revocation. Failure quarantines; never retry. */
int rpi5_phy_gpio_action_run(struct rpi5_phy_gpio_session *,const struct rpi5_gem_cap_session *,
    const struct rpi5_phy_gpio_binding *,const struct rpi5_phy_gpio_io *,struct rpi5_phy_gpio_observation *);
'''+text[end:]
    return util.once(text,'int rpi5_phy_gpio_read_allowed(const struct rpi5_phy_gpio_session *,unsigned,uint32_t);\n','')


def gpio_core(text):
    text=text.replace('static const unsigned banks[6]={0,0,1,1,1,2};\n','').replace(
        'static const uint32_t offsets[6]={0x20,0x24,0,4,8,0x14};\n','')
    text=text.replace('s->io.read','s->io.action')
    start=text.index('int rpi5_phy_gpio_read_allowed(');end=text.index('struct run {',start)
    text=text[:start]+text[end:]
    text=util.once(text,'int rpi5_phy_gpio_run(', 'int rpi5_phy_gpio_action_run(')
    start=text.index('    for(unsigned p=0;p<2;p++)for(unsigned w=0;w<6;w++){')
    end=text.index('    for(unsigned j=3;j;j--)',start)
    text=text[:start]+'''    /* No observer reads or historical snapshots authorize this action. */
    s->pending=2;
    if(guard(&r))return s->error;
    struct rpi5_phy_gpio_session action_held;copy(&action_held,s,sizeof action_held);
    int action_rc=io->action(io->context);
    if(!same(&action_held,s,sizeof action_held)||guard(&r))return fail(&r,-3);
    if(action_rc)return fail(&r,(action_rc==-5||action_rc==-6)?action_rc:-4);
    s->pending=0;
'''+text[end:]
    return text


def reset_core(text):
    text=util.once(text,'#define CTRL_MASK 0x0000f01fu',
        '''/* Public RP1 Table8 names [11:5] F_M (RW/reset4). Pinned Linux
 * rp1_set_fsel preserves this field in every bank, including bank1. Admit
 * only zero or the actually observed reset encoding; preserve, never alter. */
#define FILTER_DEFAULT 0x80u
#define CTRL_MASK 0x0000f09fu''')
    text=text.replace('value==0x8005u||value==5||value==o->ctrl_before',
        'value==((o->ctrl_before&FILTER_DEFAULT)|0x8005u)||\n    value==((o->ctrl_before&FILTER_DEFAULT)|5u)||value==o->ctrl_before')
    text=util.once(text,' update(&r,0,0x24,5,0x24,5)',
        ' update(&r,0,0x24,(o->ctrl_before&FILTER_DEFAULT)|5u,0x24,(o->ctrl_before&FILTER_DEFAULT)|5u)')
    text=util.once(text,'if(update(&r,0,0x24,0x8005,0x24,0x8005)',
        'if(update(&r,0,0x24,(o->ctrl_before&FILTER_DEFAULT)|0x8005u,0x24,(o->ctrl_before&FILTER_DEFAULT)|0x8005u)')
    return text


def header(text):
    text=timed.transport_header(timed.old.header(text))
    text=util.once(text,'#include "rp1_gem_mdio.h"',
        '#include "rp1_gem_mdio.h"\n#include "rp1_phy_reset_cycle.h"')
    text=util.once(text,'    struct rpi5_gem_mdio_observation phy;',
        '    struct rpi5_gem_mdio_observation phy;\n    struct rpi5_phy_reset_observation phy_reset;')
    text=util.once(text,'    static int phyGPIORead(void *,unsigned,uint32_t,uint32_t *);',r'''
    struct rpi5_phy_reset_session phyReset={};
    struct rpi5_phy_reset_observation phyResetObserved={};
    uint16_t phyResetLinkControl=0;bool phyResetActionActive=false,phyResetNoASPM=false;
    static int phyResetAction(void *);
    static int phyResetSource(void *,const struct rpi5_phy_reset_session *);
    static int phyResetTime(void *,uint64_t *);
    static int phyResetRead(void *,unsigned,uint32_t,uint64_t,uint64_t,uint32_t *,uint64_t *);
    static int phyResetWrite(void *,unsigned,uint32_t,uint32_t,uint64_t,uint64_t,uint64_t *);
    static int phyResetWait(void *,uint64_t,uint64_t,uint64_t,uint64_t *);
    static int phyResetManage(void *,uint64_t,uint64_t,struct rpi5_gem_mdio_observation *,uint64_t *);''')
    return text


def parent_transport(text):
    text=timed.old.parent_transport(text)
    return util.once(text,'    result.phy=mdioObserved;',
        '    result.phy=mdioObserved;\n    result.phy_reset=phyResetObserved;')


def gem_transport(text):
    text=util.once(text,'{self,phyGPIOSource,phyGPIOMap,phyGPIOUnmap,phyGPIORead}',
        '{self,phyGPIOSource,phyGPIOMap,phyGPIOUnmap,phyResetAction}')
    text=util.once(text,'return rpi5_phy_gpio_run(', 'return rpi5_phy_gpio_action_run(')
    start=text.index('int BCM2712PCIePHYTransport::phyGPIORead(')
    text=text[:start]+timed.old.ADAPTER
    text=timed.transport(text)
    text=util.once(text,'        c!=&self->capabilitySession || b!=&self->binding ||',
        '''        c!=&self->capabilitySession || b!=&self->binding ||
        phyResetSource(context,&self->phyReset) || self->phyReset.pending!=5 || self->phyReset.step!=6 ||''')
    # Enforce the outer window again on every MDIO access, not only its caller.
    text=text.replace('deadline!=self->mdioSession.deadline_us ||',
        'deadline!=self->mdioSession.deadline_us || deadline>self->phyReset.deadline_us ||')
    for name,predicate in (('mdioRead','!rpi5_gem_mdio_read_allowed(&self->mdioSession,offset)'),
        ('mdioWrite','!rpi5_gem_mdio_write_allowed(&self->mdioSession,offset,value)')):
        start=text.index('int BCM2712PCIePHYTransport::'+name+'(')
        end=text.index('\nint BCM2712PCIePHYTransport::',start+1)
        part=text[start:end]
        part=util.once(part,'    if(mdioSource(context,&self->mdioSession,&self->capabilitySession,&self->binding))return -1;',
            '    if(mdioSource(context,&self->mdioSession,&self->capabilitySession,&self->binding) || '+predicate+')return -1;')
        text=text[:start]+part+text[end:]
    return text+ADAPTER


ADAPTER=r'''
int BCM2712PCIePHYTransport::phyResetAction(void *context)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || self->phyResetActionActive || self->phyResetNoASPM ||
        self->phyReset.state!=RPI5_PHY_RESET_UNUSED || self->phyGPIO.pending!=2 ||
        self->phyGPIO.mapped!=7 || self->phyGPIO.unmapped || phyGPIOSource(context,&self->phyGPIO) ||
        self->getPhase()!=BCM2712_PHY_RP1_INSPECTING || !self->onOwnerThread())return -3;
    self->phyResetActionActive=true;
    /* One narrow halfword read, not new generic config access permission.
     * This sole pre-IOKit owner is the only possible LINK_CONTROL writer;
     * its current ownership is rechecked around every subsequent data access.
     * Linux's ASPM GPIO-spacing workaround is unnecessary only with all ASPM
     * and clock-PM bits currently clear. No Slot-Control dummy writes. */
    if(!self->guard())return -3;
    __asm__ volatile("dmb osh" ::: "memory");
    uint16_t link=*reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE]+0xbc);
    __asm__ volatile("dsb sy" ::: "memory");
    if(!self->guard() || phyGPIOSource(context,&self->phyGPIO) || (link&0x103))return -6;
    self->phyResetLinkControl=link;self->phyResetNoASPM=true;
    self->mdioFDTBytes=self->phyGPIOFDT;self->mdioFDTLength=self->phyGPIOFDTLength;
    const struct rpi5_phy_reset_io io={self,phyResetSource,phyResetTime,phyResetRead,
        phyResetWrite,phyResetWait,phyResetManage};
    int rc=rpi5_phy_reset_run(&self->phyReset,&self->phyGPIOBinding,&io,&self->phyResetObserved);
    if(rc)return rc;
    self->phyResetActionActive=false;return 0;
}
int BCM2712PCIePHYTransport::phyResetSource(void *context,const struct rpi5_phy_reset_session *s)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || s!=&self->phyReset || s->self!=s || s->state!=RPI5_PHY_RESET_ACTIVE ||
        s->busy!=1 || s->io.context!=self || !self->phyResetActionActive || !self->phyResetNoASPM ||
        (self->phyResetLinkControl&0x103) || self->phyGPIO.pending!=2 ||
        self->phyGPIO.mapped!=7 || self->phyGPIO.unmapped ||
        phyGPIOSource(context,&self->phyGPIO))return -1;
    for(unsigned i=0;i<3;i++)if(!self->phyGPIOMapValid(i,self->phyGPIO.page[i]))return -1;
    return 0;
}
int BCM2712PCIePHYTransport::phyResetTime(void *context,uint64_t *out)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !out || self->phyReset.pending!=3 || phyResetSource(context,&self->phyReset))return -1;
    uint64_t value;int rc=nowUS(context,&value);
    if(rc || phyResetSource(context,&self->phyReset))return -1;*out=value;return 0;
}
int BCM2712PCIePHYTransport::phyResetRead(void *context,unsigned bank,uint32_t offset,
    uint64_t previous,uint64_t deadline,uint32_t *out,uint64_t *completed)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !out || !completed || bank>2 || previous!=self->phyReset.last_us ||
        deadline!=self->phyReset.deadline_us || phyResetSource(context,&self->phyReset) ||
        !rpi5_phy_reset_read_allowed(&self->phyReset,bank,offset) || !self->guard())return -1;
    auto *map=self->phyGPIOMaps[bank];uint64_t before,after;
    if((offset&3) || offset>map->getLength()-4)return -1;
    if(mdioAccessStamp(previous,deadline,&before))return -5;
    if(phyResetSource(context,&self->phyReset) || !rpi5_phy_reset_read_allowed(&self->phyReset,bank,offset))return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);
    __asm__ volatile("dsb sy" ::: "memory");
    if(!self->guard() || phyResetSource(context,&self->phyReset))return -1;
    if(mdioAccessStamp(before,deadline,&after))return -5;*out=value;*completed=after;return 0;
}
int BCM2712PCIePHYTransport::phyResetWrite(void *context,unsigned bank,uint32_t offset,uint32_t value,
    uint64_t previous,uint64_t deadline,uint64_t *completed)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !completed || bank>2 || previous!=self->phyReset.last_us ||
        deadline!=self->phyReset.deadline_us || phyResetSource(context,&self->phyReset) ||
        !rpi5_phy_reset_write_allowed(&self->phyReset,bank,offset,value) || !self->guard())return -1;
    auto *map=self->phyGPIOMaps[bank];uint64_t before,after;
    if((offset&3) || offset>map->getLength()-4)return -1;
    if(mdioAccessStamp(previous,deadline,&before))return -5;
    if(phyResetSource(context,&self->phyReset) || !rpi5_phy_reset_write_allowed(&self->phyReset,bank,offset,value))return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    *reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset)=value;
    __asm__ volatile("dsb sy" ::: "memory");
    if(!self->guard() || phyResetSource(context,&self->phyReset))return -1;
    if(mdioAccessStamp(before,deadline,&after))return -5;*completed=after;return 0;
}
int BCM2712PCIePHYTransport::phyResetWait(void *context,uint64_t previous,uint64_t target,
    uint64_t deadline,uint64_t *completed)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !completed || self->phyReset.pending!=4 || self->phyReset.step!=4 ||
        previous!=self->phyReset.last_us || deadline!=self->phyReset.deadline_us ||
        previous>UINT64_MAX-5000 || target!=previous+5000 || target>=deadline || deadline-target<1000 ||
        phyResetSource(context,&self->phyReset))return -1;
    uint64_t last=previous;
    for(unsigned n=0;n<5;n++){
        if(phyResetSource(context,&self->phyReset) || !self->guard())return -1;
        uint64_t now;if(mdioAccessStamp(last,deadline,&now))return -5;
        if(phyResetSource(context,&self->phyReset))return -1;
        if(now<target)IODelay(static_cast<uint32_t>(target-now>1000?1000:target-now));
        if(!self->guard() || phyResetSource(context,&self->phyReset))return -1;
        uint64_t after;if(mdioAccessStamp(now,deadline,&after) || after<=last || after>=target+1000)return -5;
        if(after>=target){*completed=after;return 0;}last=after;
    }
    return -5;
}
int BCM2712PCIePHYTransport::phyResetManage(void *context,uint64_t previous,uint64_t deadline,
    struct rpi5_gem_mdio_observation *out,uint64_t *completed)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !out || !completed || self->phyReset.pending!=5 || self->phyReset.step!=6 ||
        previous!=self->phyReset.last_us || deadline!=self->phyReset.deadline_us ||
        phyResetSource(context,&self->phyReset))return -1;
    uint64_t before;if(mdioAccessStamp(previous,deadline,&before) || deadline-before<20000)return -5;
    if(phyResetSource(context,&self->phyReset))return -1;
    const struct rpi5_gem_mdio_io io={self,mdioSource,mdioRead,mdioWrite,mdioTime};
    int rc=rpi5_gem_mdio_run(&self->mdioSession,&self->capabilitySession,&self->binding,&io,&self->mdioObserved);
    if(rc)return rc;
    if(phyResetSource(context,&self->phyReset))return -1;
    uint64_t done;if(mdioAccessStamp(self->mdioSession.last_us,deadline,&done))return -5;
    *out=self->mdioObserved;*completed=done;return 0;
}
'''


def emit(folder):
    folder.mkdir(exist_ok=False)
    for path in FROZEN.iterdir():
        if path.is_file():(folder/path.name).write_bytes(path.read_bytes())
    for name,fn in (('BCM2712PCIePHYTransport.h',header),('BCM2712RP1ConfigTransport.inc',parent_transport),
        ('BCM2712RP1GEMIdentifyTransport.inc',gem_transport),('rp1_phy_gpio_observe.h',gpio_header),
        ('rp1_phy_gpio_observe.c',gpio_core)):
        path=folder/name;path.write_text(fn(path.read_text()))
    for suffix,fn in (('h',timed.header),('c',timed.core)):
        name='rp1_gem_mdio.'+suffix;(folder/name).write_text(fn((timed.FROZEN/name).read_text()))
    for suffix in ('h','c'):
        name='rp1_phy_reset_cycle.'+suffix;text=(ROOT/'loader/rpi5'/name).read_text()
        (folder/name).write_text(reset_core(text) if suffix=='c' else text)
    return folder/'BCM2712PCIePHYTransport.cpp'
