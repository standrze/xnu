/* SPDX-License-Identifier: BSD-2-Clause */
static rpi5_reservation_record reservation_record, alternate_reservation_record;
extern "C" const rpi5_reservation_record *
rpi5_boot_reservation_record(void)
{
    model.reservation_calls++;
    if (event() || model.mode == 7) {
        return nullptr;
    }
    if (model.mode == 8 && model.reservation_calls > 1) {
        return &alternate_reservation_record;
    }
    return &reservation_record;
}

extern "C" int
rpi5_reservation_record_validate_fdt(const rpi5_reservation_record *record,
    const void *bytes, size_t length)
{
    assert(record == &reservation_record && bytes == &fixture &&
        length == sizeof(fixture));
    return event() || model.mode == 9 ? -1 : 0;
}

extern "C" int
rpi5_reservation_kernel_buffer(const rpi5_reservation_record *record,
    uint64_t physical, uint64_t bytes)
{
    assert(record == &reservation_record && physical == model.pa &&
        bytes == sizeof(allocation));
    return event() || model.mode == 5 ? -1 : 0;
}

static BCM2712USBXHCIMemory *active;
static rpi5_pcie_released_windows *released;
static rpi5_rp1_xhci_caps caps;

static void
reenter()
{
    assert(!active->qualify(released, &caps));
}

static void
change_thread()
{
    model.thread = (void *)0x4000;
}

static int
owner(void *)
{
    model.owner_calls++;
    return event() ? -1 : 0;
}

static int
order(void *)
{
    return event() ? -1 : 0;
}

static int
read32(void *, uint32_t offset, uint32_t *value)
{
    assert(offset < sizeof(model.regs) && !(offset & 3));
    model.reads++;
    *value = model.regs[offset / 4];
    return event() ? -1 : 0;
}

static void
setup(rpi5_pcie_windows &windows, rpi5_pcie_released_windows &released_windows)
{
    model = Model{};
    fixture = {};
    fixture.bridge_regs = {0x1000120000, 0x1000129310};
    fixture.mip_regs = {0x1000130000, 0x10001300c0};
    fixture.mip_target = {0xfffffff000, 0x10000000000};
    fixture.outbound_count = 2;
    fixture.dma_count = 3;
    fixture.rp1_dma_count = 3;
    fixture.outbound[0] = {0x02000000, 0, 0x1f00000000, 0xfffffffc};
    fixture.outbound[1] = {0x43000000, 0x400000000, 0x1c00000000,
        0x300000000};
    fixture.dma[0] = {0x02000000, 0, 0x1f00000000, 0x400000};
    fixture.dma[1] = {0x43000000, 0x1000000000, 0, 0x1000000000};
    fixture.dma[2] = {0x03000000, 0xfffffff000, 0x1000130000, 0x1000};
    fixture.rp1_dma[0] = {0x43000000, 0x1000000000, 0x1000000000,
        0x1000000000};
    fixture.rp1_dma[1] = {0x02000000, 0xc040000000, 0, 0x410000};
    fixture.rp1_dma[2] = {0x02000000, 0, 0x1000000000, 0x1000000000};
    windows = {};
    assert(!rpi5_pcie_windows_plan(&fixture,
        RPI5_PCIE_WINDOW_ACK_FOUR_BYTES, &windows.plan));
    windows.state = RPI5_PCIE_WINDOWS_COMPLETE;
    windows.plan.inbound[0].bar_lo &= ~UINT32_C(31);
    windows.plan.inbound[2].bar_lo &= ~UINT32_C(31);
    windows.io.physical_base = 0x1000120000;
    windows.io.mapped_bytes = 0x9310;
    released_windows = {};
    rpi5_pcie_released_windows_io io = {
        &model, 0x1000120000, 0x9310, owner, read32, order};
    assert(!rpi5_pcie_released_windows_init(&released_windows, &windows, &io));
    released = &released_windows;
    model.regs[0x4068 / 4] = 0x80;
    for (unsigned index = 0; index < 3; index++) {
        auto &entry = windows.plan.inbound[index];
        model.regs[(0x402c + 8 * index) / 4] = entry.bar_lo;
        model.regs[(0x4030 + 8 * index) / 4] = entry.bar_hi;
        model.regs[(0x40ac + 8 * index) / 4] = entry.remap_lo;
        model.regs[(0x40b0 + 8 * index) / 4] = entry.remap_hi;
    }
    for (unsigned index = 0; index < 2; index++) {
        auto &entry = windows.plan.outbound[index];
        model.regs[(0x400c + 8 * index) / 4] = entry.pci_lo;
        model.regs[(0x4010 + 8 * index) / 4] = entry.pci_hi;
        model.regs[(0x4070 + 4 * index) / 4] = entry.base_limit;
        model.regs[(0x4080 + 8 * index) / 4] = entry.base_hi;
        model.regs[(0x4084 + 8 * index) / 4] = entry.limit_hi;
    }
    model.regs[(0x4070 + 4 * 2) / 4] = 0xfff0;
    model.regs[(0x4070 + 4 * 3) / 4] = 0xfff0;
    caps = {};
    caps.interface_version = 0x110;
    caps.capability_length = 0x20;
    caps.max_slots = 64;
    caps.max_interrupters = 4;
    caps.max_ports = 3;
    caps.max_scratchpad_buffers = 64;
    caps.address_64 = 1;
    caps.context_64 = 1;
}

int
main()
{
    rpi5_pcie_windows windows;
    rpi5_pcie_released_windows released_windows;
    setup(windows, released_windows);
    BCM2712USBXHCIMemory good;
    active = &good;
    assert(good.prepare());
    unsigned prepare_calls = model.calls;
    assert(good.qualify(&released_windows, &caps));
    unsigned all_calls = model.calls;
    assert(good.state() == BCM2712USBXHCIMemory::Held &&
        good.qualificationStep() == 12 && model.reads == 90);
    rpi5_usb_xhci_memory_observation observation = {};
    assert(good.observeCPUOwnedLayout(&observation));
    assert(observation.version == RPI5_USB_XHCI_MEMORY_VERSION &&
        observation.provider_bytes == 0x50000 &&
        observation.mapping_page_bytes == 0x4000 &&
        observation.mapping_pages == 20 &&
        observation.normal_nc_page_bitmap == 0xfffff &&
        observation.base_cpu_address == (uint64_t)allocation &&
        observation.base_physical_address == model.pa &&
        observation.base_rp1_dma_address == 0x1100000000 &&
        observation.layout.scratchpad_count == 64 &&
        observation.layout.command_ring.offset == 0x1000 &&
        observation.layout.event_ring.offset == 0x2000 &&
        observation.layout.keyboard_buffer.offset == 0x49000);
    for (unsigned index = 0; index < 20; index++) {
        assert(observation.page[index].index == index &&
            observation.page[index].cache_attribute == VM_WIMG_WCOMB &&
            observation.page[index].retained_valid == 1 &&
            observation.page[index].static_valid == 1);
    }
    struct rpi5_xhci_noop_image image = {};
    assert(good.stageNoOpCommand(&caps, &image));
    assert(good.state() == BCM2712USBXHCIMemory::Staged &&
        image.bytes_zeroed == 0x50000 && image.scratchpad_count == 64 &&
        image.noop_control == 0x5c01 && image.link_control == 0x1803);
    assert(good.observeCPUOwnedLayout(&observation));
    assert(!good.discardBeforeAdmission());

    setup(windows, released_windows);
    BCM2712USBXHCIMemory enumeration;
    active = &enumeration;
    assert(enumeration.prepare());
    assert(enumeration.qualify(&released_windows, &caps));
    rpi5_xhci_noop_image enumeration_base = {};
    struct rpi5_usb_xhci_enable_slot_plan enable = {};
    struct rpi5_usb_xhci_descriptor_batch batch = {};
    assert(enumeration.stageK65Enumeration(&caps, &enumeration_base,
        &enable, &batch));
    assert(enumeration.state() == BCM2712USBXHCIMemory::Staged &&
        enumeration_base.dcbaa_dma == 0x1100000000 &&
        enable.command_trb_dma == 0x1100001000 &&
        enable.command_control == 0x2401 && batch.transfer_count == 4 &&
        batch.trb_count == 12 && batch.ring_dma == 0x1100046000);
    struct rpi5_usb_xhci_address_device_plan address = {};
    assert(enumeration.stageK65Address(5, &address));
    assert(enumeration.state() == BCM2712USBXHCIMemory::Staged &&
        address.slot == 5 && address.root_port == 2 &&
        address.command_trb_dma == 0x1100001010 &&
        address.input_context_dma == 0x1100045000);
    auto *usb_device = reinterpret_cast<uint32_t *>(allocation + 0x44000);
    usb_device[0] = 0x08300000;
    usb_device[1] = 0x00020000;
    usb_device[3] = 0x10000001;
    const struct rpi5_usb_boot_keyboard_identity keyboard = {
        .vendor = RPI5_USB_K65_VENDOR,
        .product = RPI5_USB_K65_PRODUCT,
        .report_descriptor_bytes = 154,
        .endpoint_max_packet = 16,
        .configuration = 1,
        .interface = 0,
        .alternate = 0,
        .endpoint = 0x81,
        .interval = 4,
    };
    struct rpi5_usb_xhci_keyboard_endpoint_plan keyboard_endpoint = {};
    struct rpi5_usb_hid_boot_setup_plan keyboard_setup = {};
    struct rpi5_usb_xhci_keyboard_interrupt_plan keyboard_interrupt = {};
    assert(enumeration.stageK65Keyboard(&keyboard, &keyboard_endpoint,
        &keyboard_setup, &keyboard_interrupt));
    assert(enumeration.state() == BCM2712USBXHCIMemory::Staged &&
        keyboard_endpoint.slot == 5 && keyboard_endpoint.endpoint_id == 3 &&
        keyboard_endpoint.command_trb_dma == 0x1100001020 &&
        keyboard_setup.transfer_count == 3 && keyboard_setup.trb_count == 6 &&
        keyboard_interrupt.endpoint_id == 3 &&
        keyboard_interrupt.normal_trb_dma == 0x1100047000 &&
        keyboard_interrupt.report_dma == 0x1100049000);
    assert(!enumeration.stageK65Address(0, &address));

    setup(windows, released_windows);
    BCM2712USBXHCIMemory streaming;
    active = &streaming;
    assert(streaming.prepare());
    assert(streaming.qualify(&released_windows, &caps));
    assert(streaming.stageK65Enumeration(&caps, &enumeration_base,
        &enable, &batch));
    assert(streaming.stageK65Address(5, &address));
    usb_device = reinterpret_cast<uint32_t *>(allocation + 0x44000);
    usb_device[0] = 0x08300000;
    usb_device[1] = 0x00020000;
    usb_device[3] = 0x10000001;
    struct rpi5_usb_xhci_keyboard_stream_plan keyboard_stream = {};
    assert(streaming.stageK65KeyboardStream(&keyboard, &keyboard_endpoint,
        &keyboard_setup, &keyboard_stream));
    assert(streaming.state() == BCM2712USBXHCIMemory::Staged &&
        keyboard_setup.idle_duration == 0 &&
        keyboard_setup.transfer[2].setup_packet == 0x0000000000000a21 &&
        keyboard_stream.endpoint_id == 3 &&
        keyboard_stream.report_count == 255 &&
        keyboard_stream.first_trb_dma == 0x1100047000 &&
        keyboard_stream.last_trb_dma == 0x1100047fe0 &&
        keyboard_stream.report_dma == 0x1100049000);

    unsigned faults = 0;
    for (unsigned fail = 1; fail <= prepare_calls; fail++) {
        setup(windows, released_windows);
        BCM2712USBXHCIMemory memory;
        active = &memory;
        model.fail = fail;
        assert(!memory.prepare());
        assert(!memory.prepare());
        if (memory.state() != BCM2712USBXHCIMemory::Quarantined) {
            model.fail = 0;
            assert(memory.discardBeforeAdmission());
        }
        faults++;
    }
    for (unsigned fail = prepare_calls + 1; fail <= all_calls; fail++) {
        setup(windows, released_windows);
        BCM2712USBXHCIMemory memory;
        active = &memory;
        assert(memory.prepare());
        model.fail = fail;
        assert(!memory.qualify(&released_windows, &caps));
        assert(memory.state() == BCM2712USBXHCIMemory::Quarantined);
        assert(!memory.discardBeforeAdmission());
        faults++;
    }
    for (auto hook : {reenter, change_thread}) {
        setup(windows, released_windows);
        BCM2712USBXHCIMemory memory;
        active = &memory;
        assert(memory.prepare());
        model.trigger = model.calls + 1;
        model.hook = hook;
        assert(!memory.qualify(&released_windows, &caps));
        assert(memory.state() == BCM2712USBXHCIMemory::Quarantined);
        faults++;
    }
    setup(windows, released_windows);
    BCM2712USBXHCIMemory bad_caps;
    active = &bad_caps;
    assert(bad_caps.prepare());
    caps.address_64 = 0;
    assert(!bad_caps.qualify(&released_windows, &caps));
    assert(bad_caps.state() == BCM2712USBXHCIMemory::Quarantined &&
        bad_caps.qualificationStep() == 9);
    faults++;

    setup(windows, released_windows);
    BCM2712USBXHCIMemory discard;
    assert(discard.prepare());
    assert(discard.discardBeforeAdmission());
    assert(model.complete == 1 && model.clear == 1 && model.releases == 3);

    printf("USB_XHCI_APPLE_MEMORY_PASS faults=%u prep=%u total=%u "
        "live_reads=90 NO_HARDWARE_PROOF\n", faults, prepare_calls, all_calls);
    return 0;
}
