# CPU-translated PCI resources over original IOPCIFamily

2026-10-12. The new **abstract** resource bridge connects Apple's original PCI
allocator/address properties to the Pi's outbound CPU address windows. It
compiles against actual XNU/Apple family headers and links relocatably with
the preserved configuration adapter and original family objects. This is
**not a concrete root provider, final kernel link, attached driver, physical
BAR assignment/readback, MMIO, IRQ, DMA or Ethernet acceptance**.

No boot/catalogue/source-list, accepted image, SD, serial, firmware or Pi power
change was made. The last physically proven zsh/socket image remains intact.

## Address-space integration

`iokit/Kernel/BCM2712PCIResourceBridge.{h,cpp}` derives from the previously
screened `BCM2712PCIConfigBridge`, which derives from **original** `IOPCIBridge`.
Its one-shot `configure` registers the declared nonprefetchable/prefetchable
windows with the original allocator in **PCI bus space**, not CPU physical
space. The four excess hardware-decode bytes are not registered or usable.
Partial allocator setup fails permanently rather than retrying or publishing.

Before publication, the owner must bind a validated FDT-derived outbound table
to the *same completed window session* in the configuration/link chain. The
adapter recomputes the original freestanding window plan and compares every
outbound encoding field, including declared versus decoded extent. This
checks software consistency only: it neither rereads physical registers nor
grants hardware access. Inbound/DMA admission remains independent.

The `getDTNubAddressing` override reads original IOPCIFamily's native
`IOPCIPhysicalAddress` records, translates PCI BAR bases into CPU addresses,
and stages a fresh array of real `IOMemoryDescriptor` objects. The original
architecture-dependent record fields are used; raw big-endian FDT cells are
not confused with Apple's native property layout. It does not override
`constructRange`, whose original ARM caller may already have resolved an
address through the device tree; doing translation there would risk applying
it twice.

The pure `BCM2712PCIResourceAddress.h` helper rejects malformed byte lengths,
more than six BAR slots, duplicate/high-half slots, ROM/I/O/unsupported memory
profiles, unknown flags, wrong fixed root/RP1 BDF, unassigned tags, zero or
non-power-of-two sizes, misalignment, overflow, overlapping resources,
ambiguous/overlapping windows and spans outside the declared outbound extent.
It accepts assigned PCI base zero. The fixed profile supports nonprefetchable
MEM32 in window 0 and prefetchable MEM64 in window 1; it is not a generic PCI
topology/resource implementation. Both outputs stay unchanged on rejection.

Resource descriptors carry the original register/address tag, CPU-translated
base and exact BAR size. They request inhibited-cache, host-only, mapper-free
memory; no `map()` call is made in the adapter. The original family may map
them immediately afterward, so before descriptor creation the still-abstract
**live owner** must independently verify identity, assignment/type/size/BAR
readback, memory decode, lifetime, accessibility and fault containment for
every resource. A missing RP1 BAR1 fails rather than reporting empty success.
No public registry boolean supplies that admission. IRQ/MSI, bus mastering
and DMA are not authorized by this interface or the memory descriptors.

Existing device-memory arrays are rejected: replacing a live array is not
the original family's in-place descriptor/map relocation. Relocation is
deliberately not implemented in this first-publication layer. The concrete
owner must serialize enumeration/resource calls and retain/drain all clients,
mapping objects and callbacks before releasing any underlying resources.

Errors latch resource failure and require a bounded **local-only** owner
quarantine callback, with no MMIO, reset, cleanup writes or retry. That owner
must prohibit all other direct config/core/resource clients. The original
family sets `IOPCIResourced` before addressing; on error this adapter removes
that premature marker so a later call cannot report cached success. Previously
published descriptors are not destroyed or silently rolled back.

## Separate original-family adaptation

The pinned original
[IOPCIConfigurator](https://github.com/apple-oss-distributions/IOPCIFamily/blob/IOPCIFamily-726.100.6/IOPCIConfigurator.cpp)
publishes assigned BARs based on a nonzero `range->start`, and its property
generator uses MEM32 tags even for ranges with the original Bar64 flag. The
new `pci-bcm2712-assigned-addresses.patch` changes a **new copy only**, enabled
by `RPI5_PCI_CPU_TRANSLATED_RESOURCES` and guarded against non-BCM2712 builds:

- Allocation comes from the original allocator's non-null `nextSubRange`
  membership/sentinel plus a positive, consistent start/size/end span. A
  numeric nonzero start alone is not proof of allocation; zero alone is not
  proof of its absence.
- Actual memory ranges with the original `kIOPCIRangeFlagBar64` retain a MEM64
  tag, preserving the other original address fields.

The new `BCM2712PCIAssignedRange.h` uses original declarations, not a second
allocator. The adaptation retains Apple's original notices/license. The
pristine checkout, previously accepted adapted family and config object are
unchanged. With the opt-in macro removed, preprocessed source matches the
preserved original configurator. Native helper execution and real-header
compile/link checks are **not** execution of the configurator on the Pi.

## Local evidence

Four focused tests pass:

1. Original-type native helper execution: exact Linux-reference-shaped RP1
   BARs (including base zero), unaligned property payloads, 64-bit address and
   length fields, malformed records/flags/BDFs/slots, overlap/overflow/window
   edges, and **16,384** aligned size/position translations across both windows.
   Already-CPU-translated input is rejected. Allocation/tag helper checks
   distinguish allocated zero from unallocated nonzero and malformed spans.
   No kernel API, register access or driver executes in this host program.
2. Actual A76/XNU-header compilation, relocatable original-family linkage,
   closed input/output hashes and overwrite refusal. The new board sources
   have zero warnings; the original configurator retains 66 upstream warnings.
3. Disabled-adaptation preprocessing equivalence and wrong-board compile
   rejection.
4. Changed accepted manifest and unsafe output destination rejection.

All **161 selected regressions pass** (53.799 seconds), including physical
socket-capture replay, zsh metadata/installation, original Apple family/range
builds and the earlier PCIe bring-up/configuration models. This is a selected
host suite, not the full XNU suite or a new hardware trial.

`tools/rpi5/build_apple_pci_resources.py` validates both accepted family/config
manifests and all their captured sources/dependencies, then hashes each reused
original family/config object separately. Only the configurator unit is
recompiled with the new adaptation; the other ten original family units and
the two accepted config units are reused. The unchanged C window core is
included by a small C-linkage wrapper under the real IOKit C++ template.
No fake kernel declarations or allocator shim is used.

Final artifact:
`build/rpi5/apple-pci-resources-20261012-final/apple-bcm2712-pci-resources.o`,
751,160 bytes, SHA256
`a8b3ad6f00a5bcdd13ac22c11fea2f3ad01d6cd094569ed22ef522792abe7cf4`.
Manifest SHA256
`f2a37ca0988cbbcdc8d3cbf1925c63dd613a5d010655981e9e9827f8a00617ba`.
All 662 captured inputs match. There are 528 undefined names, of which only
the previously known `___dso_handle` is absent from the reference kernel's
symbol inventory. This is not a final link or proof of constructor/module
lifetime, ABI behavior or registration.

```
python3 -m unittest tools.rpi5.tests.test_apple_pci_resources -v
python3 tools/rpi5/build_apple_pci_resources.py --output-dir NEW_DIRECTORY
```

## Next real Ethernet work

Implement the concrete Device-mapped host owner: genuine power/clock/shared
reset/calibration and exclusive lifecycle ownership, bounded recovery and
fault-containment admission, serialized MMIO/config access, phase-specific
authorization of original enumeration writes, live BAR/resource readbacks and
local quarantine. The abstract `start`, memory-admission and owner-quarantine
methods are intentional missing implementations, not successful stubs.

Then qualify an opt-in final kernel/family/constructor/catalogue build and
admit physical RP1 enumeration/resource observation. Follow with RP1/MIP/GIC
interrupts, clocks, GEM/PHY, owned/coherent DMA and IONetworkingFamily/wire
traffic. Original SSH dependencies can advance independently. No new manual
restart, repeated soak, assumed SSH reachability or Gate 4 waiver is required
for the next software work.
