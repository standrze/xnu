# Checked boot video and inactive UART/HDMI mirror

Status on 2026-10-13: **offline software evidence only**. No SD image, loader,
boot arguments, Pi state, live memory mapping, or display settings were changed.
The kernel artifact is not a display trial package and must not be staged as one.

## Artifacts and checks

Distinct output: `build/rpi5/boot-video-console-ok0dfcku`.

- Manifest SHA256: `0e0fb194134fa0d2d5cdc50b4987e9df1f329fd8984b37ad2c7e72e747620e08`.
- `NOT_RUN_kernel.console-mirror` SHA256:
  `7e194a52ba35af624e61a3909d1613783b2b2f9053b517d67361e7df55f65874`.
- 12,143 input pins. Compiler dependency scans precede each translation unit;
  actual `-MD` dependencies must match afterward. Both source and generated
  artifact omissions are rejected by the separate byte-only checker.
- Exact one-object substitution in the complete state-confirmed kernel:
  `serial_console.o`. Original `video_console.o`, `serial_general.o`, and
  `pe_kprintf.o` remain in the link, along with every other original object.
  Actual Cortex-A76 kernel compilation succeeds with unchanged warning policy;
  complete kernel link has no undefined symbols or new linker warnings.
- Separate `NOT_RUN_boot_video.elf` links the real freestanding helper,
  descriptor/FDT/range functions, original boot-argument encoder, and real
  `memory.S`, without unresolved symbols. Its arbitrary offline link address is
  **not an approved physical placement**, and it has no boot entry sequence.
- Compiler, Mach-O linker, and ELF linker binaries are pinned. This is not a
  claim that every executable/library in the complete toolchain is pinned.

Validation:

```sh
RPI5_BOOT_VIDEO_PACKAGE=build/rpi5/boot-video-console-ok0dfcku \
python3 -m unittest tools.rpi5.tests.test_boot_video_console \
  tools.rpi5.tests.test_boot_video_console_artifact -v
```

Eight groups passed in 7.935 seconds. The native tests execute actual original
Apple function bodies with explicit host UART/video-event/lock scaffolding and
guarded ordinary RAM, under ASan/UBSan. They do not execute the target kernel,
emulate VM or the Pi, exercise the full VT100 state machine, or prove scanout.

## Opt-in boot argument encoding

`loader/rpi5/boot_video.{h,c}` leaves the frozen headless encoder unchanged. It
revalidates the framebuffer plan, admits only the original renderer's XRGB8888
format and minimum 8-by-16-pixel cell, checks the caller's RAM/live-range ledger,
and additionally excludes the whole `[phys_base, top)` bootstrap reservation.
It calls the original encoder into a temporary buffer and then changes only:

| ARM64 boot_args byte offset | Boot_Video field | Encoding |
| --- | --- | --- |
| 40 | v_baseAddr | Physical address OR 1 |
| 48 | v_display | 0, selecting Apple's text-console path |
| 56 | v_rowBytes | Validated stride |
| 64 | v_width | Validated width |
| 72 | v_height | Validated height |
| 80 | v_depth | 32; rotation 0 and encoded scale 0 means 1x |

The test compiles the **exact original ARM64 boot.h declarations**, asserts
LP64 size/offsets, decodes the bytes with those declarations, compares every
other byte against the original headless result, and checks atomic rejection.
The physical marker matches original `initialize_screen`: bit 0 requests a
physical mapping even after VM starts; the address is recovered with `& ~3UL`.

Encoding alone does not reserve memory in XNU or install page tables. The full
allocation, including padding and 16-KiB rounding, must stay excluded from every
allocator and conflicting mapping through the framebuffer's lifetime. A buffer
outside the current managed `[0x06000000, 0x10000000)` window still needs a correct
physical-to-virtual mapping and matching cache/scanout contract.

## UART-first mirror, disabled by default

`tools/rpi5/console_mirror_overlay.py` preserves the complete original
`osfmk/console/serial_console.c` and replaces only the serial console's `putc`
function pointer. The original serial `getc`, video entry, console-index rules,
ring buffer, flush mutex, newline normalization, and direct kprintf path remain
unchanged. The target continues to require the existing serial=3 route, not a
switch to serial=2 or an HDMI-only stdout.

For each normalized character, the new wrapper calls original
`serial_putc_options` **once first**, then calls unchanged `vcputc_options` only
if a one-way gate is enabled and `poll` is false. Apple's `_cnputc` makes debugger
output polled before this dispatch. Polled, suspended, and debugger paths thus
do not acquire the video ticket lock through this wrapper.

The gate starts at 0 and has **no publisher call site in this artifact**. Its
only publish transition is release-CAS 0 to 1; output uses an acquire read.
Revocation stores 2, permanently refusing another publish. Actual A76 output
contains CASL, LDAPR, and STLR. A future caller must first prove retained mapping,
cache compatibility, valid XRGB scanout and initialized Apple console state on a
quiescent setup path. Revocation is not a grace period: an already admitted
renderer call can finish, so it never authorizes unmapping/freeing the buffer.

The native dispatch tests invoke original `_cnputc`, `_cnputs`, index checks,
and `vcputc_options`. They check byte-for-byte UART prompt/nonce/exit framing,
single CR insertion per LF, UART-before-video ordering, unchanged input callbacks,
disabled/uninitialized/video-disable-under-lock cases, polled/debugger bypass,
and permanent revocation. A deliberately invalid console index is rejected.

This preserves intended UART bytes, not identical timing or fault isolation:
normal mirroring can delay later UART characters if a renderer call stalls.
The independent kprintf/watchdog path is not rerouted. No recursive console
caller may be added to the mirror, and no exception path may force `poll=false`.
Existing serial terminal geometry is retained; changing tty window size is a
separate future user-facing policy, not part of this evidence.

## Original renderer evidence and remaining display work

Native guarded-buffer tests use Apple's unchanged `iso_font.c`,
`vc_render_char`, `vc_paint_char_32`, and `vc_clear_screen`. They cover all 256
glyphs, eight attribute combinations, three foreground/background pairs, both
cached and fallback rendering (12,288 cases), last cells, row padding,
equal/changed previous glyph optimizations, and full-screen clearing. A wrong
pixel expectation is rejected. No fabricated renderer stands in for Apple code.

ARGB is still rejected. Apple's unchanged renderer writes `0x00RRGGBB`; accepting
ARGB requires a separately verified alpha-ignore scanout mode or an opaque-alpha
adaptation for **all** glyph, erase, clear and cursor writes. Clearing alpha once
is insufficient. BGR needs an explicit conversion policy too.

The next physical observation must discover the descriptor in the **same
standalone boot epoch** with a connected monitor. A declared `/chosen`
simple-framebuffer and Pi 5's `/soc/fb` firmware-mailbox candidate are different
contracts; this work does not guess an allocation or import Linux DRM addresses.
The primary-source discussion and restrictions remain in
`docs/rpi5/HDMI-CONSOLE-FEASIBILITY.md`.

Before actual drawing: validate buffer ownership/reservations, physical address
translation, live scanout, dimensions/format, and cache/PTE attributes; prove
Apple's initialization/mapping path on this platform; then activate the mirror
and compare the visible text with the complete existing UART trial. Local USB
keyboard/HID support is separate; serial input is sufficient for the first
visible zsh milestone. No GUI, window system, accelerated GPU, or display driver
completion is claimed here.
