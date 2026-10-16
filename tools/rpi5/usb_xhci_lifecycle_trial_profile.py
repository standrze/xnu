# SPDX-License-Identifier: BSD-2-Clause
"""Bounded RP1 USB0 xHCI halt/reset lifecycle layered on USB-1 evidence."""
from pathlib import Path

from tools.rpi5 import usb_xhci_caps_trial_profile as parent


ROOT = parent.ROOT
BOOTARGS = parent.BOOTARGS
FROZEN = ROOT / "build/rpi5/usb-xhci-caps-candidate-20261014-v4/overlay"


def _replace(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError("exact USB lifecycle trial anchor differs")
    return text.replace(old, new)


def marker(tag):
    return ("RPI5XNU:USB_XHCI_LIFECYCLE:ENTRY TAG=" + tag +
        " CPUS=1 HALT_RESET_ONLY NO_PORT NO_IRQ NO_BME NO_DMA")


def derive():
    files = {path.name: path.read_bytes() for path in FROZEN.iterdir() if path.is_file()}
    files["rp1_usb_xhci_lifecycle.h"] = (
        ROOT / "loader/rpi5/rp1_usb_xhci_lifecycle.h").read_bytes()

    header = files["BCM2712PCIePHYTransport.h"].decode()
    header = _replace(header, '#include "rp1_usb_xhci_caps.h"',
        '#include "rp1_usb_xhci_caps.h"\n#include "rp1_usb_xhci_lifecycle.h"')
    header = _replace(header,
        "    int usbCapabilityError=0;\n",
        "    int usbCapabilityError=0;\n"
        "    struct rpi5_xhci_lifecycle_observation usbLifecycleObserved={};\n"
        "    static int usbLifecycleRead(void *,uint32_t,uint32_t *);\n"
        "    static int usbLifecycleWrite(void *,uint32_t,uint32_t);\n"
        "    static int usbLifecycleDelay(void *,uint32_t);\n"
        "    static int usbLifecycleGuard(void *);\n")
    header = _replace(header,
        "    const struct rpi5_rp1_xhci_caps &usbObservation() const { return usbCapabilityObserved; }\n",
        "    const struct rpi5_rp1_xhci_caps &usbObservation() const { return usbCapabilityObserved; }\n"
        "    const struct rpi5_xhci_lifecycle_observation &usbLifecycleObservation() const { return usbLifecycleObserved; }\n")
    files["BCM2712PCIePHYTransport.h"] = header.encode()

    identify = files["BCM2712RP1GEMIdentifyTransport.inc"].decode()
    anchor = '''    usbCapabilityStep=5;
    if(usbCapabilityMap->unmap()!=kIOReturnSuccess || usbCapabilityMap->getVirtualAddress()) {'''
    replacement = '''    usbCapabilityObserved=decoded;usbCapabilityStep=5;
    struct rpi5_xhci_lifecycle_io lifecycleIO={this,usbLifecycleRead,
        usbLifecycleWrite,usbLifecycleDelay,usbLifecycleGuard};
    if(rpi5_rp1_xhci_halt_reset(usbCapabilityRaw[0],&lifecycleIO,&usbLifecycleObserved)) {
        usbCapabilityError=-12;return false;
    }
    usbCapabilityStep=7;
    if(usbCapabilityMap->unmap()!=kIOReturnSuccess || usbCapabilityMap->getVirtualAddress()) {'''
    identify = _replace(identify, anchor, replacement)
    identify = _replace(identify,
        "    usbCapabilityObserved=decoded;usbCapabilityStep=6;return true;\n}",
        "    usbCapabilityStep=8;return true;\n}\n")
    implementation = r'''
int BCM2712PCIePHYTransport::usbLifecycleGuard(void *context)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    return !self || !self->usbCapabilityMap || !self->usbCapabilityBacking ||
        !self->onOwnerThread() || self->checkingLifecycle || !self->guard() ||
        gemSource(self,&self->gemSession,&self->decodeCycle) ? -1 : 0;
}

int BCM2712PCIePHYTransport::usbLifecycleRead(void *context,uint32_t offset,uint32_t *value)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!value || usbLifecycleGuard(context) || (offset&3) ||
        offset>self->usbCapabilityMap->getLength()-sizeof(uint32_t))return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    *value=*reinterpret_cast<volatile uint32_t *>(self->usbCapabilityMap->getVirtualAddress()+offset);
    __asm__ volatile("dsb sy" ::: "memory");
    return usbLifecycleGuard(context);
}

int BCM2712PCIePHYTransport::usbLifecycleWrite(void *context,uint32_t offset,uint32_t value)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(usbLifecycleGuard(context) || offset!=self->usbCapabilityObserved.capability_length)return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    *reinterpret_cast<volatile uint32_t *>(self->usbCapabilityMap->getVirtualAddress()+offset)=value;
    __asm__ volatile("dsb sy" ::: "memory");
    return usbLifecycleGuard(context);
}

int BCM2712PCIePHYTransport::usbLifecycleDelay(void *context,uint32_t us)
{
    if(usbLifecycleGuard(context) || !us || us>1000)return -1;
    IODelay(us);
    return usbLifecycleGuard(context);
}
'''
    identify += implementation
    files["BCM2712RP1GEMIdentifyTransport.inc"] = identify.encode()

    progress = files["BCM2712PCIeIDTrialProgress.inc"].decode()
    progress = _replace(progress,
        "BEGIN USB_XHCI_CAPS READ_ONLY NO_RESET NO_PORT NO_IRQ NO_BME NO_DMA",
        "BEGIN USB_XHCI_LIFECYCLE HALT_RESET_ONLY NO_PORT NO_IRQ NO_BME NO_DMA")
    progress = _replace(progress,
        '    const auto *usb=transport?&transport->usbObservation():nullptr;\n',
        '    const auto *usb=transport?&transport->usbObservation():nullptr;\n'
        '    const auto *life=transport?&transport->usbLifecycleObservation():nullptr;\n')
    lifecycle_row = r'''    kprintf("RPI5XNU:USB_XHCI_LIFECYCLE:STATE STEP=%u ERROR=%d READS=%u WRITES=%u POLLS=%u DELAY_US=%u OP=%08x CMD0=%08x STS0=%08x HALT_CMD=%08x HALT_STS=%08x RESET_CMD=%08x CMD1=%08x STS1=%08x\n",
        life?life->step:0,life?life->error:0,life?life->reads:0,life?life->writes:0,
        life?life->polls:0,life?life->delayed_us:0,life?life->operational_base:0,
        life?life->command_before:0,life?life->status_before:0,life?life->halt_command:0,
        life?life->status_halted:0,life?life->reset_command:0,life?life->command_after:0,
        life?life->status_after:0);
'''
    progress = _replace(progress,
        '    kprintf("RPI5XNU:USB_XHCI_CAPS:DECODE VERSION=%04x',
        lifecycle_row + '    kprintf("RPI5XNU:USB_XHCI_CAPS:DECODE VERSION=%04x')
    files["BCM2712PCIeIDTrialProgress.inc"] = progress.encode()
    return files


def loader(original):
    return parent.loader(original).replace(
        "RPI5XNU:USB_XHCI_CAPS:ENTRY TAG=",
        "RPI5XNU:USB_XHCI_LIFECYCLE:ENTRY TAG=").replace(
        "CPUS=1 READ_ONLY NO_RESET NO_PORT NO_IRQ NO_BME NO_DMA",
        "CPUS=1 HALT_RESET_ONLY NO_PORT NO_IRQ NO_BME NO_DMA")


def psci(original):
    return parent.psci(original)


def sources():
    return [Path(__file__).resolve(), *sorted(FROZEN.iterdir()),
        ROOT / "loader/rpi5/rp1_usb_xhci_lifecycle.h",
        ROOT / "loader/rpi5/rp1_usb_xhci_lifecycle.c",
        ROOT / "tools/rpi5/tests/rp1_usb_xhci_lifecycle_host.c",
        ROOT / "tools/rpi5/tests/test_rp1_usb_xhci_lifecycle.py"]
