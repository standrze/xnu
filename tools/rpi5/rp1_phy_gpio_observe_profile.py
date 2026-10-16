# SPDX-License-Identifier: BSD-2-Clause
"""Distinct GPIO32 read-only observer replacing, not extending, MDIO."""
from tools.rpi5 import rp1_gem_capabilities_profile as prior
ROOT,util=prior.ROOT,prior.util
FROZEN=ROOT/'build/rpi5/pcie-gem-capabilities-kernel-20261013-v1/overlay'
PROFILE='rp1-phy-gpio32-read-only-observer-v1'

def header(text):
    text=util.once(text,'#include "rp1_gem_capabilities.h"','#include "rp1_gem_capabilities.h"\n#include "rp1_phy_gpio_observe.h"')
    text=util.once(text,'    struct rpi5_gem_cap_observation capabilities;',
        '    struct rpi5_gem_cap_observation capabilities;\n    struct rpi5_phy_gpio_observation phy_gpio;')
    return util.once(text,'    struct rpi5_gem_cap_observation capabilityObserved={};',r'''
    struct rpi5_gem_cap_observation capabilityObserved={};
    struct rpi5_phy_gpio_session phyGPIO={};
    struct rpi5_phy_gpio_binding phyGPIOBinding={};
    struct rpi5_phy_gpio_observation phyGPIOObserved={};
    const void *phyGPIOFDT=nullptr;size_t phyGPIOFDTLength=0;
    IOMemoryMap *phyGPIOMaps[3]={};IOMemoryDescriptor *phyGPIOBacking[3]={};
    static int phyGPIOSource(void *,const struct rpi5_phy_gpio_session *);
    static int phyGPIOMap(void *,unsigned,struct rpi5_range);
    static int phyGPIOUnmap(void *,unsigned,struct rpi5_range);
    static int phyGPIORead(void *,unsigned,uint32_t,uint32_t *);
    bool phyGPIOMapValid(unsigned,struct rpi5_range)const;''')

def parent_transport(text):
    return util.once(text,'    result.capabilities=capabilityObserved;',
        '    result.capabilities=capabilityObserved;\n    result.phy_gpio=phyGPIOObserved;')

def gem_transport(text):
    return util.once(text,'    return rpi5_gem_cap_run(&self->capabilitySession,g,&io,&self->capabilityObserved);',r'''
    int rc=rpi5_gem_cap_run(&self->capabilitySession,g,&io,&self->capabilityObserved);
    if(rc)return rc;
    if(!self->firmwareFDT)return -3;
    self->phyGPIOFDT=self->firmwareFDT->getBytesNoCopy();
    self->phyGPIOFDTLength=self->firmwareFDT->getLength();
    if(!self->phyGPIOFDT || !self->phyGPIOFDTLength || self->phyGPIOFDTLength>1048576)return -3;
    struct rpi5_pcie_fdt fresh={};
    if(rpi5_fdt_pcie_rp1(self->phyGPIOFDT,self->phyGPIOFDTLength,&fresh) ||
        !rpi5_phy_gpio_pcie_equal(&fresh,&self->binding) ||
        rpi5_phy_gpio_fdt(self->phyGPIOFDT,self->phyGPIOFDTLength,&self->phyGPIOBinding))return -3;
    const struct rpi5_phy_gpio_io observation={self,phyGPIOSource,phyGPIOMap,phyGPIOUnmap,phyGPIORead};
    return rpi5_phy_gpio_run(&self->phyGPIO,&self->capabilitySession,&self->phyGPIOBinding,
        &observation,&self->phyGPIOObserved);''')+ADAPTER

ADAPTER=r'''
int BCM2712PCIePHYTransport::phyGPIOSource(void *context,const struct rpi5_phy_gpio_session *s)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || s!=&self->phyGPIO || s->self!=s || s->state!=RPI5_PHY_GPIO_ACTIVE || s->busy!=1 ||
        s->cap!=&self->capabilitySession || s->io.context!=self ||
        !self->firmwareFDT || !self->phyGPIOFDT || !self->phyGPIOFDTLength ||
        self->firmwareFDT->getBytesNoCopy()!=self->phyGPIOFDT ||
        self->firmwareFDT->getLength()!=self->phyGPIOFDTLength ||
        self->capabilitySession.state!=RPI5_GEM_CAP_COMPLETE || self->capabilitySession.busy ||
        self->capabilitySession.pending || self->capabilitySession.reads!=16 ||
        capabilitySource(context,&self->capabilitySession,&self->gemSession,&self->decodeCycle))return -1;
    return 0;
}
bool BCM2712PCIePHYTransport::phyGPIOMapValid(unsigned i,struct rpi5_range r)const
{
    if(i>2 || r.start>=r.end || ((r.start|r.end)&0x3fff) || r.end-r.start!=0x4000)return false;
    IOMemoryMap *map=phyGPIOMaps[i];IOByteCount length=0;
    if(!map || !map->getVirtualAddress() || (map->getVirtualAddress()&0x3fff) || map->getLength()!=0x4000 ||
        (map->getMapOptions()&kIOMapCacheMask)!=kIOMapInhibitCache ||
        (map->getMapOptions()&(kIOMapStatic|kIOMapReference|kIOMapUnique)) ||
        !phyGPIOBacking[i] || map->getMemoryDescriptor()!=phyGPIOBacking[i] ||
        map->getPhysicalSegment(0,&length,kIOMemoryMapperNone)!=r.start || length!=0x4000 ||
        map->getVirtualAddress()>UINT64_MAX-0x4000)return false;
    return true;
}
int BCM2712PCIePHYTransport::phyGPIOMap(void *context,unsigned i,struct rpi5_range r)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || i>2 || self->phyGPIOMaps[i] || self->phyGPIOBacking[i] ||
        phyGPIOSource(context,&self->phyGPIO) || !rpi5_phy_gpio_map_allowed(&self->phyGPIO,i,r,0) ||
        !self->guard() || rpi5_physical_memory_type(r.start,r.end)!=2)return -1;
    IOMemoryDescriptor *memory=IOMemoryDescriptor::withAddressRange(r.start,r.end-r.start,
        kIODirectionNone|kIOMemoryMapperNone|kIOMemoryHostOnly|(kIOInhibitCache<<kIOMemoryBufferCacheShift),nullptr);
    if(!memory)return -1;
    self->phyGPIOMaps[i]=memory->map(kIOMapAnywhere|kIOMapInhibitCache);
    if(self->phyGPIOMaps[i])self->phyGPIOBacking[i]=memory;
    memory->release();
    if(!self->guard() || phyGPIOSource(context,&self->phyGPIO) || !self->phyGPIOMapValid(i,r))return -1;
    auto *map=self->phyGPIOMaps[i];
    for(unsigned j=0;j<5;j++){
        IOMemoryMap *other=j<2?self->deviceMaps[j]:self->phyGPIOMaps[j-2];
        if(!other || other==map)continue;
        if(other->getVirtualAddress()>UINT64_MAX-other->getLength() ||
            (map->getVirtualAddress()<other->getVirtualAddress()+other->getLength() &&
             other->getVirtualAddress()<map->getVirtualAddress()+map->getLength()))return -1;
    }
    return 0;
}
int BCM2712PCIePHYTransport::phyGPIOUnmap(void *context,unsigned i,struct rpi5_range r)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || i>2 || phyGPIOSource(context,&self->phyGPIO) ||
        !rpi5_phy_gpio_map_allowed(&self->phyGPIO,i,r,1) || !self->phyGPIOMapValid(i,r) || !self->guard())return -1;
    auto *map=self->phyGPIOMaps[i];
    if(map->unmap()!=kIOReturnSuccess || map->getVirtualAddress())return -1;
    map->release();self->phyGPIOMaps[i]=nullptr;self->phyGPIOBacking[i]=nullptr;
    return self->guard() && !phyGPIOSource(context,&self->phyGPIO)?0:-1;
}
int BCM2712PCIePHYTransport::phyGPIORead(void *context,unsigned i,uint32_t offset,uint32_t *out)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !out || i>2 || phyGPIOSource(context,&self->phyGPIO) ||
        !rpi5_phy_gpio_read_allowed(&self->phyGPIO,i,offset) ||
        !self->phyGPIOMapValid(i,self->phyGPIO.page[i]) || !self->guard())return -1;
    auto *map=self->phyGPIOMaps[i];
    if((offset&3) || offset>map->getLength()-4)return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);
    __asm__ volatile("dsb sy" ::: "memory");
    if(!self->guard() || phyGPIOSource(context,&self->phyGPIO) || !self->phyGPIOMapValid(i,self->phyGPIO.page[i]))return -1;
    *out=value;return 0;
}
'''

def emit(folder):
    folder.mkdir(exist_ok=False)
    for path in FROZEN.iterdir():
        if path.is_file():(folder/path.name).write_bytes(path.read_bytes())
    for name,adapt in (('BCM2712PCIePHYTransport.h',header),
        ('BCM2712RP1GEMIdentifyTransport.inc',gem_transport),('BCM2712RP1ConfigTransport.inc',parent_transport)):
        path=folder/name;path.write_text(adapt(path.read_text()))
    for suffix in ('c','h'):
        path=ROOT/'loader/rpi5'/('rp1_phy_gpio_observe.'+suffix);(folder/path.name).write_bytes(path.read_bytes())
    return folder/'BCM2712PCIePHYTransport.cpp',folder/'rp1_phy_gpio_observe.c'
