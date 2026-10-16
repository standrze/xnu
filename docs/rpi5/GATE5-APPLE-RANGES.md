# Original Apple PCI range allocator reuse

2026-10-12. The original Apple `IOPCIRange.cpp` now compiles unchanged for
Cortex-A76 and links with a small RP1 policy adapter. This is actual source
reuse, not a rewritten allocator or a declaration of whole-family support.
It is **not included in BL33/XNU, installed, or hardware-executed**.

## Pinned source and adapter boundary

Selected upstream [IOPCIFamily-726.100.6](https://github.com/apple-oss-distributions/IOPCIFamily/tree/IOPCIFamily-726.100.6),
commit `503b7da7c8d67bc2dedecd83dd07b72f4644ec4b`, is retained as a pristine
checkout at `build/rpi5/apple-IOPCIFamily-726.100.6`. This is a selected allocator
candidate, not a proven match for the entire modified Pi XNU kernel.

The unmodified [allocator](https://github.com/apple-oss-distributions/IOPCIFamily/blob/503b7da7c8d67bc2dedecd83dd07b72f4644ec4b/IOPCIRange.cpp)
and its original range declarations in
[IOPCIConfigurator.h](https://github.com/apple-oss-distributions/IOPCIFamily/blob/503b7da7c8d67bc2dedecd83dd07b72f4644ec4b/IOKit/pci/IOPCIConfigurator.h)
are compiled directly. The selected files carry APSL 2.0 notices; original
notices and `APPLE_LICENSE` remain intact. No whole-repository or redistribution
clearance claim is made. Any later external deployment needs the applicable
source/notice/license obligations handled with that release.

Source SHA256:

- `IOPCIRange.cpp`: `9306bea541846afd632b17c7b7030d39d20d79540fe0fd7ddfca7c636a3f5ca9`.
- `IOPCIConfigurator.h`: `8658be1892e3cbb0354b84c6d9700778c80c6413b2556b5f69896ddf19a21c39`.
- `APPLE_LICENSE`: `4407579a41ee5062dd5451539a05b495e699c4f1c4965c8ad65c9bc3b38d9860`.

`tools/rpi5/apple_pci_shim/IOKit/pci/IOPCIPrivate.h` is explicitly a limited
allocator adapter, **not** Apple's complete private IOKit header. It imports
the original non-kernel range declarations, omits unrelated kernel classes,
checks the pinned LP64 struct/sentinel layout and supplies zeroing/assertion
support. Unexpected heap/logger/panic paths trap instead of silently succeeding.
This selected call graph uses stack objects and never calls heap allocation.
Exceptions/RTTI/global constructors and external runtime dependencies are absent.
The source is never edited to make this profile compile.

## RP1 policy, not live BAR authority

`loader/rpi5/pcie_apple_ranges.{h,cpp}` supplies a C entry point around the
original allocator. Inputs are decoded outbound declarations, three independently
validated BAR sizes and at most eight occupied **PCI-space** spans. One MEM32
window is required; an optional PREFETCH64 declaration is checked but unused.
All three RP1 BARs are treated as independent nonprefetchable 32-bit memory BARs.

The wrapper validates overflow/containment/overlap/alignment, reserves occupied
spans and allocates largest BAR first. At most eleven original allocation calls
traverse private bounded lists. Zero PCI base is valid; CPU physical resources
are not accepted as PCI addresses. Only declared bytes are available, never
the four-byte hardware decode excess. Failure preserves the caller's output.

The result is explicitly **candidates**, not assigned BAR observations. It does
not probe/program BARs, turn on memory decoding/bus mastering, access RP1, map
Device pages, allocate DMA, enable interrupts or send packets. Once hardware
assignment/readbacks actually exist, the existing `rpi5_pcie_resource_plan` must
reconcile live BAR1 with CPU GEM/clock spans. The wrapper does not manufacture
an `assigned=1` observation from a proposal.

## Evidence

`tools/rpi5/build_apple_pci_ranges.py` verifies the pristine checkout/pins,
compiles the two original/adapter units separately and produces a composed
A76 relocatable object. Compiler-discovered headers, sources, commands,
outputs and emitted stack frames are recorded and input stability rechecked.
Only the original unit suppresses its existing parentheses/unused-parameter
warnings; local policy code retains strict warnings. This is not a boot image,
whole IOPCIFamily kext build, complete stack bound or XNU driver attachment.

Artifact `build/rpi5/apple-rp1-ranges-20261012/apple-rp1-ranges.o`, SHA256
`b420266be8499fa5705ce242c217c7f9475a8b19dd62a7e455e8ec55da43e98c`.
Manifest SHA256 `7a34518689f14b439ce41715f3222059b5c634c187313d273432154ee04d84c4`.
No undefined symbols; original allocator and C policy symbols are both present.

Three focused tests pass: pristine-source/pin rejection; ASan/UBSan execution
of the original allocator plus wrapper and existing CPU translation planner;
actual freestanding cross-build/input/output hashes and overwrite refusal.
The host model covers 4,096 fragmented windows (4,081 successful proposals,
15 exhausted/output-preserved results), reserved-order independence, zero base,
32-bit endpoint boundaries, malformed windows/sizes and reservation overlaps.
Golden sizes are 16 KiB/4 MiB/64 KiB from the saved Linux reference; that is
historical input to a synthetic model, not current XNU hardware evidence.
All 130 selected regression tests pass; no full-XNU or hardware qualification
is implied.

```
python3 -m unittest tools.rpi5.tests.test_apple_pci_ranges -v
python3 tools/rpi5/build_apple_pci_ranges.py --output-dir NEW_DIRECTORY
```

## Remaining physical integration

Next close actual Device/power/clock/shared ownership and the access candidate's
bounded reset/one-shot recovery destination. Then compose existing reset,
calibration, SerDes, UBUS, RC/windows and link cores; observe RP1 configuration;
connect original compatible IOPCIFamily enumeration/configuration to the board
backend and these candidates, program/read back BARs and reconcile resources.
RP1/MSI-X/MIP interrupts, GEM clocks/PHY, DMA coherency and an original
IONetworkingFamily attachment still follow. This component alone closes none
of those physical gates.

Fresh SSH returned No route to host. Read-only Mac checks show an incomplete
ARP entry/rejected en0 host route for 192.168.4.23; `kamidana.local` did not
resolve. These do not establish Pi power/OS or authorize assuming SSD Linux.
No serial/media/power/firmware/reboot operation occurred; installed
`b67b8013...`, accepted zsh, socket diagnostic image and backups are unchanged.
Gate 4 durable storage/history stays independently held.
