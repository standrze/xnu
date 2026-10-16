# SPDX-License-Identifier: BSD-2-Clause
"""Distinct live-owned C22 management inside the accepted GEM clock bracket."""
from tools.rpi5 import rp1_gem_capabilities_profile as prior
ROOT,util=prior.ROOT,prior.util
FROZEN=ROOT/'build/rpi5/pcie-gem-capabilities-kernel-20261013-v1/overlay'
PROFILE='rp1-held-device-gem-c22-mdio-v1'

def header(text):
    text=util.once(text,'#include "rp1_gem_capabilities.h"','#include "rp1_gem_capabilities.h"\n#include "rp1_gem_mdio.h"')
    text=util.once(text,'    struct rpi5_gem_cap_observation capabilities;',
        '    struct rpi5_gem_cap_observation capabilities;\n    struct rpi5_gem_mdio_observation phy;')
    return util.once(text,'    struct rpi5_gem_cap_observation capabilityObserved={};',
        '''    struct rpi5_gem_cap_observation capabilityObserved={};
    struct rpi5_gem_mdio_session mdioSession={};
    struct rpi5_gem_mdio_observation mdioObserved={};
    const void *mdioFDTBytes=nullptr;
    size_t mdioFDTLength=0;
    static int mdioSource(void *,const struct rpi5_gem_mdio_session *,
        const struct rpi5_gem_cap_session *,const struct rpi5_pcie_fdt *);
    static int mdioRead(void *,uint32_t,uint32_t *);
    static int mdioWrite(void *,uint32_t,uint32_t);
    static int mdioTime(void *,uint64_t *);''')

def parent_transport(text):
    return util.once(text,'    result.capabilities=capabilityObserved;',
        '    result.capabilities=capabilityObserved;\n    result.phy=mdioObserved;')

def gem_transport(text):
    return util.once(text,'    return rpi5_gem_cap_run(&self->capabilitySession,g,&io,&self->capabilityObserved);',r'''
    int rc=rpi5_gem_cap_run(&self->capabilitySession,g,&io,&self->capabilityObserved);
    if(rc)return rc;
    if(!self->firmwareFDT)return -3;
    self->mdioFDTBytes=self->firmwareFDT->getBytesNoCopy();
    self->mdioFDTLength=self->firmwareFDT->getLength();
    if(!self->mdioFDTBytes || !self->mdioFDTLength || self->mdioFDTLength>1048576)return -3;
    struct rpi5_pcie_fdt fresh={};
    if(rpi5_fdt_pcie_rp1(self->mdioFDTBytes,self->mdioFDTLength,&fresh) ||
        !rpi5_gem_mdio_binding_equal(&fresh,&self->binding))return -3;
    const struct rpi5_gem_mdio_io management={self,mdioSource,mdioRead,mdioWrite,mdioTime};
    return rpi5_gem_mdio_run(&self->mdioSession,&self->capabilitySession,&self->binding,
        &management,&self->mdioObserved);''')+ADAPTER

ADAPTER=r'''
int BCM2712PCIePHYTransport::mdioSource(void *context,const struct rpi5_gem_mdio_session *s,
    const struct rpi5_gem_cap_session *c,const struct rpi5_pcie_fdt *b)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || s!=&self->mdioSession || c!=&self->capabilitySession || b!=&self->binding ||
        !self->firmwareFDT || !self->mdioFDTBytes || !self->mdioFDTLength ||
        self->firmwareFDT->getBytesNoCopy()!=self->mdioFDTBytes ||
        self->firmwareFDT->getLength()!=self->mdioFDTLength ||
        c->state!=RPI5_GEM_CAP_COMPLETE || c->busy || c->pending || c->reads!=16 ||
        capabilitySource(context,c,&self->gemSession,&self->decodeCycle))return -1;
    return 0;
}
int BCM2712PCIePHYTransport::mdioRead(void *context,uint32_t offset,uint32_t *out)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !out || mdioSource(context,&self->mdioSession,&self->capabilitySession,&self->binding) ||
        !rpi5_gem_mdio_read_allowed(&self->mdioSession,offset) || !self->guard())return -1;
    IOMemoryMap *map=self->deviceMaps[0];
    if(!map || (offset&3) || map->getLength()<4 || offset>map->getLength()-4)return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);
    __asm__ volatile("dsb sy" ::: "memory");
    if(!self->guard() || mdioSource(context,&self->mdioSession,&self->capabilitySession,&self->binding))return -1;
    *out=value;return 0;
}
int BCM2712PCIePHYTransport::mdioWrite(void *context,uint32_t offset,uint32_t value)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || mdioSource(context,&self->mdioSession,&self->capabilitySession,&self->binding) ||
        !rpi5_gem_mdio_write_allowed(&self->mdioSession,offset,value) || !self->guard())return -1;
    IOMemoryMap *map=self->deviceMaps[0];
    if(!map || (offset&3) || map->getLength()<4 || offset>map->getLength()-4)return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    *reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset)=value;
    __asm__ volatile("dsb sy" ::: "memory");
    return self->guard() && !mdioSource(context,&self->mdioSession,&self->capabilitySession,&self->binding)?0:-1;
}
int BCM2712PCIePHYTransport::mdioTime(void *context,uint64_t *out)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !out || mdioSource(context,&self->mdioSession,&self->capabilitySession,&self->binding) ||
        !rpi5_gem_mdio_clock_allowed(&self->mdioSession))return -1;
    uint64_t value;int rc=nowUS(context,&value);
    if(rc || mdioSource(context,&self->mdioSession,&self->capabilitySession,&self->binding))return -1;
    *out=value;return 0;
}
'''

def emit(folder):
    folder.mkdir(exist_ok=False)
    for path in FROZEN.iterdir():
        if path.is_file():(folder/path.name).write_bytes(path.read_bytes())
    for name,transform in (('BCM2712PCIePHYTransport.h',header),
        ('BCM2712RP1GEMIdentifyTransport.inc',gem_transport),('BCM2712RP1ConfigTransport.inc',parent_transport)):
        path=folder/name;path.write_text(transform(path.read_text()))
    for suffix in ('c','h'):
        path=ROOT/'loader/rpi5'/('rp1_gem_mdio.'+suffix);(folder/path.name).write_bytes(path.read_bytes())
    return (folder/'BCM2712PCIePHYTransport.cpp',folder/'rp1_gem_mdio.c')
