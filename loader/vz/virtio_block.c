/* SPDX-License-Identifier: BSD-2-Clause
 * Independently implemented from OASIS virtio 1.2 sections 2.7, 4.1 and 5.2.
 * One split-ring queue; coherent VZ guest RAM; no IRQ/MSI or physical host DMA.
 */
#include "virtio_block.h"
#define QUEUE_SIZE 8
#define AVAIL 0x100
#define USED 0x200
#define HEADER 0x400
#define STATUS 0x420
struct descriptor { uint64_t address; uint32_t length; uint16_t flags, next; };
static void barrier(void) { __asm__ volatile("dmb osh" ::: "memory"); }
static uint64_t ticks(void) { uint64_t v; __asm__ volatile("mrs %0, cntvct_el0" : "=r"(v)); return v; }
static uint64_t frequency(void) { uint64_t v; __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(v)); return v; }
static uint16_t r16(volatile uint8_t *p, unsigned o) { return *(volatile uint16_t *)(p+o); }
static uint32_t r32(volatile uint8_t *p, unsigned o) { return *(volatile uint32_t *)(p+o); }
static void w16(volatile uint8_t *p, unsigned o, uint16_t v) { *(volatile uint16_t *)(p+o)=v; }
static void w32(volatile uint8_t *p, unsigned o, uint32_t v) { *(volatile uint32_t *)(p+o)=v; }
static void w64(volatile uint8_t *p, unsigned o, uint64_t v) { *(volatile uint64_t *)(p+o)=v; }

int vz_block_discover(uint64_t ecam, unsigned start, unsigned end, struct vz_block_device *out)
{
    if (!ecam || !out || start>end || end>255) return -1;
    unsigned found=0;
    for (unsigned bus=start; bus<=end; bus++) for (unsigned dev=0; dev<32; dev++)
    for (unsigned function=0; function<8; function++) {
        volatile uint8_t *pci=(volatile uint8_t *)(uintptr_t)(ecam+((uint64_t)(bus-start)<<20)+
            ((uint64_t)dev<<15)+((uint64_t)function<<12));
        if (r32(pci,0)!=UINT32_C(0x10421af4)) continue;
        uint64_t bars[6]={0};
        for (unsigned i=0; i<6; i++) {
            uint32_t low=r32(pci,0x10+i*4);
            if (low&1) continue;
            bars[i]=low&~UINT64_C(15);
            if ((low&6)==4 && i<5) { bars[i]|=(uint64_t)r32(pci,0x14+i*4)<<32; i++; }
        }
        struct vz_block_device d={0};
        unsigned cap=pci[0x34]&~3U;
        for (unsigned seen=0; cap>=0x40 && cap<=0xfc && seen<48; seen++) {
            unsigned next=pci[cap+1]&~3U;
            if (pci[cap]==9 && cap<=0xec && pci[cap+2]>=16) {
                unsigned type=pci[cap+3], bar=pci[cap+4];
                uint32_t offset=r32(pci,cap+8), length=r32(pci,cap+12);
                if (bar<6 && bars[bar] && length && offset<=UINT32_MAX-length) {
                    if (type==1 && length>=56) d.common_pa=bars[bar]+offset;
                    if (type==4 && length>=8) d.config_pa=bars[bar]+offset;
                    if (type==2 && pci[cap+2]>=20 && cap<=0xe8) {
                        d.notify_pa=bars[bar]+offset; d.notify_length=length;
                        d.notify_multiplier=r32(pci,cap+16);
                    }
                }
            }
            if (!next || next==cap) break;
            cap=next;
        }
        if (!d.common_pa || !d.notify_pa || !d.config_pa || !d.notify_multiplier ||
            (d.common_pa&7) || (d.config_pa&7) || (d.notify_pa&1)) return -1;
        volatile uint8_t *common=(volatile uint8_t *)(uintptr_t)d.common_pa;
        w32(common,0,0); barrier();
        if (r32(common,4)&(1U<<5)) continue; /* EFI disk remains untouched. */
        if (++found!=1) return -1;
        w16(pci,4,(uint16_t)(r16(pci,4)|6|0x400));
        d.magic=VZ_BLOCK_MAGIC; *out=d;
    }
    return found ? 0 : 1;
}

int vz_block_start(const struct vz_block_device *d, struct vz_block_queue *q,
    uintptr_t (*map)(uint64_t,size_t), volatile void *dma, uint64_t pa)
{
    if (!d || !q || d->magic!=VZ_BLOCK_MAGIC || !map || !dma || !pa || (pa&0x3fff)) return -1;
    q->common=(volatile uint8_t *)map(d->common_pa,56);
    q->notify=(volatile uint8_t *)map(d->notify_pa,d->notify_length);
    q->config=(volatile uint8_t *)map(d->config_pa,8);
    q->dma=(volatile uint8_t *)dma; q->dma_pa=pa; q->failed=1;
    if (!q->common || !q->notify || !q->config || d->notify_length<2 || d->notify_length>65536) return -1;
    volatile uint8_t *c=q->common;
    c[20]=0; barrier();
    uint64_t begin=ticks(), budget=frequency();
    if (!budget) return -1;
    while (c[20]) if (ticks()-begin>budget) return -1;
    c[20]=1; c[20]=3;
    w32(c,0,0); barrier(); uint32_t low=r32(c,4);
    if ((low&(1U<<5)) || !(low&(1U<<9))) return -1;
    w32(c,0,1); barrier(); if (!(r32(c,4)&1)) return -1;
    w32(c,8,0); w32(c,12,1U<<9); /* mandatory FLUSH, no optional layout features */
    w32(c,8,1); w32(c,12,1); /* VERSION_1 */
    c[20]=11; barrier(); if (!(c[20]&8)) return -1;
    for (unsigned attempt=0; attempt<16; attempt++) {
        unsigned generation=c[21]; barrier();
        q->capacity=(uint64_t)r32(q->config,0)|((uint64_t)r32(q->config,4)<<32);
        barrier(); if (generation==c[21]) break;
        if (attempt==15) return -1;
    }
    if (!q->capacity || q->capacity>UINT64_MAX/512) return -1;
    w16(c,16,UINT16_MAX); w16(c,22,0);
    if (r16(c,24)<QUEUE_SIZE || r16(c,28)) return -1;
    w16(c,24,QUEUE_SIZE); w16(c,26,UINT16_MAX);
    uint64_t notify=(uint64_t)r16(c,30)*d->notify_multiplier;
    if (notify>d->notify_length-2 || (notify&1)) return -1;
    q->notify_offset=(uint32_t)notify;
    for (unsigned i=0; i<VZ_BLOCK_DMA_BYTES; i++) q->dma[i]=0;
    w16(q->dma,AVAIL,1); /* poll, no interrupts */
    w64(c,32,pa); w64(c,40,pa+AVAIL); w64(c,48,pa+USED);
    barrier(); w16(c,28,1); c[20]=15; barrier();
    if (c[20]!=15) return -1;
    q->available=q->used=0; q->failed=0;
    return 0;
}

int vz_block_request(struct vz_block_queue *q, unsigned type, uint64_t sector, uint32_t bytes)
{
    if (!q || q->failed || (type!=0 && type!=1 && type!=4) ||
        (type==4 ? (bytes || sector) : (!bytes || bytes>VZ_BLOCK_MAX_BYTES || (bytes&511) ||
        sector>=q->capacity || bytes/512>q->capacity-sector))) return -1;
    volatile uint8_t *dma=q->dma;
    volatile struct descriptor *desc=(volatile struct descriptor *)(uintptr_t)dma;
    w32(dma,HEADER,type); w32(dma,HEADER+4,0); w64(dma,HEADER+8,sector); dma[STATUS]=0xff;
    desc[0]=(struct descriptor){q->dma_pa+HEADER,16,1, type==4 ? 2 : 1};
    desc[1]=(struct descriptor){q->dma_pa+VZ_BLOCK_DATA_OFFSET,bytes,(uint16_t)(type==0 ? 3 : 1),2};
    desc[2]=(struct descriptor){q->dma_pa+STATUS,1,2,0};
    w16(dma,AVAIL+4+(q->available%QUEUE_SIZE)*2,0);
    barrier(); w16(dma,AVAIL+2,++q->available); barrier(); w16(q->notify,q->notify_offset,0);
    uint64_t begin=ticks(), budget=frequency();
    while (r16(dma,USED+2)==q->used) {
        if (ticks()-begin>budget) goto failure;
        __asm__ volatile("yield");
    }
    barrier();
    unsigned slot=q->used%QUEUE_SIZE;
    if (r16(dma,USED+2)!=(uint16_t)(q->used+1) || r32(dma,USED+4+slot*8)!=0 ||
        r32(dma,USED+8+slot*8)!=(type==0 ? bytes+1 : 1)) goto failure;
    q->used++;
    if (dma[STATUS]!=0) return -1;
    return 0;
failure:
    q->failed=1; q->common[20]=0; barrier();
    /* Do not free or reuse DMA, even if the device has not confirmed reset. */
    return -1;
}
