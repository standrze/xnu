/* SPDX-License-Identifier: BSD-2-Clause */
#if !defined(ARM64_BOARD_CONFIG_BCM2712) || !DEVELOPMENT || !RPI5_FIRMWARE_FDT_HANDOFF
#error "GEM memory provider requires the separate BCM2712 DEVELOPMENT build"
#endif
#include "BCM2712GEMDMAMemory.h"
#include "BCM2712FirmwareFDT.h"
#include <machine/machine_routines.h>
#include <kern/thread.h>
#include <kern/task.h>
#include <vm/pmap.h>
#include <arm64/proc_reg.h>
#include <vm/memory_types.h>
extern "C" unsigned rpi5_physical_memory_type(uint64_t, uint64_t);
extern "C" int get_preemption_level(void);
/* Genuine private XNU symbol, declared in osfmk/vm/pmap.h's MACH_KERNEL guard.
 * This IOKit TU deliberately does not redefine MACH_KERNEL for all headers. */
extern "C" unsigned pmap_cache_attributes(ppnum_t);

/* AT has no memory access or mapping write. Preserve PAR and interrupt state;
 * local masking excludes migration/PAR clobber during the two instructions.
 * A76/48-bit PAR encoding only, verified actual EL1 read AND write translations.
 * ATTR=0x44 is Normal inner/outer NC, not Device. No CPU-PA/bus alias guess. */
static bool translated_nc(uint64_t va, uint64_t physical,
    uint64_t *readProof=nullptr, uint64_t *writeProof=nullptr)
{
    uint64_t saved, read, write;
    boolean_t interrupts=ml_set_interrupts_enabled(FALSE);
    __asm__ volatile("mrs %0, par_el1\n\tat s1e1r, %3\n\tisb\n\tmrs %1, par_el1\n\t"
        "at s1e1w, %3\n\tisb\n\tmrs %2, par_el1\n\tmsr par_el1, %0\n\tisb"
        : "=&r"(saved), "=&r"(read), "=&r"(write) : "r"(va) : "memory");
    ml_set_interrupts_enabled(interrupts);
    if (readProof) *readProof=read;
    if (writeProof) *writeProof=write;
    constexpr uint64_t mask=UINT64_C(0x0000fffffffff000);
    return !(read&PAR_F) && !(write&PAR_F) && (read>>56)==0x44 && (write>>56)==0x44 &&
        (read&mask)==(physical&mask) && (write&mask)==(physical&mask);
}
bool BCM2712GEMDMAMemory::context() const
{
    return !ml_at_interrupt_context() && ml_get_interrupts_enabled() &&
        get_preemption_level()==0 && (!thread_ || thread_==(void *)current_thread());
}
bool BCM2712GEMDMAMemory::mapping(uint64_t *normalNCPageBitmap,
    struct rpi5_gem_full_provider_page *pages) const
{
    mappingReason_=1;mappingPage_=0;mappingAttribute_=0;mappingPhysical_=0;
    mappingRetainedReadPAR_=mappingRetainedWritePAR_=0;
    mappingStaticReadPAR_=mappingStaticWritePAR_=0;
    auto fail=[&](uint32_t reason,uint32_t page,uint32_t attribute,uint64_t physical,
        uint64_t retainedRead,uint64_t retainedWrite,uint64_t staticRead,uint64_t staticWrite) {
        mappingReason_=reason;mappingPage_=page;mappingAttribute_=attribute;
        mappingPhysical_=physical;mappingRetainedReadPAR_=retainedRead;
        mappingRetainedWritePAR_=retainedWrite;mappingStaticReadPAR_=staticRead;
        mappingStaticWritePAR_=staticWrite;return false;
    };
    if (!resolved_ || resolved_!=rpi5_boot_reservation_record() ||
        !buffer_ || !command_ || !commandPrepared_ || !cpu_ || !physical_ ||
        buffer_->getLength()!=AllocationBytes || buffer_->getCapacity()!=AllocationBytes ||
        (uint64_t)buffer_->getBytesNoCopy()!=cpu_ ||
        ((cpu_|physical_)&(Alignment-1)) || cpu_>UINT64_MAX-AllocationBytes ||
        physical_>UINT64_MAX-AllocationBytes ||
        rpi5_physical_memory_type(physical_,physical_+AllocationBytes)!=1)
        return fail(2,0,0,physical_,0,0,0,0);
    IOByteCount bytes=0;
    if (buffer_->getPhysicalSegment(0,&bytes,kIOMemoryMapperNone)!=physical_ || bytes!=AllocationBytes)
        return fail(3,0,0,physical_,0,0,0,0);
    /* IOBuffer owns/wires these pages; Apple pmap's cache transition updates
     * physmap plus every managed CPU PV alias and synchronizes TLB/cache state.
     * Validate the actual retained VA and physical-aperture translations too.
     * No user/external aliases are created or handed out by this provider. */
    uint64_t bitmap=0;
    for (uint64_t offset=0;offset<AllocationBytes;offset+=Alignment) {
        uint64_t pa=physical_+offset;
        uint32_t index=(uint32_t)(offset/Alignment);
        unsigned attribute=pmap_cache_attributes((ppnum_t)(pa>>PAGE_SHIFT))&VM_WIMG_MASK;
        uint64_t retainedRead=0,retainedWrite=0,staticRead=0,staticWrite=0;
        uint64_t staticVA=ml_static_ptovirt(pa);
        bool retainedValid=translated_nc(cpu_+offset,pa,&retainedRead,&retainedWrite);
        bool staticValid=translated_nc(staticVA,pa,&staticRead,&staticWrite);
        if (attribute!=VM_WIMG_WCOMB || !retainedValid || !staticValid)
            return fail(attribute!=VM_WIMG_WCOMB?4:(!retainedValid?5:6),index,
                (uint32_t)attribute,pa,retainedRead,retainedWrite,staticRead,staticWrite);
        if (pages) pages[index]={index,(uint32_t)attribute,
            (uint32_t)retainedValid,(uint32_t)staticValid,cpu_+offset,staticVA,pa,
            retainedRead,retainedWrite,staticRead,staticWrite};
        bitmap|=UINT64_C(1)<<index;
    }
    if (normalNCPageBitmap) *normalNCPageBitmap=bitmap;
    mappingReason_=100;
    return true;
}
bool BCM2712GEMDMAMemory::route(const struct rpi5_pcie_window_plan *plan,
    struct rpi5_gem_dma_route *out, bool released) const
{
    if (!plan || !resolved_ || resolved_!=rpi5_boot_reservation_record() ||
        rpi5_reservation_kernel_buffer(resolved_,physical_,AllocationBytes)) return false;
    /* The kernel boot path already bound every dynamic request one-to-one to
     * its actual resolved extent and validated this immutable record against
     * the same retained original FDT. Keep those resolved extents excluded
     * above; do not also reject broad unresolved alloc-ranges windows. */
    struct rpi5_reservation_plan fixed=reservations_;
    fixed.count=0;
    struct rpi5_pcie_window_plan routePlan=*plan;
    if (released) {
        /* The board's released plan deliberately leaves the device and MIP
         * inbound decoders disabled. Require those exact disabled encodings,
         * then restore only their FDT-derived size bits in this local value so
         * the pure full-plan route validator can prove every remaining field.
         * The preferred RAM decoder stays live and must match unchanged. */
        const unsigned disabledSlots[2]={0,2};
        for (unsigned slot : disabledSlots) {
            uint32_t expected=expected_.inbound[slot].bar_lo;
            if (routePlan.inbound[slot].bar_lo!=(expected&~UINT32_C(31))) return false;
            routePlan.inbound[slot].bar_lo=expected;
        }
    }
    return !rpi5_gem_dma_route(&binding_,&routePlan,&ram_,&fixed,
        hasInitrd_ ? &initrd_ : nullptr,physical_,AllocationBytes,out);
}
bool BCM2712GEMDMAMemory::prepare()
{
    if (state_==Preparing || state_==Checking || state_==Discarding) { state_=Quarantined; return false; }
    if (state_!=Empty || !context() || PAGE_SIZE!=Alignment) return false;
    state_=Preparing; thread_=(void *)current_thread();prepareStep_=1;prepareError_=0;
    fdt_=rpi5_copy_boot_firmware_fdt();
    struct rpi5_pcie_profile profile={};
    prepareStep_=2;if (!fdt_) { prepareError_=-2;goto reject; }
    prepareStep_=3;if (rpi5_pcie_profile_decode(fdt_->getBytesNoCopy(),fdt_->getLength(),&binding_,&profile)) { prepareError_=-3;goto reject; }
    prepareStep_=4;if (rpi5_fdt_memory(fdt_->getBytesNoCopy(),fdt_->getLength(),&ram_)) { prepareError_=-4;goto reject; }
    prepareStep_=5;if (rpi5_fdt_reservation_plan(fdt_->getBytesNoCopy(),fdt_->getLength(),&reservations_)) { prepareError_=-5;goto reject; }
    prepareStep_=6;if (rpi5_pcie_windows_plan(&binding_,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES,&expected_)) { prepareError_=-6;goto reject; }
    {
        prepareStep_=7;
        int rc=rpi5_fdt_initrd(fdt_->getBytesNoCopy(),fdt_->getLength(),&initrd_);
        if (rc!=0 && rc!=1) { prepareError_=-7;goto reject; }
        hasInitrd_=rc==0;
        resolved_=rpi5_boot_reservation_record();
        if (!resolved_ || rpi5_reservation_record_validate_fdt(resolved_,
            fdt_->getBytesNoCopy(),fdt_->getLength())) { prepareError_=-17;goto reject; }
    }
    prepareStep_=8;
    buffer_=IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task,
        kIODirectionInOut | kIOMemoryPhysicallyContiguous | kIOMemoryMapperNone |
        kIOMapWriteCombineCache,AllocationBytes,Alignment);
    if (!buffer_) { prepareError_=-8;goto reject; }
    prepareStep_=9;
    command_=IODMACommand::withSpecification(kIODMACommandOutputHost64,64,AllocationBytes,
        IODMACommand::kUnmapped,AllocationBytes,(UInt32)Alignment,nullptr,nullptr);
    if (!command_) { prepareError_=-9;goto reject; }
    prepareStep_=10;
    if (command_->setMemoryDescriptor(buffer_,false)!=kIOReturnSuccess) { prepareError_=-10;goto reject; }
    /* IODMACommand::prepare increments fActive before several possible errors.
     * Its failure cannot safely be treated as an unprepared object to release. */
    prepareStep_=11;
    if (command_->prepare(0,AllocationBytes)!=kIOReturnSuccess) {
        prepareError_=-11;
        state_=Quarantined; return false;
    }
    commandPrepared_=true;
    {
        UInt64 offset=0; UInt32 count=1; IODMACommand::Segment64 segment={};
        IOByteCount bytes=0;
        prepareStep_=12;physical_=buffer_->getPhysicalSegment(0,&bytes,kIOMemoryMapperNone);
        cpu_=(uint64_t)buffer_->getBytesNoCopy();
        if (!physical_ || bytes!=AllocationBytes) { prepareError_=-12;goto reject; }
        prepareStep_=13;
        if (command_->gen64IOVMSegments(&offset,&segment,&count)!=kIOReturnSuccess || count!=1 ||
            offset!=AllocationBytes || segment.fIOVMAddr!=physical_ || segment.fLength!=AllocationBytes) {
            prepareError_=-13;goto reject;
        }
        prepareStep_=14;if (!mapping()) { prepareError_=-14;goto reject; }
        struct rpi5_gem_dma_route geometry;
        prepareStep_=15;if (!route(&expected_,&geometry,false)) { prepareError_=-15;goto reject; }
    }
    prepareStep_=16;if (!context() || state_!=Preparing) { prepareError_=-16;goto reject; }
    state_=Prepared;prepareStep_=17;
    return true;
reject:
    if (state_!=Quarantined) state_=Rejected; /* Explicit discard, never retry. */
    return false;
}
bool BCM2712GEMDMAMemory::discardBeforeAdmission()
{
    if (state_==Preparing || state_==Checking || state_==Discarding) { state_=Quarantined; return false; }
    if ((state_!=Prepared && state_!=Rejected) || !context()) return false;
    state_=Discarding;
    if (commandPrepared_ && (command_->complete()!=kIOReturnSuccess || state_!=Discarding || !context())) {
        state_=Quarantined; return false;
    }
    commandPrepared_=false;
    if (command_ && (command_->clearMemoryDescriptor(false)!=kIOReturnSuccess || state_!=Discarding || !context())) {
        state_=Quarantined; return false;
    }
    if (command_) command_->release();
    if (buffer_) buffer_->release();
    if (fdt_) fdt_->release();
    command_=nullptr; buffer_=nullptr; fdt_=nullptr; state_=Discarded;
    return true;
}
bool BCM2712GEMDMAMemory::qualify(struct rpi5_pcie_released_windows *windows,
    struct rpi5_gem_dma_route *out)
{
    if (state_==Preparing || state_==Checking || state_==Discarding) { state_=Quarantined; return false; }
    if (state_!=Prepared || !windows || !out || thread_!=(void *)current_thread() ||
        ml_at_interrupt_context()) return false;
    state_=Checking; /* All failures from here retain command+descriptor until reset. */
    qualificationStep_=1;qualificationError_=0;
    const auto io=windows->io;
    const auto source=windows->windows;
    auto owner=[&]() {
        return state_==Checking && thread_==(void *)current_thread() &&
            windows->state==RPI5_PCIE_RELEASED_READY && windows->windows==source &&
            windows->io.context==io.context && windows->io.check_owner==io.check_owner &&
            windows->io.read32==io.read32 && windows->io.order==io.order &&
            windows->io.physical_base==io.physical_base && windows->io.mapped_bytes==io.mapped_bytes &&
            io.check_owner && !io.check_owner(io.context) &&
            state_==Checking && thread_==(void *)current_thread() &&
            windows->state==RPI5_PCIE_RELEASED_READY && windows->windows==source &&
            windows->io.context==io.context && windows->io.check_owner==io.check_owner &&
            windows->io.read32==io.read32 && windows->io.order==io.order &&
            windows->io.physical_base==io.physical_base && windows->io.mapped_bytes==io.mapped_bytes;
    };
    struct rpi5_gem_dma_route geometry;
    struct rpi5_pcie_released_observation observed;
    auto reject=[&](uint32_t step,int32_t error) {
        qualificationStep_=step;qualificationError_=error;state_=Quarantined;return false;
    };
    qualificationStep_=2;if (!owner()) return reject(2,-2);
    qualificationStep_=3;if (!mapping()) return reject(3,-3);
    qualificationStep_=4;if (!route(&windows->expected,&geometry,true)) return reject(4,-4);
    qualificationStep_=5;if (!owner()) return reject(5,-5);
    qualificationStep_=6;
    int released=rpi5_pcie_released_windows_check(windows,&observed);
    if (released) return reject(6,released);
    qualificationStep_=7;if (!owner()) return reject(7,-7);
    qualificationStep_=8;if (!mapping()) return reject(8,-8);
    qualificationStep_=9;if (!owner()) return reject(9,-9);
    qualificationStep_=10;
    if (thread_!=(void *)current_thread() || state_!=Checking) return reject(10,-10);
    qualificationStep_=11;if (!route(&windows->expected,&geometry,true)) return reject(11,-11);
    qualificationStep_=12;if (!owner()) return reject(12,-12);
    geometry_=geometry; state_=Held; *out=geometry;
    qualificationStep_=13;qualificationError_=0;
    return true;
}

bool BCM2712GEMDMAMemory::observeCPUOwnedLayout(
    struct rpi5_gem_full_provider_observation *out) const
{
    static_assert(AllocationBytes==
        RPI5_GEM_FULL_PROVIDER_RING_PAGES*RPI5_GEM_FULL_PROVIDER_PAGE_BYTES+
        RPI5_GEM_FULL_PROVIDER_PACKET_SPANS*RPI5_GEM_FULL_PROVIDER_PACKET_BYTES);
    static_assert(AllocationBytes/Alignment==RPI5_GEM_FULL_PROVIDER_MAPPING_PAGES);
    static_assert(Alignment%RPI5_GEM_FULL_PROVIDER_PACKET_BYTES==0);
    if (!out || state_!=Held || thread_!=(void *)current_thread() || !context() ||
        geometry_.bytes!=AllocationBytes || geometry_.physical!=physical_ ||
        geometry_.rp1>UINT64_MAX-AllocationBytes || cpu_>UINT64_MAX-AllocationBytes)
        return false;
    uint64_t bitmap=0;
    observation_={};
    if (!mapping(&bitmap,observation_.page) ||
        state_!=Held || thread_!=(void *)current_thread() ||
        bitmap!=(UINT64_C(1)<<RPI5_GEM_FULL_PROVIDER_MAPPING_PAGES)-1) return false;
    observation_.version=RPI5_GEM_FULL_PROVIDER_VERSION;
    observation_.provider_bytes=(uint32_t)AllocationBytes;
    observation_.mapping_page_bytes=RPI5_GEM_FULL_PROVIDER_PAGE_BYTES;
    observation_.mapping_pages=RPI5_GEM_FULL_PROVIDER_MAPPING_PAGES;
    observation_.normal_nc_page_bitmap=bitmap;
    observation_.base_cpu_address=cpu_;
    observation_.base_physical_address=physical_;
    observation_.base_rp1_dma_address=geometry_.rp1;
    observation_.ring_pages=RPI5_GEM_FULL_PROVIDER_RING_PAGES;
    observation_.packet_spans=RPI5_GEM_FULL_PROVIDER_PACKET_SPANS;
    observation_.packet_bytes=RPI5_GEM_FULL_PROVIDER_PACKET_BYTES;
    observation_.packet_mapped_bytes=
        RPI5_GEM_FULL_PROVIDER_PACKET_SPANS*RPI5_GEM_FULL_PROVIDER_PACKET_BYTES;
    observation_.packet_spans_cpu_owned=RPI5_GEM_FULL_PROVIDER_PACKET_SPANS;
    for (uint32_t index=0;index<RPI5_GEM_FULL_PROVIDER_RING_PAGES;index++) {
        uint64_t offset=(uint64_t)index*RPI5_GEM_FULL_PROVIDER_PAGE_BYTES;
        observation_.ring[index]={cpu_+offset,geometry_.rp1+offset,
            RPI5_GEM_FULL_PROVIDER_PAGE_BYTES,index,RPI5_GEM_FULL_PROVIDER_OWNER_CPU};
    }
    for (uint32_t index=0;index<RPI5_GEM_FULL_PROVIDER_PACKET_SPANS;index++) {
        uint64_t offset=
            (uint64_t)RPI5_GEM_FULL_PROVIDER_RING_PAGES*RPI5_GEM_FULL_PROVIDER_PAGE_BYTES+
            (uint64_t)index*RPI5_GEM_FULL_PROVIDER_PACKET_BYTES;
        uint32_t page=(uint32_t)(offset/Alignment);
        if (page>=RPI5_GEM_FULL_PROVIDER_MAPPING_PAGES || !(bitmap&(UINT64_C(1)<<page)))
            return false;
        observation_.packet[index]={cpu_+offset,geometry_.rp1+offset,
            RPI5_GEM_FULL_PROVIDER_PACKET_BYTES,page,RPI5_GEM_FULL_PROVIDER_OWNER_CPU};
    }
    if (state_!=Held || thread_!=(void *)current_thread() || !context()) return false;
    *out=observation_;
    return true;
}
