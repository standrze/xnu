# SPDX-License-Identifier: BSD-2-Clause
"""Private decode successor: stable inherited SYS clock + two GEM MID reads."""
from tools.rpi5 import rp1_decode_profile as prior
ROOT,util=prior.ROOT,prior.util
FROZEN=ROOT/'build/rpi5/pcie-decode-cycle-kernel-20261013-v1/overlay'
PROFILE='rp1-held-device-clocks-gem-mid-readonly-v1'
FIELDS=prior.FIELDS


def decode_header(text):
    text=util.once(text,'    int (*unmap)(void *,unsigned,struct rpi5_range);',
        '    int (*unmap)(void *,unsigned,struct rpi5_range);\n'
        '    int (*identify)(void *,const struct rpi5_rp1_decode_cycle *);')
    text=text.replace('Neither callback may read/write endpoint registers or enable DMA/IRQs.',
        'Map/unmap callbacks never access endpoint registers or enable DMA/IRQs.\n'
        '     * identify performs the separate bounded read-only clock/MID stage.')
    return text.replace('IO/BME remain zero. No BAR write, NIC register read/write, clock/reset,',
        'IO/BME remain zero. Bounded clock-state/MID reads occur while both maps\n'
        ' * are held. No BAR write, NIC register write, clock/reset change,')


def decode_core(text):
    for old,new in (
        ('!s->io.map || !s->io.unmap ||','!s->io.map || !s->io.unmap || !s->io.identify ||'),
        ('!io->map || !io->unmap)return -1;','!io->map || !io->unmap || !io->identify)return -1;'),
        ('s->io.map || s->io.unmap ||','s->io.map || s->io.unmap || s->io.identify ||'),
        ('    /* No device-register dereference in this mapping-only version. */',
         '    if((rc=s->io.identify(s->io.context,s)))return fail(s,rc);\n'
         '    if(!retained(s))return fail(s,-3);')):
        text=util.once(text,old,new)
    return text


def header(text):
    text=util.once(text,'#include "rp1_decode_cycle.h"','#include "rp1_decode_cycle.h"\n#include "rp1_gem_identify.h"')
    text=util.once(text,'    struct rpi5_rp1_decode_observation decode;',
        '    struct rpi5_rp1_decode_observation decode;\n    struct rpi5_gem_observation gem;')
    text=util.once(text,'    struct rpi5_rp1_decode_cycle decodeCycle={};',
        '''    struct rpi5_rp1_decode_cycle decodeCycle={};
    struct rpi5_gem_identify gemSession={};
    struct rpi5_gem_observation gemObserved={};
    int diagGemRC=0;unsigned diagGemCall=0;
    static int gemIdentify(void *,const struct rpi5_rp1_decode_cycle *);
    static int gemSource(void *,const struct rpi5_gem_identify *,const struct rpi5_rp1_decode_cycle *);
    static int gemRead(void *,unsigned,uint32_t,uint32_t *);''')
    return util.once(text,'    unsigned traceDecodeCall()',
        '''    int traceGemRC() const { return diagGemRC; }
    unsigned traceGemCall() const { return diagGemCall; }
    const struct rpi5_gem_identify *traceGem() const { return &gemSession; }
    unsigned traceDecodeCall()''')


def transport(text):
    text=util.once(text,'{this,decodeSource,decodeMap,decodeUnmap};',
        '{this,decodeSource,decodeMap,decodeUnmap,gemIdentify};')
    return util.once(text,'    decodeActive=false;diagDecodeCall=3;',
        '    result.gem=gemObserved;\n    decodeActive=false;diagDecodeCall=3;')


ADAPTER=r'''
int BCM2712PCIePHYTransport::gemSource(void *context,const struct rpi5_gem_identify *s,
    const struct rpi5_rp1_decode_cycle *d)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || s!=&self->gemSession || d!=&self->decodeCycle ||
        d->state!=RPI5_RP1_DECODE_MAPPED || d->mapped!=3 || d->unmapped ||
        d->pending_write || d->pending_map || decodeSource(context,d,&self->assignment) ||
        !self->decodeMapValid(0,d->geometry.gem_pages) ||
        !self->decodeMapValid(1,d->geometry.clock_pages))return -1;
    return 0;
}
int BCM2712PCIePHYTransport::gemRead(void *context,unsigned index,uint32_t offset,uint32_t *out)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !out || index>1 || gemSource(context,&self->gemSession,&self->decodeCycle) ||
        !rpi5_gem_read_allowed(&self->gemSession,index,offset) || !self->guard())return -1;
    IOMemoryMap *map=self->deviceMaps[index];
    if(!map || (offset&3) || map->getLength()<4 || offset>map->getLength()-4)return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);
    __asm__ volatile("dsb sy" ::: "memory");
    if(!self->guard() || gemSource(context,&self->gemSession,&self->decodeCycle))return -1;
    *out=value;return 0;
}
int BCM2712PCIePHYTransport::gemIdentify(void *context,const struct rpi5_rp1_decode_cycle *d)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || gemSource(context,&self->gemSession,d))return -3;
    const struct rpi5_gem_io io={self,gemSource,gemRead};
    self->diagGemCall=1;
    self->diagGemRC=rpi5_gem_identify_run(&self->gemSession,d,&io,&self->gemObserved);
    if(self->diagGemRC)return self->diagGemRC;
    self->diagGemCall=2;return 0;
}
'''


def diagnostic_calls():
    lines=['    const struct rpi5_gem_identify emptyGem={};',
        '    const struct rpi5_gem_identify *gem=transport?transport->traceGem():&emptyGem;',
        '    kprintf("RPI5XNU:PCIEID:GEM CALL=%u RC=%d STAGE=%u READS=%u READY=%u INDEX=%u OFFSET=%08x\\n",',
        '        transport?transport->traceGemCall():0,transport?transport->traceGemRC():0,',
        '        gem->stage,gem->reads,gem->clocks_ready,gem->index,gem->offset);']
    for name in ('before','after'):
        for group,labels in ((0,'CTRL DIV SEL CS'),(1,'PWR INT FRAC PRIM'),
            (2,'ETH_CTRL ETH_DIV ETH_SEL TSU_CTRL'),(3,'TSU_DIV TSU_SEL SEC')):
            fmt=' '.join(v+'=%08x' for v in labels.split())
            args=','.join(f'gem->{name}[{i}]' for i in range(group*4,group*4+len(labels.split())))
            lines.append(f'    kprintf("RPI5XNU:PCIEID:CLOCK_{name.upper()}{group} {fmt}\\n",{args});')
    lines+=['    kprintf("RPI5XNU:PCIEID:GEM_MID FIRST=%08x SECOND=%08x COMMITTED=%08x HZ=%u\\n",',
        '        gem->mid[0],gem->mid[1],observed.gem.mid,observed.gem.system_hz);']
    return '\n'.join(lines)+'\n'


def emit(folder):
    folder.mkdir(exist_ok=False)
    for path in FROZEN.iterdir():
        if path.is_file():(folder/path.name).write_bytes(path.read_bytes())
    for name,adapt in (('BCM2712PCIePHYTransport.h',header),('BCM2712RP1ConfigTransport.inc',transport),
        ('rp1_decode_cycle.h',decode_header),('rp1_decode_cycle.c',decode_core)):
        path=folder/name;path.write_text(adapt(path.read_text()))
    path=folder/'BCM2712PCIeIDTrialProgress.inc'
    path.write_text(util.once(path.read_text(),'    kprintf("RPI5XNU:PCIEID:END ',diagnostic_calls()+'    kprintf("RPI5XNU:PCIEID:END '))
    (folder/'BCM2712RP1GEMIdentifyTransport.inc').write_text(ADAPTER)
    path=folder/'BCM2712PCIePHYTransport.cpp';path.write_text(path.read_text()+'\n#include "BCM2712RP1GEMIdentifyTransport.inc"\n')
    for suffix in ('c','h'):
        source=ROOT/'loader/rpi5'/('rp1_gem_identify.'+suffix);(folder/source.name).write_bytes(source.read_bytes())
    return path,folder/'rp1_decode_cycle.c',folder/'rp1_gem_identify.c'
