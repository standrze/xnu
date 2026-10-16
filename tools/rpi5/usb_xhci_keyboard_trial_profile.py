# SPDX-License-Identifier: BSD-2-Clause
"""First K65 interrupt-IN report layered on the passed USB-4 gate."""
from pathlib import Path

from tools.rpi5 import usb_xhci_enumerate_trial_profile as parent


ROOT = parent.ROOT
BOOTARGS = parent.BOOTARGS


def _replace(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError("exact USB keyboard trial anchor differs")
    return text.replace(old, new)


def marker(tag):
    return ("RPI5XNU:USB_XHCI_KBD:ENTRY TAG=" + tag +
        " CPUS=1 POLLING PORT2 SLOT ADDRESS EP0 K65 DCI3 HID_SETUP "
        "REPORT8 NO_IRQ BME_LEASE DMA")


def derive():
    files = parent.derive()
    for name, relative in {
        "usb_hid_boot_keyboard.h": "loader/rpi5/usb_hid_boot_keyboard.h",
        "usb_hid_boot_setup.h": "loader/rpi5/usb_hid_boot_setup.h",
        "usb_xhci_keyboard_endpoint.h":
            "loader/rpi5/usb_xhci_keyboard_endpoint.h",
        "rp1_usb_xhci_keyboard_input.h":
            "loader/rpi5/rp1_usb_xhci_keyboard_input.h",
    }.items():
        files[name] = (ROOT / relative).read_bytes()

    header = files["BCM2712PCIePHYTransport.h"].decode()
    header = _replace(header, '#include "rp1_usb_xhci_enumerate.h"',
        '#include "rp1_usb_xhci_enumerate.h"\n'
        '#include "rp1_usb_xhci_keyboard_input.h"')
    header = _replace(header,
        '''    struct rpi5_usb_xhci_descriptor_batch usbDescriptorBatch={};
    struct rpi5_xhci_enumerate_observation usbEnumerationObserved={};''',
        '''    struct rpi5_usb_xhci_descriptor_batch usbDescriptorBatch={};
    struct rpi5_xhci_enumerate_observation usbEnumerationObserved={};
    struct rpi5_usb_xhci_keyboard_endpoint_plan usbKeyboardEndpoint={};
    struct rpi5_usb_hid_boot_setup_plan usbKeyboardSetup={};
    struct rpi5_usb_xhci_keyboard_interrupt_plan usbKeyboardInterrupt={};
    struct rpi5_xhci_keyboard_input_observation usbKeyboardObserved={};''')
    header = _replace(header,
        '''    const struct rpi5_usb_xhci_descriptor_batch &usbDescriptorBatchObservation() const { return usbDescriptorBatch; }
    const struct rpi5_xhci_enumerate_observation &usbEnumerationObservation() const { return usbEnumerationObserved; }''',
        '''    const struct rpi5_usb_xhci_descriptor_batch &usbDescriptorBatchObservation() const { return usbDescriptorBatch; }
    const struct rpi5_xhci_enumerate_observation &usbEnumerationObservation() const { return usbEnumerationObserved; }
    const struct rpi5_usb_xhci_keyboard_endpoint_plan &usbKeyboardEndpointObservation() const { return usbKeyboardEndpoint; }
    const struct rpi5_usb_hid_boot_setup_plan &usbKeyboardSetupObservation() const { return usbKeyboardSetup; }
    const struct rpi5_usb_xhci_keyboard_interrupt_plan &usbKeyboardInterruptObservation() const { return usbKeyboardInterrupt; }
    const struct rpi5_xhci_keyboard_input_observation &usbKeyboardObservation() const { return usbKeyboardObserved; }''')
    files["BCM2712PCIePHYTransport.h"] = header.encode()

    progress = files["BCM2712PCIeIDTrialProgress.inc"].decode()
    progress = progress.replace("USB_XHCI_ENUM", "USB_XHCI_KBD")
    progress = _replace(progress,
        "BEGIN USB_XHCI_KBD POLLING PORT2 SLOT ADDRESS EP0 K65 NO_IRQ BME_LEASE DMA",
        "BEGIN USB_XHCI_KBD POLLING PORT2 SLOT ADDRESS EP0 K65 DCI3 HID_SETUP REPORT8 NO_IRQ BME_LEASE DMA")
    progress = _replace(progress,
        '''    const auto *run=transport?&transport->usbEnumerationObservation():nullptr;
    const auto *bme=transport?&transport->usbBMEObservation():nullptr;''',
        '''    const auto *run=transport?&transport->usbEnumerationObservation():nullptr;
    const auto *kbdEndpoint=transport?&transport->usbKeyboardEndpointObservation():nullptr;
    const auto *kbdSetup=transport?&transport->usbKeyboardSetupObservation():nullptr;
    const auto *kbdInterrupt=transport?&transport->usbKeyboardInterruptObservation():nullptr;
    const auto *kbd=transport?&transport->usbKeyboardObservation():nullptr;
    const auto *bme=transport?&transport->usbBMEObservation():nullptr;''')
    anchor = '''        run?run->keyboard.endpoint:0,run?run->keyboard.endpoint_max_packet:0,
        run?run->keyboard.interval:0,run?run->keyboard.report_descriptor_bytes:0);
'''
    rows = anchor + '''    kprintf("RPI5XNU:USB_XHCI_KBD:KBD_PLAN SLOT=%u DCI=%u COMMAND=%llu SETUP_FIRST=%u SETUP_COUNT=%u REPORT_DMA=%llu REPORT_BYTES=%u\\n",
        kbdEndpoint?kbdEndpoint->slot:0,kbdEndpoint?kbdEndpoint->endpoint_id:0,
        (unsigned long long)(kbdEndpoint?kbdEndpoint->command_trb_dma:0),
        kbdSetup?kbdSetup->first_trb:0,kbdSetup?kbdSetup->transfer_count:0,
        (unsigned long long)(kbdInterrupt?kbdInterrupt->report_dma:0),
        kbdInterrupt?kbdInterrupt->report_bytes:0);
    kprintf("RPI5XNU:USB_XHCI_KBD:KBD_RUN STEP=%u ERROR=%d READS=%u WRITES=%u POLLS=%u DELAY_US=%u DMA_CHECKS=%u EVENT_INDEX=%u PSC=%u SLOT=%u DCI=%u TRANSFER=%u EVENT_PARAM=%llu EVENT_STATUS=%08x EVENT_CONTROL=%08x REPORT=%02x%02x%02x%02x%02x%02x%02x%02x OUTPUT_COUNT=%u OUTPUT0=%02x HALT_CMD=%08x HALT_STS=%08x\\n",
        kbd?kbd->step:0,kbd?kbd->error:0,kbd?kbd->reads:0,kbd?kbd->writes:0,
        kbd?kbd->polls:0,kbd?kbd->delayed_us:0,kbd?kbd->dma_checks:0,
        kbd?kbd->event_index:0,kbd?kbd->port_status_events:0,
        kbd?kbd->slot:0,kbd?kbd->endpoint_id:0,
        kbd?kbd->transfer_index:0,
        (unsigned long long)(kbd?kbd->event_parameter:0),
        kbd?kbd->event_status:0,kbd?kbd->event_control:0,
        kbd?kbd->report[0]:0,kbd?kbd->report[1]:0,kbd?kbd->report[2]:0,
        kbd?kbd->report[3]:0,kbd?kbd->report[4]:0,kbd?kbd->report[5]:0,
        kbd?kbd->report[6]:0,kbd?kbd->report[7]:0,kbd?kbd->output_count:0,
        kbd&&kbd->output_count?kbd->output[0]:0,
        kbd?kbd->command_halted:0,kbd?kbd->status_halted:0);
'''
    progress = _replace(progress, anchor, rows)
    progress = _replace(progress,
        "EVENT_INDEX=%u HALT_CMD=%08x HALT_STS=%08x\\n\",",
        "EVENT_INDEX=%u HALT_CMD=%08x HALT_STS=%08x LIVE=%u\\n\",")
    progress = _replace(progress,
        "run?run->command_halted:0,run?run->status_halted:0);",
        "run?run->command_halted:0,run?run->status_halted:0,"
        "run?run->left_running:0);")
    files["BCM2712PCIeIDTrialProgress.inc"] = progress.encode()

    identify = files["BCM2712RP1GEMIdentifyTransport.inc"].decode()
    identify = identify.replace("USB_XHCI_ENUM", "USB_XHCI_KBD")
    identify = _replace(identify, "rpi5_rp1_xhci_enumerate_k65(",
        "rpi5_rp1_xhci_enumerate_k65_live(")
    identify = _replace(identify,
        '''    const bool slotDoorbell=self->usbEnumerationSlot &&
        offset==db+self->usbEnumerationSlot*4 && value==1;''',
        '''    const bool slotDoorbell=self->usbEnumerationSlot &&
        offset==db+self->usbEnumerationSlot*4 && (value==1||value==3);''')
    identify = _replace(identify,
        '''    usbNoopStep=5;
    if(rpi5_rp1_usb_bme_disable(&usbBME)) { usbNoopError=-5;return false; }
    dmaRingActive=false;usbDMAActive=false;usbNoopStep=6;return true;''',
        '''    usbNoopStep=5;
    if(!dmaMemory->stageK65Keyboard(&usbEnumerationObserved.keyboard,
            &usbKeyboardEndpoint,&usbKeyboardSetup,&usbKeyboardInterrupt)) {
        usbNoopError=-5;return false;
    }
    const struct rpi5_xhci_keyboard_input_io keyboardIO={this,usbNoopRead,
        usbNoopWrite,usbNoopDelay,usbNoopGuard,usbDMAGuard};
    usbNoopStep=6;
    if(rpi5_rp1_xhci_k65_keyboard_input(&usbCapabilityObserved,&layout,
            &usbEnumerationObserved,&usbKeyboardEndpoint,&usbKeyboardSetup,
            &usbKeyboardInterrupt,&keyboardIO,&usbKeyboardObserved)) {
        usbNoopError=-6;return false;
    }
    usbNoopStep=7;
    if(rpi5_rp1_usb_bme_disable(&usbBME)) { usbNoopError=-7;return false; }
    dmaRingActive=false;usbDMAActive=false;usbNoopStep=8;return true;''')
    files["BCM2712RP1GEMIdentifyTransport.inc"] = identify.encode()
    return files


def loader(original):
    return parent.loader(original).replace("USB_XHCI_ENUM", "USB_XHCI_KBD").replace(
        "CPUS=1 POLLING PORT2 SLOT ADDRESS EP0 K65 NO_IRQ BME_LEASE DMA",
        "CPUS=1 POLLING PORT2 SLOT ADDRESS EP0 K65 DCI3 HID_SETUP REPORT8 NO_IRQ BME_LEASE DMA")


def psci(original):
    return parent.psci(original)


def sources():
    own = [
        ROOT / "loader/rpi5/usb_hid_boot_keyboard.h",
        ROOT / "loader/rpi5/usb_hid_boot_keyboard.c",
        ROOT / "loader/rpi5/usb_hid_boot_setup.h",
        ROOT / "loader/rpi5/usb_hid_boot_setup.c",
        ROOT / "loader/rpi5/usb_xhci_keyboard_endpoint.h",
        ROOT / "loader/rpi5/usb_xhci_keyboard_endpoint.c",
        ROOT / "loader/rpi5/rp1_usb_xhci_keyboard_input.h",
        ROOT / "loader/rpi5/rp1_usb_xhci_keyboard_input.c",
    ]
    return list(dict.fromkeys([Path(__file__).resolve(), *parent.sources(), *own]))
