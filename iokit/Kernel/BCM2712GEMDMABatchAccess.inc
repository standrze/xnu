/* SPDX-License-Identifier: BSD-2-Clause */
/* Fixed private CPU-RAM batches, never Device accesses or queue publication. */
int BCM2712GEMDMABatch::ringWrite(void *context,const struct rpi5_gem_stage_session *s,
    unsigned ring,uint32_t offset,const uint32_t values[16])
{
    auto *p=(BCM2712GEMDMABatch *)context;
    if (!p || s!=&p->ringSession_ || !p->ringIntact() ||
        !rpi5_gem_ring_batch_access_allowed(s,RPI5_GEM_STAGE_WRITE,ring,offset) ||
        !rpi5_gem_ring_batch_values(s,&p->ringRequest_,ring,offset,values)) return -1;
    auto *dst=(volatile uint32_t *)(uintptr_t)(p->cpu_+ring*Alignment+offset);
    /* Four complete16-byte descriptors; no callbacks or external calls may
     * occur inside this bounded64-byte body. CPU ownership is never released.
     * A synchronous exception is terminal; attempted batch is not rolled back. */
    for(unsigned i=0;i<16;i+=4) {
        dst[i+2]=values[i+2];dst[i+3]=values[i+3];
        dst[i+1]=values[i+1];dst[i]=values[i];
    }
    return 0;
}
int BCM2712GEMDMABatch::ringRead(void *context,const struct rpi5_gem_stage_session *s,
    unsigned ring,uint32_t offset,uint32_t values[16])
{
    auto *p=(BCM2712GEMDMABatch *)context;
    if (!p || s!=&p->ringSession_ || !values || !p->ringIntact() ||
        !rpi5_gem_ring_batch_access_allowed(s,RPI5_GEM_STAGE_READ,ring,offset)) return -1;
    auto *src=(volatile const uint32_t *)(uintptr_t)(p->cpu_+ring*Alignment+offset);
    for(unsigned i=0;i<16;i++)values[i]=src[i];
    return 0;
}
bool BCM2712GEMDMABatch::disabled(const struct rpi5_pcie_window_plan *plan) const
{
    if (!plan) return false;
    /* All inbound RAM/MIP/device slots are independently disabled in this
     * CPU-owned profile. Validate every original FDT field after restoring
     * only the three known size encodings in this local value copy. Geometry
     * is therefore a CANDIDATE address, not active inbound DMA reachability. */
    struct rpi5_pcie_window_plan encoded=*plan;
    for(unsigned i=0;i<3;i++) {
        if (encoded.inbound[i].bar_lo&31) return false;
        encoded.inbound[i].bar_lo|=expected_.inbound[i].bar_lo&31;
    }
    struct rpi5_gem_dma_route ignored;
    return route(&encoded,&ignored);
}
