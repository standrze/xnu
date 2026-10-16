/* SPDX-License-Identifier: BSD-2-Clause */
#if !defined(ARM64_BOARD_CONFIG_BCM2712) || !DEVELOPMENT || \
    !RPI5_FIRMWARE_FDT_HANDOFF
#error "USB xHCI memory provider requires the BCM2712 DEVELOPMENT build"
#endif

#include "BCM2712USBXHCIMemory.h"
#include "BCM2712FirmwareFDT.h"

#include <IOKit/IOLib.h>
#include <arm64/proc_reg.h>
#include <kern/task.h>
#include <kern/thread.h>
#include <machine/machine_routines.h>
#include <vm/memory_types.h>
#include <vm/pmap.h>

extern "C" unsigned rpi5_physical_memory_type(uint64_t, uint64_t);
extern "C" int get_preemption_level(void);
extern "C" unsigned pmap_cache_attributes(ppnum_t);

static bool
translated_nc(uint64_t virtual_address, uint64_t physical,
    uint64_t *read_proof = nullptr, uint64_t *write_proof = nullptr)
{
    uint64_t saved, read, write;
    boolean_t interrupts = ml_set_interrupts_enabled(FALSE);
    __asm__ volatile(
        "mrs %0, par_el1\n\tat s1e1r, %3\n\tisb\n\tmrs %1, par_el1\n\t"
        "at s1e1w, %3\n\tisb\n\tmrs %2, par_el1\n\tmsr par_el1, %0\n\tisb"
        : "=&r"(saved), "=&r"(read), "=&r"(write)
        : "r"(virtual_address) : "memory");
    ml_set_interrupts_enabled(interrupts);
    if (read_proof) {
        *read_proof = read;
    }
    if (write_proof) {
        *write_proof = write;
    }
    constexpr uint64_t address_mask = UINT64_C(0x0000fffffffff000);
    return !(read & PAR_F) && !(write & PAR_F) && (read >> 56) == 0x44 &&
        (write >> 56) == 0x44 &&
        (read & address_mask) == (physical & address_mask) &&
        (write & address_mask) == (physical & address_mask);
}

bool
BCM2712USBXHCIMemory::context() const
{
    return !ml_at_interrupt_context() && ml_get_interrupts_enabled() &&
        get_preemption_level() == 0 &&
        (!thread_ || thread_ == (void *)current_thread());
}

bool
BCM2712USBXHCIMemory::mapping(uint64_t *normal_nc_bitmap,
    struct rpi5_usb_xhci_memory_page *pages) const
{
    if (!resolved_ || resolved_ != rpi5_boot_reservation_record() ||
        !buffer_ || !command_ || !commandPrepared_ || !cpu_ || !physical_ ||
        buffer_->getLength() != AllocationBytes ||
        buffer_->getCapacity() != AllocationBytes ||
        (uint64_t)buffer_->getBytesNoCopy() != cpu_ ||
        ((cpu_ | physical_) & (Alignment - 1)) ||
        cpu_ > UINT64_MAX - AllocationBytes ||
        physical_ > UINT64_MAX - AllocationBytes ||
        rpi5_physical_memory_type(physical_, physical_ + AllocationBytes) != 1) {
        return false;
    }

    IOByteCount bytes = 0;
    if (buffer_->getPhysicalSegment(0, &bytes, kIOMemoryMapperNone) !=
            physical_ || bytes != AllocationBytes) {
        return false;
    }

    uint64_t bitmap = 0;
    for (uint64_t offset = 0; offset < AllocationBytes;
        offset += Alignment) {
        uint64_t physical_page = physical_ + offset;
        uint32_t index = (uint32_t)(offset / Alignment);
        unsigned attribute = pmap_cache_attributes(
            (ppnum_t)(physical_page >> PAGE_SHIFT)) & VM_WIMG_MASK;
        uint64_t retained_read = 0, retained_write = 0;
        uint64_t static_read = 0, static_write = 0;
        uint64_t static_virtual = ml_static_ptovirt(physical_page);
        bool retained_valid = translated_nc(cpu_ + offset, physical_page,
            &retained_read, &retained_write);
        bool static_valid = translated_nc(static_virtual, physical_page,
            &static_read, &static_write);
        if (attribute != VM_WIMG_WCOMB || !retained_valid || !static_valid) {
            return false;
        }
        if (pages) {
            pages[index] = {index, (uint32_t)attribute,
                (uint32_t)retained_valid, (uint32_t)static_valid,
                cpu_ + offset, static_virtual, physical_page,
                retained_read, retained_write, static_read, static_write};
        }
        bitmap |= UINT64_C(1) << index;
    }
    if (normal_nc_bitmap) {
        *normal_nc_bitmap = bitmap;
    }
    return true;
}

bool
BCM2712USBXHCIMemory::route(const struct rpi5_pcie_window_plan *plan,
    struct rpi5_rp1_dma_route *out, bool released) const
{
    if (!plan || !resolved_ || resolved_ != rpi5_boot_reservation_record() ||
        rpi5_reservation_kernel_buffer(resolved_, physical_, AllocationBytes)) {
        return false;
    }
    struct rpi5_reservation_plan fixed = reservations_;
    fixed.count = 0;
    struct rpi5_pcie_window_plan route_plan = *plan;
    if (released) {
        const unsigned disabled_slots[2] = {0, 2};
        for (unsigned slot : disabled_slots) {
            uint32_t expected = expected_.inbound[slot].bar_lo;
            if (route_plan.inbound[slot].bar_lo !=
                (expected & ~UINT32_C(31))) {
                return false;
            }
            route_plan.inbound[slot].bar_lo = expected;
        }
    }
    return rpi5_rp1_dma_route(&binding_, &route_plan, &ram_, &fixed,
        hasInitrd_ ? &initrd_ : nullptr, physical_, AllocationBytes, out) == 0;
}

bool
BCM2712USBXHCIMemory::prepare()
{
    if (state_ == Preparing || state_ == Checking || state_ == Staging ||
        state_ == Discarding) {
        state_ = Quarantined;
        return false;
    }
    if (state_ != Empty || !context() || PAGE_SIZE != Alignment) {
        return false;
    }
    state_ = Preparing;
    thread_ = (void *)current_thread();
    preparationStep_ = 1;
    preparationError_ = 0;
    auto active = [&]() { return state_ == Preparing && context(); };

    fdt_ = rpi5_copy_boot_firmware_fdt();
    if (!active()) {
        goto quarantine;
    }
    preparationStep_ = 2;
    if (!fdt_) {
        preparationError_ = -2;
        goto reject;
    }
    {
        const void *bytes = fdt_->getBytesNoCopy();
        unsigned length = fdt_->getLength();
        struct rpi5_pcie_profile profile = {};
        preparationStep_ = 3;
        if (!bytes || rpi5_pcie_profile_decode(bytes, length, &binding_,
                &profile)) {
            preparationError_ = -3;
            goto reject;
        }
        preparationStep_ = 4;
        if (rpi5_fdt_memory(bytes, length, &ram_)) {
            preparationError_ = -4;
            goto reject;
        }
        preparationStep_ = 5;
        if (rpi5_fdt_reservation_plan(bytes, length, &reservations_)) {
            preparationError_ = -5;
            goto reject;
        }
        preparationStep_ = 6;
        if (rpi5_pcie_windows_plan(&binding_,
                RPI5_PCIE_WINDOW_ACK_FOUR_BYTES, &expected_)) {
            preparationError_ = -6;
            goto reject;
        }
        preparationStep_ = 7;
        int result = rpi5_fdt_initrd(bytes, length, &initrd_);
        if (result != 0 && result != 1) {
            preparationError_ = -7;
            goto reject;
        }
        hasInitrd_ = result == 0;
        resolved_ = rpi5_boot_reservation_record();
        if (!resolved_ || rpi5_reservation_record_validate_fdt(resolved_,
                bytes, length)) {
            preparationError_ = -17;
            goto reject;
        }
    }
    if (!active()) {
        goto quarantine;
    }

    preparationStep_ = 8;
    buffer_ = IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task,
        kIODirectionInOut | kIOMemoryPhysicallyContiguous |
        kIOMemoryMapperNone | kIOMapWriteCombineCache,
        AllocationBytes, Alignment);
    if (!active()) {
        goto quarantine;
    }
    if (!buffer_) {
        preparationError_ = -8;
        goto reject;
    }
    preparationStep_ = 9;
    command_ = IODMACommand::withSpecification(kIODMACommandOutputHost64,
        64, AllocationBytes, IODMACommand::kUnmapped, AllocationBytes,
        (UInt32)Alignment, nullptr, nullptr);
    if (!active()) {
        goto quarantine;
    }
    if (!command_) {
        preparationError_ = -9;
        goto reject;
    }
    preparationStep_ = 10;
    if (command_->setMemoryDescriptor(buffer_, false) != kIOReturnSuccess) {
        preparationError_ = -10;
        goto reject;
    }
    preparationStep_ = 11;
    if (command_->prepare(0, AllocationBytes) != kIOReturnSuccess) {
        preparationError_ = -11;
        goto quarantine;
    }
    commandPrepared_ = true;
    if (!active()) {
        goto quarantine;
    }
    {
        IOByteCount bytes = 0;
        physical_ = buffer_->getPhysicalSegment(0, &bytes,
            kIOMemoryMapperNone);
        cpu_ = (uint64_t)buffer_->getBytesNoCopy();
        preparationStep_ = 12;
        if (!physical_ || bytes != AllocationBytes) {
            preparationError_ = -12;
            goto reject;
        }
        UInt64 offset = 0;
        UInt32 count = 1;
        IODMACommand::Segment64 segment = {};
        preparationStep_ = 13;
        if (command_->gen64IOVMSegments(&offset, &segment, &count) !=
                kIOReturnSuccess || count != 1 || offset != AllocationBytes ||
            segment.fIOVMAddr != physical_ ||
            segment.fLength != AllocationBytes) {
            preparationError_ = -13;
            goto reject;
        }
        preparationStep_ = 14;
        if (!mapping()) {
            preparationError_ = -14;
            goto reject;
        }
        struct rpi5_rp1_dma_route route;
        preparationStep_ = 15;
        if (!this->route(&expected_, &route, false)) {
            preparationError_ = -15;
            goto reject;
        }
    }
    if (!active()) {
        preparationError_ = -16;
        goto quarantine;
    }
    state_ = Prepared;
    preparationStep_ = 17;
    return true;

reject:
    if (active()) {
        state_ = Rejected;
        return false;
    }
quarantine:
    state_ = Quarantined;
    return false;
}

bool
BCM2712USBXHCIMemory::discardBeforeAdmission()
{
    if (state_ == Preparing || state_ == Checking || state_ == Staging ||
        state_ == Discarding) {
        state_ = Quarantined;
        return false;
    }
    if ((state_ != Prepared && state_ != Rejected) || !context()) {
        return false;
    }
    state_ = Discarding;
    auto active = [&]() { return state_ == Discarding && context(); };
    if (commandPrepared_) {
        if (command_->complete() != kIOReturnSuccess || !active()) {
            goto quarantine;
        }
        commandPrepared_ = false;
    }
    if (command_) {
        if (command_->clearMemoryDescriptor(false) != kIOReturnSuccess ||
            !active()) {
            goto quarantine;
        }
        command_->release();
        command_ = nullptr;
    }
    if (buffer_) {
        buffer_->release();
        buffer_ = nullptr;
    }
    if (fdt_) {
        fdt_->release();
        fdt_ = nullptr;
    }
    if (!active()) {
        goto quarantine;
    }
    state_ = Discarded;
    return true;

quarantine:
    state_ = Quarantined;
    return false;
}

bool
BCM2712USBXHCIMemory::qualify(struct rpi5_pcie_released_windows *windows,
    const struct rpi5_rp1_xhci_caps *caps)
{
    if (state_ == Preparing || state_ == Checking || state_ == Staging ||
        state_ == Discarding) {
        state_ = Quarantined;
        return false;
    }
    if (state_ != Prepared || !windows || !caps ||
        thread_ != (void *)current_thread() || ml_at_interrupt_context()) {
        return false;
    }
    state_ = Checking;
    qualificationStep_ = 1;
    qualificationError_ = 0;
    const auto io = windows->io;
    const auto source = windows->windows;
    auto owner = [&]() {
        return state_ == Checking && thread_ == (void *)current_thread() &&
            windows->state == RPI5_PCIE_RELEASED_READY &&
            windows->windows == source && windows->io.context == io.context &&
            windows->io.check_owner == io.check_owner &&
            windows->io.read32 == io.read32 && windows->io.order == io.order &&
            windows->io.physical_base == io.physical_base &&
            windows->io.mapped_bytes == io.mapped_bytes && io.check_owner &&
            !io.check_owner(io.context);
    };
    auto reject = [&](uint32_t step, int32_t error) {
        qualificationStep_ = step;
        qualificationError_ = error;
        state_ = Quarantined;
        return false;
    };
    struct rpi5_pcie_released_observation observed;
    struct rpi5_rp1_dma_route route;
    struct rpi5_xhci_dma_layout layout;
    qualificationStep_ = 2;
    if (!owner()) {
        return reject(2, -2);
    }
    qualificationStep_ = 3;
    if (!mapping()) {
        return reject(3, -3);
    }
    qualificationStep_ = 4;
    if (!this->route(&windows->expected, &route, true)) {
        return reject(4, -4);
    }
    qualificationStep_ = 5;
    if (!owner()) {
        return reject(5, -5);
    }
    qualificationStep_ = 6;
    int released = rpi5_pcie_released_windows_check(windows, &observed);
    if (released) {
        return reject(6, released);
    }
    qualificationStep_ = 7;
    if (!owner()) {
        return reject(7, -7);
    }
    qualificationStep_ = 8;
    if (!mapping()) {
        return reject(8, -8);
    }
    qualificationStep_ = 9;
    if (rpi5_rp1_xhci_dma_layout(caps, cpu_, route.rp1,
            (uint32_t)AllocationBytes, &layout)) {
        return reject(9, -9);
    }
    qualificationStep_ = 10;
    if (!owner()) {
        return reject(10, -10);
    }
    qualificationStep_ = 11;
    if (!this->route(&windows->expected, &route, true) ||
        state_ != Checking || thread_ != (void *)current_thread()) {
        return reject(11, -11);
    }
    route_ = route;
    layout_ = layout;
    state_ = Held;
    qualificationStep_ = 12;
    return true;
}

bool
BCM2712USBXHCIMemory::stageNoOpCommand(
    const struct rpi5_rp1_xhci_caps *caps,
    struct rpi5_xhci_noop_image *out)
{
    if (state_ == Preparing || state_ == Checking || state_ == Staging ||
        state_ == Discarding) {
        state_ = Quarantined;
        return false;
    }
    if (state_ != Held || !caps || !out || !context() ||
        thread_ != (void *)current_thread()) {
        return false;
    }
    state_ = Staging;
    struct rpi5_xhci_noop_image image;
    if (!mapping() || rpi5_rp1_xhci_noop_image(caps, &layout_,
            (void *)cpu_, (uint32_t)AllocationBytes, &image)) {
        state_ = Quarantined;
        return false;
    }
    OSSynchronizeIO();
    if (state_ != Staging || !context() || !mapping()) {
        state_ = Quarantined;
        return false;
    }
    noop_ = image;
    state_ = Staged;
    *out = image;
    return true;
}

bool
BCM2712USBXHCIMemory::stageK65Enumeration(
    const struct rpi5_rp1_xhci_caps *caps,
    struct rpi5_xhci_noop_image *base,
    struct rpi5_usb_xhci_enable_slot_plan *enable,
    struct rpi5_usb_xhci_descriptor_batch *batch)
{
    if (state_ == Preparing || state_ == Checking || state_ == Staging ||
        state_ == Discarding) {
        state_ = Quarantined;
        return false;
    }
    if (state_ != Held || !caps || !base || !enable || !batch || !context() ||
        thread_ != (void *)current_thread()) {
        return false;
    }
    state_ = Staging;
    struct rpi5_xhci_noop_image stagedBase;
    struct rpi5_usb_xhci_enable_slot_plan stagedEnable;
    struct rpi5_usb_xhci_descriptor_batch stagedBatch;
    if (!mapping() || rpi5_rp1_xhci_noop_image(caps, &layout_,
            (void *)cpu_, (uint32_t)AllocationBytes, &stagedBase) ||
        rpi5_usb_xhci_enable_slot_plan(&layout_, (void *)cpu_,
            (uint32_t)AllocationBytes, &stagedEnable) ||
        rpi5_usb_k65_descriptor_batch(&layout_, (void *)cpu_,
            (uint32_t)AllocationBytes, &stagedBatch)) {
        state_ = Quarantined;
        return false;
    }
    OSSynchronizeIO();
    if (state_ != Staging || !context() || !mapping()) {
        state_ = Quarantined;
        return false;
    }
    noop_ = stagedBase;
    enable_ = stagedEnable;
    descriptorBatch_ = stagedBatch;
    state_ = Staged;
    *base = stagedBase;
    *enable = stagedEnable;
    *batch = stagedBatch;
    return true;
}

bool
BCM2712USBXHCIMemory::stageK65Address(
    uint8_t slot, struct rpi5_usb_xhci_address_device_plan *out)
{
    if (state_ == Preparing || state_ == Checking || state_ == Staging ||
        state_ == Discarding) {
        state_ = Quarantined;
        return false;
    }
    if (state_ != Staged || !slot || slot > 64 || !out || !context() ||
        thread_ != (void *)current_thread()) {
        return false;
    }
    state_ = Staging;
    struct rpi5_usb_xhci_address_device_plan stagedAddress;
    if (!mapping() || rpi5_usb_xhci_address_k65_plan(&layout_,
            (void *)cpu_, (uint32_t)AllocationBytes, slot, &stagedAddress)) {
        state_ = Quarantined;
        return false;
    }
    OSSynchronizeIO();
    if (state_ != Staging || !context() || !mapping()) {
        state_ = Quarantined;
        return false;
    }
    address_ = stagedAddress;
    state_ = Staged;
    *out = stagedAddress;
    return true;
}

bool
BCM2712USBXHCIMemory::stageK65Keyboard(
    const struct rpi5_usb_boot_keyboard_identity *identity,
    struct rpi5_usb_xhci_keyboard_endpoint_plan *endpoint,
    struct rpi5_usb_hid_boot_setup_plan *setup,
    struct rpi5_usb_xhci_keyboard_interrupt_plan *interrupt)
{
    if (state_ == Preparing || state_ == Checking || state_ == Staging ||
        state_ == Discarding) {
        state_ = Quarantined;
        return false;
    }
    if (state_ != Staged || !identity || !endpoint || !setup || !interrupt ||
        !address_.slot || !context() ||
        thread_ != (void *)current_thread()) {
        return false;
    }
    state_ = Staging;
    struct rpi5_usb_xhci_keyboard_endpoint_plan stagedEndpoint;
    struct rpi5_usb_hid_boot_setup_plan stagedSetup;
    struct rpi5_usb_xhci_keyboard_interrupt_plan stagedInterrupt;
    if (!mapping() || rpi5_usb_xhci_configure_k65_keyboard(&layout_,
            (void *)cpu_, (uint32_t)AllocationBytes, &address_, identity,
            &stagedEndpoint) ||
        rpi5_usb_k65_hid_boot_setup(&layout_, (void *)cpu_,
            (uint32_t)AllocationBytes, (uint8_t)address_.slot,
            &stagedSetup) ||
        rpi5_usb_xhci_k65_interrupt_plan(&layout_, (void *)cpu_,
            (uint32_t)AllocationBytes, &stagedEndpoint,
            &stagedInterrupt)) {
        state_ = Quarantined;
        return false;
    }
    OSSynchronizeIO();
    if (state_ != Staging || !context() || !mapping()) {
        state_ = Quarantined;
        return false;
    }
    keyboardEndpoint_ = stagedEndpoint;
    keyboardSetup_ = stagedSetup;
    keyboardInterrupt_ = stagedInterrupt;
    state_ = Staged;
    *endpoint = stagedEndpoint;
    *setup = stagedSetup;
    *interrupt = stagedInterrupt;
    return true;
}

bool
BCM2712USBXHCIMemory::stageK65KeyboardStream(
    const struct rpi5_usb_boot_keyboard_identity *identity,
    struct rpi5_usb_xhci_keyboard_endpoint_plan *endpoint,
    struct rpi5_usb_hid_boot_setup_plan *setup,
    struct rpi5_usb_xhci_keyboard_stream_plan *stream)
{
    if (state_ == Preparing || state_ == Checking || state_ == Staging ||
        state_ == Discarding) {
        state_ = Quarantined;
        return false;
    }
    if (state_ != Staged || !identity || !endpoint || !setup || !stream ||
        !address_.slot || !context() ||
        thread_ != (void *)current_thread()) {
        return false;
    }
    state_ = Staging;
    struct rpi5_usb_xhci_keyboard_endpoint_plan stagedEndpoint;
    struct rpi5_usb_hid_boot_setup_plan stagedSetup;
    struct rpi5_usb_xhci_keyboard_stream_plan stagedStream;
    if (!mapping() || rpi5_usb_xhci_configure_k65_keyboard(&layout_,
            (void *)cpu_, (uint32_t)AllocationBytes, &address_, identity,
            &stagedEndpoint) ||
        rpi5_usb_k65_hid_boot_setup_idle(&layout_, (void *)cpu_,
            (uint32_t)AllocationBytes, (uint8_t)address_.slot, 0,
            &stagedSetup) ||
        rpi5_usb_xhci_k65_stream_plan(&layout_, (void *)cpu_,
            (uint32_t)AllocationBytes, &stagedEndpoint, &stagedStream)) {
        state_ = Quarantined;
        return false;
    }
    OSSynchronizeIO();
    if (state_ != Staging || !context() || !mapping()) {
        state_ = Quarantined;
        return false;
    }
    keyboardEndpoint_ = stagedEndpoint;
    keyboardSetup_ = stagedSetup;
    keyboardStream_ = stagedStream;
    state_ = Staged;
    *endpoint = stagedEndpoint;
    *setup = stagedSetup;
    *stream = stagedStream;
    return true;
}

bool
BCM2712USBXHCIMemory::observeCPUOwnedLayout(
    struct rpi5_usb_xhci_memory_observation *out) const
{
    static_assert(RPI5_USB_XHCI_MEMORY_PAGES == 20);
    if (!out || (state_ != Held && state_ != Staged) ||
        thread_ != (void *)current_thread() ||
        !context() || route_.bytes != AllocationBytes ||
        route_.physical != physical_ || layout_.allocation_bytes !=
            AllocationBytes) {
        return false;
    }
    observation_ = {};
    uint64_t bitmap = 0;
    State expected_state = state_;
    if (!mapping(&bitmap, observation_.page) || state_ != expected_state ||
        thread_ != (void *)current_thread() ||
        bitmap != (UINT64_C(1) << RPI5_USB_XHCI_MEMORY_PAGES) - 1) {
        return false;
    }
    observation_.version = RPI5_USB_XHCI_MEMORY_VERSION;
    observation_.provider_bytes = (uint32_t)AllocationBytes;
    observation_.mapping_page_bytes = (uint32_t)Alignment;
    observation_.mapping_pages = RPI5_USB_XHCI_MEMORY_PAGES;
    observation_.normal_nc_page_bitmap = bitmap;
    observation_.base_cpu_address = cpu_;
    observation_.base_physical_address = physical_;
    observation_.base_rp1_dma_address = route_.rp1;
    observation_.route = route_;
    observation_.layout = layout_;
    if (state_ != expected_state || thread_ != (void *)current_thread() ||
        !context()) {
        return false;
    }
    *out = observation_;
    return true;
}
