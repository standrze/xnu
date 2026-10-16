/* SPDX-License-Identifier: BSD-2-Clause */
#include "display_mailbox_transaction.h"

/* Broadcom arm_control.h, raspberrypi/linux 2a8d45ec0883e3cbdce920855b3461ac77308a5f:
 * ARM_0_MAIL0_POL at RX+0x10 is explicitly "none-pop read". Current Pi5 FDT
 * and bcm2835-mailbox.c at80d4218 retain the same compatible/register layout.
 * Exact reference bytes/pins are in display_mailbox_transaction_sources.json.
 * This is an original pure state machine; no Broadcom/Linux code is imported.
 */
struct run {
    struct rpi5_display_mailbox_session *s;
    const struct rpi5_display_mailbox_fdt *binding;
    const struct rpi5_display_mailbox_buffer *buffers;
    const struct rpi5_display_mailbox_ops *original_ops;
    struct rpi5_display_mailbox_ops ops;
    struct rpi5_display_mailbox_fdt binding_copy;
    struct rpi5_display_mailbox_buffer buffer_copy[3];
    struct rpi5_display_mailbox_session held;
    uint64_t owner;
};
static int same(const void *a,const void *b,size_t n)
{
    const unsigned char *x=a,*y=b;
    for(size_t i=0;i<n;i++)if(x[i]!=y[i])return 0;
    return 1;
}
static void copy(void *a,const void *b,size_t n)
{
    unsigned char *x=a;const unsigned char *y=b;
    for(size_t i=0;i<n;i++)x[i]=y[i];
}
static int apart(const void *a,size_t na,const void *b,size_t nb)
{
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    return a && b && na<=UINTPTR_MAX-x && nb<=UINTPTR_MAX-y &&
        (x+na<=y || y+nb<=x);
}
static int fail(struct run *r,int error)
{
    r->s->state=RPI5_DISPLAY_MBOX_QUARANTINED;r->s->busy=0;
    r->s->quarantined_buffers=7;r->s->error=error;return error;
}
static int intact(struct run *r)
{
    return r->s->self==r->s && r->s->state==RPI5_DISPLAY_MBOX_ACTIVE &&
        r->s->busy==1 && r->s->owner==r->owner &&
        same(r->binding,&r->binding_copy,sizeof r->binding_copy) &&
        same(r->buffers,r->buffer_copy,sizeof r->buffer_copy) &&
        same(r->original_ops,&r->ops,sizeof r->ops);
}
static int guard(struct run *r)
{
    if(!intact(r))return fail(r,-2);
    struct rpi5_display_mailbox_session before;
    copy(&before,r->s,sizeof before);
    int rc=r->ops.current(r->ops.context,r->s,r->binding,r->buffers,r->owner);
    if(rc || !intact(r) || !same(&before,r->s,sizeof before))return fail(r,-2);
    return 0;
}
static int before(struct run *r)
{
    if(guard(r))return -2;
    if(r->s->callbacks>=RPI5_DISPLAY_MBOX_MAX_CALLBACKS)return fail(r,-3);
    r->s->callbacks++;copy(&r->held,r->s,sizeof r->held);return 0;
}
static int after(struct run *r,int rc)
{
    if(!same(&r->held,r->s,sizeof r->held))return fail(r,-2);
    if(guard(r))return -2;
    return rc ? fail(r,-4) : 0;
}
static int clock_read(struct run *r,uint64_t *value)
{
    if(before(r))return -2;
    uint64_t now=0;int rc=r->ops.now_us(r->ops.context,&now);
    if(after(r,rc))return -4;
    *value=now;return 0;
}
static int tick(struct run *r)
{
    uint64_t now;
    if(clock_read(r,&now))return -4;
    if(now<r->s->last_us || now>=r->s->deadline_us)return fail(r,-3);
    r->s->last_us=now;return 0;
}
static int read_reg(struct run *r,uint32_t offset,uint32_t *value)
{
    if(offset!=RPI5_DISPLAY_MBOX_RX && offset!=RPI5_DISPLAY_MBOX_PEEK &&
        offset!=RPI5_DISPLAY_MBOX_RX_STATUS && offset!=RPI5_DISPLAY_MBOX_TX_STATUS)
        return fail(r,-1);
    if(tick(r) || before(r))return -4;
    uint32_t v=0;int rc=r->ops.read32(r->ops.context,offset,&v);
    if(after(r,rc) || tick(r))return -4;
    *value=v;return 0;
}
static int cache(struct run *r,enum rpi5_display_mailbox_cache direction,size_t bytes)
{
    if(tick(r) || before(r))return -4;
    int rc=r->ops.cache(r->ops.context,r->s->slot,&r->buffers[r->s->slot],bytes,direction);
    return after(r,rc) || tick(r) ? -4 : 0;
}
static int empty(struct run *r)
{
    uint32_t value;
    if(read_reg(r,RPI5_DISPLAY_MBOX_RX_STATUS,&value))return -4;
    return value&RPI5_DISPLAY_MBOX_EMPTY ? 0 : fail(r,-5);
}
static int poll(struct run *r,uint32_t offset,uint32_t bit)
{
    for(;;){
        if(r->s->polls>=RPI5_DISPLAY_MBOX_MAX_POLLS)return fail(r,-3);
        r->s->polls++;
        uint32_t value;if(read_reg(r,offset,&value))return -4;
        if(!(value&bit))return 0;
    }
}
static int transaction(struct run *r,uint32_t kind,uint32_t count,uint32_t index,
    struct rpi5_display_get_reply *reply)
{
    struct rpi5_display_mailbox_session *s=r->s;
    const struct rpi5_display_mailbox_buffer *buffer=&r->buffers[s->slot];
    s->stage=RPI5_DISPLAY_MBOX_ADMISSION;
    if(tick(r) || before(r))return -4;
    int rc=r->ops.admit(r->ops.context,s->slot,buffer,r->binding);
    if(after(r,rc) || tick(r) || empty(r))return -4;
    s->stage=RPI5_DISPLAY_MBOX_REQUEST;size_t bytes=0;
    if(guard(r))return -2;
    rc=rpi5_display_get_request(kind,count,index,buffer->cpu,buffer->capacity,&bytes);
    if(guard(r))return -2;
    if(rc)return fail(r,-6);
    s->stage=RPI5_DISPLAY_MBOX_PUBLISHING;
    if(cache(r,RPI5_DISPLAY_MBOX_PUBLISH,bytes))return -4;
    s->stage=RPI5_DISPLAY_MBOX_WAIT_TX;
    if(poll(r,RPI5_DISPLAY_MBOX_TX_STATUS,RPI5_DISPLAY_MBOX_FULL) || empty(r))return -4;
    s->stage=RPI5_DISPLAY_MBOX_SENDING;
    s->expected_word=(uint32_t)buffer->mailbox_address|RPI5_DISPLAY_MBOX_CHANNEL;
    if(tick(r) || before(r))return -4;
    s->tx_attempted|=1u<<s->slot;
    copy(&r->held,s,sizeof r->held);
    rc=r->ops.write32(r->ops.context,RPI5_DISPLAY_MBOX_TX,s->expected_word);
    if(after(r,rc) || tick(r))return -4;
    s->stage=RPI5_DISPLAY_MBOX_WAIT_RX;
    if(poll(r,RPI5_DISPLAY_MBOX_RX_STATUS,RPI5_DISPLAY_MBOX_EMPTY))return -4;
    s->stage=RPI5_DISPLAY_MBOX_PEEKING;
    if(read_reg(r,RPI5_DISPLAY_MBOX_PEEK,&s->peek_word))return -4;
    if(s->peek_word!=s->expected_word)return fail(r,-5);
    s->stage=RPI5_DISPLAY_MBOX_POPPING;
    /* No callback can consume RX except this single exact-match operation.
     * current() must retain continuous exclusive consumer ownership. */
    s->pop_attempted|=1u<<s->slot;
    if(read_reg(r,RPI5_DISPLAY_MBOX_RX,&s->popped_word))return -4;
    if(s->popped_word!=s->expected_word)return fail(r,-5);
    s->stage=RPI5_DISPLAY_MBOX_ACQUIRING;
    if(cache(r,RPI5_DISPLAY_MBOX_ACQUIRE,bytes))return -4;
    s->stage=RPI5_DISPLAY_MBOX_VALIDATING;
    if(guard(r))return -2;
    rc=rpi5_display_get_response(kind,count,index,buffer->cpu,bytes,reply);
    if(guard(r))return -2;
    if(rc)return fail(r,-6);
    s->stage=RPI5_DISPLAY_MBOX_QUIET;
    if(empty(r))return -4;
    s->completed|=1u<<s->slot;return 0;
}
int rpi5_display_mailbox_query(struct rpi5_display_mailbox_session *s,
    const struct rpi5_display_mailbox_fdt *binding,
    const struct rpi5_display_mailbox_buffer buffers[3],
    const struct rpi5_display_mailbox_ops *ops,uint64_t owner,uint32_t duration,
    struct rpi5_display_mailbox_result *out)
{
    if(!s)return -1;
    if(s->state!=RPI5_DISPLAY_MBOX_UNUSED || s->busy){
        if(s->state==RPI5_DISPLAY_MBOX_ACTIVE){s->state=RPI5_DISPLAY_MBOX_QUARANTINED;s->busy=0;s->quarantined_buffers=7;s->error=-2;}
        return -1;
    }
    /* Semantic zero state; never make uninitialized C padding an admission
     * condition. During callbacks snapshots are copied byte-for-byte. */
    if(s->self || s->owner || s->start_us || s->last_us || s->deadline_us ||
        s->stage || s->slot || s->polls || s->callbacks || s->tx_attempted ||
        s->pop_attempted || s->completed || s->quarantined_buffers ||
        s->expected_word || s->peek_word || s->popped_word || s->error ||
        !binding || !buffers || !ops || !out || !owner ||
        !duration || duration>RPI5_DISPLAY_MBOX_MAX_DURATION_US || !ops->current ||
        !ops->admit || !ops->now_us || !ops->read32 || !ops->write32 || !ops->cache)return -1;
    const void *objects[]={s,binding,buffers,ops,out};
    const size_t sizes[]={sizeof *s,sizeof *binding,3*sizeof *buffers,sizeof *ops,sizeof *out};
    for(unsigned i=0;i<5;i++)for(unsigned j=i+1;j<5;j++)
        if(!apart(objects[i],sizes[i],objects[j],sizes[j]))return -1;
    for(unsigned i=0;i<3;i++){
        const struct rpi5_display_mailbox_buffer *b=&buffers[i];
        if(!b->cpu || ((uintptr_t)b->cpu&15) || b->capacity<RPI5_DISPLAY_GET_MAX_BYTES ||
            b->capacity>RPI5_DISPLAY_MBOX_MAX_CAPACITY || !b->mailbox_address ||
            (b->mailbox_address&15) || b->mailbox_address>UINT32_MAX ||
            b->capacity>UINT64_C(0x100000000)-b->mailbox_address)return -1;
        for(unsigned j=0;j<5;j++)if(!apart(b->cpu,b->capacity,objects[j],sizes[j]))return -1;
        for(unsigned j=0;j<i;j++){
            const struct rpi5_display_mailbox_buffer *a=&buffers[j];
            if(!apart(a->cpu,a->capacity,b->cpu,b->capacity) ||
                !(a->mailbox_address+a->capacity<=b->mailbox_address ||
                    b->mailbox_address+b->capacity<=a->mailbox_address))return -1;
        }
    }
    struct run r={.s=s,.binding=binding,.buffers=buffers,.original_ops=ops,.owner=owner};
    copy(&r.ops,ops,sizeof *ops);copy(&r.binding_copy,binding,sizeof *binding);
    copy(r.buffer_copy,buffers,sizeof r.buffer_copy);
    s->state=RPI5_DISPLAY_MBOX_ACTIVE;s->self=s;s->owner=owner;s->busy=1;
    s->stage=RPI5_DISPLAY_MBOX_ADMISSION;
    uint64_t start;if(clock_read(&r,&start))return s->error;
    if(start>UINT64_MAX-duration)return fail(&r,-3);
    s->start_us=start;s->last_us=start;s->deadline_us=start+duration;
    /* A fresh exclusive session requires BOTH FIFO directions empty. A
     * non-full TX queue alone could still hold an earlier outstanding send. */
    uint32_t initial_tx;
    if(empty(&r) || read_reg(&r,RPI5_DISPLAY_MBOX_TX_STATUS,&initial_tx))return s->error;
    if((initial_tx&(RPI5_DISPLAY_MBOX_EMPTY|RPI5_DISPLAY_MBOX_FULL))!=RPI5_DISPLAY_MBOX_EMPTY)
        return fail(&r,-5);
    struct rpi5_display_mailbox_result result={0};
    if(transaction(&r,RPI5_DISPLAY_GET_COUNT,0,0,&result.count_reply))return s->error;
    result.count=result.count_reply.words[0];
    for(unsigned i=0;i<result.count;i++){
        s->slot=i+1;
        if(transaction(&r,RPI5_DISPLAY_GET_SETTINGS,result.count,i,&result.settings[i]))return s->error;
    }
    s->stage=RPI5_DISPLAY_MBOX_FINISH;
    if(tick(&r) || guard(&r))return s->error;
    s->state=RPI5_DISPLAY_MBOX_COMPLETE;s->busy=0;*out=result;return 0;
}
