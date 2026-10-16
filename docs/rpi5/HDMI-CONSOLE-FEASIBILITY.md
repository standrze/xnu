# Pi 5 visible XNU / zsh console — X0 feasibility slice

2026-10-13. Immediate target: genuine XNU text and the existing genuine zsh
on one HDMI monitor, with UART input initially. Not a compositor, GPU driver,
USB keyboard, window system, or desktop claim. This narrows the next milestone
without making Ethernet a prerequisite.

## Current evidence and stop conditions

The parent agent's current read-only Linux observation has both HDMI connectors
disconnected and no chosen framebuffer declaration. That is not evidence of
absent retained display memory, and Linux's allocation epoch must not supply
addresses for the later standalone XNU boot. No connected-display standalone
descriptor or physical framebuffer write is yet observed.

The loader's `probe_main.c` explicitly supplies no framebuffer and
`boot_args.c` zeroes the video fields. Merely plugging in HDMI therefore does
not redirect the current zsh. A monitor must be connected and powered for a
fresh handoff observation; the hardware-owning agent controls any reboot or
configuration change.

## Pi 5-specific primary evidence

- The BCM2712 EEPROM release notes explicitly document a **2025-06-09**
  correction to the D0 alpha mode for simple-framebuffer users. They also
  describe Pi 5 as implementing a subset of the original mailbox properties.
  This supports investigating retained firmware scanout, not assuming the
  Pi 4 allocation/mode-setting API works unchanged. Pin the installed EEPROM
  revision and actual result before relying on a fix.
  [Official EEPROM notes](https://github.com/raspberrypi/rpi-eeprom/blob/131548b60eaffaf2c5e9b01d6e6f6275ba419034/firmware-2712/release-notes.md)
- The Pi-specific BCM2712 DTS includes `/soc/fb` with
  `brcm,bcm2708-fb`, referencing the firmware service. Absence of a
  `/chosen/framebuffer@...` node alone is therefore not proof that this board
  has no firmware framebuffer interface. The next diagnostic should inventory
  both forms, without treating the legacy node as an allocation descriptor.
  [Official BCM2712 DTS](https://github.com/raspberrypi/linux/blob/43c132e8863c3bff3647033b6a7d2bf87b15501c/arch/arm64/boot/dts/broadcom/bcm2712-rpi.dtsi)
- The generic simple-framebuffer binding describes already-configured scanout,
  with runtime nodes under `/chosen` and explicit geometry, format, and memory.
  `memory-region` can override `reg`; the parser must not silently ignore it.
  [Kernel binding](https://github.com/torvalds/linux/blob/24a19b953e2a3d0ea5a8c4951a0ab8f32720c907/Documentation/devicetree/bindings/display/simple-framebuffer.yaml)
- Official configuration documentation says `disable_fw_kms_setup` suppresses
  firmware-selected Linux mode arguments and defaults to 1 on Pi 5. It does
  **not** establish framebuffer deallocation or ownership.
  [Configuration documentation](https://www.raspberrypi.com/documentation/computers/config_txt.html#disable_fw_kms_setup)
- Pi 5 issue reports include disagreement between requested/reported pixel
  depth and actual scanout, and D0 alpha behavior. The latter was acknowledged
  by Raspberry Pi's maintainer and received the release-note fix above. These
  are reasons to qualify geometry and colors physically, not to infer that a
  successful mailbox response proves a usable format.
  [Depth report](https://github.com/raspberrypi/firmware/issues/1904),
  [D0 alpha report and maintainer discussion](https://github.com/raspberrypi/firmware/issues/1971)

No undocumented mailbox allocation, display-list register programming, EEPROM
update, or firmware-node deletion was performed by this slice.

The three immutable source documents above were independently fetched and
SHA256-hashed without execution: EEPROM notes
`ad0070310cfe18247e65439875dc211ad5e4bf05eeffdf14f5daf57894301966`,
BCM2712 DTS
`874963e6586489a6cad16c148499dc93eb77de5f8ce26e37cda7e5e2f37dd7f7`,
simplefb binding
`021e9990eb37b83b548a379e218043e1a6c324182e2e16ffc49365f4a807a871`.

## Reuse the original Apple text console

The repository already contains the useful implementation:

1. `pexpert/arm/pe_init.c` copies `boot_args.Video` into `PE_state.video`.
2. Its `PE_create_console` selects text mode when `v_display == 0`.
3. `osfmk/console/video_console.c:initialize_screen` maps the supplied memory
   and provides the existing font, color, scrolling, and text machinery.
4. Existing `/dev/console` userspace can then write through that console.

There are important integration requirements:

- The current `serial=3` selects both serial output and input and explicitly
  switches the console to UART in `osfmk/arm/arm_init.c`. The existing
  `serial=2` input-only flag is a source-supported candidate: retain the video
  output path while original `serial_keyboard_poll` feeds `cons_cinput`.
  Preserve independent UART kprintf diagnostics and automatic recovery.
- **Input-only serial is not sufficient for the current test protocol.** The
  existing recorders require complete UART userspace stdout, prompt, nonce
  frames, and exit statuses. Moving those bytes exclusively to HDMI would
  invalidate their proof. The preferred trial integration is therefore an
  explicit video-plus-UART console sink: one bounded console-output call
  dispatches the same character to original `vcputc_options` and original
  `serial_putc_options`, while serial input stays enabled. The existing
  `cons_ops` dispatch in `osfmk/console/serial_console.c` is the narrow seam;
  do not tee by calling `console_write` recursively or changing kprintf's
  independent diagnostic path. A distinct kernel overlay must prove lock
  ordering, polled/non-polled behavior, exact byte ordering/newlines, and no
  duplicate UART bytes under both sinks. Until that actual-source test exists,
  the tee is a design candidate, not implemented functionality.
- The unchanged 32-bit Apple color table uses `0x00RRGGBB`; do not feed ABGR
  or meaningful-alpha ARGB scanout without a checked conversion/opaque-alpha
  policy. The pure helper only labels XRGB8888 as pixel-compatible with the
  unchanged renderer, with at least one complete 8×16 text cell. This is not
  a complete mapping/console admission.
  If actual firmware reports ARGB, a distinct renderer adaptation would have
  to write opaque alpha on **all** glyph, erase, clear, and scrolling-related
  paths, tested against the original renderer with guard buffers. Alternatively
  qualify an actual documented firmware alpha-ignore mode. Setting alpha once
  at boot or trusting an unverified firmware revision is insufficient.
- `initialize_screen`'s cache-mode assumptions come from Apple hardware.
  BCM2712 scanout coherence must be explicitly qualified. A checked firmware
  descriptor does not prove cache visibility or the right mapping attributes.
- Preserve the entire allocation and rounded mapping pages, including padding,
  outside the XNU allocator, kernel, root archive, FDT, stacks, TF-A, and other
  retained firmware allocations. If the buffer lies outside advertised DRAM,
  obtain explicit backing evidence; do not classify an arbitrary address as
  safe RAM. Keep the existing ownership ledger's firmware trust contract.
  A framebuffer outside the present `[0x06000000,0x10000000)` managed window
  may avoid allocator overlap but still needs an explicit compatible kernel
  PTE/cache mapping; range exclusion alone does not provide that mapping.
- Boot-video ABI serialization, any page-offset handling, and actual kernel
  mapping still need implementation and actual-source tests in a distinct
  loader/kernel package. No current boot arguments were changed here.

## New offline implementation

`loader/rpi5/framebuffer_descriptor.{h,c}` adds three pure operations:

- Parse a caller-discovered exact `/chosen/framebuffer@<physical-address>`
  against the real existing FDT validator. Require a Pi 5 / BCM2712 root,
  exactly one simplefb declaration, enabled ancestry, explicit 1/2-cell chosen
  widths, exact reg/width/height/stride/format and no overriding memory-region
  or unhandled clock/power ownership declarations. All unknown node properties
  and children are rejected, including arbitrary `*-supply` extensions;
  supported metadata phandles are shape-checked but do not prove ownership.
- Validate bounded initial geometry: 32-bit pixels, at most 1920×1080,
  bounded aligned pitch, non-wrapping 40-bit physical extents, and enough
  allocation bytes for all rows. Decode four RGB/BGR/alpha formats without
  claiming they are interchangeable.
- Produce a full-allocation 16-KiB-rounded exclusion only after backing-range
  coverage and conflicts are checked. All failures leave output unchanged.

This intentionally rejects multi-output, missing chosen cell widths,
memory-region references, RGB565/24-bit formats, and other unsupported shapes.
It is not integrated into the accepted loader. Actual firmware shape must
drive a reviewed extension, rather than relaxing checks to accept invented
descriptors. The caller still owns clock retention and full memory provenance.

Validation:

```
python3 -m unittest tools.rpi5.tests.test_framebuffer_descriptor -v
```

Four groups passed in 1.714 seconds: three actual-C ASan/UBSan groups plus
Cortex-A76 freestanding compilation of the real helper/FDT/range sources.
They cover all four
supported formats and cell-width combinations, every fixture truncation,
duplicate/missing/disabled/wrong-board properties, overflows and insufficient
buffers, unhandled resource ownership, page-padding conflicts and fragmented
backing RAM, and unchanged failure output. They never map or dereference a
framebuffer or claim physical scanout.

## Next bounded physical sequence

1. With one monitor powered and attached, capture a fresh standalone firmware
   handoff: exact EEPROM/DTB/config identities, node paths, display format,
   pitch, dimensions, physical allocation and all reservations. If no supported
   retained descriptor exists, stop before writes and choose an explicitly
   Pi 5-qualified firmware interface or a scoped display-driver task.
2. Bind that actual descriptor to the reservation planner and video ABI.
   In a distinct recovery-bounded image, draw a small color/bounds test and
   original Apple text; obtain visible confirmation, not just serial markers.
3. Route the accepted root's real zsh through `/dev/console` to Apple video
   output while keeping serial input **and mirrored serial output** for the
   marker-guarded protocol. Require a visible prompt, text entry, an external
   command's output/status, the same complete UART command evidence, and
   preserved serial recovery evidence. A serial=2-only variant would require
   a separately designed evidence protocol; it must not inherit the current
   recorder's acceptance claim.

USB keyboard is a separate host/HID milestone. Ethernet, a full desktop, and
GPU acceleration need not precede this visible text-console milestone.
