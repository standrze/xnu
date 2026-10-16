# SPDX-License-Identifier: BSD-2-Clause
"""K65 polling-enumeration composition layered on the passed USB-3 gate."""
from pathlib import Path

from tools.rpi5 import usb_xhci_noop_trial_profile as parent


ROOT = parent.ROOT
BOOTARGS = parent.BOOTARGS


def _replace(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError("exact USB enumeration trial anchor differs")
    return text.replace(old, new)


def marker(tag):
    return ("RPI5XNU:USB_XHCI_ENUM:ENTRY TAG=" + tag +
        " CPUS=1 POLLING PORT2 SLOT ADDRESS EP0 K65 NO_IRQ BME_LEASE DMA")


def derive():
    files = parent.derive()
    for name, relative in {
        "rp1_usb_xhci_port_reset.h": "loader/rpi5/rp1_usb_xhci_port_reset.h",
        "usb_xhci_device_context.h": "loader/rpi5/usb_xhci_device_context.h",
        "usb_xhci_control_transfer.h": "loader/rpi5/usb_xhci_control_transfer.h",
        "usb_hid_boot_descriptor.h": "loader/rpi5/usb_hid_boot_descriptor.h",
        "rp1_usb_xhci_enumerate.h": "loader/rpi5/rp1_usb_xhci_enumerate.h",
    }.items():
        files[name] = (ROOT / relative).read_bytes()

    header = files["BCM2712PCIePHYTransport.h"].decode()
    header = _replace(header, '#include "rp1_usb_xhci_noop_run.h"',
        '#include "rp1_usb_xhci_enumerate.h"')
    header = _replace(header,
        '''    struct rpi5_xhci_noop_image usbNoopImage={};
    struct rpi5_xhci_noop_run_observation usbNoopObserved={};''',
        '''    struct rpi5_xhci_noop_image usbNoopImage={};
    struct rpi5_usb_xhci_enable_slot_plan usbEnable={};
    struct rpi5_usb_xhci_descriptor_batch usbDescriptorBatch={};
    struct rpi5_xhci_enumerate_observation usbEnumerationObserved={};''')
    header = _replace(header,
        '''    bool usbDMAActive=false,usbQualificationActive=false;
    unsigned usbNoopStep=0;''',
        '''    bool usbDMAActive=false,usbQualificationActive=false;
    uint8_t usbEnumerationSlot=0;
    unsigned usbNoopStep=0;''')
    header = _replace(header,
        '''    static int usbBMETransfer(void *,const struct rpi5_pcie_config_request *,uint32_t *);
    bool runUSBNoOp();''',
        '''    static int usbBMETransfer(void *,const struct rpi5_pcie_config_request *,uint32_t *);
    static int usbStageAddress(void *,uint8_t,struct rpi5_usb_xhci_address_device_plan *);
    bool runUSBEnumeration();''')
    header = _replace(header,
        '''    const struct rpi5_xhci_noop_image &usbNoopImageObservation() const { return usbNoopImage; }
    const struct rpi5_xhci_noop_run_observation &usbNoopRunObservation() const { return usbNoopObserved; }''',
        '''    const struct rpi5_xhci_noop_image &usbNoopImageObservation() const { return usbNoopImage; }
    const struct rpi5_usb_xhci_enable_slot_plan &usbEnableObservation() const { return usbEnable; }
    const struct rpi5_usb_xhci_descriptor_batch &usbDescriptorBatchObservation() const { return usbDescriptorBatch; }
    const struct rpi5_xhci_enumerate_observation &usbEnumerationObservation() const { return usbEnumerationObserved; }''')
    files["BCM2712PCIePHYTransport.h"] = header.encode()

    progress = files["BCM2712PCIeIDTrialProgress.inc"].decode()
    progress = progress.replace("USB_XHCI_NOOP", "USB_XHCI_ENUM")
    progress = _replace(progress,
        "BEGIN USB_XHCI_ENUM POLLING ONE_NOOP NO_PORT NO_IRQ BME_LEASE DMA",
        "BEGIN USB_XHCI_ENUM POLLING PORT2 SLOT ADDRESS EP0 K65 NO_IRQ BME_LEASE DMA")
    progress = _replace(progress,
        '''    const auto *run=transport?&transport->usbNoopRunObservation():nullptr;
    const auto *bme=transport?&transport->usbBMEObservation():nullptr;''',
        '''    const auto *enable=transport?&transport->usbEnableObservation():nullptr;
    const auto *batch=transport?&transport->usbDescriptorBatchObservation():nullptr;
    const auto *run=transport?&transport->usbEnumerationObservation():nullptr;
    const auto *bme=transport?&transport->usbBMEObservation():nullptr;''')
    old_start = progress.index(
        '    kprintf("RPI5XNU:USB_XHCI_ENUM:RUN STEP=')
    old_end = progress.index('\n', progress.index(');', old_start)) + 1
    rows = '''    kprintf("RPI5XNU:USB_XHCI_ENUM:PLAN ENABLE=%llu ENABLE_CTL=%08x TD_COUNT=%u TRB_COUNT=%u RING=%llu\\n",
        (unsigned long long)(enable?enable->command_trb_dma:0),enable?enable->command_control:0,
        batch?batch->transfer_count:0,batch?batch->trb_count:0,
        (unsigned long long)(batch?batch->ring_dma:0));
    kprintf("RPI5XNU:USB_XHCI_ENUM:RUN STEP=%u ERROR=%d READS=%u WRITES=%u POLLS=%u DELAY_US=%u DMA_CHECKS=%u SLOT=%u PSC=%u EVENT_INDEX=%u HALT_CMD=%08x HALT_STS=%08x\\n",
        run?run->step:0,run?run->error:0,run?run->reads:0,run?run->writes:0,
        run?run->polls:0,run?run->delayed_us:0,run?run->dma_checks:0,
        run?run->slot:0,run?run->port_status_events:0,run?run->event_index:0,
        run?run->command_halted:0,run?run->status_halted:0);
    kprintf("RPI5XNU:USB_XHCI_ENUM:PORT STEP=%u ERROR=%d PORT=%u OFFSET=%08x BEFORE=%08x AFTER=%08x FINAL=%08x SPEED=%u LINK=%u WRITES=%u POLLS=%u\\n",
        run?run->port.step:0,run?run->port.error:0,run?run->port.port:0,
        run?run->port.portsc_offset:0,run?run->port.before:0,run?run->port.after:0,
        run?run->port.final:0,run?run->port.speed:0,run?run->port.link_state:0,
        run?run->port.writes:0,run?run->port.polls:0);
    kprintf("RPI5XNU:USB_XHCI_ENUM:DEVICE SLOT=%u PORT=%u SPEED=%u EP0=%u ADDRESS_CMD=%llu VENDOR=%04x PRODUCT=%04x USB=%04x CONFIG_BYTES=%u INTERFACES=%u INTERFACE=%u ENDPOINT=%02x PACKET=%u INTERVAL=%u REPORT=%u\\n",
        run?run->address.slot:0,run?run->address.root_port:0,run?run->address.speed:0,
        run?run->address.endpoint0_max_packet:0,
        (unsigned long long)(run?run->address.command_trb_dma:0),
        run?run->keyboard.vendor:0,run?run->keyboard.product:0,
        run?run->keyboard.usb_version:0,run?run->keyboard.configuration_bytes:0,
        run?run->keyboard.interface_count:0,run?run->keyboard.interface:0,
        run?run->keyboard.endpoint:0,run?run->keyboard.endpoint_max_packet:0,
        run?run->keyboard.interval:0,run?run->keyboard.report_descriptor_bytes:0);
'''
    progress = progress[:old_start] + rows + progress[old_end:]
    files["BCM2712PCIeIDTrialProgress.inc"] = progress.encode()

    identify = files["BCM2712RP1GEMIdentifyTransport.inc"].decode()
    identify = _replace(identify,
        '''        !dmaMemory->stageNoOpCommand(&usbCapabilityObserved,&usbNoopImage)) {''',
        '''        !dmaMemory->stageK65Enumeration(&usbCapabilityObserved,&usbNoopImage,
            &usbEnable,&usbDescriptorBatch)) {''')
    identify = _replace(identify,
        "    if(!runUSBNoOp()) { usbCapabilityError=-14;return false; }",
        "    if(!runUSBEnumeration()) { usbCapabilityError=-14;return false; }")
    identify = _replace(identify,
        '''    bool allowed=offset==op || offset==op+4 || offset==op+8 || offset==rt+0x20;''',
        '''    bool allowed=offset==op || offset==op+4 || offset==op+8 ||
        offset==op+0x410 || offset==rt+0x20;''')
    old = '''    bool allowed=offset==op || offset==op+0x18 || offset==op+0x1c ||
        offset==op+0x30 || offset==op+0x34 || offset==op+0x38 ||
        offset==rt+0x24 || offset==rt+0x28 || offset==rt+0x30 ||
        offset==rt+0x34 || offset==rt+0x38 || offset==rt+0x3c || offset==db;
    if(!allowed || offset>self->usbCapabilityMap->getLength()-4)return -1;'''
    new = '''    const bool setup=offset==op || offset==op+0x18 || offset==op+0x1c ||
        offset==op+0x30 || offset==op+0x34 || offset==op+0x38 ||
        offset==rt+0x24 || offset==rt+0x28 || offset==rt+0x30 ||
        offset==rt+0x34 || offset==rt+0x38 || offset==rt+0x3c;
    const bool port=offset==op+0x410;
    const bool controllerDoorbell=offset==db && value==0;
    const bool slotDoorbell=self->usbEnumerationSlot &&
        offset==db+self->usbEnumerationSlot*4 && value==1;
    if((!setup&&!port&&!controllerDoorbell&&!slotDoorbell) ||
        offset>self->usbCapabilityMap->getLength()-4)return -1;'''
    identify = _replace(identify, old, new)
    start = identify.index("bool BCM2712PCIePHYTransport::runUSBNoOp()")
    implementation = r'''int BCM2712PCIePHYTransport::usbStageAddress(void *context,uint8_t slot,
    struct rpi5_usb_xhci_address_device_plan *out)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || usbNoopGuard(context) || !out || self->usbEnumerationSlot ||
        !self->dmaMemory->stageK65Address(slot,out) || usbNoopGuard(context))return -1;
    self->usbEnumerationSlot=slot;
    return 0;
}

bool BCM2712PCIePHYTransport::runUSBEnumeration()
{
    usbNoopStep=1;usbNoopError=0;usbEnumerationSlot=0;
    if(usbDMAActive || !dmaMemory ||
        dmaMemory->state()!=BCM2712USBXHCIMemory::Staged ||
        usbLifecycleGuard(this)) { usbNoopError=-1;return false; }
    usbDMAActive=true;dmaRingAttempted=true;dmaRingActive=true;
    const struct rpi5_rp1_usb_bme_io bmeIO={this,usbBMEGuard,usbBMETransfer};
    usbNoopStep=2;
    if(rpi5_rp1_usb_bme_init(&usbBME,&bmeIO)) { usbNoopError=-2;return false; }
    usbNoopStep=3;
    if(rpi5_rp1_usb_bme_enable(&usbBME)) { usbNoopError=-3;return false; }
    const auto &layout=dmaObserved.layout;
    const struct rpi5_xhci_enumerate_io runIO={this,usbNoopRead,usbNoopWrite,
        usbNoopDelay,usbNoopGuard,usbDMAGuard,usbStageAddress};
    usbNoopStep=4;
    if(rpi5_rp1_xhci_enumerate_k65(&usbCapabilityObserved,&layout,&usbNoopImage,
        &usbEnable,&usbDescriptorBatch,&runIO,&usbEnumerationObserved)) {
        usbNoopError=-4;return false;
    }
    usbNoopStep=5;
    if(rpi5_rp1_usb_bme_disable(&usbBME)) { usbNoopError=-5;return false; }
    dmaRingActive=false;usbDMAActive=false;usbNoopStep=6;return true;
}
'''
    identify = identify[:start] + implementation
    identify = identify.replace("USB_XHCI_NOOP", "USB_XHCI_ENUM")
    files["BCM2712RP1GEMIdentifyTransport.inc"] = identify.encode()
    return files


def loader(original):
    return parent.loader(original).replace("USB_XHCI_NOOP", "USB_XHCI_ENUM").replace(
        "CPUS=1 POLLING ONE_NOOP NO_PORT NO_IRQ BME_LEASE DMA",
        "CPUS=1 POLLING PORT2 SLOT ADDRESS EP0 K65 NO_IRQ BME_LEASE DMA")


def psci(original):
    return parent.psci(original)


def sources():
    own = [
        ROOT / "loader/rpi5/rp1_usb_xhci_port_reset.h",
        ROOT / "loader/rpi5/rp1_usb_xhci_port_reset.c",
        ROOT / "loader/rpi5/usb_xhci_device_context.h",
        ROOT / "loader/rpi5/usb_xhci_device_context.c",
        ROOT / "loader/rpi5/usb_xhci_control_transfer.h",
        ROOT / "loader/rpi5/usb_xhci_control_transfer.c",
        ROOT / "loader/rpi5/usb_hid_boot_descriptor.h",
        ROOT / "loader/rpi5/usb_hid_boot_descriptor.c",
        ROOT / "loader/rpi5/rp1_usb_xhci_enumerate.h",
        ROOT / "loader/rpi5/rp1_usb_xhci_enumerate.c",
    ]
    return list(dict.fromkeys([Path(__file__).resolve(), *parent.sources(), *own]))
