# SPDX-License-Identifier: BSD-2-Clause
"""Read-only RP1 USB0/xHCI capability observer layered on the passed provider."""
from pathlib import Path

from tools.rpi5 import gem_full_provider_trial_profile as parent


ROOT = parent.ROOT
BOOTARGS = parent.BOOTARGS
FROZEN = ROOT / "build/rpi5/gem-full-provider-trial-20261014-v13/overlay"


def _replace(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError("exact USB capability trial anchor differs")
    return text.replace(old, new)


def marker(tag):
    return "RPI5XNU:USB_XHCI_CAPS:ENTRY TAG=" + tag + " CPUS=1 READ_ONLY NO_RESET NO_PORT NO_IRQ NO_BME NO_DMA"


def derive():
    files = {path.name: path.read_bytes() for path in FROZEN.iterdir() if path.is_file()}
    files["rp1_usb_xhci_caps.h"] = (ROOT / "loader/rpi5/rp1_usb_xhci_caps.h").read_bytes()

    header = files["BCM2712PCIePHYTransport.h"].decode()
    header = _replace(header, '#include "rpi5_gem_ram_window.h"',
        '#include "rpi5_gem_ram_window.h"\n#include "rp1_usb_xhci_caps.h"')
    header = _replace(header, "    int dmaObserveError=0;\n",
        "    int dmaObserveError=0;\n"
        "    IOMemoryMap *usbCapabilityMap=nullptr;\n"
        "    IOMemoryDescriptor *usbCapabilityBacking=nullptr;\n"
        "    uint32_t usbCapabilityRaw[2][RPI5_RP1_XHCI_CAP_WORDS]={};\n"
        "    struct rpi5_rp1_xhci_caps usbCapabilityObserved={};\n"
        "    uint64_t usbCapabilityPhysical=0;\n"
        "    unsigned usbCapabilityStep=0,usbCapabilityReads=0;\n"
        "    int usbCapabilityError=0;\n"
        "    bool observeUSB0Capabilities();\n")
    header = _replace(header,
        "    int dmaObservationError() const { return dmaObserveError; }\n",
        "    int dmaObservationError() const { return dmaObserveError; }\n"
        "    unsigned usbObservationStep() const { return usbCapabilityStep; }\n"
        "    int usbObservationError() const { return usbCapabilityError; }\n"
        "    unsigned usbObservationReads() const { return usbCapabilityReads; }\n"
        "    uint64_t usbObservationPhysical() const { return usbCapabilityPhysical; }\n"
        "    const uint32_t *usbObservationRaw(unsigned pass) const { return pass<2?usbCapabilityRaw[pass]:nullptr; }\n"
        "    const struct rpi5_rp1_xhci_caps &usbObservation() const { return usbCapabilityObserved; }\n")
    files["BCM2712PCIePHYTransport.h"] = header.encode()

    identify = files["BCM2712RP1GEMIdentifyTransport.inc"].decode()
    identify = _replace(identify,
        "    if(!self->observePreparedFullProvider())return -7;\n"
        "    self->diagGemCall=2;return 0;",
        "    if(!self->observePreparedFullProvider())return -7;\n"
        "    if(!self->observeUSB0Capabilities())return -8;\n"
        "    self->diagGemCall=2;return 0;")
    implementation = r'''
bool BCM2712PCIePHYTransport::observeUSB0Capabilities()
{
    usbCapabilityStep=1;usbCapabilityError=0;
    if(usbCapabilityMap || usbCapabilityBacking || usbCapabilityReads ||
        !onOwnerThread() || checkingLifecycle || !guard() ||
        gemSource(this,&gemSession,&decodeCycle)) {
        usbCapabilityError=-1;return false;
    }
    uint32_t childOffset=0,childLength=0;
    const auto &outbound=windows.plan.outbound[0];
    if(rpi5_rp1_usb_bar1_range(0,&childOffset,&childLength) ||
        binding.outbound_count!=2 || binding.outbound[0].pci_base ||
        outbound.pci_base || outbound.cpu_base!=binding.outbound[0].cpu_base ||
        outbound.declared_end!=binding.outbound[0].cpu_base+binding.outbound[0].size ||
        outbound.cpu_base!=UINT64_C(0x1f00000000) ||
        outbound.cpu_base>UINT64_MAX-childOffset ||
        outbound.cpu_base+childOffset>UINT64_MAX-childLength) {
        usbCapabilityError=-2;return false;
    }
    const uint64_t physical=outbound.cpu_base+childOffset;
    if(physical+childLength>outbound.declared_end ||
        rpi5_physical_memory_type(physical,physical+childLength)!=2) {
        usbCapabilityError=-3;return false;
    }
    usbCapabilityPhysical=physical;usbCapabilityStep=2;
    IOMemoryDescriptor *memory=IOMemoryDescriptor::withAddressRange(physical,childLength,
        kIODirectionNone|kIOMemoryMapperNone|kIOMemoryHostOnly|
        (kIOInhibitCache<<kIOMemoryBufferCacheShift),nullptr);
    if(!memory) { usbCapabilityError=-4;return false; }
    usbCapabilityMap=memory->map(kIOMapAnywhere|kIOMapInhibitCache);
    if(usbCapabilityMap)usbCapabilityBacking=memory;
    memory->release();
    IOByteCount segmentLength=0;
    if(!usbCapabilityMap || !usbCapabilityBacking ||
        usbCapabilityMap->getMemoryDescriptor()!=usbCapabilityBacking ||
        !usbCapabilityMap->getVirtualAddress() ||
        usbCapabilityMap->getLength()!=childLength ||
        (usbCapabilityMap->getMapOptions()&kIOMapCacheMask)!=kIOMapInhibitCache ||
        usbCapabilityMap->getPhysicalSegment(0,&segmentLength,kIOMemoryMapperNone)!=physical ||
        segmentLength!=childLength || !guard() ||
        gemSource(this,&gemSession,&decodeCycle)) {
        usbCapabilityError=-5;return false;
    }
    usbCapabilityStep=3;
    for(unsigned pass=0;pass<2;pass++)for(unsigned index=0;index<RPI5_RP1_XHCI_CAP_WORDS;index++) {
        const uint32_t offset=index*4;
        if(!guard() || gemSource(this,&gemSession,&decodeCycle)) {
            usbCapabilityError=-6;return false;
        }
        __asm__ volatile("dmb osh" ::: "memory");
        uint32_t value=*reinterpret_cast<volatile uint32_t *>(usbCapabilityMap->getVirtualAddress()+offset);
        __asm__ volatile("dsb sy" ::: "memory");
        if(value==UINT32_MAX || !guard() || gemSource(this,&gemSession,&decodeCycle)) {
            usbCapabilityError=-7;return false;
        }
        usbCapabilityRaw[pass][index]=value;usbCapabilityReads++;
    }
    usbCapabilityStep=4;
    for(unsigned index=0;index<RPI5_RP1_XHCI_CAP_WORDS;index++)
        if(usbCapabilityRaw[0][index]!=usbCapabilityRaw[1][index]) {
            usbCapabilityError=-8;return false;
        }
    struct rpi5_rp1_xhci_caps decoded={};
    if(rpi5_rp1_xhci_caps_decode(usbCapabilityRaw[0],&decoded)) {
        usbCapabilityError=-9;return false;
    }
    usbCapabilityStep=5;
    if(usbCapabilityMap->unmap()!=kIOReturnSuccess || usbCapabilityMap->getVirtualAddress()) {
        usbCapabilityError=-10;return false;
    }
    usbCapabilityMap->release();usbCapabilityMap=nullptr;usbCapabilityBacking=nullptr;
    if(!guard() || gemSource(this,&gemSession,&decodeCycle)) {
        usbCapabilityError=-11;return false;
    }
    usbCapabilityObserved=decoded;usbCapabilityStep=6;return true;
}
'''
    identify += implementation
    files["BCM2712RP1GEMIdentifyTransport.inc"] = identify.encode()

    progress = files["BCM2712PCIeIDTrialProgress.inc"].decode()
    progress = _replace(progress,
        'kprintf("RPI5XNU:PCIEID:BEGIN FULL_PROVIDER PREFERRED_RAM_ONLY NO_QUEUE NO_BME NO_DMA\\n");',
        'kprintf("RPI5XNU:PCIEID:BEGIN USB_XHCI_CAPS READ_ONLY NO_RESET NO_PORT NO_IRQ NO_BME NO_DMA\\n");')
    rows = r'''    const auto *usb=transport?&transport->usbObservation():nullptr;
    const uint32_t *usb0=transport?transport->usbObservationRaw(0):nullptr;
    const uint32_t *usb1=transport?transport->usbObservationRaw(1):nullptr;
    kprintf("RPI5XNU:USB_XHCI_CAPS:STATE STEP=%u ERROR=%d READS=%u PHYSICAL=%llu BYTES=%u\n",
        transport?transport->usbObservationStep():0,transport?transport->usbObservationError():0,
        transport?transport->usbObservationReads():0,
        (unsigned long long)(transport?transport->usbObservationPhysical():0),RPI5_RP1_USB_WINDOW_SIZE);
    kprintf("RPI5XNU:USB_XHCI_CAPS:RAW0 CAP=%08x HCS1=%08x HCS2=%08x HCS3=%08x HCC1=%08x DBOFF=%08x RTSOFF=%08x HCC2=%08x\n",
        usb0?usb0[0]:0,usb0?usb0[1]:0,usb0?usb0[2]:0,usb0?usb0[3]:0,
        usb0?usb0[4]:0,usb0?usb0[5]:0,usb0?usb0[6]:0,usb0?usb0[7]:0);
    kprintf("RPI5XNU:USB_XHCI_CAPS:RAW1 CAP=%08x HCS1=%08x HCS2=%08x HCS3=%08x HCC1=%08x DBOFF=%08x RTSOFF=%08x HCC2=%08x\n",
        usb1?usb1[0]:0,usb1?usb1[1]:0,usb1?usb1[2]:0,usb1?usb1[3]:0,
        usb1?usb1[4]:0,usb1?usb1[5]:0,usb1?usb1[6]:0,usb1?usb1[7]:0);
    kprintf("RPI5XNU:USB_XHCI_CAPS:DECODE VERSION=%04x CAPLEN=%u SLOTS=%u INTRS=%u PORTS=%u SCRATCH=%u DB=%08x RT=%08x XECP=%08x AC64=%u CSZ64=%u PPC=%u\n",
        usb?usb->interface_version:0,usb?usb->capability_length:0,usb?usb->max_slots:0,
        usb?usb->max_interrupters:0,usb?usb->max_ports:0,usb?usb->max_scratchpad_buffers:0,
        usb?usb->doorbell_offset:0,usb?usb->runtime_offset:0,usb?usb->extended_capability_offset:0,
        usb?usb->address_64:0,usb?usb->context_64:0,usb?usb->port_power_control:0);
'''
    anchor = '    kprintf("RPI5XNU:PCIEID:END OK=%u PHASE=%u LAST=%u LIFE=%u FLAGS=%02x ID=%08x COMMAND=%04x BAR1=%08x GEN=%u LANES=%u\\n",'
    progress = _replace(progress, anchor, rows + anchor)
    files["BCM2712PCIeIDTrialProgress.inc"] = progress.encode()
    return files


def loader(original):
    text = parent.loader(original)
    text = _replace(text, '#include "rp1_device_handoff.h"',
        '#include "rp1_usb_device_handoff.h"')
    text = _replace(text, "rpi5_rp1_device_handoff(",
        "rpi5_rp1_usb_device_handoff(")
    text = _replace(text,
        "RPI5XNU:BL33:RP1_DEVICE_HANDOFF RANGES=2 PAGES=6 GEM_CLOCK_ONLY DECLARATIONS_ONLY RP1_MMIO=0",
        "RPI5XNU:BL33:RP1_DEVICE_HANDOFF RANGES=3 PAGES=70 GEM_CLOCK_USB0_ONLY DECLARATIONS_ONLY RP1_MMIO=0")
    return text.replace(
        "RPI5XNU:FULL_PROVIDER:ENTRY TAG=", "RPI5XNU:USB_XHCI_CAPS:ENTRY TAG=").replace(
        "CPUS=1 NO_CPU_ON NO_QUEUE NO_BME NO_DMA",
        "CPUS=1 READ_ONLY NO_RESET NO_PORT NO_IRQ NO_BME NO_DMA")


def psci(original):
    return parent.psci(original)


def sources():
    return [Path(__file__).resolve(), *sorted(FROZEN.iterdir()),
        ROOT / "loader/rpi5/rp1_usb_device_handoff.h",
        ROOT / "loader/rpi5/rp1_usb_device_handoff.c",
        ROOT / "loader/rpi5/rp1_usb_xhci_caps.h",
        ROOT / "loader/rpi5/rp1_usb_xhci_caps.c",
        ROOT / "tools/rpi5/tests/rp1_usb_device_handoff_host.c",
        ROOT / "tools/rpi5/tests/test_rp1_usb_device_handoff.py"]
