# Early Apple DT consumers — incomplete translation contract

## Official firmware blob checkpoint

Read the Pi 5 DTB from raspberrypi/firmware commit
`2768f6105ab38838934f9cfb3c5e5c16326d8a01`, boot/bcm2712-rpi-5-b.dtb.
Local ignored copy: build/rpi5/bcm2712-rpi-5-b-2768f610.dtb; SHA-256
`399caff4dcf03c55e20b6a4a7907dd8bd1c0cc42a9fc79e0b3b2ad4f7511585a`.
The parser accepts its structure. CPU reg values are 0, 0x100, 0x200, 0x300.
Its static RAM declaration is 640 MiB, not evidence of the user's actual RAM SKU.
Firmware can modify the runtime tree, so this blob cannot replace that handoff.

The static atf reservation covers [0, 0x80000), marked no-map. Earlier synthetic
header PA 0x1004000 maps a rounded prefix starting at zero and is therefore
incompatible with this reservation. Do not use that synthetic placement on Pi.
The linux,cma node requests dynamic storage, and the memory planner correctly
rejects it. A deliberate policy or allocation implementation is required before
using this tree for placement; it has not been silently dropped or rewritten.
An optional hash-pinned regression exercises this downloaded blob when present.

## Consumer requirements

`fdt_clock.fixed_clock_rates` resolves zero-argument fixed-clock phandles.
The pinned serial10 node names uartclk (9,216,000 Hz) and apb_pclk (750,000,000
Hz). It rejects programmable/unavailable providers, malformed rates and unresolved
references. The rates are DT declarations only; baud verification still requires
runtime clock state and UART divisor reads. No MMIO has been performed.

`fdt_address.reg_ranges` translates exact paths through simple-bus ranges;
unsupported cell widths (including PCI formats) are rejected. On the pinned
blob, serial10 points to /soc@107c000000/serial@7d001000, whose translated range
is [0x107d001000, 0x107d001200). This is address evidence only, not proof of UART
clocking or operation. Translation follows
[DTSpec ranges](https://devicetree-specification.readthedocs.io/en/stable/devicetree-basics.html#ranges).

This is source evidence for the pinned kernel, not a valid Pi device tree.
The encoder's root-only fixture is insufficient for boot.

The host `tools/rpi5/fdt.py` reader now decodes the DTB header, reservation map,
node hierarchy and raw property bytes using the
[Devicetree Specification format](https://devicetree-specification.readthedocs.io/en/stable/flattened-format.html).
It checks block bounds/overlaps, termination, nesting, padding and duplicate
names. Tests use synthetic input only; real firmware blobs and independent
libfdt comparison remain pending. Header reservations alone are not a complete
reserved-memory inventory: `/reserved-memory` nodes, firmware allocations and
live loader buffers still need separate semantic handling. No raw property is
implicitly translated into an Apple property.

`memory_ranges` decodes root-level memory reg tuples using explicit one- or
two-cell address/size widths. It preserves discontiguous RAM and addresses above
4 GiB, rejecting overlapping ranges, malformed tuples and addresses outside the
Pi 40-bit profile. These are advertised RAM ranges, not free memory: reservation
subtraction and reserved-memory child interpretation are still pending. Reference:
[DTSpec memory nodes](https://devicetree-specification.readthedocs.io/en/stable/devicenodes.html#memory-node).

`available_memory` now subtracts the header reservation map, static
reserved-memory child ranges and caller-supplied live reservations. It merges
overlapping exclusions, preserves RAM holes and keeps reusable pools excluded.
The initial profile requires matching root cell widths and empty ranges;
dynamic/nested/IOMMU reservations are rejected rather than ignored. Binding:
[reserved-memory schema](https://raw.githubusercontent.com/devicetree-org/dt-schema/main/dtschema/schemas/reserved-memory/reserved-memory.yaml).
The caller still must supply the DTB's physical allocation and any firmware/live
buffers not represented in the tree. These host results have not been validated
on an actual Pi firmware tree and are not yet wired to native allocation.

| Consumer | Required input and interpretation |
| --- | --- |
| osfmk/arm/arm_init.c, before arm_vm_init | `/chosen/dram-base` and `dram-size` must exist. The consumer dereferences unsigned long values (64-bit on this ABI). Supply explicit little-endian uint64 values describing actual DRAM, distinct from the bounded managed boot_args extent. |
| pexpert/gen/pe_gen.c, PE_get_random_seed | `/chosen/random-seed` must exist and be nonempty. The routine copies and clears the consumed bytes in place. The tree must be writable at consumption. The project contract additionally requires at least 256 fresh seed bytes and an identified runtime entropy source; encoding bytes does not prove entropy. |
| pexpert/arm/pe_identify_machine.c | Looks for `arm-io`; reads device_type as a C string and uses the second uintptr_t in ranges as the SoC physical base, without validating these lookups locally. A Linux FDT ranges array is not interchangeable. Do not add an arm-io node with missing or mechanically copied properties. |
| pexpert/arm/pe_identify_machine.c, clock setup | If the SoC base is nonzero, requires `/cpus`, searches for a state string matching running, and reads timebase-frequency. Supply the measured architectural timer frequency, not the upstream default clock values. The timebase property should be uint32. |
| osfmk/arm64/machine_routines.c, topology | CPU state is mandatory; `running` identifies the boot CPU. Numeric properties go through ml_readprop, which accepts widths 1, 2, 4 or 8 bytes in native byte order. CPU reg is mandatory and becomes phys_id; Linux affinity and Apple topology semantics require deliberate translation. |

No board property values have been invented from these consumers. The next
translation work must inspect all mandatory topology properties, UART/address
translation, FDT memory reservations and firmware-discovered CPU identities.
Keep per-property widths and byte order explicit. A compiled parser test or
well-formed encoding cannot validate clocks, physical addresses or seed quality.

## Newly identified DRAM consumer mismatch — 2026-09-10

Do not yet emit a final `/chosen/dram-base`/`dram-size` pair. `arm_init.c`
copies them into gDramBase/gDramSize, but `pmap_map_bd` in
`osfmk/arm/pmap/pmap.c` rejects `!gDramBase || !gDramSize`. Physical base zero
is valid for the Pi and therefore conflicts with that initialization sentinel.
This is a source-observed conditional failure, not a captured board panic.
Do not invent a nonzero actual DRAM base to bypass it.

The BCM2712-only sentinel is now changed to require nonzero gDramSize, allowing
legitimate base zero. `arm_init.c` validates both property widths before their
respective dereferences, rejects zero size and bounds the envelope to 40-bit PA.
Other platforms retain the original sentinel. A sanitizer regression executes
the actual preprocessor-guarded checks for both configurations and tests widths,
zero size, maximum boundary and overflow inputs. This fixes initialization
validation only; it does not resolve memory-hole classification below.

`is_dram_addr` in `osfmk/mach/arm/vm_param.h` classifies a single contiguous
interval using those globals. Its pmap consumers use the result for mapping
attributes, not just accounting. Linux's advertised [0x3fc00000,0x40000000) hole
does not by itself establish the physical memory type or ownership of every
address in that hole. A base-plus-total-size pair cannot encode it. Resolve
the zero-base sentinel and actual DRAM versus reserved/managed/MMIO semantics
before changing this classifier or composing the final board tree. Keep
the bounded kernel-managed extent distinct from actual installed memory.

Independent Pi 5 implementation evidence: worproject/rpi5-uefi commit
`a6135b06d661b5f11bbf4bd742b42a1919b264dc` pins edk2-platforms commit
`8e1779b538bcc1e6dc68d7df625394f933651d7a`. Its
[Pi 5 memory-map implementation](https://github.com/worproject/edk2-platforms/blob/8e1779b538bcc1e6dc68d7df625394f933651d7a/Platform/RaspberryPi/RPi5/Library/PlatformLib/RaspberryPiMem.c)
separately describes GPU-reserved space below 1 GiB with device attributes and
an unmapped-region classification. It derives that boundary from firmware RAM
information, not a fixed 0x3fc00000 constant. Its 3–4 GiB treatment also depends
on PCIe BAR policy. This is software-policy evidence, not an authoritative
datasheet or proof of our selected firmware configuration. It does not justify
flattening the installed-memory envelope into one normal-memory classification,
nor importing UEFI's address assignments unchanged.

Required direction: keep the actual-DRAM envelope for accounting separate from
explicit runtime normal-memory ranges and allocation exclusions. Unknown holes
must remain inaccessible until their intended memory type and owner are known.
Do not make the existing single-envelope classifier cover the whole board solely
because the user confirmed an 8 GB SKU. No mapping policy was changed by this
source investigation.

The handoff encoder `rpi5_memory_types_encode` now defines the proposed
`rpi5-memory-map` property payload: little-endian 32-bit version (1) and
record count, followed by 24-byte records containing little-endian 64-bit
type (1 Normal, 2 Device), start, and exclusive end. Normal records precede
Device records; each class is sorted and both classes are mutually disjoint.
All endpoints are 16 KiB aligned and bounded by the 40-bit physical limit.
An absent address is UNKNOWN, not implicitly Device. Reservations remain
separate: a Normal classification does not grant allocation ownership.
The encoder validates before publishing, supports unaligned output, and has
sanitizer coverage for exact bytes, the observed RAM hole, maximum record
count, short output and invalid-map preservation. The probe now attaches
runtime FDT Normal ranges to the board tree before measuring or planning it;
seed insertion preserves this third chosen property. The Device list now
permits only the UART10-containing 16 KiB page [0x107d000000,0x107d004000).
This is the minimum mapping granule for `ml_io_map` of the existing 512-byte
PL011 register window; it does not authorize register accesses outside that
window. Raspberry Pi's [BCM2712 device tree](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/arch/arm64/boot/dts/broadcom/bcm2712.dtsi)
corroborates the UART register address and size. No broad bus aperture or RAM
hole is classified as Device. Additional peripherals require explicit entries.
BCM2712 XNU now consumes the property before arm_vm_init, validates the managed
span, and rejects unknown mappings in the reviewed pmap consumers. Updated
hardware verification remains pending.
The pmap mapping entry points must reject UNKNOWN pages independently of
their requested cache mode, not merely replace the `is_dram_addr` boolean.

`loader/rpi5/memory_type.c` now implements the explicit range-classification
contract separately from allocation planning. It validates sorted, 16 KiB-aligned
normal/device lists, rejects overlap between classes and answers queries only
when the entire interval is covered by one type. Gaps, mixed ranges and malformed
maps return UNKNOWN, never an implicit device or normal mapping. Native sanitizer
tests cover zero-based normal RAM, adjacent spans, holes, cross-type boundaries,
overlap, alignment and the 40-bit endpoint. It is compiled into the probe but
not called, serialized into the board tree or installed into XNU. Populating it
from trustworthy runtime evidence and adapting XNU's consumers remain required.

Serial-tree follow-through: `pl011_uart_setup` expects compatible `arm,pl011`
and exactly two native uint64 values in reg (SoC-relative offset, length).
It adds the SoC base obtained from the second native uintptr_t in arm-io ranges.
Its init preserves baud divisors but rewrites UART control and line format.
The loader must drain before transfer; its earlier preservation check does not
prove that XNU's subsequent UART initialization is glitch-free on the board.

## CPU subtree implementation — 2026-09-10

`loader/rpi5/cpu_tree.c` now constructs only `/cpus` from explicitly supplied
validated affinities, boot affinity and counter frequency. It accepts unique
IDs from {0,0x100,0x200,0x300}, requires the boot ID exactly once, retains physical
IDs in little-endian 32-bit reg values and supplies NUL-terminated state strings
and 32-bit timebase-frequency. No cache size, core frequency or Apple-specific
register range is invented. The input frequency must come from the architectural
counter; the test's 54 MHz value is synthetic, not a board measurement.

The current BCM2712 header enables HAS_CLUSTER with four physical cluster IDs
to preserve Aff1 reset lookup. These IDs do not establish shared-cache domains.
The builder preserves them rather than renumbering reg to 0,1,2,3. It has no CPU
startup side effects and does not implement XNU SMP startup. Its self-referential
output must remain at a stable address until serialization. Tests verify exact
bytes against Python encoding, a nonzero boot CPU, a single-CPU subset and
unchanged output for invalid inputs. The builder is compiled into diagnostic
builds but is not yet called by the runtime; the complete board tree is unfinished.

## Serial subtree implementation — 2026-09-10

`serial_tree.c` supplies arm-io and defaults nodes for the narrow UART10 profile.
It requires the exact validated translated UART window, encodes the SoC-relative
reg offset/length as two little-endian uint64 values and uses an explicitly
provided nonzero Apple phandle. The matching `/defaults/serial-device` property
is essential: `get_serial_device_phandle` panics if defaults is absent, and
otherwise serial_init returns without a driver if no serial selection exists.
The UART's `AAPL,phandle` must match that 32-bit native value. These properties
are deliberately not copied from Linux's phandle scheme.

The builder validates the narrow addresses, not runtime ownership; callers must
first validate FDT translation and ensure phandle uniqueness across the complete
Apple tree. It advertises no interrupt-controller or timer MMIO nodes: XNU's
Apple interrupt setup is not a GIC driver. Host tests compare exact bytes with
Python encoding and check invalid-input atomicity. Both subtrees must remain at
stable addresses until serialization. Compiled but not runtime-connected.

## Composed early-consumer tree — 2026-09-10

`board_tree.c` now composes chosen, cpus, arm-io and defaults at stable addresses.
It accepts explicit DRAM envelope values, CPU identities, boot CPU, architectural
counter frequency and the validated UART window; it does not derive actual DRAM
from the bounded managed extent. Its sole Apple phandle is assigned consistently
to UART10 and the defaults selection. No seed is present until `seed_tree.c`
performs its preflight/collection/encoding transaction.

The sanitizer integration test builds all four nodes, adds model seed bytes,
compares the final encoding with a separately assembled property graph and
verifies original graph preservation and invalid-input atomicity. It is included
in probe compile/link checks, not called by the runtime. This composes the
reviewed early-consumer properties; it is not proof of all IOKit requirements,
DRAM classification, hardware truth or a boot. Runtime ownership and provider
checks must precede calling it with board values.

`rpi5_seed_tree_measure` now validates the final tree size without contacting an
entropy provider. `tree_handoff.c` uses that exact size to construct the native
handoff plan, rejecting a caller-supplied tree length rather than allowing a
placeholder to disagree with encoding. This establishes the intended ordering:
measure tree, prove placement/ownership, then collect and encode the seed.
The native sanitizer test checks encoded boot_args length and atomic rejection
of insufficient tree capacity, stale length and overlap with a live loader.
No provider is called by this planning API and no physical writes occur.

The reservation-backed `rpi5_resolved_tree_handoff` now requires an explicit
validated `rpi5_memory_types` map. Both the full managed-RAM interval and the
rounded bootstrap mapping must be covered as NORMAL. A reservation-free
extent alone is not sufficient evidence for cache attributes. Missing maps,
holes, device regions and malformed maps fail before output publication;
the inner plan is held locally until its rounded extent passes. The sanitizer
test includes a normal managed interval whose block-rounded mapping extends
below that interval, proving rejection even after the inner planner succeeds.
This does not establish attribute provenance, populate the map from firmware,
change XNU's DRAM classifier, or connect the planner to runtime execution.
