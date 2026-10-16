/* SPDX-License-Identifier: BSD-2-Clause */
/* Included only in the separately emitted ring-owning provider TU. All writes
 * below are within the genuine retained Apple allocation, never device MMIO. */
static bool rings_equal(const void *a,const void *b,size_t n)
{const auto *x=(const unsigned char *)a,*y=(const unsigned char *)b;for(size_t i=0;i<n;i++)if(x[i]!=y[i])return false;return true;}
template<class T> static void rings_snapshot(T &to,const T &from)
{
    static_assert(__is_trivially_copyable(T),"Only immutable C value representations are snapshotted");
    /* ringIntact compares the complete object representation. C++ memberwise
     * assignment need not copy padding, so preserve every source byte. */
    auto *x=(unsigned char *)&to;const auto *y=(const unsigned char *)&from;
    for(size_t i=0;i<sizeof(T);i++)x[i]=y[i];
}
static bool rings_disjoint(const void *a,size_t an,const void *b,size_t bn)
{
    uint64_t x=(uintptr_t)a,y=(uintptr_t)b;
    return x && y && an && bn && x<=UINT64_MAX-an && y<=UINT64_MAX-bn &&
        (x+an<=y || y+bn<=x);
}
bool BCM2712GEMDMARings::ringIntact() const
{
    if (state_!=Staging || !liveSource_ || !live_.owner || !live_.context || !live_.current ||
        !live_.generation || !live_.capabilities || thread_!=(void *)current_thread() || ml_at_interrupt_context() ||
        !rings_equal(liveSource_,&live_,sizeof live_) ||
        !rings_equal(live_.capabilities,&capSnapshot_,sizeof capSnapshot_) ||
        !capSnapshot_.identity || !rings_equal(capSnapshot_.identity,&identitySnapshot_,sizeof identitySnapshot_)) return false;
    const auto *d=identitySnapshot_.decode;
    return d && d==decodeSource_ && rings_equal(d,&decodeSnapshot_,sizeof decodeSnapshot_) &&
        d->assignment && d->assignment==assignmentSource_ &&
        rings_equal(d->assignment,&assignmentSnapshot_,sizeof assignmentSnapshot_);
}
int BCM2712GEMDMARings::ringCurrent(void *context,const struct rpi5_gem_stage_session *s,
    const struct rpi5_gem_stage_request *q,uint64_t *now)
{
    auto *p=(BCM2712GEMDMARings *)context;
    if (!p || s!=&p->ringSession_ || q!=&p->ringRequest_ || !now || !p->ringIntact() ||
        !p->mapping()) return -1;
    /* Mapping checks are bounded CPU-only observations of privately retained
     * storage. The real owner runs LAST, returning a fresh time before a RAM
     * access, not a timestamp captured before those checks. No authority cache. */
    uint64_t fresh=0;
    if (p->live_.current(p->live_.context,p,p->live_.capabilities,&fresh) || !p->ringIntact()) return -1;
    *now=fresh;return 0;
}
int BCM2712GEMDMARings::ringWrite(void *context,const struct rpi5_gem_stage_session *s,
    unsigned ring,uint32_t offset,uint32_t value)
{
    auto *p=(BCM2712GEMDMARings *)context;
    if (!p || s!=&p->ringSession_ || !p->ringIntact() ||
        !rpi5_gem_ring_stage_access_allowed(s,RPI5_GEM_STAGE_WRITE,ring,offset,value)) return -1;
    *(volatile uint32_t *)(uintptr_t)(p->cpu_+ring*Alignment+offset)=value;
    return 0;
}
int BCM2712GEMDMARings::ringRead(void *context,const struct rpi5_gem_stage_session *s,
    unsigned ring,uint32_t offset,uint32_t *value)
{
    auto *p=(BCM2712GEMDMARings *)context;
    if (!p || s!=&p->ringSession_ || !value || !p->ringIntact() ||
        !rpi5_gem_ring_stage_access_allowed(s,RPI5_GEM_STAGE_READ,ring,offset,0)) return -1;
    *value=*(volatile const uint32_t *)(uintptr_t)(p->cpu_+ring*Alignment+offset);
    return 0;
}
int BCM2712GEMDMARings::ringBarrier(void *context,const struct rpi5_gem_stage_session *s)
{
    auto *p=(BCM2712GEMDMARings *)context;
    if (!p || s!=&p->ringSession_ || !p->ringIntact() ||
        !rpi5_gem_ring_stage_access_allowed(s,RPI5_GEM_STAGE_BARRIER,0,0,0)) return -1;
    /* Normal-NC retained descriptor RAM, full outer-shareable completion.
     * No cache-line cleaning and no packet or ownership publication to GEM. */
    __asm__ volatile("dsb osh" ::: "memory");
    return 0;
}
bool BCM2712GEMDMARings::stageCPUOwned(const struct BCM2712GEMDMALive *live,
    struct rpi5_gem_stage_observation *out)
{
    if (state_==Staging || state_==Preparing || state_==Checking || state_==Discarding) {
        state_=Quarantined;return false;
    }
    if (state_!=Held || !rings_disjoint(this,sizeof *this,live,sizeof *live) ||
        !rings_disjoint(this,sizeof *this,out,sizeof *out) ||
        !rings_disjoint(live,sizeof *live,out,sizeof *out) || !live->capabilities || !live->current || !live->context ||
        !live->owner || !live->generation || live->not_before>=live->deadline ||
        live->deadline-live->not_before>StageMaximumUS || thread_!=(void *)current_thread() ||
        ml_at_interrupt_context()) return false;
    /* Storage is already admitted/retained. A failed capability/source check
     * quarantines it; there is no recovery through reinitialization or retry. */
    state_=Staging;liveSource_=live;rings_snapshot(live_,*live);rings_snapshot(capSnapshot_,*live->capabilities);
    if (capSnapshot_.state!=RPI5_GEM_CAP_COMPLETE || capSnapshot_.self!=live->capabilities ||
        capSnapshot_.busy || capSnapshot_.pending || capSnapshot_.reads!=16 || !capSnapshot_.identity ||
        !rings_equal(capSnapshot_.words[0],capSnapshot_.words[1],sizeof capSnapshot_.words[0])) goto failed;
    rings_snapshot(identitySnapshot_,*capSnapshot_.identity);
    if (identitySnapshot_.stage!=RPI5_GEM_COMPLETE || identitySnapshot_.reads!=32 ||
        !identitySnapshot_.clocks_ready || identitySnapshot_.pending || !identitySnapshot_.decode ||
        identitySnapshot_.mid[0]!=capSnapshot_.words[0][0] || identitySnapshot_.mid[1]!=identitySnapshot_.mid[0] ||
        !rings_equal(identitySnapshot_.before,identitySnapshot_.after,sizeof identitySnapshot_.before)) goto failed;
    decodeSource_=identitySnapshot_.decode;rings_snapshot(decodeSnapshot_,*decodeSource_);
    if (decodeSnapshot_.state!=RPI5_RP1_DECODE_MAPPED || decodeSnapshot_.mapped!=3 || decodeSnapshot_.unmapped ||
        decodeSnapshot_.pending_map || decodeSnapshot_.pending_write || !decodeSnapshot_.assignment) goto failed;
    assignmentSource_=decodeSnapshot_.assignment;rings_snapshot(assignmentSnapshot_,*assignmentSource_);
    if (assignmentSnapshot_.state!=RPI5_RP1_ASSIGN_ASSIGNED || assignmentSnapshot_.pending_write ||
        assignmentSnapshot_.restored_mask || assignmentSnapshot_.assigned_mask!=7) goto failed;
    {
        struct rpi5_gem_dma_route geometry;
        if (!mapping() || !route(&expected_,&geometry)) goto failed;
        ringRequest_.owner=live_.owner;ringRequest_.mapping_provider=this;
        ringRequest_.capability_source=live_.capabilities;ringRequest_.generation=live_.generation;
        ringRequest_.not_before=live_.not_before;ringRequest_.deadline=live_.deadline;
        ringRequest_.descriptor_memory=RPI5_GEM_MEMORY_UNCACHED;ringRequest_.packet_granule=256;
        for(unsigned i=0;i<8;i++)ringRequest_.raw_capabilities[i]=capSnapshot_.words[0][i];
        for(unsigned r=0;r<2;r++) {
            ringRequest_.ring[r]={(void *)(uintptr_t)(cpu_+r*Alignment),geometry.rp1+r*Alignment,RPI5_GEM_STAGE_RING_BYTES};
            for(unsigned i=0;i<RPI5_GEM_STAGE_SLOTS;i++) {
                uint64_t offset=2*Alignment+(r*RPI5_GEM_STAGE_SLOTS+i)*RPI5_GEM_BUFFER_BYTES;
                ringRequest_.packet[r][i]={(void *)(uintptr_t)(cpu_+offset),geometry.rp1+offset,RPI5_GEM_BUFFER_BYTES};
            }
        }
        ringIO_={this,ringCurrent,ringWrite,ringRead,ringBarrier};
        struct rpi5_gem_stage_observation result;
        if (rpi5_gem_ring_stage(&ringSession_,&ringRequest_,&ringIO_,&result) || !ringIntact()) goto failed;
        state_=RingsHeld;*out=result;return true;
    }
failed:
    state_=Quarantined;return false;
}
