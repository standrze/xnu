/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef BCM2712_USB_XHCI_MEMORY_H
#define BCM2712_USB_XHCI_MEMORY_H

#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IODMACommand.h>
#include <libkern/c++/OSData.h>

#include "rpi5_rp1_dma_route.h"
extern "C" {
#include "../../loader/rpi5/pcie_profile.h"
#include "../../loader/rpi5/pcie_released_windows.h"
#include "../../loader/rpi5/rp1_usb_xhci_dma_layout.h"
#include "../../loader/rpi5/rp1_usb_xhci_noop.h"
#include "../../loader/rpi5/usb_hid_boot_setup.h"
#include "../../loader/rpi5/usb_xhci_control_transfer.h"
#include "../../loader/rpi5/usb_xhci_device_context.h"
#include "../../loader/rpi5/usb_xhci_keyboard_endpoint.h"
#include "../../loader/rpi5/rp1_usb_xhci_keyboard_stream.h"
#include "../../osfmk/arm64/rpi5_reservation_api.h"
#include "../../osfmk/arm64/rpi5_reservation_kernel.h"
}

#define RPI5_USB_XHCI_MEMORY_VERSION 1u
#define RPI5_USB_XHCI_MEMORY_PAGES \
    (RPI5_XHCI_DMA_ALLOCATION_BYTES / RPI5_XHCI_DMA_HOST_PAGE_BYTES)

struct rpi5_usb_xhci_memory_page {
    uint32_t index, cache_attribute, retained_valid, static_valid;
    uint64_t retained_cpu_address, static_cpu_address, physical_address;
    uint64_t retained_read_par, retained_write_par;
    uint64_t static_read_par, static_write_par;
};

struct rpi5_usb_xhci_memory_observation {
    uint32_t version, provider_bytes, mapping_page_bytes, mapping_pages;
    uint64_t normal_nc_page_bitmap;
    uint64_t base_cpu_address, base_physical_address, base_rp1_dma_address;
    struct rpi5_rp1_dma_route route;
    struct rpi5_xhci_dma_layout layout;
    struct rpi5_usb_xhci_memory_page page[RPI5_USB_XHCI_MEMORY_PAGES];
};

/* Default-off retained Apple allocation.  No method returns the descriptor,
 * DMA command or a writable CPU pointer.  Successful qualification proves a
 * CPU-owned layout; it does not enable PCI BME, program xHCI or grant DMA. */
class BCM2712USBXHCIMemory final {
public:
    enum State {
        Empty, Preparing, Prepared, Checking, Held, Staging, Staged, Rejected,
        Quarantined, Discarding, Discarded
    };
    static constexpr uint64_t AllocationBytes =
        RPI5_XHCI_DMA_ALLOCATION_BYTES;
    static constexpr uint64_t Alignment = RPI5_XHCI_DMA_HOST_PAGE_BYTES;

    BCM2712USBXHCIMemory() = default;
    BCM2712USBXHCIMemory(const BCM2712USBXHCIMemory &) = delete;
    BCM2712USBXHCIMemory &operator=(const BCM2712USBXHCIMemory &) = delete;

    bool prepare();
    bool discardBeforeAdmission();
    bool qualify(struct rpi5_pcie_released_windows *,
        const struct rpi5_rp1_xhci_caps *);
    /* CPU-only construction after admission. No MMIO or DMA activation. */
    bool stageNoOpCommand(const struct rpi5_rp1_xhci_caps *,
        struct rpi5_xhci_noop_image *);
    bool stageK65Enumeration(const struct rpi5_rp1_xhci_caps *,
        struct rpi5_xhci_noop_image *,
        struct rpi5_usb_xhci_enable_slot_plan *,
        struct rpi5_usb_xhci_descriptor_batch *);
    bool stageK65Address(uint8_t,
        struct rpi5_usb_xhci_address_device_plan *);
    bool stageK65Keyboard(
        const struct rpi5_usb_boot_keyboard_identity *,
        struct rpi5_usb_xhci_keyboard_endpoint_plan *,
        struct rpi5_usb_hid_boot_setup_plan *,
        struct rpi5_usb_xhci_keyboard_interrupt_plan *);
    bool stageK65KeyboardStream(
        const struct rpi5_usb_boot_keyboard_identity *,
        struct rpi5_usb_xhci_keyboard_endpoint_plan *,
        struct rpi5_usb_hid_boot_setup_plan *,
        struct rpi5_usb_xhci_keyboard_stream_plan *);
    bool observeCPUOwnedLayout(
        struct rpi5_usb_xhci_memory_observation *) const;

    State state() const { return state_; }
    uint32_t preparationStep() const { return preparationStep_; }
    int32_t preparationError() const { return preparationError_; }
    uint32_t qualificationStep() const { return qualificationStep_; }
    int32_t qualificationError() const { return qualificationError_; }

private:
    bool context() const;
    bool mapping(uint64_t *bitmap = nullptr,
        struct rpi5_usb_xhci_memory_page *pages = nullptr) const;
    bool route(const struct rpi5_pcie_window_plan *,
        struct rpi5_rp1_dma_route *, bool released) const;

    State state_ = Empty;
    IOBufferMemoryDescriptor *buffer_ = nullptr;
    IODMACommand *command_ = nullptr;
    OSData *fdt_ = nullptr;
    void *thread_ = nullptr;
    uint64_t cpu_ = 0, physical_ = 0;
    bool commandPrepared_ = false;
    const struct rpi5_reservation_record *resolved_ = nullptr;
    struct rpi5_pcie_fdt binding_ = {};
    struct rpi5_pcie_window_plan expected_ = {};
    struct rpi5_fdt_memory ram_ = {};
    struct rpi5_reservation_plan reservations_ = {};
    struct rpi5_range initrd_ = {};
    bool hasInitrd_ = false;
    struct rpi5_rp1_dma_route route_ = {};
    struct rpi5_xhci_dma_layout layout_ = {};
    struct rpi5_xhci_noop_image noop_ = {};
    struct rpi5_usb_xhci_enable_slot_plan enable_ = {};
    struct rpi5_usb_xhci_descriptor_batch descriptorBatch_ = {};
    struct rpi5_usb_xhci_address_device_plan address_ = {};
    struct rpi5_usb_xhci_keyboard_endpoint_plan keyboardEndpoint_ = {};
    struct rpi5_usb_hid_boot_setup_plan keyboardSetup_ = {};
    struct rpi5_usb_xhci_keyboard_interrupt_plan keyboardInterrupt_ = {};
    struct rpi5_usb_xhci_keyboard_stream_plan keyboardStream_ = {};
    uint32_t preparationStep_ = 0, qualificationStep_ = 0;
    int32_t preparationError_ = 0, qualificationError_ = 0;
    mutable struct rpi5_usb_xhci_memory_observation observation_ = {};
};

#endif
