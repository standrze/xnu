/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_gem_ring_stage.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static _Alignas(256) unsigned char rings[2][1536],packets[2][RPI5_GEM_STAGE_SLOTS][2048];
static unsigned char packet_pattern[sizeof packets];
static struct rpi5_gem_stage_session session;
static struct rpi5_gem_stage_request request;
static struct rpi5_gem_stage_io io;
static struct rpi5_gem_stage_observation output;
static unsigned events,currents,target,mode,revoke,corrupt;
static uint64_t ticks;
static const int owner=1,provider=2,source=3;
enum { FAIL_EVENT=1, MUTATE_SESSION, MUTATE_REQUEST, MUTATE_IO, REENTER,
       FAIL_CURRENT, MUTATE_CURRENT_SESSION, MUTATE_CURRENT_REQUEST, REENTER_CURRENT,
       EXPIRE_CURRENT, BACKWARD_CURRENT, REVOKE_CURRENT, FAIL_BEFORE_WRITE };
static void perturb(unsigned kind)
{
    if(kind==MUTATE_SESSION || kind==MUTATE_CURRENT_SESSION)session.offset^=4;
    if(kind==MUTATE_REQUEST || kind==MUTATE_CURRENT_REQUEST)request.generation++;
    if(kind==MUTATE_IO)io.context=&output;
    if(kind==REENTER || kind==REENTER_CURRENT)
        assert(rpi5_gem_ring_stage(&session,&request,&io,&output)==-2);
}
static int current(void *context,const struct rpi5_gem_stage_session *s,
    const struct rpi5_gem_stage_request *q,uint64_t *now)
{
    assert(context==&events && s==&session && q==&request);
    currents++;assert(currents==s->current_checks);
    /* Explicit model only: a genuine driver must establish these130 mapping
     * leases and quiescence via its live provider, not copy these booleans. */
    if(revoke)return -1;
    assert(q->owner==&owner && q->mapping_provider==&provider && q->capability_source==&source);
    *now=++ticks;
    if(currents==target && mode>=FAIL_CURRENT && mode<=REVOKE_CURRENT){
        perturb(mode);
        if(mode==EXPIRE_CURRENT)*now=q->deadline;
        if(mode==BACKWARD_CURRENT)*now=s->last-1;
        if(mode==REVOKE_CURRENT)revoke=1;
        if(mode==FAIL_CURRENT || mode==REVOKE_CURRENT)return -1;
    }
    return 0;
}
static int finish(void)
{
    if(events==target && mode<=REENTER){perturb(mode);if(mode==FAIL_EVENT)return -1;}
    return 0;
}
static int write32(void *context,const struct rpi5_gem_stage_session *s,unsigned ring,uint32_t offset,uint32_t value)
{
    assert(context==&events && s==&session);
    assert(rpi5_gem_ring_stage_access_allowed(s,RPI5_GEM_STAGE_WRITE,ring,offset,value));
    assert(!rpi5_gem_ring_stage_access_allowed(s,RPI5_GEM_STAGE_WRITE,ring,offset,value^1));
    events++;assert(events==s->callbacks);
    if(events==target && mode==FAIL_BEFORE_WRITE)return -1;
    *(uint32_t *)(void *)(rings[ring]+offset)=value;
    return finish();
}
static int read32(void *context,const struct rpi5_gem_stage_session *s,unsigned ring,uint32_t offset,uint32_t *value)
{
    assert(context==&events && s==&session);
    assert(rpi5_gem_ring_stage_access_allowed(s,RPI5_GEM_STAGE_READ,ring,offset,0));
    events++;assert(events==s->callbacks);
    *value=*(uint32_t *)(void *)(rings[ring]+offset);
    if(corrupt==events)*value^=1;
    return finish();
}
static int barrier(void *context,const struct rpi5_gem_stage_session *s)
{
    assert(context==&events && s==&session);
    assert(rpi5_gem_ring_stage_access_allowed(s,RPI5_GEM_STAGE_BARRIER,0,0,0));
    events++;assert(events==641 && events==s->callbacks);return finish();
}
static void init(void)
{
    memset(&session,0,sizeof session);memset(&request,0,sizeof request);
    memset(&output,0xa5,sizeof output);memset(rings,0xcc,sizeof rings);memset(packets,0x5a,sizeof packets);
    events=currents=target=mode=revoke=corrupt=0;ticks=100;
    request.owner=&owner;request.mapping_provider=&provider;request.capability_source=&source;
    request.generation=7;request.not_before=100;request.deadline=10000;
    const uint32_t cap[]={0x00070109,0x08508513,0x6eb13fff,0x502e5b45,0x08820000,0,0x24444444,0};
    memcpy(request.raw_capabilities,cap,sizeof cap);
    request.descriptor_memory=RPI5_GEM_MEMORY_COHERENT;request.packet_granule=256;
    for(unsigned r=0;r<2;r++){
        request.ring[r]=(struct rpi5_gem_stage_span){rings[r],((uint64_t)r+1)*0x100000000ULL+0x10000,1280};
        for(unsigned i=0;i<RPI5_GEM_STAGE_SLOTS;i++)request.packet[r][i]=(struct rpi5_gem_stage_span){
            packets[r][i],0x300000000ULL+(r*RPI5_GEM_STAGE_SLOTS+i)*0x1000,2048};
    }
    io=(struct rpi5_gem_stage_io){&events,current,write32,read32,barrier};
}
static void unchanged(void)
{
    unsigned char expected[sizeof output];memset(expected,0xa5,sizeof expected);
    assert(!memcmp(&output,expected,sizeof output));
    for(unsigned r=0;r<2;r++){
        for(unsigned i=1280;i<1536;i++)assert(rings[r][i]==0xcc);
    }
    assert(!memcmp(packets,packet_pattern,sizeof packets));
}
static void failed(void)
{
    assert(rpi5_gem_ring_stage(&session,&request,&io,&output)<0);
    assert(session.state==RPI5_GEM_STAGE_QUARANTINED && !session.busy && !session.pending);
    unchanged();unsigned oldevents=events,oldcurrents=currents;
    assert(rpi5_gem_ring_stage(&session,&request,&io,&output)==-2);
    assert(events==oldevents && currents==oldcurrents);
}
static void invalid(void)
{
    assert(rpi5_gem_ring_stage(&session,&request,&io,&output)==-1);
    assert(!events && !currents && session.state==RPI5_GEM_STAGE_UNUSED);unchanged();
}
static void success(void)
{
    assert(!rpi5_gem_ring_stage(&session,&request,&io,&output));
    assert(session.state==RPI5_GEM_STAGE_HELD && !session.pending && !session.busy);
    assert(events==1281 && currents==2564 && output.callbacks==1281 && output.current_checks==2564);
    assert(output.writes==640 && output.reads==640 && session.writes_attempted==640);
    assert(output.cpu_owned_descriptors==160 && output.ring_bytes==1280 && output.prefetch_bytes==256);
    assert(output.real_slots==64 && output.descriptor_bytes==16 && output.generation==7);
    for(unsigned r=0;r<2;r++){
        assert(output.ring_dma[r]==request.ring[r].dma);
        for(unsigned i=0;i<80;i++){
            const struct rpi5_gem_descriptor *d=(const void *)(rings[r]+16*i);
            uint64_t expected=i<64?request.packet[r][i].dma:0;
            assert(d->address_high==(expected>>32) && d->reserved==0);
            if(!r){assert(d->address==(uint32_t)expected);assert(d->control==(0x80000000u|(i==63?0x40000000u:0)));}
            else {assert(d->address==((uint32_t)expected|1u|(i==63?2u:0)));assert(d->control==0);}
        }
        for(unsigned i=1280;i<1536;i++)assert(rings[r][i]==0xcc);
    }
    assert(!memcmp(packets,packet_pattern,sizeof packets));
    assert(!rpi5_gem_ring_stage_access_allowed(&session,RPI5_GEM_STAGE_WRITE,0,0,0));
    assert(rpi5_gem_ring_stage(&session,&request,&io,&output)==-2);
}
int main(void)
{
    memset(packet_pattern,0x5a,sizeof packet_pattern);
    init();success();init();request.descriptor_memory=RPI5_GEM_MEMORY_UNCACHED;success();
    for(unsigned granule=64;granule<=256;granule*=2){init();request.packet_granule=granule;success();}
    /* Every RAM-access/barrier failure and fresh-provider checkpoint; callback
     * mutation/reentry/clock faults cover phase/ring/wrap/tail boundaries.
     * All are actual core calls, not a state shortcut. */
    unsigned event_cases=0,current_cases=0;
    for(unsigned pos=1;pos<=1281;pos++){
        init();mode=FAIL_EVENT;target=pos;failed();assert(events==pos);event_cases++;
    }
    const unsigned event_edges[]={1,2,3,4,252,253,254,255,256,257,319,320,321,572,576,577,639,640,641,642,897,962,1217,1280,1281};
    for(unsigned kind=MUTATE_SESSION;kind<=REENTER;kind++)for(unsigned i=0;i<sizeof event_edges/sizeof *event_edges;i++){
        init();mode=kind;target=event_edges[i];failed();assert(events==target);event_cases++;
    }
    for(unsigned pos=1;pos<=640;pos++){init();mode=FAIL_BEFORE_WRITE;target=pos;failed();
        assert(session.writes_attempted==pos && session.writes_completed==pos-1);event_cases++;}
    for(unsigned pos=1;pos<=2564;pos++){
        init();mode=FAIL_CURRENT;target=pos;failed();assert(currents==pos);current_cases++;
    }
    const unsigned current_edges[]={1,2,3,4,5,512,513,514,641,642,643,1025,1280,1281,1282,1283,1284,1537,1793,2050,2305,2562,2563,2564};
    for(unsigned kind=MUTATE_CURRENT_SESSION;kind<=REVOKE_CURRENT;kind++)for(unsigned i=0;i<sizeof current_edges/sizeof *current_edges;i++){
        init();mode=kind;target=current_edges[i];failed();assert(currents==target);current_cases++;
    }
    for(unsigned pos=642;pos<=1281;pos++){init();corrupt=pos;failed();assert(session.error==-6);event_cases++;}
    /* Actual partial side-effect vs completed-write accounting. */
    init();mode=FAIL_EVENT;target=1;failed();assert(session.writes_attempted==1 && session.writes_completed==0);
    assert(*(uint32_t *)(void *)(rings[0]+8)==3);
    init();mode=FAIL_CURRENT;target=3;failed();assert(session.writes_attempted==1 && session.writes_completed==0);
    /* Immutable input/provenance/geometry gates; no callback before rejection. */
    init();request.generation=0;invalid();init();request.owner=0;invalid();
    init();request.mapping_provider=0;invalid();init();request.capability_source=0;invalid();
    init();request.deadline=100;invalid();init();request.descriptor_memory=RPI5_GEM_MEMORY_UNPROVEN;invalid();
    init();request.packet_granule=32;invalid();init();request.packet_granule=129;invalid();
    init();request.packet_granule=512;invalid();
    for(unsigned kind=0;kind<2;kind++){
        init();request.ring[kind].bytes=64;invalid();
        init();request.ring[kind].dma=0x1ffffffc0ULL;invalid(); /* entire prefetch tail crosses4GiB */
        init();request.ring[kind].dma=UINT64_MAX-63;invalid();
        init();request.ring[kind].cpu=(void *)(UINTPTR_MAX-63);invalid();
        init();request.ring[kind].cpu=(void *)&output;invalid();
        init();request.ring[kind].dma++;invalid();
    }
    for(unsigned r=0;r<2;r++)for(unsigned i=0;i<RPI5_GEM_STAGE_SLOTS;i++){
        init();request.packet[r][i].bytes=2047;invalid();
        init();request.packet[r][i].dma++;invalid();
        init();request.packet[r][i].dma=UINT64_MAX-255;invalid();
        init();request.packet[r][i].cpu=(void *)(UINTPTR_MAX-255);invalid();
    }
    init();request.packet[1][3].dma=request.packet[0][0].dma;invalid();
    init();request.packet[1][3].cpu=request.packet[0][0].cpu;invalid();
    init();request.ring[1].dma=request.ring[0].dma;invalid();
    init();request.ring[1].cpu=request.ring[0].cpu;invalid();
    init();request.ring[0].dma=request.packet[0][0].dma;invalid();
    init();request.ring[0].cpu=request.packet[0][0].cpu;invalid();
    const unsigned ci[]={0,1,2,4,6,7},bits[]={0,25,20,23,8,26};
    for(unsigned i=0;i<6;i++){init();request.raw_capabilities[ci[i]]^=1u<<bits[i];invalid();}
    init();request.raw_capabilities[4]|=2;invalid();
    init();request.raw_capabilities[6]^=1u<<12;invalid();
    init();io.current=0;invalid();init();io.read32=0;invalid();init();io.write32=0;invalid();init();io.barrier=0;invalid();
    init();struct rpi5_gem_stage_session copied=session;copied.self=&session;
    assert(rpi5_gem_ring_stage(&copied,&request,&io,&output)==-1 && !events);
    printf("GEM_RING_STAGE_PASS events=%u owners=%u writes=640 reads=640 held=160 NO_DMA_PROOF\n",event_cases,current_cases);
    return 0;
}
