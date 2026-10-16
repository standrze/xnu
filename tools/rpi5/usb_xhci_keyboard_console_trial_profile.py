# SPDX-License-Identifier: BSD-2-Clause
"""One-CPU USB keyboard console layered on the passed first-report gate.

This profile is offline until its distinct builder, checker and physical
recorder approve it. It preserves the existing terminal-watchdog service,
keeps xHCI interrupts disabled and polls the cyclic report ring from one
dedicated kernel thread.
"""
from pathlib import Path

from tools.rpi5 import usb_xhci_keyboard_trial_profile as parent


ROOT = parent.ROOT
BOOTARGS = parent.BOOTARGS
OWNER_TRACE = ROOT / "build/rpi5/pcie-owner-trace-kernel-20261013-v1/overlay"
TRACE_WATCHDOG_OWNER = OWNER_TRACE / "rpi5_pcie_watchdog_owner.inc"
TRACE_IRQ_OWNER = OWNER_TRACE / "rpi5_pcie_irq_owner.inc"
TRACE_FW_OWNER = OWNER_TRACE / "rpi5_pcie_fw_owner.inc"


def _replace(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError("exact USB console trial anchor differs")
    return text.replace(old, new)


def marker(tag):
    return ("RPI5XNU:USB_XHCI_CONSOLE:ENTRY TAG=" + tag +
        " CPUS=1 POLLING PORT2 K65 STREAM255 IRQ_OFF TERMINAL_WDOG "
        "CONS_CINPUT")


def derive():
    files = parent.derive()
    for name, relative in {
        "rp1_usb_xhci_keyboard_stream.h":
            "loader/rpi5/rp1_usb_xhci_keyboard_stream.h",
        "pcie_watchdog_console_lease.h":
            "loader/rpi5/pcie_watchdog_console_lease.h",
        "rpi5_pcie_watchdog_console_api.h":
            "pexpert/arm/rpi5_pcie_watchdog_console_api.h",
        "rpi5_pcie_watchdog_console_owner.inc":
            "pexpert/arm/rpi5_pcie_watchdog_console_owner.inc",
    }.items():
        files[name] = (ROOT / relative).read_bytes()

    console_owner = files["rpi5_pcie_watchdog_console_owner.inc"].decode()
    console_owner = _replace(console_owner,
        "#include <pexpert/arm/rpi5_pcie_watchdog_owner.inc>",
        '#include "' + str(TRACE_WATCHDOG_OWNER) + '"')
    files["rpi5_pcie_watchdog_console_owner.inc"] = console_owner.encode()
    files["rpi5_pcie_irq_console_owner.inc"] = TRACE_IRQ_OWNER.read_text().replace(
        "pe_rpi5_watchdog_check_pcie(",
        "pe_rpi5_watchdog_check_usb_console(").encode()
    files["rpi5_pcie_fw_console_owner.inc"] = TRACE_FW_OWNER.read_bytes()

    header = files["BCM2712PCIePHYTransport.h"].decode()
    header = _replace(header, '#include "rp1_usb_xhci_keyboard_input.h"',
        '#include "rp1_usb_xhci_keyboard_input.h"\n'
        '#include "rp1_usb_xhci_keyboard_stream.h"')
    header = _replace(header, 'extern "C" {',
        'extern "C" {\n#include "rpi5_pcie_watchdog_console_api.h"')
    header = _replace(header,
        '''    struct rpi5_usb_xhci_keyboard_interrupt_plan usbKeyboardInterrupt={};
    struct rpi5_xhci_keyboard_input_observation usbKeyboardObserved={};''',
        '''    struct rpi5_usb_xhci_keyboard_interrupt_plan usbKeyboardInterrupt={};
    struct rpi5_usb_xhci_keyboard_stream_plan usbKeyboardStream={};
    struct rpi5_xhci_keyboard_stream_state usbKeyboardStreamState={};
    struct rpi5_xhci_keyboard_stream_observation usbKeyboardStreamObserved={};
    struct rpi5_xhci_keyboard_input_observation usbKeyboardObserved={};
    void *usbKeyboardThread=nullptr;
    bool usbKeyboardWorkerStarted=false;
    bool usbKeyboardWorkerActive=false;
    int usbKeyboardWorkerError=0;
    static int usbConsoleGuard(void *);
    static int usbConsoleEmit(void *,const uint8_t *,uint32_t);
    void usbConsoleWorker();''')
    header = _replace(header, 'public:\n',
        'public:\n    void runUSBKeyboardConsole();\n')
    header = _replace(header,
        '''    const struct rpi5_usb_xhci_keyboard_interrupt_plan &usbKeyboardInterruptObservation() const { return usbKeyboardInterrupt; }
    const struct rpi5_xhci_keyboard_input_observation &usbKeyboardObservation() const { return usbKeyboardObserved; }''',
        '''    const struct rpi5_usb_xhci_keyboard_interrupt_plan &usbKeyboardInterruptObservation() const { return usbKeyboardInterrupt; }
    const struct rpi5_usb_xhci_keyboard_stream_plan &usbKeyboardStreamPlanObservation() const { return usbKeyboardStream; }
    const struct rpi5_xhci_keyboard_stream_state &usbKeyboardStreamStateObservation() const { return usbKeyboardStreamState; }
    const struct rpi5_xhci_keyboard_stream_observation &usbKeyboardStreamObservation() const { return usbKeyboardStreamObserved; }
    const struct rpi5_xhci_keyboard_input_observation &usbKeyboardObservation() const { return usbKeyboardObserved; }
    unsigned usbKeyboardWorkerState() const { return (unsigned)usbKeyboardWorkerStarted | ((unsigned)usbKeyboardWorkerActive<<1); }
    int usbKeyboardWorkerResult() const { return usbKeyboardWorkerError; }''')
    files["BCM2712PCIePHYTransport.h"] = header.encode()

    transport = files["BCM2712PCIePHYTransport.cpp"].decode()
    transport = _replace(transport,
        '''    struct bcm2712_phy_observation result = {};
    if (!pe_rpi5_watchdog_claim_pcie(this, &result.watchdog)) { fail(); return false; }''',
        '''    struct bcm2712_phy_observation result = {};
    struct rpi5_pcie_watchdog_console_observation consoleWatchdog={};
    if (!pe_rpi5_watchdog_claim_usb_console(this, &consoleWatchdog)) { fail(); return false; }
    result.watchdog.start=consoleWatchdog.start;
    result.watchdog.sampled_counter=consoleWatchdog.sampled_counter;
    result.watchdog.prior_countdown=consoleWatchdog.countdown;
    result.watchdog.armed_countdown=consoleWatchdog.countdown;''')
    transport = transport.replace("pe_rpi5_watchdog_check_pcie(",
        "pe_rpi5_watchdog_check_usb_console(")
    files["BCM2712PCIePHYTransport.cpp"] = transport.encode()
    for name in list(files):
        if not name.endswith(".inc") or "watchdog" in name:
            continue
        text = files[name].decode()
        files[name] = text.replace("pe_rpi5_watchdog_check_pcie(",
            "pe_rpi5_watchdog_check_usb_console(").encode()

    identify = files["BCM2712RP1GEMIdentifyTransport.inc"].decode()
    identify = _replace(identify,
        '''    if(!runUSBEnumeration()) { usbCapabilityError=-14;return false; }
    if(usbCapabilityMap->unmap()!=kIOReturnSuccess || usbCapabilityMap->getVirtualAddress()) {
        usbCapabilityError=-10;return false;
    }
    usbCapabilityMap->release();usbCapabilityMap=nullptr;usbCapabilityBacking=nullptr;
    if(!guard() || gemSource(this,&gemSession,&decodeCycle)) {
        usbCapabilityError=-11;return false;
    }
    usbCapabilityStep=8;return true;''',
        '''    if(!runUSBEnumeration()) { usbCapabilityError=-14;return false; }
    /* The live console owns this map until watchdog reset. Never unmap a
     * running controller or its retained DMA allocation. */
    if(!guard() || gemSource(this,&gemSession,&decodeCycle)) {
        usbCapabilityError=-11;return false;
    }
    usbCapabilityStep=8;return true;''')
    identify = _replace(identify,
        '''int BCM2712PCIePHYTransport::usbNoopGuard(void *context)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    return !self || !self->usbDMAActive || !self->dmaMemory ||
        self->dmaMemory->state()!=BCM2712USBXHCIMemory::Staged ||
        usbLifecycleGuard(context) ? -1 : 0;
}''',
        '''int BCM2712PCIePHYTransport::usbNoopGuard(void *context)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || !self->usbDMAActive || !self->dmaMemory ||
        self->dmaMemory->state()!=BCM2712USBXHCIMemory::Staged)return -1;
    return self->usbKeyboardWorkerActive ? usbConsoleGuard(context) :
        usbLifecycleGuard(context);
}''')
    identify = _replace(identify,
        '''    return !self || !self->usbDMAActive || !self->decodeActive ||
        self->decodeCycle.state!=RPI5_RP1_DECODE_MAPPED ||
        usbLifecycleGuard(context) ? -1 : 0;''',
        '''    if(!self || !self->usbDMAActive || !self->decodeActive ||
        self->decodeCycle.state!=RPI5_RP1_DECODE_MAPPED)return -1;
    return self->usbKeyboardWorkerActive ? usbConsoleGuard(context) :
        usbLifecycleGuard(context);''')
    identify = _replace(identify,
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
    dmaRingActive=false;usbDMAActive=false;usbNoopStep=8;return true;''',
        '''    usbNoopStep=5;
    if(!dmaMemory->stageK65KeyboardStream(&usbEnumerationObserved.keyboard,
            &usbKeyboardEndpoint,&usbKeyboardSetup,&usbKeyboardStream)) {
        usbNoopError=-5;return false;
    }
    const struct rpi5_xhci_keyboard_stream_io keyboardIO={this,usbNoopRead,
        usbNoopWrite,usbNoopDelay,usbNoopGuard,usbDMAGuard,usbConsoleEmit};
    usbNoopStep=6;
    if(rpi5_rp1_xhci_k65_keyboard_stream_start(&usbCapabilityObserved,&layout,
            &usbEnumerationObserved,&usbKeyboardEndpoint,&usbKeyboardSetup,
            &usbKeyboardStream,&keyboardIO,&usbKeyboardStreamState,
            &usbKeyboardStreamObserved)) {
        usbNoopError=-6;return false;
    }
    /* Controller, BME, mapping and allocation remain live for the worker.
     * Watchdog reset is the only recovery path for this bounded candidate. */
    usbNoopStep=7;return true;''')

    worker = r'''

extern "C" int initialized;
extern "C" void cons_cinput(char);
extern "C" void thread_terminate_self(void);

int BCM2712PCIePHYTransport::usbConsoleGuard(void *context)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    return !self || !self->usbKeyboardWorkerActive || ml_at_interrupt_context() ||
        self->usbKeyboardThread!=current_thread() ||
        __atomic_load_n(&phyOwner,__ATOMIC_ACQUIRE)!=self ||
        !self->providerOpened || !self->ownerProvider ||
        !self->ownerProvider->isOpen(self) || !self->usbCapabilityMap ||
        !self->usbCapabilityBacking || !self->decodeActive ||
        self->decodeCycle.state!=RPI5_RP1_DECODE_MAPPED ||
        !pe_rpi5_watchdog_check_usb_console(self) ? -1 : 0;
}

int BCM2712PCIePHYTransport::usbConsoleEmit(void *context,
    const uint8_t *bytes,uint32_t count)
{
    if(!bytes || !count || count>RPI5_USB_HID_BOOT_MAX_OUTPUT ||
        !::initialized || usbConsoleGuard(context))return -1;
    for(uint32_t index=0;index<count;index++)cons_cinput((char)bytes[index]);
    return 0;
}

void BCM2712PCIePHYTransport::usbConsoleWorker()
{
    usbKeyboardWorkerActive=true;
    kprintf("RPI5XNU:USB_XHCI_CONSOLE:WORKER READY=1 IRQ=0 POLL_MS=16\n");
    const struct rpi5_xhci_keyboard_stream_io io={this,usbNoopRead,
        usbNoopWrite,usbNoopDelay,usbNoopGuard,usbDMAGuard,usbConsoleEmit};
    while(usbConsoleGuard(this)==0) {
        struct rpi5_xhci_keyboard_stream_observation observed={};
        int rc=rpi5_rp1_xhci_k65_keyboard_stream_poll(&usbCapabilityObserved,
            &dmaObserved.layout,&usbKeyboardStream,&io,
            &usbKeyboardStreamState,&observed);
        usbKeyboardStreamObserved=observed;
        if(rc<0) { usbKeyboardWorkerError=rc;break; }
        IOSleep(16);
    }
    usbKeyboardWorkerActive=false;
    kprintf("RPI5XNU:USB_XHCI_CONSOLE:WORKER_STOP ERROR=%d REPORTS=%u BYTES=%u\n",
        usbKeyboardWorkerError,usbKeyboardStreamState.reports,
        usbKeyboardStreamState.output_bytes);
}

void BCM2712PCIePHYTransport::runUSBKeyboardConsole()
{
    if(usbKeyboardWorkerStarted || usbKeyboardWorkerActive ||
        !usbDMAActive || !rpi5_rp1_usb_bme_ready(&usbBME) ||
        !usbKeyboardStreamState.active || !onOwnerThread() || !guard())return;
    usbKeyboardThread=current_thread();
    usbKeyboardWorkerStarted=true;
    usbConsoleWorker();
}
'''
    identify += worker
    files["BCM2712RP1GEMIdentifyTransport.inc"] = identify.encode()

    progress = files["BCM2712PCIeIDTrialProgress.inc"].decode()
    progress = progress.replace("USB_XHCI_KBD", "USB_XHCI_CONSOLE")
    progress = _replace(progress,
        'extern "C" void rpi5_pcie_id_trial_start(void) __attribute__((noreturn));\n',
        'extern "C" bool rpi5_terminal_watchdog_start(void);\n'
        'extern "C" void thread_terminate_self(void);\n'
        'extern "C" void rpi5_pcie_id_trial_start(void);\n')
    progress = _replace(progress,
        'extern "C" void rpi5_pcie_id_trial_start(void)\n{',
        'static void rpi5_pcie_id_trial_run(void)\n{')
    progress = _replace(progress,
        '''    bool ok=false;
    IOService *provider=new IOService;''',
        r'''    bool ok=rpi5_terminal_watchdog_start();
    kprintf("RPI5XNU:USB_XHCI_CONSOLE:WATCHDOG ACTIVE=%u\n",(unsigned)ok);
    IOService *provider=new IOService;''')
    progress = _replace(progress,
        '''    bool prepared=provider && transport && provider->init() && transport->init() &&
        transport->prepareBoot(provider);''',
        '''    bool prepared=ok && provider && transport && provider->init() && transport->init() &&
        transport->prepareBoot(provider);''')
    progress = _replace(progress,
        '''    (void)ml_set_interrupts_enabled(false);
    for(;;)__asm__ volatile("wfi" ::: "memory");
}''',
        r'''    bool worker=ok && transport;
    kprintf("RPI5XNU:USB_XHCI_CONSOLE:HANDOFF OK=%u WORKER=%u STATE=%u ERROR=%d\n",
        (unsigned)ok,(unsigned)worker,
        transport?transport->usbKeyboardWorkerState():0,
        transport?transport->usbKeyboardWorkerResult():-1);
    if(worker)transport->runUSBKeyboardConsole();
}

static void rpi5_usb_console_entry(void *,wait_result_t)
{
    /* IOKitBSDInit dispatches us after platform matching and BSD console
     * initialization.  Retain an explicit platform-service check so a
     * future startup-order regression fails closed instead of touching RP1. */
    mach_timespec_t timeout={30,0};
    IOService *platform=IOService::waitForService(
        IOService::serviceMatching("BCM2712PlatformExpert"),&timeout);
    kprintf("RPI5XNU:USB_XHCI_CONSOLE:PLATFORM READY=%u\n",
        (unsigned)(platform!=nullptr));
    if(platform)rpi5_pcie_id_trial_run();
    thread_terminate_self();
}

extern "C" void rpi5_pcie_id_trial_start(void)
{
    static bool dispatched=false;
    bool expected=false;
    if(!__atomic_compare_exchange_n(&dispatched,&expected,true,false,
            __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return;
    thread_t thread=THREAD_NULL;
    kern_return_t rc=kernel_thread_start(rpi5_usb_console_entry,nullptr,&thread);
    if(rc==KERN_SUCCESS)thread_deallocate(thread);
    else __atomic_store_n(&dispatched,false,__ATOMIC_RELEASE);
    kprintf("RPI5XNU:USB_XHCI_CONSOLE:DISPATCH RC=%d\n",rc);
}''')
    files["BCM2712PCIeIDTrialProgress.inc"] = progress.encode()

    # The generated pe_fiq translation unit includes this copied owner body.
    pe = files["pe_fiq.c"].decode()
    old_include = next(line for line in pe.splitlines()
        if "rpi5_pcie_watchdog_owner.inc" in line)
    pe = pe.replace(old_include,
        '#include "rpi5_pcie_watchdog_console_owner.inc"')
    irq_include = next(line for line in pe.splitlines()
        if "rpi5_pcie_irq_owner.inc" in line)
    pe = pe.replace(irq_include,
        '#include "rpi5_pcie_irq_console_owner.inc"')
    fw_include = next(line for line in pe.splitlines()
        if "rpi5_pcie_fw_owner.inc" in line)
    pe = pe.replace(fw_include,
        '#include "rpi5_pcie_fw_console_owner.inc"')
    files["pe_fiq.c"] = pe.encode()
    return files


def loader(original):
    return parent.loader(original).replace("USB_XHCI_KBD", "USB_XHCI_CONSOLE").replace(
        "DCI3 HID_SETUP REPORT8 NO_IRQ BME_LEASE DMA",
        "DCI3 HID_SETUP STREAM255 IRQ_OFF TERMINAL_WDOG CONS_CINPUT")


def psci(original):
    return parent.psci(original)


def sources():
    own = [
        ROOT / "loader/rpi5/rp1_usb_xhci_keyboard_stream.h",
        ROOT / "loader/rpi5/rp1_usb_xhci_keyboard_stream.c",
        ROOT / "loader/rpi5/pcie_watchdog_console_lease.h",
        ROOT / "loader/rpi5/pcie_watchdog_console_lease.c",
        ROOT / "pexpert/arm/rpi5_pcie_watchdog_console_api.h",
        ROOT / "pexpert/arm/rpi5_pcie_watchdog_console_owner.inc",
        TRACE_WATCHDOG_OWNER,
        TRACE_IRQ_OWNER,
        TRACE_FW_OWNER,
    ]
    return list(dict.fromkeys([Path(__file__).resolve(), *parent.sources(), *own]))
