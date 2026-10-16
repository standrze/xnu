/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_sd_contract.h"
static uint64_t little(const uint8_t *p, unsigned count)
{
    uint64_t value=0;
    for (unsigned i=0;i<count;i++) value|=(uint64_t)p[i]<<(i*8);
    return value;
}
int rpi5_sd_binding_decode(const void *host, size_t host_bytes,
    const void *power, size_t power_bytes, const void *variant, size_t variant_bytes,
    const void *clock, size_t clock_bytes, const void *settle, size_t settle_bytes,
    const void *irq, size_t irq_bytes, struct rpi5_sd_binding *out)
{
    if (!host || !power || !variant || !clock || !settle || !irq || !out ||
        host_bytes!=32 || power_bytes!=48 || variant_bytes!=4 || clock_bytes!=4 ||
        settle_bytes!=4 || irq_bytes!=4) return -1;
    struct rpi5_sd_binding result={0};
    static const uint64_t bases[5]={0x1000fff000ull,0x1000fff400ull,0x107d517c00ull,
        0x107d504100ull,0x107d510700ull};
    static const uint32_t sizes[5]={0x260,0x200,0x40,0x30,0x20};
    for (unsigned i=0;i<5;i++) {
        const uint8_t *tuple=i<2 ? (const uint8_t *)host+i*16 : (const uint8_t *)power+(i-2)*16;
        if (little(tuple,8)!=bases[i] || little(tuple+8,8)!=sizes[i]) return -1;
        result.base[i]=bases[i]; result.size[i]=sizes[i];
    }
    result.variant=(uint32_t)little(variant,4);
    result.source_hz=(uint32_t)little(clock,4);
    result.settling_us=(uint32_t)little(settle,4);
    if (result.variant>1 || result.source_hz!=200000000 || result.settling_us!=5000 ||
        little(irq,4)!=305) return -1;
    *out=result;
    return 0;
}
int rpi5_sd_read_request_valid(uint64_t sectors, uint64_t block, uint64_t count, uint64_t bytes)
{
    return sectors && sectors<=(UINT64_C(1)<<32) && count && count<=RPI5_SD_MAX_READ_BLOCKS &&
        block<sectors && count<=sectors-block && block<=UINT32_MAX &&
        count-1<=UINT32_MAX-block && bytes==count*512;
}
int rpi5_sd_queue_push(struct rpi5_sd_request_queue *q, struct rpi5_sd_request_link *item)
{
    if (!q || !item || !q->accepting || q->active>1 ||
        q->queued>=RPI5_SD_MAX_REQUESTS-q->active) return -1;
    item->next=0;
    if (q->tail) q->tail->next=item;
    else q->head=item;
    q->tail=item; q->queued++;
    return 0;
}
struct rpi5_sd_request_link *rpi5_sd_queue_pop(struct rpi5_sd_request_queue *q)
{
    if (!q || q->active || !q->head || !q->queued) return 0;
    struct rpi5_sd_request_link *item=q->head;
    q->head=item->next;
    if (!q->head) q->tail=0;
    item->next=0; q->queued--; q->active=1;
    return item;
}
int rpi5_sd_queue_complete(struct rpi5_sd_request_queue *q)
{
    if (!q || q->active!=1) return -1;
    q->active=0;
    return 0;
}
