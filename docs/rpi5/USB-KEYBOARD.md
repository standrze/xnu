# RP1 USB keyboard track

Status on 2026-10-16: **RAM execution is proven, physical USB-1 through USB-4
pass, and USB-5 has received and decoded the first real K65 interrupt report on
the Pi. Two USB-6 startup attempts exposed an early-IOKit dispatch race; the
corrected v13 candidate restores the proven early startup object and dispatches
from IOKitBSDInit. Repeated physical reports and a keyboard-only zsh command
remain unproven.**

## What “running in RAM” means here

The current Pi image already loads the XNU kernel, read-only mockfs root,
Apple-distributed zsh 5.9 and its command payload into RAM. The physical Pi has
passed file paging, `fork`/`execve`/`wait4`, the zsh command smoke, and visible
HDMI output from that RAM-resident system. The SD card remains the cold-boot
transport used by Raspberry Pi firmware and the loader; XNU does not execute
zsh or its root filesystem from the SD card after handoff. “No SD card at power
on” is a different future boot-media goal and is not required for a local USB
keyboard.

## Fresh Linux hardware inventory

The Pi was verified on NVMe root `/dev/nvme0n1p2`, boot ID
`b78ce2fc-b053-4277-a2e9-34cada155cda`. Its RP1 endpoint is PCI
`0002:01:00.0`, ID `1de4:0001`; BAR1 is the 4-MiB aperture
`0x1f00000000..0x1f003fffff`.

The official Raspberry Pi device tree describes two Synopsys DWC3 controllers
in host mode at RP1 child offsets `0x200000` and `0x300000`, each with a 1-MiB
window. Linux maps those as `0x1f00200000` and `0x1f00300000`, xHCI 1.1. The
first reports Linux IRQ 137/RP1 interrupt 31; the second reports Linux IRQ
142/RP1 interrupt 36. See Raspberry Pi's
[RP1 device tree](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/arch/arm64/boot/dts/broadcom/rp1.dtsi)
and [RP1 peripherals specification](https://datasheets.raspberrypi.com/rp1/rp1-peripherals.pdf).

A real acceptance keyboard is already attached to controller 0, high-speed bus
1 port 2: Corsair K65 RGB Mini, USB ID `1b1c:1baf`. Interface 0 is HID class,
boot subclass, keyboard protocol (`03/01/01`); interfaces 1 and 2 are
vendor-specific HID functions. The first implementation deliberately binds
only interface 0.

## Apple source boundary

Apple's official [IOUSBFamily](https://github.com/apple-oss-distributions/IOUSBFamily)
release contains the USB ABI headers, XHCI register definitions and some async/
isochronous queue code. It does **not** contain a complete reusable controller
stack: the central XHCI UIM/root-hub implementation, hub implementation,
`IOUSBController`, `IOUSBDevice`, and `IOUSBHIDDriver` source files are zero-byte
placeholders in the pinned release. The exact audit is
`tools/rpi5/apple_usb_sources.json`.

Apple's official [IOHIDFamily](https://github.com/apple-oss-distributions/IOHIDFamily)
does contain keyboard and HID implementation code. It is retained for the full
IOKit input-device milestone. The current BCM2712 kernel selects
`NO_KERNEL_HID`, so importing all of IOHIDFamily before a host controller can
enumerate a device would add build surface without producing input.

The initial local console therefore uses Apple/XNU's existing `cons_cinput`
TTY boundary with a small USB HID boot-keyboard decoder. That is a bootstrap
console path, not a claim of full IOHID event-system support.

## Passed physical USB gates

USB-1 passed with package
`build/rpi5/usb-xhci-caps-candidate-20261014-v4`, manifest SHA
`09cc872d8765553377e6121dec1b0b8c4a63d2f593616ecf4d7494de0149c956`.
The receive-only capture is
`build/rpi5/usb-xhci-caps-capture-20261014-v5/serial.bin`, 55,074 bytes,
SHA `d36f6d93bda13dcead442f04e3a52f4b91996abb1b79c4ce849128ec461f5ea2`.
XNU read controller 0's eight capability dwords twice (16 stable reads) at
physical `0x1f00200000`, decoded xHCI 1.1, 64 slots, four interrupters, three
ports and 64 scratchpad buffers, then unmapped. It performed no USB write,
reset, port action, IRQ, BME or DMA operation.

USB-2 passed with package
`build/rpi5/usb-xhci-lifecycle-candidate-20261014-v2`, manifest SHA
`9d9b7e1624409d77ffd5fe0dec3c43b963356143946c6abd11ea269f51c3851b`.
The receive-only capture is
`build/rpi5/usb-xhci-lifecycle-capture-20261014-v1/serial.bin`, 55,287 bytes,
SHA `c158a03c528b16c23cd06dd199b71542b36df900528a918aedd2c25218445968`.
The controller began running (`USBCMD=0x0d`), halted, accepted HCRST and
cleared both HCRST and Controller Not Ready in 19 bounded polls. It ended
halted (`USBCMD=0`, `USBSTS=0x11`) after exactly two USBCMD writes. The
write callback rejected every offset except the operational USBCMD at `0x20`;
there were no USBSTS, port, doorbell, runtime, DMA-pointer or interrupt writes.

Both trials retained the passed 146-record full-provider prerequisite,
transmitted zero serial bytes and returned automatically to NVMe Linux. After
each trial the byte-exact normal SD triple was restored. The current restoration
is superseded by the USB-3 restoration recorded below.

USB-3 passed with package
`build/rpi5/usb-xhci-noop-candidate-20261015-v11`, manifest SHA
`044d6a63897f8318bbe403b2c55dd7a9836eab6b5383b4963238c0e3d5d2d6e5`,
image SHA `87443667ab25cc2a047e3b23a2719e6fc232bd67a7feff03ac3ad36b1973dcc5`
and kernel SHA
`b02d01493a72ef5c169465344868d333ee0a72a428d1342576355660d394a7c4`.
The zero-transmit physical capture is
`build/rpi5/usb-xhci-noop-capture-20261015-v6/serial.bin`, 37,546 bytes,
SHA `aea25d42b2805659a6f2ab8c4acbb2d05cda64b9223a7118a48e6a850591cc8f`.
Its corrected native-USB parser report is `evidence.json`, SHA
`177c9c301815b1f92a220acf9e3bbb0610ce7b262302d5836976a4ffbe187634`.
XNU qualified all twenty pages, built the DCBAA/rings/ERST/scratchpads, changed
RP1 COMMAND from `0x0002` to `0x0006`, consumed one asynchronous Port Status
Change event, received the No-Op Command Completion Event (`CC=1`, `TYPE=33`),
halted the controller and restored COMMAND to `0x0002`. The outer decode cycle
also completed all 34 transactions and removed both mappings; `END OK=1`.
The board returned automatically to NVMe Linux. The exact normal probe/config/
firmware triple was restored in
`build/rpi5/usb-xhci-noop-restored-20261015-v7`.

USB-4 passed with package
`build/rpi5/usb-xhci-enumerate-candidate-20261015-v4`, manifest SHA
`5928699eab7e62f07d2bc061bf37fbe11585afaeae2ae9c2fb4a9da900ab4dcb`,
image SHA `202a336986fed5d5b53ebc624dc481499ee99c0204906cb7eb59f1bc604c1ab3`
and kernel SHA
`afea363db8bce0e6e5c82e113c17457372d72941879e49fda3fb28e9efecfdc6`.
The 37,972-byte receive-only capture is
`build/rpi5/usb-xhci-enumerate-capture-20261015-v1/serial.bin`, SHA
`22bc59d8f47d10d0bfa0542b50fd42c370c9690556c4327cc6802bdf4b4398d3`.
Its strict parser report SHA is
`0d74f641f946186a1b662f265d30b1cc89df3d1a67bf3b589b98ff08760c0ee7`.
XNU reset controller 0 port 2, consumed one successful port-status event,
enabled slot 1, addressed the device, completed all four EP0 descriptor
transfers and selected exactly Corsair `1b1c:1baf` interface 0/endpoint `0x81`.
Interrupts remained disabled, the controller halted, RP1 BME was restored,
the terminal guard passed and the watchdog owner completed after 73,500
checks. The recorder transmitted zero bytes, the board returned automatically
to NVMe Linux, and the exact normal probe/config/firmware triple was restored
in `build/rpi5/usb-xhci-enumerate-restored-20261015-v1`.

USB-5's first-report subgate passed with package
`build/rpi5/usb-xhci-keyboard-candidate-20261015-v7`, manifest SHA
`4b73b5f4888665238fe9a4e2c666d5dc70f542ec42eda9b29ca3f960cca737fe`,
image SHA `1465c35d1aff61618009efb824a998ea7c5a9ea2d977460d9243bf673a9dbf11`
and kernel SHA
`fe24ee49b68a239305a9093dfbb55b98117ff70650665331c5dae9d27506961e`.
The 38,442-byte zero-transmit capture is
`build/rpi5/usb-xhci-keyboard-capture-20261015-v5/serial.bin`, SHA
`8d87fd92e21062a82b5935540e62057a37b07f684282416b6b1f1093703444c2`;
its strict parser report SHA is
`bbeae295c258f1fe465c1354f51faac048fa62fc16f6e4abb3c7dfdcd0dc53da`.
XNU completed SET_CONFIGURATION(1), SET_PROTOCOL(boot), SET_IDLE(1), configured
DCI 3 and received one successful 8-byte interrupt-IN transfer. The report was
`0000000000000000`, as expected for a periodic idle probe, and decoded to zero
bytes. Interrupts remained disabled; the controller halted, RP1 BME was
restored, serial TX stayed zero and the board returned automatically to NVMe
Linux. The exact normal triple was restored without reboot in
`build/rpi5/usb-xhci-keyboard-restored-20261015-v5`; result SHA
`a1ee4d8b337aed0b0d5fe5db5c7ef78ac94528a47451c1c7616cab2791ef41a9`.

Four retained failed captures define the path to that result. The first three
failed at SET_CONFIGURATION while experimenting with halt/restart ordering.
The fourth proved all setup and Configure Endpoint operations but timed out
waiting for input because SET_IDLE(0) correctly reports only state changes and
no key was pressed. None is counted as USB-5 success.

## Implemented software boundary

- `loader/rpi5/rp1_usb_xhci_caps.{h,c}` defines the two official RP1 USB BAR1
  child ranges and decodes only the eight read-only xHCI capability dwords.
  It rejects invalid versions, geometry and out-of-window doorbell/runtime/
  extended-capability offsets. It has no reset, port, interrupt or DMA access.
- `loader/rpi5/usb_hid_boot_keyboard.{h,c}` is a no-allocation boot-protocol
  report decoder. It emits printable US ASCII, control letters, Enter, Tab,
  Escape, Delete and ANSI cursor sequences; tracks press/release and Caps Lock;
  and fails atomically on rollover, duplicate usages or a short output buffer.
- `loader/rpi5/rp1_usb_device_handoff.{h,c}` extends the strict loader map with
  only controller 0's validated 1-MiB Device interval. It does not grant
  register or DMA authority.
- `loader/rpi5/rp1_usb_xhci_lifecycle.{h,c}` implements the passed bounded
  halt/HCRST/ready sequence. It is callback-based, allocation-free and cannot
  write anything except USBCMD.
- `loader/rpi5/rp1_usb_xhci_dma_layout.{h,c}` now supplies USB-3's pure layout
  for the exact observed 64-byte-context/64-scratchpad geometry. One `0x50000`
  contiguous allocation contains the DCBAA, command/event rings, ERST,
  scratchpad array and buffers, device/input contexts, endpoint rings and
  transfer buffers. Host sanitizer and A76 freestanding tests pass, but no
  allocation has yet been published to the controller.
- `iokit/Kernel/BCM2712USBXHCIMemory.{h,cpp}` is the USB-specific retained
  Apple allocation provider. It uses a physically contiguous, MapperNone,
  write-combine `IOBufferMemoryDescriptor` plus a prepared unmapped
  `IODMACommand`; proves all twenty 16-KiB pages Normal-NC through both retained
  and physmap translations; rechecks the live released RP1 windows; and retains
  the descriptor and command after admission. It does not depend on the GEM
  provider and exposes no Apple memory or DMA-command handle.
- `iokit/Kernel/rpi5_rp1_dma_route.{h,c}` proves the complete preferred-RAM
  CPU-to-PCI-to-RP1 translation for the USB allocation without reusing an
  Ethernet-named authority object.
- `loader/rpi5/rp1_usb_xhci_noop.{h,c}` constructs the exact CPU-owned DCBAA,
  64 scratchpad pointers, No-Op command ring, empty event ring and ERST inside
  that retained allocation. `rp1_usb_xhci_noop_run.{h,c}` implements one
  bounded polling command completion: interrupts stay disabled, no port is
  touched, and the controller is halted again after success.
- `loader/rpi5/rp1_usb_bme.{h,c}` is an exact PCI COMMAND bit-2 lease for RP1
  `01:00.0`. It preserves every other command bit, requires immediate
  readbacks, restores the original word on success, and quarantines any
  indeterminate post-write failure for watchdog recovery.
- `loader/rpi5/rp1_usb_xhci_port_reset.{h,c}` is USB-4's bounded controller-0
  port-2 reset core. It requires a running, non-fatal controller and a connected,
  powered port; writes only port 2 `PORTSC`; requires reset completion, enabled
  high-speed/U0 state; acknowledges only `PRC`; and has no command, runtime,
  doorbell, PCI, DMA or interrupt write path. Its sanitizer fault tests and A76
  freestanding compile pass, and the composed USB-4 trial passed on physical
  port 2.
- `loader/rpi5/usb_xhci_control_transfer.{h,c}` constructs only the three-TRB
  endpoint-0 GET_DESCRIPTOR transactions needed for the K65 device/configuration
  reads (`8/18` and `9/91` bytes). `usb_hid_boot_descriptor.{h,c}` accepts only
  the observed `1b1c:1baf` device and its single `03/01/01` interface, endpoint
  `0x81`, 16-byte maximum packet and 4-frame interval while ignoring the two
  vendor HID interfaces. Both modules are allocation-free, sanitizer-tested,
  freestanding-compiled and exercised by the passing physical USB-4 trial.
- `loader/rpi5/usb_xhci_device_context.{h,c}` builds the exact Enable Slot and
  Address Device command images, validates their successful completion events,
  and creates only a 64-byte slot context plus EP0 context for high-speed root
  port 2. The slot is accepted only from the Enable Slot completion, bounded to
  `1..64`; DCBAA publication is confined to that slot. Host sanitizers and A76
  freestanding compilation pass. Both commands completed successfully in the
  physical USB-4 trial.
- `loader/rpi5/rp1_usb_xhci_enumerate.{h,c}` composes those pieces as one
  bounded polling state machine: passed USB-3 register setup, port-2 reset,
  Enable Slot, Address Device, four EP0 TDs, controller halt, prefix-consistency
  checks and strict K65 identity. It consumes only successful port-2 status
  events, keeps interrupts disabled, and delegates BME/watchdog recovery to the
  existing outer owner. The host hardware model covers the complete success
  path and a mutated-descriptor rejection; A76 freestanding compilation passes.
  `BCM2712USBXHCIMemory` now stages the enumeration and later slot-specific
  address image without exposing its writable CPU/DMA pointer. The v4 board
  package and zero-transmit capture above are the corresponding Pi result.
- `loader/rpi5/usb_xhci_keyboard_endpoint.{h,c}` and
  `usb_hid_boot_setup.{h,c}` now preserve the passed one-report image and also
  build USB-6's separate 255-entry DCI-3 ring with disjoint 8-byte buffers and
  change-only SET_IDLE(0). `rp1_usb_xhci_keyboard_stream.{h,c}` starts that
  ring without enabling interrupts, tracks both event and transfer cycle bits,
  rearms each consumed TRB for the next pass, preserves HID decoder state and
  emits only complete decoded byte batches. Host sanitizer tests exercise both
  event-ring and transfer-ring wrap; A76 freestanding compilation passes.
- USB-6's corrected distinct package is
  `build/rpi5/usb-xhci-keyboard-console-candidate-20261016-v13`, manifest SHA
  `8c5e9111a40399bdeb277663cda71206bd5ad5fa5ccb8c91b2917a988c0a8e3a`,
  image SHA `d3b6b4736d61893fe6709fb81f6aecdd529087dae05bd18a9451d6672edc6a84`
  and kernel SHA
  `2d8886392d960cc62317abefacc8dba98357239deb4c1a34727c1a712dd7aa80`.
  It dispatches the entire PCIe/xHCI bring-up and 16-ms cyclic poll on one
  kernel thread, preserving the existing owner-thread contract. It restores
  the physically proven `IOStartIOKit.cpo` exactly and dispatches only after
  `IOKitBSDInit` publishes `IOBSD`. Its observation-only console lease
  has no PM write callback and leaves the terminal watchdog service active.
  The linked worker retains BME, the xHCI map and DMA allocation, keeps IRQs
  disabled, and injects complete decoded batches through Apple's existing
  `cons_cinput` boundary. The independent checker validates the actual Mach-O
  call order and all hashes with zero undefined symbols. The v13 package has not
  been staged or run on the Pi. Exact-hash, NVMe-root, SD-identity, full-backup
  staging and restoration wrappers are prepared in
  `stage_usb_xhci_keyboard_console_trial.py` and
  `restore_usb_xhci_keyboard_console_trial.py`; neither script reboots. This is
  software qualification, not physical repeated-key or console-input evidence.
- The earlier v9 and v11 USB-6 images both reached XNU but panicked before the
  worker marker with `Unable to find driver for this platform` while private
  IOService work raced platform matching from the inherited early hook. They
  remain failed evidence and were followed by exact restoration to probe SHA
  `f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536`.
  A subsequent receive-only baseline boot reached the four-CPU read-only RAM
  root and `RPI5XNU:SHELL:READY`; it is not USB input evidence.
- Host AddressSanitizer/UndefinedBehaviorSanitizer tests and Cortex-A76
  freestanding compilation pass for the provider, layout, image builder,
  polling command core and BME lease. These are software checks, not physical
  XNU USB evidence.
- USB-3 is composed and physically passed in the v11 package and capture named
  above. `check_usb_xhci_noop_trial.py` accepts it with zero undefined symbols;
  `parse_usb_xhci_noop_trial.py` validates the native USB, BME, lifecycle,
  decode-teardown, firmware-watchdog and terminal records without fabricating
  removed GEM-provider records. The profile links a distinct finite 131,072-
  check watchdog object because the inherited controller path consumes 64,868
  of the normal 65,536 checks before a DMA lease begins. The 12-second deadline,
  countdown checks and every ordinary profile's 65,536-check object remain
  unchanged.

The preceding v6 through v9 captures remain failed-boundary evidence: v6 found
the `Prepared`/`Staged` admission mismatch; v7 exposed the legitimate first
Port Status Change event; v8 completed USB/BME but exhausted the inherited
verifier budget during decode teardown; v9 completed decode teardown but
exhausted the same budget later in the enclosing controller path. Each returned
to NVMe and was followed by exact baseline restoration. None widened the MMIO,
port, IRQ or PCI-write allowlists.

Reproduce:

```sh
python3 -m unittest \
  tools.rpi5.tests.test_rp1_usb_xhci_caps \
  tools.rpi5.tests.test_rp1_usb_device_handoff \
  tools.rpi5.tests.test_rp1_usb_xhci_lifecycle \
  tools.rpi5.tests.test_rp1_usb_xhci_dma_layout \
  tools.rpi5.tests.test_rp1_usb_xhci_memory \
  tools.rpi5.tests.test_rp1_usb_xhci_noop \
  tools.rpi5.tests.test_rp1_usb_xhci_noop_run \
  tools.rpi5.tests.test_rp1_usb_bme \
  tools.rpi5.tests.test_rp1_usb_xhci_port_reset \
  tools.rpi5.tests.test_usb_xhci_device_context \
  tools.rpi5.tests.test_usb_xhci_control_transfer \
  tools.rpi5.tests.test_usb_hid_boot_descriptor \
  tools.rpi5.tests.test_rp1_usb_xhci_enumerate \
  tools.rpi5.tests.test_usb_hid_boot_keyboard \
  tools.rpi5.tests.test_usb_xhci_keyboard_endpoint \
  tools.rpi5.tests.test_usb_hid_boot_setup \
  tools.rpi5.tests.test_rp1_usb_xhci_keyboard_input \
  tools.rpi5.tests.test_rp1_usb_xhci_keyboard_stream \
  tools.rpi5.tests.test_pcie_watchdog_console_lease \
  tools.rpi5.tests.test_usb_xhci_keyboard_console_trial_profile \
  tools.rpi5.tests.test_check_usb_xhci_keyboard_console_trial -v
```

## Gate sequence to the requested local zsh

1. **USB-1 — read-only capability observation — passed.** Compose the new decoder with
   the already-passed RP1 PCI/BAR owner. Map only controller 0's 1-MiB range,
   read capability dwords twice, require equality, publish the decoded xHCI
   1.1 geometry, unmap, restore, and return automatically to Linux. No MMIO
   writes, BME change, DMA, IRQ or port action.
2. **USB-2 — DWC3/xHCI lifecycle — passed.** Add bounded host-mode/reset sequencing and
   readback with a watchdog recovery path. Preserve controller 1 and Ethernet.
3. **USB-3 — one command/event path — passed on the Pi.** Retain the qualified Apple allocation, construct DCBAA, command
   ring, event ring, ERST and scratchpads, acquire the exact RP1 BME lease,
   issue one No-Op command under polling, halt the controller, restore COMMAND,
   and return by watchdog. The zero-transmit physical completion and automatic
   Linux return are recorded above; no interrupt was enabled in this gate.
4. **USB-4 — root port and control endpoint — passed on the Pi.** Controller 0
   port 2 reset, the K65 enumerated, all four bounded device/configuration
   descriptor transfers completed, and only interface `03/01/01`/endpoint
   `0x81` was selected. No RGB/vendor-interface traffic was issued.
5. **USB-5 — first keyboard interrupt report — passed on the Pi.** Boot
   protocol, the 4-ms idle probe, DCI 3 and one complete 8-byte interrupt-IN
   report all passed. Its all-zero idle report correctly decoded to no bytes;
   it does not prove a keypress or console injection.
6. **USB-6 — corrected linked candidate; physical acceptance pending.** The v13 candidate
   now runs the change-only cyclic report ring on its retained owner thread,
   preserves decoder state across press/release reports, and injects resulting
   bytes at XNU's `cons_cinput` boundary. The offline build/checker pass is not
   a keyboard result. In the physical test, with serial input disabled, type
   `print -r -- USB_KEYBOARD_OK`, edit with arrows/backspace, run one external
   command, and exit back to the XNU prompt while HDMI shows the same session.
   Preserve serial output as recovery evidence. A single clean cold boot is
   enough; no soak or repeated power-cycle campaign is required.

USB keyboard work is independent of the Ethernet queue-0 gate. It reuses the
same passed RP1 ownership, mapping, watchdog and automatic Linux-return
machinery, but neither track counts as evidence for the other.
