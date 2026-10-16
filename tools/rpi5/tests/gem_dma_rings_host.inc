/* SPDX-License-Identifier: BSD-2-Clause */
static unsigned ring_calls,ring_fail,ring_hook_at;
static void (*ring_hook)();
static uint64_t ring_now;
static rpi5_gem_cap_session caps;
static rpi5_gem_identify identity;
static rpi5_rp1_decode_cycle decode;
static rpi5_rp1_assignment assignment;
static BCM2712GEMDMALive live;
static int ring_owner(void *,const BCM2712GEMDMARings *p,const rpi5_gem_cap_session *c,uint64_t *now)
{
    assert(p==active && c==&caps);ring_calls++;
    if(ring_hook && ring_calls==ring_hook_at)ring_hook();
    *now=++ring_now;return ring_calls==ring_fail?-1:0;
}
static void ring_setup()
{
    caps={};identity={};decode={};assignment={};ring_calls=ring_fail=ring_hook_at=0;ring_hook=nullptr;ring_now=100;
    caps.state=RPI5_GEM_CAP_COMPLETE;caps.self=&caps;caps.identity=&identity;caps.reads=16;
    const uint32_t words[]={0x00070109,0x08508513,0x6eb13fff,0x502e5b45,0x08820000,0,0x24444444,0};
    for(unsigned i=0;i<8;i++)caps.words[0][i]=caps.words[1][i]=words[i];
    identity.stage=RPI5_GEM_COMPLETE;identity.reads=32;identity.clocks_ready=1;identity.decode=&decode;
    identity.mid[0]=identity.mid[1]=words[0];
    decode.state=RPI5_RP1_DECODE_MAPPED;decode.mapped=3;decode.assignment=&assignment;
    assignment.state=RPI5_RP1_ASSIGN_ASSIGNED;assignment.assigned_mask=7;
    /* Deliberately nonzero padding proves the exact-object snapshot contract,
     * rather than relying on optimizer-dependent aggregate assignment. */
    static_assert(offsetof(rpi5_gem_cap_session,self)>sizeof caps.state,"Expected native ABI padding");
    memset((unsigned char *)&caps+sizeof caps.state,0x39,offsetof(rpi5_gem_cap_session,self)-sizeof caps.state);
    memset((unsigned char *)&identity+sizeof identity.stage,0x7a,offsetof(rpi5_gem_identify,decode)-sizeof identity.stage);
    memset((unsigned char *)&decode+sizeof decode.state,0xb5,offsetof(rpi5_rp1_decode_cycle,assignment)-sizeof decode.state);
    memset((unsigned char *)&assignment+sizeof assignment.state,0xd2,offsetof(rpi5_rp1_assignment,config)-sizeof assignment.state);
    live={&model,&model,&caps,17,100,500100,ring_owner};
    memset(allocation,0xa5,sizeof allocation);
}
static void ring_reenter(){rpi5_gem_stage_observation o;assert(!active->stageCPUOwned(&live,&o));}
static void ring_mutate(){caps.words[0][1]^=1;}
static void ring_source_mutate(){live.generation++;}
static void ring_padding_mutate(){((unsigned char *)&caps)[sizeof caps.state]^=1;}
int main()
{
    rpi5_pcie_windows w;rpi5_pcie_released_windows r;setup(w,r);
    BCM2712GEMDMARings good;active=&good;assert(good.prepare());unsigned prep=model.calls;
    struct rpi5_gem_dma_route geometry;assert(good.qualify(&r,&geometry));
    unsigned qualification=model.calls;assert(model.reads==90);
    ring_setup();rpi5_gem_stage_observation out,before;
    assert(good.stageCPUOwned(&live,&out));unsigned total=ring_calls;
    assert(good.state()==BCM2712GEMDMARings::RingsHeld && total==2564);
    assert(!good.discardBeforeAdmission() && !good.stageCPUOwned(&live,&out));
    assert(model.reads==90 && !model.releases && !model.complete);
    /* Full ring writes land in the real retained mock allocation. No packet
     * bytes or gaps touched, and both rings retain CPU ownership. */
    for(unsigned ring=0;ring<2;ring++) {
        const auto *p=(const uint32_t *)(allocation+ring*0x4000);
        for(unsigned slot=0;slot<80;slot++) {
            assert((p[slot*4+(ring?0:1)]&(ring?1u:0x80000000u))!=0);
            assert(p[slot*4+3]==0);
        }
        for(unsigned n=1280;n<0x4000;n++)assert(allocation[ring*0x4000+n]==0xa5);
    }
    for(unsigned n=0x8000;n<sizeof allocation;n++)assert(allocation[n]==0xa5);
    unsigned faults=0;
    /* Every genuine allocating/virtual/cache boundary is modelled as an
     * event. Reentry and context revocation must stop at that boundary, not
     * merely prevent eventual publication after more allocations/releases. */
    for(auto hook:{reenter,change_thread})for(unsigned at=1;at<=prep;at++) {
        setup(w,r);BCM2712GEMDMARings m;active=&m;model.hook=hook;model.trigger=at;
        assert(!m.prepare());assert(m.state()==BCM2712GEMDMARings::Quarantined);
        assert(model.calls==at && !model.reads && !model.releases && !model.complete);
        assert(!m.discardBeforeAdmission());faults++;
    }
    for(unsigned at=1;at<=5;at++)for(auto hook:{reenter,change_thread}) {
        setup(w,r);BCM2712GEMDMARings m;active=&m;assert(m.prepare());unsigned start=model.calls;
        model.hook=hook;model.trigger=start+at;
        assert(!m.discardBeforeAdmission());assert(m.state()==BCM2712GEMDMARings::Quarantined);
        assert(model.calls==start+at);assert(model.releases==(at>2?at-2:0));
        assert(!m.discardBeforeAdmission());faults++;
    }
    for(unsigned at:{1u,2u,3u,256u,512u,1024u,1282u,2048u,2563u,2564u}) {
        setup(w,r);BCM2712GEMDMARings m;active=&m;assert(m.prepare());assert(m.qualify(&r,&geometry));ring_setup();ring_fail=at;
        memset(&out,0xa5,sizeof out);memcpy(&before,&out,sizeof out);assert(!m.stageCPUOwned(&live,&out));
        assert(m.state()==BCM2712GEMDMARings::Quarantined && ring_calls==at && !memcmp(&out,&before,sizeof out));
        assert(!m.discardBeforeAdmission() && !model.releases && model.reads==90);faults++;
    }
    for(auto hook:{ring_reenter,ring_mutate,ring_source_mutate,ring_padding_mutate,change_thread})for(unsigned at:{1u,1282u,2564u}) {
        setup(w,r);BCM2712GEMDMARings m;active=&m;assert(m.prepare());assert(m.qualify(&r,&geometry));ring_setup();ring_hook=hook;ring_hook_at=at;
        memset(&out,0xa5,sizeof out);memcpy(&before,&out,sizeof out);assert(!m.stageCPUOwned(&live,&out));
        assert(m.state()==BCM2712GEMDMARings::Quarantined && ring_calls==at && !memcmp(&out,&before,sizeof out));faults++;
    }
    setup(w,r);BCM2712GEMDMARings discard;active=&discard;assert(discard.prepare());assert(discard.discardBeforeAdmission());
    assert(model.complete==1 && model.clear==1 && model.releases==3);
    printf("DMA_RINGS_REAL_METHODS_PASS lifecycle_and_owner_faults=%u prep=%u qualification=%u ring_checkpoints=%u NO_HARDWARE_PROOF\n",faults,prep,qualification,total);
}
