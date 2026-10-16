/* SPDX-License-Identifier: BSD-2-Clause */
/* Private successor only: stop after every allocating/virtual lifecycle
 * boundary if a reentrant call or context change revoked this operation. */
bool BCM2712GEMDMARings::prepare()
{
    if (state_==Preparing || state_==Checking || state_==Discarding || state_==Staging) {
        state_=Quarantined;return false;
    }
    if (state_!=Empty || !context() || PAGE_SIZE!=Alignment) return false;
    state_=Preparing;thread_=(void *)current_thread();
    auto active=[&]() {return state_==Preparing && context();};
    fdt_=rpi5_copy_boot_firmware_fdt();
    if (!active()) goto quarantine;
    if (!fdt_) goto reject;
    {
        const void *bytes=fdt_->getBytesNoCopy();
        if (!active()) goto quarantine;
        unsigned length=fdt_->getLength();
        if (!active()) goto quarantine;
        struct rpi5_pcie_profile profile={};
        if (!bytes || rpi5_pcie_profile_decode(bytes,length,&binding_,&profile)) goto reject;
        if (!active()) goto quarantine;
        if (rpi5_fdt_memory(bytes,length,&ram_)) goto reject;
        if (!active()) goto quarantine;
        if (rpi5_fdt_reservation_plan(bytes,length,&reservations_)) goto reject;
        if (!active()) goto quarantine;
        if (rpi5_pcie_windows_plan(&binding_,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES,&expected_)) goto reject;
        int rc=rpi5_fdt_initrd(bytes,length,&initrd_);
        if (rc!=0 && rc!=1) goto reject;
        hasInitrd_=rc==0;
        resolved_=rpi5_boot_reservation_record();
        if (!active()) goto quarantine;
        if (!resolved_ || rpi5_reservation_record_validate_fdt(resolved_,bytes,length)) goto reject;
    }
    if (!active()) goto quarantine;
    buffer_=IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task,
        kIODirectionInOut | kIOMemoryPhysicallyContiguous | kIOMemoryMapperNone |
        kIOMapWriteCombineCache,AllocationBytes,Alignment);
    if (!active()) goto quarantine;
    if (!buffer_) goto reject;
    command_=IODMACommand::withSpecification(kIODMACommandOutputHost64,64,AllocationBytes,
        IODMACommand::kUnmapped,AllocationBytes,(UInt32)Alignment,nullptr,nullptr);
    if (!active()) goto quarantine;
    if (!command_) goto reject;
    {
        auto rc=command_->setMemoryDescriptor(buffer_,false);
        if (!active()) goto quarantine;
        if (rc!=kIOReturnSuccess) goto reject;
        rc=command_->prepare(0,AllocationBytes);
        if (rc!=kIOReturnSuccess) goto quarantine; /* fActive may be nonzero. */
        commandPrepared_=true;
        if (!active()) goto quarantine;
        IOByteCount bytes=0;
        physical_=buffer_->getPhysicalSegment(0,&bytes,kIOMemoryMapperNone);
        if (!active()) goto quarantine;
        cpu_=(uint64_t)buffer_->getBytesNoCopy();
        if (!active()) goto quarantine;
        if (!physical_ || bytes!=AllocationBytes) goto reject;
        UInt64 offset=0;UInt32 count=1;IODMACommand::Segment64 segment={};
        rc=command_->gen64IOVMSegments(&offset,&segment,&count);
        if (!active()) goto quarantine;
        if (rc!=kIOReturnSuccess || count!=1 || offset!=AllocationBytes ||
            segment.fIOVMAddr!=physical_ || segment.fLength!=AllocationBytes || !mapping()) goto reject;
        struct rpi5_gem_dma_route geometry;
        if (!route(&expected_,&geometry)) goto reject;
    }
    if (!active()) goto quarantine;
    state_=Prepared;return true;
reject:
    if (!active()) goto quarantine;
    state_=Rejected;return false;
quarantine:
    state_=Quarantined;return false;
}
bool BCM2712GEMDMARings::discardBeforeAdmission()
{
    if (state_==Preparing || state_==Checking || state_==Discarding || state_==Staging) {
        state_=Quarantined;return false;
    }
    if ((state_!=Prepared && state_!=Rejected) || !context()) return false;
    state_=Discarding;
    auto active=[&]() {return state_==Discarding && context();};
    if (commandPrepared_) {
        auto rc=command_->complete();
        if (rc==kIOReturnSuccess) commandPrepared_=false;
        if (rc!=kIOReturnSuccess || !active()) goto quarantine;
    }
    if (command_) {
        auto rc=command_->clearMemoryDescriptor(false);
        if (rc!=kIOReturnSuccess || !active()) goto quarantine;
        auto *released=command_;command_=nullptr;
        released->release();
        if (!active()) goto quarantine;
    }
    if (buffer_) {
        auto *released=buffer_;buffer_=nullptr;
        released->release();
        if (!active()) goto quarantine;
    }
    if (fdt_) {
        auto *released=fdt_;fdt_=nullptr;
        released->release();
        if (!active()) goto quarantine;
    }
    state_=Discarded;return true;
quarantine:
    state_=Quarantined;return false;
}
