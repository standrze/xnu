# SPDX-License-Identifier: BSD-2-Clause
"""Distinct design-word reader inside the existing same-boot clock bracket."""
from tools.rpi5 import rp1_gem_selected_clock_profile as prior
ROOT,util=prior.ROOT,prior.util
FROZEN=ROOT/'build/rpi5/pcie-gem-selected-kernel-20261013-v1/overlay'
PROFILE='rp1-held-device-gem-design-capabilities-v1'


def gem_header(text):
    return util.once(text,'    int (*read)(void *, unsigned, uint32_t, uint32_t *);',
        '    int (*read)(void *, unsigned, uint32_t, uint32_t *);\n'
        '    int (*capabilities)(void *,const struct rpi5_gem_identify *);')


def gem_core(text):
    for old,new in (
        ('s->io.current && s->io.read &&','s->io.current && s->io.read && s->io.capabilities &&'),
        ('!io->current || !io->read)return -1;','!io->current || !io->read || !io->capabilities)return -1;'),
        ('s->io.current || s->io.read ||','s->io.current || s->io.read || s->io.capabilities ||'),
        ('    s->stage=RPI5_GEM_CLOCK_AFTER;',
         '    if((rc=s->io.capabilities(s->io.context,s)))return fail(s,rc);\n'
         '    if(!retained(s))return fail(s,-3);\n'
         '    s->stage=RPI5_GEM_CLOCK_AFTER;')):
        text=util.once(text,old,new)
    return text


def transport_header(text):
    text=util.once(text,'#include "rp1_gem_identify.h"',
        '#include "rp1_gem_identify.h"\n#include "rp1_gem_capabilities.h"')
    text=util.once(text,'    struct rpi5_gem_observation gem;',
        '    struct rpi5_gem_observation gem;\n    struct rpi5_gem_cap_observation capabilities;')
    return util.once(text,'    struct rpi5_gem_observation gemObserved={};',
        '''    struct rpi5_gem_observation gemObserved={};
    struct rpi5_gem_cap_session capabilitySession={};
    struct rpi5_gem_cap_observation capabilityObserved={};
    static int gemCapabilities(void *,const struct rpi5_gem_identify *);
    static int capabilitySource(void *,const struct rpi5_gem_cap_session *,
        const struct rpi5_gem_identify *,const struct rpi5_rp1_decode_cycle *);
    static int capabilityRead(void *,uint32_t,uint32_t *);''')


def gem_transport(text):
    return util.once(text,'const struct rpi5_gem_io io={self,gemSource,gemRead};',
        'const struct rpi5_gem_io io={self,gemSource,gemRead,gemCapabilities};')+ADAPTER


def parent_transport(text):
    return util.once(text,'    result.gem=gemObserved;',
        '    result.gem=gemObserved;\n    result.capabilities=capabilityObserved;')


ADAPTER=r'''
int BCM2712PCIePHYTransport::capabilitySource(void *context,const struct rpi5_gem_cap_session *s,
    const struct rpi5_gem_identify *g,const struct rpi5_rp1_decode_cycle *d)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || s!=&self->capabilitySession || g!=&self->gemSession || d!=&self->decodeCycle ||
        g->stage!=RPI5_GEM_MID_SECOND || g->reads!=17 || g->pending ||
        gemSource(context,g,d))return -1;
    return 0;
}
int BCM2712PCIePHYTransport::capabilityRead(void *context,uint32_t offset,uint32_t *out)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !out || capabilitySource(context,&self->capabilitySession,&self->gemSession,&self->decodeCycle) ||
        !rpi5_gem_cap_read_allowed(&self->capabilitySession,offset) || !self->guard())return -1;
    IOMemoryMap *map=self->deviceMaps[0];
    if(!map || (offset&3) || map->getLength()<4 || offset>map->getLength()-4)return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);
    __asm__ volatile("dsb sy" ::: "memory");
    if(!self->guard() || capabilitySource(context,&self->capabilitySession,&self->gemSession,&self->decodeCycle))return -1;
    *out=value;return 0;
}
int BCM2712PCIePHYTransport::gemCapabilities(void *context,const struct rpi5_gem_identify *g)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || capabilitySource(context,&self->capabilitySession,g,&self->decodeCycle))return -3;
    const struct rpi5_gem_cap_io io={self,capabilitySource,capabilityRead};
    return rpi5_gem_cap_run(&self->capabilitySession,g,&io,&self->capabilityObserved);
}
'''


def emit(folder):
    folder.mkdir(exist_ok=False)
    for path in FROZEN.iterdir():
        if path.is_file():(folder/path.name).write_bytes(path.read_bytes())
    transforms={'rp1_gem_identify.h':gem_header,'rp1_gem_identify.c':gem_core,
        'BCM2712PCIePHYTransport.h':transport_header,
        'BCM2712RP1GEMIdentifyTransport.inc':gem_transport,
        'BCM2712RP1ConfigTransport.inc':parent_transport}
    for name,transform in transforms.items():
        path=folder/name;path.write_text(transform(path.read_text()))
    for suffix in ('c','h'):
        path=ROOT/'loader/rpi5'/('rp1_gem_capabilities.'+suffix)
        (folder/path.name).write_bytes(path.read_bytes())
    return (folder/'BCM2712PCIePHYTransport.cpp',folder/'rp1_gem_identify.c',folder/'rp1_gem_capabilities.c')
