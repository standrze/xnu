/* SPDX-License-Identifier: BSD-2-Clause */
/* Same physical/CPU-cache qualification as the frozen prototype, with explicit
 * revocation checks after each virtual boundary. No authority is cached. */
bool BCM2712GEMDMARings::mapping() const
{
    const auto state=state_;
    auto intact=[&]() {
        return state_==state && (state==Preparing || state==Checking || state==Staging) &&
            thread_==(void *)current_thread() && !ml_at_interrupt_context();
    };
    if (!intact() || !resolved_ || resolved_!=rpi5_boot_reservation_record() ||
        !buffer_ || !command_ || !commandPrepared_ || !cpu_ || !physical_ ||
        ((cpu_|physical_)&(Alignment-1)) || cpu_>UINT64_MAX-AllocationBytes ||
        physical_>UINT64_MAX-AllocationBytes) return false;
    auto length=buffer_->getLength();
    if (!intact() || length!=AllocationBytes) return false;
    auto capacity=buffer_->getCapacity();
    if (!intact() || capacity!=AllocationBytes) return false;
    auto bytesVA=buffer_->getBytesNoCopy();
    if (!intact() || (uint64_t)bytesVA!=cpu_) return false;
    auto type=rpi5_physical_memory_type(physical_,physical_+AllocationBytes);
    if (!intact() || type!=1) return false;
    IOByteCount bytes=0;
    auto pa=buffer_->getPhysicalSegment(0,&bytes,kIOMemoryMapperNone);
    if (!intact() || pa!=physical_ || bytes!=AllocationBytes) return false;
    for (uint64_t offset=0;offset<AllocationBytes;offset+=Alignment) {
        pa=physical_+offset;
        auto attr=pmap_cache_attributes((ppnum_t)(pa>>PAGE_SHIFT));
        if (!intact() || (attr&VM_WIMG_MASK)!=VM_WIMG_WCOMB) return false;
        auto valid=translated_nc(cpu_+offset,pa);
        if (!intact() || !valid) return false;
        auto alias=ml_static_ptovirt(pa);
        if (!intact()) return false;
        valid=translated_nc(alias,pa);
        if (!intact() || !valid) return false;
    }
    return intact();
}
