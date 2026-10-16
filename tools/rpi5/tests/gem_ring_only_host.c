/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_gem_ring_only_batch.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static _Alignas(256) unsigned char rings[2][1536];
static struct rpi5_gem_stage_session session;
static struct rpi5_gem_stage_request request;
static struct rpi5_gem_ring_only_io io;
static struct rpi5_gem_stage_observation output;
static unsigned events,currents,fail_event,fail_current;
static uint64_t ticks;
static const int owner=1,provider=2,capability=3;

static int current(void *context,const struct rpi5_gem_stage_session *s,
    const struct rpi5_gem_stage_request *q,uint64_t *now)
{
    assert(context==&events&&s==&session&&q==&request);
    currents++;assert(currents==s->current_checks);
    if(currents==fail_current)return -1;
    *now=++ticks;return 0;
}
static int write64(void *context,const struct rpi5_gem_stage_session *s,
    unsigned ring,uint32_t offset,const uint32_t values[16])
{
    assert(context==&events&&s==&session);
    assert(rpi5_gem_ring_only_access_allowed(s,RPI5_GEM_STAGE_WRITE,ring,offset));
    assert(rpi5_gem_ring_only_values(s,&request,ring,offset,values));
    events++;if(events==fail_event)return -1;
    memcpy(rings[ring]+offset,values,64);return 0;
}
static int read64(void *context,const struct rpi5_gem_stage_session *s,
    unsigned ring,uint32_t offset,uint32_t values[16])
{
    assert(context==&events&&s==&session);
    assert(rpi5_gem_ring_only_access_allowed(s,RPI5_GEM_STAGE_READ,ring,offset));
    events++;if(events==fail_event)return -1;
    memcpy(values,rings[ring]+offset,64);return 0;
}
static int barrier(void *context,const struct rpi5_gem_stage_session *s)
{
    assert(context==&events&&s==&session);
    assert(rpi5_gem_ring_only_access_allowed(s,RPI5_GEM_STAGE_BARRIER,0,0));
    events++;return events==fail_event?-1:0;
}
static void init(void)
{
    memset(&session,0,sizeof session);memset(&request,0,sizeof request);
    memset(&output,0xa5,sizeof output);memset(rings,0xcc,sizeof rings);
    events=currents=fail_event=fail_current=0;ticks=100;
    request.owner=&owner;request.mapping_provider=&provider;request.capability_source=&capability;
    request.generation=7;request.not_before=100;request.deadline=10000;
    const uint32_t cap[]={0x00070109,0x08508513,0x6eb13fff,0x502e5b45,0x08820000,0,0x24444444,0};
    memcpy(request.raw_capabilities,cap,sizeof cap);
    request.descriptor_memory=RPI5_GEM_MEMORY_UNCACHED;request.packet_granule=0;
    request.ring[0]=(struct rpi5_gem_stage_span){rings[0],0x1100010000,1280};
    request.ring[1]=(struct rpi5_gem_stage_span){rings[1],0x1100014000,1280};
    io=(struct rpi5_gem_ring_only_io){&events,current,write64,read64,barrier};
}
static void unchanged(void)
{
    unsigned char bytes[sizeof output];memset(bytes,0xa5,sizeof bytes);
    assert(!memcmp(&output,bytes,sizeof output));
    for(unsigned r=0;r<2;r++)for(unsigned i=1280;i<sizeof rings[r];i++)assert(rings[r][i]==0xcc);
}
static void tails(void)
{
    for(unsigned r=0;r<2;r++)for(unsigned i=1280;i<sizeof rings[r];i++)assert(rings[r][i]==0xcc);
}
static void invalid(void)
{
    assert(rpi5_gem_ring_only_batch(&session,&request,&io,&output)==-1);
    assert(session.state==RPI5_GEM_STAGE_UNUSED&&!events&&!currents);unchanged();
}
static void failed(void)
{
    assert(rpi5_gem_ring_only_batch(&session,&request,&io,&output)<0);
    assert(session.state==RPI5_GEM_STAGE_QUARANTINED&&!session.busy&&!session.pending);unchanged();
}
static void success(void)
{
    assert(!rpi5_gem_ring_only_batch(&session,&request,&io,&output));
    assert(session.state==RPI5_GEM_STAGE_HELD&&events==81&&currents==164);
    assert(output.writes==640&&output.reads==640&&output.cpu_owned_descriptors==160);
    for(unsigned r=0;r<2;r++)for(unsigned i=0;i<80;i++){
        const struct rpi5_gem_descriptor *d=(const void *)(rings[r]+16*i);
        assert(!d->address_high&&!d->reserved);
        if(!r){assert(!d->address);assert(d->control==(0x80000000u|(i==63?0x40000000u:0)));}
        else {assert(d->address==(1u|(i==63?2u:0)));assert(!d->control);}
    }
    tails();
}
int main(void)
{
    init();success();
    unsigned event_faults=0,current_faults=0,packet_negatives=0;
    for(unsigned n=1;n<=81;n++){init();fail_event=n;failed();assert(events==n);event_faults++;}
    for(unsigned n=1;n<=164;n++){init();fail_current=n;failed();assert(currents==n);current_faults++;}
    for(unsigned r=0;r<2;r++)for(unsigned i=0;i<RPI5_GEM_STAGE_SLOTS;i++){
        init();request.packet[r][i].cpu=rings[0];invalid();packet_negatives++;
        init();request.packet[r][i].dma=0x1000;invalid();packet_negatives++;
        init();request.packet[r][i].bytes=2048;invalid();packet_negatives++;
    }
    init();request.packet_granule=64;invalid();
    init();request.ring[0].bytes=64;invalid();
    init();request.ring[1].dma=request.ring[0].dma;invalid();
    init();request.ring[1].cpu=request.ring[0].cpu;invalid();
    init();request.descriptor_memory=RPI5_GEM_MEMORY_UNPROVEN;invalid();
    printf("GEM_RING_ONLY_PASS events=%u owners=%u packet_negatives=%u writes=640 reads=640 held=160 NO_PACKET_MEMORY=1 NO_DMA=1\n",
        event_faults,current_faults,packet_negatives);
    return 0;
}
