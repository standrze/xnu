# SPDX-License-Identifier: BSD-2-Clause
"""Separate MEM-only Device-map cycle; no RP1 register dereference or DMA."""
from tools.rpi5 import rp1_bars_root_profile as util
ROOT=util.ROOT
FROZEN=ROOT/'build/rpi5/pcie-bars-assignment-kernel-20261013-v2/overlay'
PROFILE='rp1-mem-only-device-map-revoke-v1'
# Retained predecessor literal required by the immutable common linker audit.
FIELDS='CALL=%u RC=%d STATE=%u SLOT=%u TXNS=%u WRITES=%u ASSIGNED=%02x RESTORED=%02x'


def header(text):
    text=util.once(text,'#include "rp1_bars_assign.h"','#include "rp1_bars_assign.h"\n#include "rp1_decode_cycle.h"')
    text=util.once(text,'    struct rpi5_rp1_mapping_candidate mapping;',
        '    struct rpi5_rp1_mapping_candidate mapping;\n    struct rpi5_rp1_decode_observation decode;')
    text=util.once(text,'    struct rpi5_rp1_assignment assignment={};',
        '''    struct rpi5_rp1_assignment assignment={};
    struct rpi5_rp1_decode_cycle decodeCycle={};
    IOMemoryMap *deviceMaps[2]={};
    IOMemoryDescriptor *deviceBacking[2]={}; /* Borrowed only while map retains it. */
    bool decodeActive=false;unsigned diagDecodeCall=0;int diagDecodeRC=0;
    static int decodeSource(void *,const struct rpi5_rp1_decode_cycle *,const struct rpi5_rp1_assignment *);
    static int decodeAuthorize(void *,const struct rpi5_pcie_config_request *);
    static int decodeWrite(void *,uint32_t,uint32_t,uint32_t);
    static int decodeMap(void *,unsigned,struct rpi5_range);
    static int decodeUnmap(void *,unsigned,struct rpi5_range);
    bool decodeMapValid(unsigned,struct rpi5_range) const;''')
    return util.once(text,'    unsigned traceAssignCall()',
        '\n'.join('    '+kind+' traceDecode'+name+'() const { return '+value+'; }' for kind,name,value in (
            ('unsigned','Call','diagDecodeCall'),('int','RC','diagDecodeRC'),('unsigned','State','decodeCycle.state'),
            ('unsigned','Transactions','decodeCycle.transactions'),('unsigned','Writes','decodeCycle.writes_started'),
            ('unsigned','Mapped','decodeCycle.mapped'),('unsigned','Unmapped','decodeCycle.unmapped')))+'\n'
        '    unsigned traceAssignCall()')


def transport(text):
    text=util.once(text,'assignmentAuthorize,rp1Read,assignmentWrite,order','decodeAuthorize,rp1Read,decodeWrite,order')
    text=util.once(text,'    const struct rpi5_rp1_assignment_source source={this,assignmentSource};',
        '    const struct rpi5_rp1_assignment_source source={this,assignmentSource};\n'
        '    const struct rpi5_rp1_decode_io decodeIO={this,decodeSource,decodeMap,decodeUnmap};')
    return util.once(text,'''    /* This geometry is not mapped or dereferenced. A future Device-map owner
     * must revoke its mappings before the following restoration operation. */''',
        '''    decodeActive=true;diagDecodeCall=1;
    diagDecodeRC=rpi5_rp1_decode_run(&decodeCycle,&assignment,&decodeIO,&result.decode);
    if(diagDecodeRC)goto rp1_failed;
    diagDecodeCall=2;
    if(deviceMaps[0] || deviceMaps[1] || deviceBacking[0] || deviceBacking[1] || !guard())goto rp1_failed;
    decodeActive=false;diagDecodeCall=3;''')


def diagnostic_calls():
    return '''    kprintf("RPI5XNU:PCIEID:DECODE CALL=%u RC=%d STATE=%u TXNS=%u WRITES=%u MAPPED=%02x UNMAPPED=%02x\\n",
        transport?transport->traceDecodeCall():0,transport?transport->traceDecodeRC():0,
        transport?transport->traceDecodeState():0,transport?transport->traceDecodeTransactions():0,
        transport?transport->traceDecodeWrites():0,transport?transport->traceDecodeMapped():0,
        transport?transport->traceDecodeUnmapped():0);
    kprintf("RPI5XNU:PCIEID:DECODE_COMMAND BEFORE=%04x ENABLED=%04x AFTER=%04x\\n",
        observed.decode.command_before,observed.decode.command_enabled,observed.decode.command_after);
'''


ADAPTER=r'''
int BCM2712PCIePHYTransport::decodeSource(void *context,const struct rpi5_rp1_decode_cycle *s,
    const struct rpi5_rp1_assignment *a)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !self->decodeActive || s!=&self->decodeCycle || a!=&self->assignment)return -1;
    return assignmentSource(context,&self->rp1Config,&self->binding,&self->barsProbe,&self->assignmentSizes);
}
int BCM2712PCIePHYTransport::decodeAuthorize(void *context,const struct rpi5_pcie_config_request *r)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self)return -1;
    if(!self->decodeActive)return assignmentAuthorize(context,r);
    if(!self->rp1Locked || self->rp1Config.state!=RPI5_PCIE_CONFIG_BUSY ||
        !rpi5_rp1_decode_write_allowed(&self->decodeCycle,r))return -1;
    return self->guard()?0:-1;
}
int BCM2712PCIePHYTransport::decodeWrite(void *context,uint32_t offset,uint32_t width,uint32_t value)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self)return -1;
    if(!self->decodeActive || offset==0x9000)return assignmentWrite(context,offset,width,value);
    if(!self->onOwnerThread())return -1;
    self->diagIOBank=BCM2712_PHY_BRIDGE;self->diagIOOffset=offset;
    self->diagIODirection=1;self->diagIOStage=1;self->diagIOValue=value;
    if(offset!=0x8004 || width!=2 || (value&~0xfffaU))return -1;
    const struct rpi5_pcie_config_request request={1,0,0,4,2,1,value};
    if(decodeAuthorize(context,&request))return -1;
    self->diagIOStage=2;
    __asm__ volatile("dmb osh" ::: "memory");
    *reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=(uint16_t)value;
    __asm__ volatile("dsb sy" ::: "memory");
    self->diagIOStage=3;
    if(!self->guard())return -1;
    self->diagIOStage=4;return 0;
}
bool BCM2712PCIePHYTransport::decodeMapValid(unsigned index,struct rpi5_range range) const
{
    if(index>1 || range.start>=range.end || ((range.start|range.end)&0x3fff))return false;
    IOMemoryMap *map=deviceMaps[index];IOByteCount length=0;
    if(!map || !map->getVirtualAddress() || (map->getVirtualAddress()&0x3fff) ||
        map->getLength()!=range.end-range.start ||
        (map->getMapOptions()&kIOMapCacheMask)!=kIOMapInhibitCache ||
        (map->getMapOptions()&(kIOMapStatic|kIOMapReference|kIOMapUnique)) ||
        !deviceBacking[index] || map->getMemoryDescriptor()!=deviceBacking[index] ||
        map->getPhysicalSegment(0,&length,kIOMemoryMapperNone)!=range.start ||
        length!=range.end-range.start)return false;
    return range.end-range.start<=UINT64_MAX-map->getVirtualAddress();
}
int BCM2712PCIePHYTransport::decodeMap(void *context,unsigned index,struct rpi5_range range)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || index>1 || self->deviceMaps[index] || self->deviceBacking[index] ||
        !rpi5_rp1_decode_mapping_allowed(&self->decodeCycle,index,range,0) || !self->guard())return -1;
    if(rpi5_physical_memory_type(range.start,range.end)!=2)return -1;
    IOMemoryDescriptor *memory=IOMemoryDescriptor::withAddressRange(range.start,range.end-range.start,
        kIODirectionNone|kIOMemoryMapperNone|kIOMemoryHostOnly|(kIOInhibitCache<<kIOMemoryBufferCacheShift),nullptr);
    if(!memory)return -1;
    /* A newly created, unshared descriptor has no compatible prior mapping.
     * Avoid kIOMapUnique: Apple recreates physical backing without HostOnly.
     * Require the actual map to retain this exact original descriptor. */
    self->deviceMaps[index]=memory->map(kIOMapAnywhere|kIOMapInhibitCache);
    if(self->deviceMaps[index])self->deviceBacking[index]=memory;
    memory->release();
    if(!self->guard() || !self->decodeMapValid(index,range))return -1;
    if(index) {
        auto *a=self->deviceMaps[0];auto *b=self->deviceMaps[1];
        if(!a || (a->getVirtualAddress()<b->getVirtualAddress()+b->getLength() &&
            b->getVirtualAddress()<a->getVirtualAddress()+a->getLength()))return -1;
    }
    return 0;
}
int BCM2712PCIePHYTransport::decodeUnmap(void *context,unsigned index,struct rpi5_range range)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !rpi5_rp1_decode_mapping_allowed(&self->decodeCycle,index,range,1) ||
        !self->decodeMapValid(index,range) || !self->guard())return -1;
    IOMemoryMap *map=self->deviceMaps[index];
    if(map->unmap()!=kIOReturnSuccess || map->getVirtualAddress())return -1;
    map->release();self->deviceMaps[index]=nullptr;self->deviceBacking[index]=nullptr;
    return self->guard()?0:-1;
}
'''


def emit(folder):
    folder.mkdir(exist_ok=False)
    for path in FROZEN.iterdir():
        if path.is_file():(folder/path.name).write_bytes(path.read_bytes())
    for name,adapt in (('BCM2712PCIePHYTransport.h',header),('BCM2712RP1ConfigTransport.inc',transport)):
        path=folder/name;path.write_text(adapt(path.read_text()))
    path=folder/'BCM2712PCIeIDTrialProgress.inc'
    path.write_text(util.once(path.read_text(),'    kprintf("RPI5XNU:PCIEID:END ',diagnostic_calls()+'    kprintf("RPI5XNU:PCIEID:END '))
    (folder/'BCM2712RP1DecodeTransport.inc').write_text(ADAPTER)
    path=folder/'BCM2712PCIePHYTransport.cpp';path.write_text(path.read_text()+'\n#include "BCM2712RP1DecodeTransport.inc"\n')
    for suffix in ('c','h'):
        source=ROOT/'loader/rpi5'/('rp1_decode_cycle.'+suffix);(folder/source.name).write_bytes(source.read_bytes())
    return path,folder/'rp1_decode_cycle.c'
