/* SPDX-License-Identifier: BSD-2-Clause
 * Original implementation of OASIS virtio 1.2 split rings and network device.
 * One RX/TX queue pair, Ethernet MTU 1500, MAC + VERSION_1; checksum completion,
 * mergeable RX, multiqueue, MSI, host DMA, physical hardware or promiscuous mode.
 */
#include "virtio_net.h"
#define AVAIL 0x100
#define USED 0x200
struct descriptor { uint64_t address; uint32_t length; uint16_t flags, next; };
static void barrier(void) { __asm__ volatile("dmb osh" ::: "memory"); }
static uint64_t ticks(void) { uint64_t v; __asm__ volatile("mrs %0, cntvct_el0" : "=r"(v)); return v; }
static uint64_t frequency(void) { uint64_t v; __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(v)); return v; }
static uint16_t r16(volatile uint8_t *p, unsigned o) { return *(volatile uint16_t *)(uintptr_t)(p+o); }
static uint32_t r32(volatile uint8_t *p, unsigned o) { return *(volatile uint32_t *)(uintptr_t)(p+o); }
static void w16(volatile uint8_t *p, unsigned o, uint16_t v) { *(volatile uint16_t *)(uintptr_t)(p+o)=v; }
static void w32(volatile uint8_t *p, unsigned o, uint32_t v) { *(volatile uint32_t *)(uintptr_t)(p+o)=v; }
static void w64(volatile uint8_t *p, unsigned o, uint64_t v) { *(volatile uint64_t *)(uintptr_t)(p+o)=v; }

int vz_net_discover(uint64_t ecam, unsigned first, unsigned last, struct vz_net_device *out)
{
    if (!ecam || !out || first>last || last>255) return -1;
    unsigned found=0;
    for (unsigned bus=first; bus<=last; bus++) for (unsigned dev=0; dev<32; dev++)
    for (unsigned function=0; function<8; function++) {
        volatile uint8_t *pci=(volatile uint8_t *)(uintptr_t)(ecam+((uint64_t)(bus-first)<<20)+
            ((uint64_t)dev<<15)+((uint64_t)function<<12));
        if (r32(pci,0)!=UINT32_C(0x10411af4)) continue;
        if (++found!=1) return -1;
        uint64_t bars[6]={0};
        for (unsigned i=0; i<6; i++) {
            uint32_t low=r32(pci,0x10+i*4);
            if (low&1) continue;
            bars[i]=low&~UINT64_C(15);
            if ((low&6)==4 && i<5) { bars[i]|=(uint64_t)r32(pci,0x14+i*4)<<32; i++; }
        }
        struct vz_net_device d={0};
        unsigned cap=pci[0x34]&~3U;
        for (unsigned seen=0; cap>=0x40 && cap<=0xfc && seen<48; seen++) {
            unsigned next=pci[cap+1]&~3U;
            if (pci[cap]==9 && cap<=0xec && pci[cap+2]>=16) {
                unsigned type=pci[cap+3], bar=pci[cap+4];
                uint32_t offset=r32(pci,cap+8), length=r32(pci,cap+12);
                if (bar<6 && bars[bar] && length && offset<=UINT32_MAX-length) {
                    if (type==1 && length>=56) d.common_pa=bars[bar]+offset;
                    if (type==4 && length>=6) d.config_pa=bars[bar]+offset;
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
            (d.common_pa&7) || (d.notify_pa&1)) return -1;
        w16(pci,4,(uint16_t)(r16(pci,4)|6|0x400));
        d.magic=VZ_NET_MAGIC; *out=d;
    }
    return found ? 0 : 1;
}

static void notify(struct vz_net_queue *q, unsigned queue)
{
    barrier(); w16(q->notify,q->notify_offset[queue],(uint16_t)queue);
}

static int failure(struct vz_net_queue *q)
{
    q->failed=1;
    if (q->common) { q->common[20]=0; barrier(); }
    /* Keep all DMA memory pinned until VM termination, including failed reset. */
    return -1;
}

int vz_net_start(const struct vz_net_device *d, struct vz_net_queue *q,
    uintptr_t (*map)(uint64_t,size_t), volatile void *dma, uint64_t pa)
{
    if (!d || !q || d->magic!=VZ_NET_MAGIC || !map || !dma || !pa || (pa&0x3fff) ||
        d->notify_length<2 || d->notify_length>65536) return -1;
    q->common=(volatile uint8_t *)map(d->common_pa,56);
    q->notify=(volatile uint8_t *)map(d->notify_pa,d->notify_length);
    q->config=(volatile uint8_t *)map(d->config_pa,12);
    q->dma=(volatile uint8_t *)dma; q->dma_pa=pa; q->failed=1; q->tx_busy=0;
    q->stage=1;
    if (!q->common || !q->notify || !q->config) return -1;
    volatile uint8_t *c=q->common;
    c[20]=0; barrier();
    uint64_t begin=ticks(), budget=frequency();
    if (!budget) return -1;
    while (c[20]) if (ticks()-begin>budget) return -1;
    q->stage=2;
    c[20]=1; c[20]=3;
    w32(c,0,0); barrier(); q->features_low=r32(c,4);
    w32(c,0,1); barrier(); q->features_high=r32(c,4);
    if (!(q->features_low&(1U<<5)) || !(q->features_high&1)) return failure(q); /* MAC + VERSION_1 */
    q->stage=20;
    /* Advertise checksum completion, but never GSO/TSO. Outgoing frames have
     * their checksums computed by BSD; incoming partial checksums are finished
     * below before the Ethernet frame reaches the stack. */
    /* MTU/status are read-only configuration. INDIRECT_DESC permits direct
     * descriptors too; this driver continues using direct, bounded rings. */
    uint32_t accepted=(1U<<5)|(q->features_low&(3U|(1U<<3)|(1U<<16)|(1U<<28)));
    w32(c,8,0); w32(c,12,accepted);
    w32(c,8,1); w32(c,12,1);
    c[20]=11; barrier(); if (!(c[20]&8)) { q->stage=200+c[20]; return failure(q); }
    q->stage=3;
    for (unsigned attempt=0; attempt<16; attempt++) {
        unsigned generation=c[21]; barrier();
        for (unsigned i=0; i<6; i++) q->mac[i]=q->config[i];
        barrier(); if (generation==c[21]) break;
        if (attempt==15) return failure(q);
    }
    unsigned nonzero=0;
    for (unsigned i=0; i<6; i++) nonzero|=q->mac[i];
    if (!nonzero || (q->mac[0]&1)) return failure(q);
    if ((accepted&(1U<<3)) && r16(q->config,10)<1500) return failure(q);
    if ((accepted&(1U<<16)) && !(r16(q->config,6)&1)) return failure(q);
    for (unsigned i=0; i<VZ_NET_DMA_BYTES; i++) q->dma[i]=0;
    w16(c,16,UINT16_MAX);
    for (unsigned queue=0; queue<2; queue++) {
        q->stage=4+queue;
        w16(c,22,(uint16_t)queue);
        if (r16(c,24)<VZ_NET_QUEUE_SIZE || r16(c,28)) return failure(q);
        w16(c,24,VZ_NET_QUEUE_SIZE); w16(c,26,UINT16_MAX);
        uint64_t offset=(uint64_t)r16(c,30)*d->notify_multiplier;
        if (offset>d->notify_length-2 || (offset&1)) return failure(q);
        q->notify_offset[queue]=(uint32_t)offset;
        volatile uint8_t *area=q->dma+queue*VZ_NET_QUEUE_BYTES;
        volatile struct descriptor *desc=(volatile struct descriptor *)(uintptr_t)area;
        for (unsigned i=0; i<VZ_NET_QUEUE_SIZE; i++) {
            desc[i].address=pa+queue*VZ_NET_QUEUE_BYTES+VZ_NET_BUFFER_OFFSET+i*VZ_NET_BUFFER_BYTES;
            desc[i].length=VZ_NET_BUFFER_BYTES; desc[i].flags=(uint16_t)(queue ? 0 : 2);
            if (!queue) w16(area,AVAIL+4+2*i,(uint16_t)i);
        }
        w16(area,AVAIL,1); q->used[queue]=0;
        q->available[queue]=(uint16_t)(queue ? 0 : VZ_NET_QUEUE_SIZE);
        w16(area,AVAIL+2,q->available[queue]);
        w64(c,32,pa+queue*VZ_NET_QUEUE_BYTES);
        w64(c,40,pa+queue*VZ_NET_QUEUE_BYTES+AVAIL);
        w64(c,48,pa+queue*VZ_NET_QUEUE_BYTES+USED);
        barrier(); w16(c,28,1);
    }
    c[20]=15; barrier(); if (c[20]!=15) return failure(q);
    q->stage=6;
    q->failed=0; notify(q,0);
    return 0;
}

static int reap_tx(struct vz_net_queue *q)
{
    volatile uint8_t *area=q->dma+VZ_NET_QUEUE_BYTES;
    uint16_t end=r16(area,USED+2); barrier();
    if ((uint16_t)(end-q->used[1])>VZ_NET_QUEUE_SIZE) return failure(q);
    while (q->used[1]!=end) {
        unsigned slot=q->used[1]%VZ_NET_QUEUE_SIZE;
        uint32_t id=r32(area,USED+4+slot*8);
        if (id>=VZ_NET_QUEUE_SIZE || !(q->tx_busy&(1U<<id))) return failure(q);
        q->tx_busy=(uint16_t)(q->tx_busy&~(1U<<id)); q->used[1]++;
    }
    return 0;
}

int vz_net_send(struct vz_net_queue *q, const unsigned char *frame, size_t n)
{
    if (!q || q->failed || !frame || n<14 || n>VZ_NET_FRAME_MAX) return -1;
    if (reap_tx(q)) return -1;
    unsigned id=0;
    while (id<VZ_NET_QUEUE_SIZE && (q->tx_busy&(1U<<id))) id++;
    if (id==VZ_NET_QUEUE_SIZE) return 1;
    volatile uint8_t *area=q->dma+VZ_NET_QUEUE_BYTES;
    volatile uint8_t *buffer=area+VZ_NET_BUFFER_OFFSET+id*VZ_NET_BUFFER_BYTES;
    for (unsigned i=0; i<VZ_NET_HEADER_BYTES; i++) buffer[i]=0;
    for (size_t i=0; i<n; i++) buffer[VZ_NET_HEADER_BYTES+i]=frame[i];
    /* Ethernet payload minimum excludes the FCS; ARP frames need padding. */
    size_t wire_size=n<60 ? 60 : n;
    for(size_t i=n;i<wire_size;i++)buffer[VZ_NET_HEADER_BYTES+i]=0;
    volatile struct descriptor *desc=(volatile struct descriptor *)(uintptr_t)area;
    desc[id].length=(uint32_t)(VZ_NET_HEADER_BYTES+wire_size);
    q->tx_busy=(uint16_t)(q->tx_busy|(1U<<id));
    w16(area,AVAIL+4+2*(q->available[1]%VZ_NET_QUEUE_SIZE),(uint16_t)id);
    barrier(); w16(area,AVAIL+2,++q->available[1]); notify(q,1);
    return 0;
}

int vz_net_receive(struct vz_net_queue *q, unsigned char frame[VZ_NET_FRAME_MAX], size_t *size)
{
    if (!q || q->failed || !frame || !size) return -1;
    volatile uint8_t *area=q->dma;
    uint16_t end=r16(area,USED+2); barrier();
    if (end==q->used[0]) return 0;
    if ((uint16_t)(end-q->used[0])>VZ_NET_QUEUE_SIZE) return failure(q);
    unsigned slot=q->used[0]%VZ_NET_QUEUE_SIZE;
    uint32_t id=r32(area,USED+4+slot*8), length=r32(area,USED+8+slot*8);
    if (id>=VZ_NET_QUEUE_SIZE || length>VZ_NET_BUFFER_BYTES) return failure(q);
    volatile uint8_t *buffer=area+VZ_NET_BUFFER_OFFSET+id*VZ_NET_BUFFER_BYTES;
    /* Some VZ receive packets carry DATA_VALID|RSC_INFO (6), even with GSO
     * disabled. With gso_type NONE and a complete MTU-bounded Ethernet frame,
     * ignore that advisory metadata and let BSD verify the IP/transport
     * checksums. Never interpret RSC fields as partial-checksum offsets. */
    unsigned flags=buffer[0];
    int supported_flags=!(flags&~7U) && (!(flags&4) || (flags&3)==2);
    int accepted=length>=VZ_NET_HEADER_BYTES+14 && length<=VZ_NET_HEADER_BYTES+VZ_NET_FRAME_MAX &&
        supported_flags && buffer[1]==0;
    if (accepted) {
        *size=length-VZ_NET_HEADER_BYTES;
        for (size_t i=0; i<*size; i++) frame[i]=buffer[VZ_NET_HEADER_BYTES+i];
        if (buffer[0]&1) {
            unsigned start=(unsigned)buffer[6]|((unsigned)buffer[7]<<8);
            unsigned offset=(unsigned)buffer[8]|((unsigned)buffer[9]<<8);
            if (start>*size || offset>*size-start || *size-start-offset<2) accepted=0;
            else {
                uint32_t sum=0;
                for (size_t i=start; i<*size; i+=2)
                    sum+=((uint32_t)frame[i]<<8)+(i+1<*size ? frame[i+1] : 0);
                while (sum>>16) sum=(sum&0xffff)+(sum>>16);
                uint16_t checksum=(uint16_t)~sum;
                frame[start+offset]=(unsigned char)(checksum>>8);
                frame[start+offset+1]=(unsigned char)checksum;
            }
        }
    }
    if (!accepted) q->last_rejected=((uint64_t)length<<48)|((uint64_t)buffer[0]<<40)|
        ((uint64_t)buffer[1]<<32)|((uint64_t)r16(buffer,6)<<16)|r16(buffer,8);
    w16(area,AVAIL+4+2*(q->available[0]%VZ_NET_QUEUE_SIZE),(uint16_t)id);
    barrier(); w16(area,AVAIL+2,++q->available[0]); q->used[0]++; notify(q,0);
    return accepted ? 1 : 2;
}
