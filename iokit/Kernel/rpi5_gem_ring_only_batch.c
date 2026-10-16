/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_gem_ring_only_batch.h"
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "The staged GEM descriptor profile requires a little-endian CPU"
#endif
_Static_assert(sizeof(struct rpi5_gem_descriptor)==16,"64-bit non-PTP descriptor");
_Static_assert(offsetof(struct rpi5_gem_descriptor,address_high)==8,"upper address");
_Static_assert(offsetof(struct rpi5_gem_descriptor,reserved)==12,"reserved word");

static int same(const void *a,const void *b,size_t n)
{const unsigned char *x=a,*y=b;for(size_t i=0;i<n;i++)if(x[i]!=y[i])return 0;return 1;}
static void copy(void *a,const void *b,size_t n)
{unsigned char *x=a;const unsigned char *y=b;for(size_t i=0;i<n;i++)x[i]=y[i];}
static int zero(const void *a,size_t n)
{const unsigned char *x=a;for(size_t i=0;i<n;i++)if(x[i])return 0;return 1;}
static int apart(const void *a,size_t na,const void *b,size_t nb)
{uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return a&&b&&na<=UINTPTR_MAX-x&&nb<=UINTPTR_MAX-y&&(x+na<=y||y+nb<=x);}
static int dma_apart(uint64_t a,size_t na,uint64_t b,size_t nb)
{return a&&b&&na<=UINT64_MAX-a&&nb<=UINT64_MAX-b&&(a+na<=b||b+nb<=a);}
static int cap_profile(const uint32_t c[8])
{
    return c[0]==0x00070109&&((c[1]>>25)&7)==4&&(c[1]&1)&&
        ((c[2]>>20)&3)==3&&((c[2]>>22)&15)==10&&
        (c[4]&255)==0&&((c[4]>>23)&1)==1&&
        ((c[6]>>8)&15)==4&&((c[6]>>12)&15)==4&&!(c[7]&(1u<<26));
}
static int spans(const struct rpi5_gem_stage_request *q,const void *const *objects,
    const size_t *sizes)
{
    for(unsigned r=0;r<2;r++){
        const struct rpi5_gem_stage_span *s=&q->ring[r];
        if(!s->cpu||!s->dma||s->bytes!=RPI5_GEM_STAGE_RING_BYTES||
            ((uintptr_t)s->cpu&63)||(s->dma&63)||s->bytes>UINTPTR_MAX-(uintptr_t)s->cpu||
            s->bytes>UINT64_MAX-s->dma||(s->dma>>32)!=((s->dma+s->bytes-1)>>32))return 0;
        for(unsigned j=0;j<4;j++)if(!apart(s->cpu,s->bytes,objects[j],sizes[j]))return 0;
        if(r&&(!apart(s->cpu,s->bytes,q->ring[0].cpu,q->ring[0].bytes)||
            !dma_apart(s->dma,s->bytes,q->ring[0].dma,q->ring[0].bytes)))return 0;
    }
    for(unsigned r=0;r<2;r++)for(unsigned i=0;i<RPI5_GEM_STAGE_SLOTS;i++)
        if(q->packet[r][i].cpu||q->packet[r][i].dma||q->packet[r][i].bytes)return 0;
    return 1;
}
static uint32_t word(unsigned r,unsigned offset)
{
    unsigned index=offset/16,part=(offset%16)/4;
    if(part==2||part==3)return 0;
    if(part==1)return r?0:(0x80000000u|(index==RPI5_GEM_STAGE_SLOTS-1?0x40000000u:0));
    return r?(1u|(index==RPI5_GEM_STAGE_SLOTS-1?2u:0)):0;
}
int rpi5_gem_ring_only_access_allowed(const struct rpi5_gem_stage_session *s,
    enum rpi5_gem_stage_operation op,unsigned ring,uint32_t offset)
{
    return s&&s->self==s&&s->state==RPI5_GEM_STAGE_BUILDING&&s->busy==1&&
        s->pending==op&&s->callbacks&&s->callbacks<=RPI5_GEM_RING_ONLY_IO_LIMIT&&
        ((op==RPI5_GEM_STAGE_BARRIER&&ring==0&&offset==0)||
         ((op==RPI5_GEM_STAGE_READ||op==RPI5_GEM_STAGE_WRITE)&&ring<2&&
          s->ring==ring&&s->offset==offset&&offset<=RPI5_GEM_STAGE_RING_BYTES-RPI5_GEM_RING_ONLY_BATCH_BYTES&&
          !(offset&(RPI5_GEM_RING_ONLY_BATCH_BYTES-1))));
}
int rpi5_gem_ring_only_values(const struct rpi5_gem_stage_session *s,
    const struct rpi5_gem_stage_request *q,unsigned ring,uint32_t offset,
    const uint32_t values[16])
{
    if(!s||!q||!values||s->request!=q||
       !rpi5_gem_ring_only_access_allowed(s,RPI5_GEM_STAGE_WRITE,ring,offset))return 0;
    for(unsigned i=0;i<16;i++)if(values[i]!=word(ring,offset+4*i))return 0;
    return 1;
}
struct run {struct rpi5_gem_stage_session *s;const struct rpi5_gem_stage_request *original;
    const struct rpi5_gem_ring_only_io *original_io;struct rpi5_gem_stage_request q;
    struct rpi5_gem_ring_only_io io;};
static int fail(struct run *r,int error)
{r->s->state=RPI5_GEM_STAGE_QUARANTINED;r->s->busy=0;r->s->pending=RPI5_GEM_STAGE_NONE;r->s->error=error;return error;}
static int intact(const struct run *r)
{return r->s->self==r->s&&r->s->state==RPI5_GEM_STAGE_BUILDING&&r->s->busy==1&&
    r->s->request==r->original&&same(r->original,&r->q,sizeof r->q)&&
    same(r->original_io,&r->io,sizeof r->io);}
static int guard(struct run *r)
{
    if(!intact(r)||r->s->current_checks>=RPI5_GEM_RING_ONLY_CURRENT_LIMIT)return fail(r,-3);
    r->s->current_checks++;struct rpi5_gem_stage_session held;copy(&held,r->s,sizeof held);
    uint64_t now=0;int rc=r->io.current(r->io.context,r->s,r->original,&now);
    if(rc||!intact(r)||!same(&held,r->s,sizeof held))return fail(r,-3);
    if(now<r->q.not_before||now<r->s->last||now>=r->q.deadline)return fail(r,-4);
    r->s->last=now;return 0;
}
static int operation(struct run *r,enum rpi5_gem_stage_operation op,unsigned ring,unsigned offset)
{
    struct rpi5_gem_stage_session *s=r->s;if(s->callbacks>=RPI5_GEM_RING_ONLY_IO_LIMIT)return fail(r,-3);
    s->pending=op;s->ring=ring;s->offset=offset;s->value=op==RPI5_GEM_STAGE_BARRIER?0:word(ring,offset);
    s->callbacks++;if(guard(r))return s->error;
    if(!rpi5_gem_ring_only_access_allowed(s,op,ring,offset))return fail(r,-3);
    if(op==RPI5_GEM_STAGE_WRITE)s->writes_attempted+=16;
    struct rpi5_gem_stage_session held;copy(&held,s,sizeof held);uint32_t values[16];
    for(unsigned i=0;i<16;i++)values[i]=op==RPI5_GEM_STAGE_BARRIER?0:word(ring,offset+4*i);
    int rc=op==RPI5_GEM_STAGE_WRITE?r->io.write64(r->io.context,s,ring,offset,values):
        op==RPI5_GEM_STAGE_READ?r->io.read64(r->io.context,s,ring,offset,values):r->io.barrier(r->io.context,s);
    if(!same(s,&held,sizeof held))return fail(r,-3);if(guard(r))return s->error;if(rc)return fail(r,-5);
    if(op==RPI5_GEM_STAGE_READ)for(unsigned i=0;i<16;i++)if(values[i]!=word(ring,offset+4*i))return fail(r,-6);
    if(op==RPI5_GEM_STAGE_WRITE)s->writes_completed+=16;if(op==RPI5_GEM_STAGE_READ)s->reads_completed+=16;
    s->pending=RPI5_GEM_STAGE_NONE;return 0;
}
int rpi5_gem_ring_only_batch(struct rpi5_gem_stage_session *s,
    const struct rpi5_gem_stage_request *q,const struct rpi5_gem_ring_only_io *io,
    struct rpi5_gem_stage_observation *out)
{
    if(!s)return -1;if(s->state!=RPI5_GEM_STAGE_UNUSED){if(s->state==RPI5_GEM_STAGE_BUILDING){
        s->state=RPI5_GEM_STAGE_QUARANTINED;s->busy=0;s->pending=RPI5_GEM_STAGE_NONE;s->error=-2;}return -2;}
    if(!q||!io||!out||!zero(s,sizeof *s)||!io->current||!io->write64||!io->read64||!io->barrier||
        !q->owner||!q->mapping_provider||!q->capability_source||!q->generation||!q->deadline||q->not_before>=q->deadline||
        (q->descriptor_memory!=RPI5_GEM_MEMORY_COHERENT&&q->descriptor_memory!=RPI5_GEM_MEMORY_UNCACHED)||
        q->packet_granule||!cap_profile(q->raw_capabilities))return -1;
    const void *objects[]={s,q,io,out};const size_t sizes[]={sizeof *s,sizeof *q,sizeof *io,sizeof *out};
    for(unsigned i=0;i<4;i++)for(unsigned j=0;j<i;j++)if(!apart(objects[i],sizes[i],objects[j],sizes[j]))return -1;
    if(!spans(q,objects,sizes))return -1;
    struct run r;r.s=s;r.original=q;r.original_io=io;
    copy(&r.q,q,sizeof *q);copy(&r.io,io,sizeof *io);
    s->self=s;s->request=q;s->state=RPI5_GEM_STAGE_BUILDING;s->busy=1;s->last=q->not_before;if(guard(&r))return s->error;
    for(unsigned ring=0;ring<2;ring++)for(unsigned offset=0;offset<RPI5_GEM_STAGE_RING_BYTES;offset+=64)
        if(operation(&r,RPI5_GEM_STAGE_WRITE,ring,offset))return s->error;
    if(operation(&r,RPI5_GEM_STAGE_BARRIER,0,0))return s->error;
    for(unsigned ring=0;ring<2;ring++)for(unsigned offset=0;offset<RPI5_GEM_STAGE_RING_BYTES;offset+=64)
        if(operation(&r,RPI5_GEM_STAGE_READ,ring,offset))return s->error;
    if(guard(&r))return s->error;
    struct rpi5_gem_stage_observation result={{q->ring[0].dma,q->ring[1].dma},q->generation,
        RPI5_GEM_STAGE_RING_BYTES,16,RPI5_GEM_STAGE_SLOTS,RPI5_GEM_STAGE_TAIL_BYTES,
        2*RPI5_GEM_STAGE_RING_BYTES/16,s->writes_completed,s->reads_completed,s->callbacks,s->current_checks};
    s->state=RPI5_GEM_STAGE_HELD;s->busy=0;*out=result;return 0;
}
