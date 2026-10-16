# SPDX-License-Identifier: BSD-2-Clause
"""Distinct timed MMIO ABI: preserve both fresh MMIO guards, fuse time samples.

The original20ms/32poll/five-read-command limits and all access predicates stay
unchanged. No owner count is reset, cached or increased. Initial/final clocks
still use the original guarded nowUS; each real access independently samples
the same Apple monotonic clock inside its existing pre/post owner envelope.
The pre-access sample refuses an expired write before its side effect; a late
completion quarantines and does not pretend a performed write was undone.
This is an offline successor building block, not a reset/PHY admission claim.
"""
from tools.rpi5 import rp1_gem_mdio_profile as old
ROOT,util=old.ROOT,old.util
FROZEN=ROOT/'build/rpi5/pcie-gem-mdio-kernel-20261014-v2/overlay'
PROFILE='rp1-gem-mdio-fused-timed-access-v1'


def header(text):
    text=util.once(text,'    int (*read)(void *,uint32_t,uint32_t *);',
        '''    /* Access callbacks must reject time <previous or >=deadline BEFORE
     * MMIO, and publish a monotonic completion sampled AFTER the post-owner
     * guard. Every actual MMIO keeps fresh pre/post firmware/IRQ/PM guards.
     * Error -5 identifies a deadline/clock failure; a failed write may already
     * have happened. No cleanup/retry is implied by absent completion. */
    int (*read)(void *,uint32_t,uint64_t,uint64_t,uint32_t *,uint64_t *);''')
    text=util.once(text,'    int (*write)(void *,uint32_t,uint32_t);',
        '    int (*write)(void *,uint32_t,uint32_t,uint64_t,uint64_t,uint64_t *);')
    return text.replace('time sampled before every MMIO and after final',
        'time sampled before and after every MMIO and after final')


def core(text):
    text=util.once(text,'    if(tick(r))return s->error;if(s->reads>=46)return fail(r,-4);',
        '    if(s->reads>=46)return fail(r,-4);')
    text=util.once(text,'    int rc=r->io.read(r->io.context,offset,&value);',
        '    uint64_t completed=0;int rc=r->io.read(r->io.context,offset,s->last_us,s->deadline_us,&value,&completed);')
    begin=text.index('static int read_reg(');end=text.index('static int write_reg(',begin)
    part=util.once(text[begin:end],'    if(rc)return fail(r,-4);s->pending=0;*out=value;return 0;',
        '''    if(rc)return fail(r,rc==-5?-5:-4);
    if(completed<s->last_us||completed>=s->deadline_us)return fail(r,-5);
    s->last_us=completed;s->pending=0;*out=value;return 0;''')
    text=text[:begin]+part+text[end:]
    text=util.once(text,'    if(tick(r))return s->error;if(s->writes>=9)return fail(r,-4);',
        '    if(s->writes>=9)return fail(r,-4);')
    text=util.once(text,'    int rc=r->io.write(r->io.context,offset,value);',
        '    uint64_t completed=0;int rc=r->io.write(r->io.context,offset,value,s->last_us,s->deadline_us,&completed);')
    text=util.once(text,'    if(rc)return fail(r,-4);s->pending=0;return 0;',
        '''    if(rc)return fail(r,rc==-5?-5:-4);
    if(completed<s->last_us||completed>=s->deadline_us)return fail(r,-5);
    s->last_us=completed;s->pending=0;return 0;''')
    return text


def transport_header(text):
    text=util.once(text,'    static int mdioRead(void *,uint32_t,uint32_t *);',
        '    static int mdioRead(void *,uint32_t,uint64_t,uint64_t,uint32_t *,uint64_t *);')
    return util.once(text,'    static int mdioWrite(void *,uint32_t,uint32_t);',
        '    static int mdioWrite(void *,uint32_t,uint32_t,uint64_t,uint64_t,uint64_t *);')


def transport(text):
    text=util.once(text,
        '    if(!self || s!=&self->mdioSession || c!=&self->capabilitySession || b!=&self->binding ||',
        '''    if(!self || s!=&self->mdioSession || s->self!=s ||
        s->state!=RPI5_GEM_MDIO_ACTIVE || s->busy!=1 || s->io.context!=self ||
        c!=&self->capabilitySession || b!=&self->binding ||''')
    start=text.index('int BCM2712PCIePHYTransport::mdioRead(')
    end=text.index('int BCM2712PCIePHYTransport::mdioTime(',start)
    return text[:start]+TIMED+text[end:]


TIMED=r'''
/* Same clock source/conversion as nowUS, inside each existing MMIO guard
 * envelope. This helper has no authority and performs no device access. */
static int mdioAccessStamp(uint64_t previous,uint64_t deadline,uint64_t *out)
{
    uint64_t absolute,ns;
    clock_get_uptime(&absolute);
    absolutetime_to_nanoseconds(absolute,&ns);
    uint64_t now=ns/1000;
    if(now<previous || now>=deadline)return -5;
    *out=now;return 0;
}
int BCM2712PCIePHYTransport::mdioRead(void *context,uint32_t offset,
    uint64_t previous,uint64_t deadline,uint32_t *out,uint64_t *completed)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !out || !completed || previous!=self->mdioSession.last_us ||
        deadline!=self->mdioSession.deadline_us ||
        mdioSource(context,&self->mdioSession,&self->capabilitySession,&self->binding) ||
        !rpi5_gem_mdio_read_allowed(&self->mdioSession,offset) || !self->guard())return -1;
    IOMemoryMap *map=self->deviceMaps[0];
    if(!map || (offset&3) || map->getLength()<4 || offset>map->getLength()-4)return -1;
    uint64_t before,after;
    if(mdioAccessStamp(previous,deadline,&before))return -5;
    if(mdioSource(context,&self->mdioSession,&self->capabilitySession,&self->binding))return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);
    __asm__ volatile("dsb sy" ::: "memory");
    if(!self->guard() || mdioSource(context,&self->mdioSession,&self->capabilitySession,&self->binding))return -1;
    if(mdioAccessStamp(before,deadline,&after))return -5;
    *out=value;*completed=after;return 0;
}
int BCM2712PCIePHYTransport::mdioWrite(void *context,uint32_t offset,uint32_t value,
    uint64_t previous,uint64_t deadline,uint64_t *completed)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !completed || previous!=self->mdioSession.last_us ||
        deadline!=self->mdioSession.deadline_us ||
        mdioSource(context,&self->mdioSession,&self->capabilitySession,&self->binding) ||
        !rpi5_gem_mdio_write_allowed(&self->mdioSession,offset,value) || !self->guard())return -1;
    IOMemoryMap *map=self->deviceMaps[0];
    if(!map || (offset&3) || map->getLength()<4 || offset>map->getLength()-4)return -1;
    uint64_t before,after;
    if(mdioAccessStamp(previous,deadline,&before))return -5;
    if(mdioSource(context,&self->mdioSession,&self->capabilitySession,&self->binding))return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    *reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset)=value;
    __asm__ volatile("dsb sy" ::: "memory");
    if(!self->guard() || mdioSource(context,&self->mdioSession,&self->capabilitySession,&self->binding))return -1;
    if(mdioAccessStamp(before,deadline,&after))return -5;
    *completed=after;return 0;
}
'''


def emit(folder):
    folder.mkdir(exist_ok=False)
    for path in FROZEN.iterdir():
        if path.is_file():(folder/path.name).write_bytes(path.read_bytes())
    for name,fn in (('rp1_gem_mdio.h',header),('rp1_gem_mdio.c',core),
        ('BCM2712PCIePHYTransport.h',transport_header),('BCM2712RP1GEMIdentifyTransport.inc',transport)):
        path=folder/name;path.write_text(fn(path.read_text()))
    return folder/'BCM2712PCIePHYTransport.cpp',folder/'rp1_gem_mdio.c'
