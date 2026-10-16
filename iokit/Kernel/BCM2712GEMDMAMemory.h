/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef BCM2712_GEM_DMA_MEMORY_H
#define BCM2712_GEM_DMA_MEMORY_H
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IODMACommand.h>
#include <libkern/c++/OSData.h>
#include "rpi5_gem_dma_route.h"
extern "C" {
#include "../../loader/rpi5/pcie_profile.h"
#include "../../loader/rpi5/pcie_released_windows.h"
#include "../../osfmk/arm64/rpi5_reservation_kernel.h"
#include "../../osfmk/arm64/rpi5_reservation_api.h"
}

#define RPI5_GEM_FULL_PROVIDER_VERSION 2u
#define RPI5_GEM_FULL_PROVIDER_RING_PAGES 2u
#define RPI5_GEM_FULL_PROVIDER_PACKET_SPANS 128u
#define RPI5_GEM_FULL_PROVIDER_PAGE_BYTES UINT32_C(0x4000)
#define RPI5_GEM_FULL_PROVIDER_PACKET_BYTES UINT32_C(0x0800)
#define RPI5_GEM_FULL_PROVIDER_MAPPING_PAGES 18u

enum rpi5_gem_full_provider_owner {
    RPI5_GEM_FULL_PROVIDER_OWNER_NONE = 0,
    RPI5_GEM_FULL_PROVIDER_OWNER_CPU = 1
};

struct rpi5_gem_full_provider_span {
    uint64_t cpu_address;
    uint64_t dma_address;
    uint32_t bytes;
    uint32_t mapping_page;
    enum rpi5_gem_full_provider_owner owner;
};

struct rpi5_gem_full_provider_page {
    uint32_t index;
    uint32_t cache_attribute;
    uint32_t retained_valid;
    uint32_t static_valid;
    uint64_t retained_cpu_address;
    uint64_t static_cpu_address;
    uint64_t physical_address;
    uint64_t retained_read_par;
    uint64_t retained_write_par;
    uint64_t static_read_par;
    uint64_t static_write_par;
};

/*
 * Read-only software evidence for the retained Apple allocation.  Addresses
 * are never written to GEM or PCIe hardware by this provider.  Each 2-KiB
 * packet span is disjoint, lies wholly inside one independently checked 16-KiB
 * Normal-NC page, and remains CPU-owned.  The descriptor and command remain
 * private and prepared after this snapshot is returned.
 */
struct rpi5_gem_full_provider_observation {
    uint32_t version;
    uint32_t provider_bytes;
    uint32_t mapping_page_bytes;
    uint32_t mapping_pages;
    uint64_t normal_nc_page_bitmap;
    uint64_t base_cpu_address;
    uint64_t base_physical_address;
    uint64_t base_rp1_dma_address;
    uint32_t ring_pages;
    uint32_t packet_spans;
    uint32_t packet_bytes;
    uint32_t packet_mapped_bytes;
    uint32_t packet_spans_cpu_owned;
    struct rpi5_gem_full_provider_page page[RPI5_GEM_FULL_PROVIDER_MAPPING_PAGES];
    struct rpi5_gem_full_provider_span ring[RPI5_GEM_FULL_PROVIDER_RING_PAGES];
    struct rpi5_gem_full_provider_span packet[RPI5_GEM_FULL_PROVIDER_PACKET_SPANS];
};

/* Default-off: no constructor registration, boot argument, matching personality
 * or current kernel caller. Must live in serialized driver-owned storage until
 * reboot after admission; raw retained references deliberately do not release
 * in a destructor. A prepared-but-never-admitted object can explicitly discard.
 * No method returns an IODMA/IOBuffer handle or publishes queue addresses.
 * This is memory-provider qualification, NOT DMA, IRQ or packet activation.
 * A future driver must supply the real released-window owner's callbacks and
 * separately close endpoint quiescence, fresh capabilities and ring ownership.
 * In particular this class does not reset the existing owner's finite budget. */
class BCM2712GEMDMAMemory final {
public:
    enum State { Empty, Preparing, Prepared, Checking, Held, Rejected, Quarantined, Discarding, Discarded };
    static constexpr uint64_t AllocationBytes=0x48000;
    static constexpr uint64_t Alignment=0x4000;
    BCM2712GEMDMAMemory()=default;
    BCM2712GEMDMAMemory(const BCM2712GEMDMAMemory &)=delete;
    BCM2712GEMDMAMemory &operator=(const BCM2712GEMDMAMemory &)=delete;
    /* These operations may allocate/block. Only ordinary ungated driver thread
     * context: interrupts enabled, no preemption disable, not interrupt context.
     * Caller must additionally prove no WorkLoop command gate is held. */
    bool prepare();
    bool discardBeforeAdmission();
    /* Reads the actual existing released-window provider (90 register reads),
     * never accepts a saved observation/receipt. Serialized one-shot owner and
     * same current thread; permanent retention on any admitted failure.
     * Successful output is qualified geometry only, not access authority. */
    bool qualify(struct rpi5_pcie_released_windows *, struct rpi5_gem_dma_route *);
    /* Available only after qualify() retained the exact preferred-RAM route.
     * Revalidates every mapped page, then copies the fixed CPU-owned layout.
     * It performs no register access and grants no DMA ownership. */
    bool observeCPUOwnedLayout(struct rpi5_gem_full_provider_observation *) const;
    State state() const { return state_; }
    uint32_t preparationStep() const { return prepareStep_; }
    int32_t preparationError() const { return prepareError_; }
    uint32_t qualificationStep() const { return qualificationStep_; }
    int32_t qualificationError() const { return qualificationError_; }
    uint32_t mappingReason() const { return mappingReason_; }
    uint32_t mappingPage() const { return mappingPage_; }
    uint32_t mappingAttribute() const { return mappingAttribute_; }
    uint64_t mappingPhysical() const { return mappingPhysical_; }
    uint64_t mappingRetainedReadPAR() const { return mappingRetainedReadPAR_; }
    uint64_t mappingRetainedWritePAR() const { return mappingRetainedWritePAR_; }
    uint64_t mappingStaticReadPAR() const { return mappingStaticReadPAR_; }
    uint64_t mappingStaticWritePAR() const { return mappingStaticWritePAR_; }
private:
    const struct rpi5_reservation_record *resolved_=nullptr;
    bool context() const;
    bool mapping(uint64_t *normalNCPageBitmap=nullptr,
        struct rpi5_gem_full_provider_page *pages=nullptr) const;
    bool route(const struct rpi5_pcie_window_plan *, struct rpi5_gem_dma_route *, bool released) const;
    State state_=Empty;
    IOBufferMemoryDescriptor *buffer_=nullptr;
    IODMACommand *command_=nullptr;
    OSData *fdt_=nullptr;
    void *thread_=nullptr;
    uint64_t cpu_=0, physical_=0;
    bool commandPrepared_=false;
    struct rpi5_pcie_fdt binding_={};
    struct rpi5_pcie_window_plan expected_={};
    struct rpi5_fdt_memory ram_={};
    struct rpi5_reservation_plan reservations_={};
    struct rpi5_range initrd_={};
    bool hasInitrd_=false;
    struct rpi5_gem_dma_route geometry_={};
    uint32_t prepareStep_=0;
    int32_t prepareError_=0;
    uint32_t qualificationStep_=0;
    int32_t qualificationError_=0;
    mutable uint32_t mappingReason_=0,mappingPage_=0,mappingAttribute_=0;
    mutable uint64_t mappingPhysical_=0;
    mutable uint64_t mappingRetainedReadPAR_=0,mappingRetainedWritePAR_=0;
    mutable uint64_t mappingStaticReadPAR_=0,mappingStaticWritePAR_=0;
    /* Heap-resident scratch preserves the caller's atomic output contract
     * without putting the 128-span observation on a kernel thread stack. */
    mutable struct rpi5_gem_full_provider_observation observation_={};
};
#endif
