# Reservation policy investigation — 2026-09-05

## Post-board placement revision

The successful hardware diagnostic proposes low CMA at [0x80000,0x4080000).
The historical host geometry's kernel destination [0x3004000,0x4078000)
overlaps that reservation and is not a deployable handoff layout.

New host-only experiment: kernel header 0x7004000, retained probe at 0x9000000,
FDT capacity [0xb000000,0xb400000), managed extent [0x6000000,0x10000000).
Candidate `bl33-probe-qcl6wkda` is linked at 0x9000000. The native/Python
handoff cross-check accepts it with `--post-cma-layout`, using its actual ELF
live extent and the full low reservation exclusion. Kernel validation and
host copy/zero-fill still agree for 18 segments and 93292 relocations.

This resolves the demonstrated geometry conflict only. Complete firmware
ownership and Normal-memory attribute provenance are still prerequisites.
No SD configuration or physical kernel destination has been changed. The
current working SD remains the previously verified 0x6000000 diagnostic.

## Contiguous handoff placement constraint — 2026-09-10

The diagnostic probe's historical 0x200000 link address is incompatible with
the current contiguous handoff contract if that live probe is retained there.
The handoff requires every live buffer inside the selected reservation-free
extent and its bootstrap mapping. Mapping the block containing 0x200000 includes
[0, 0x80000), which must remain excluded. Moving only the kernel above the first
32 MiB block leaves the low probe outside the accepted extent; it does not fix
the conflict. The same containment requirement applies to the live runtime FDT.

Before runtime handoff integration, select a firmware-supported BL33 placement
inside a suitable higher extent, accounting for the full probe, embedded payload,
BSS/stacks and FDT. If firmware cannot place all required live inputs there,
explicit relocation or a separately reviewed mapping/lifetime contract is needed.
Do not simply omit low live buffers from ownership checks or reclaim them while
terminal vectors/secondary stacks still depend on them. No new board address is
approved by this note.

`test_handoff.py` now rejects both low-probe layouts and accepts a synthetic
co-located layout above 32 MiB. This is Python planner regression evidence, not
proof of actual firmware placement, native execution or available board RAM.

### Pinned TF-A placement mechanism

Inspected clean source checkout at
`332b62e0443b004287d2cfc032a70bba6fb86f35`. The rpi5 platform includes
`plat/rpi/common/rpi4_bl31_setup.c`: absent compile-time overrides, its entry
and FDT getters consume the firmware-populated 32-bit armstub header fields.
With direct boot enabled, the FDT address is passed in x0 and x1–x3 are zero.
`docs/plat/rpi5.rst` explicitly documents `kernel_address` and
`device_tree_address` for firmware placement. Therefore a higher linked BL33
and deliberately placed FDT are supported by the source contract; self-relocation
is not yet required. The overrides specify addresses, not memory ownership.

A fresh host build at **test-only** 0x2100000 succeeded:
`build/rpi5/bl33-probe-udphgj7r/manifest.json`. It has no embedded kernel and
reports `board_placement_verified: false`. Do not use its file length to reserve
the image: its writable segment also contains 167808 bytes of BSS/stacks.
Embedding the kernel changes the full extent and requires a new layout review.
Next select loader, FDT and destination ranges together against complete
exclusions; archive their observed addresses during the first disposable-media
run. No config.txt has been generated or installed from this candidate.

## Reservation inventory

Runtime placement follow-up (2026-09-10): after resolving reservations,
`runtime_reservations` now validates the complete live probe and FDT against
`reservation_free`, not `available`. Subtraction can succeed with a live image
inside a fixed foreign reservation; that arithmetic success is not proof of
valid placement. Such overlap now stops runtime diagnostics before CPU_ON.
Successful validation prints the exact live probe (including BSS/stacks) and
FDT extents, explicitly retaining the incomplete-inventory warning. No raw FDT
contents are printed. Resolver integration tests demonstrate the distinction,
and runtime control-flow tests inject failure independently of console success.
The probe builds as `build/rpi5/bl33-probe-2qm151k_`; no board run occurred.

The native `rpi5_resolved_tree_handoff` wrapper now derives the usable mapping
extent from the resolver's `reservation_free` output. It rejects a separately
supplied usable range, malformed range lists, uncovered live allocations and a
managed extent spanning a reservation. It deliberately uses the view retaining
live loader buffers, not `available`, which excludes them. Seed-aware tree length
and remaining kernel/bootstrap checks then flow through the existing planner.
The integration test exercises actual reservation resolution before handoff and
rejects a foreign reservation splitting the proposed contiguous mapping, with
unchanged plan output on failure. This is still a pure host-testable composition:
the caller must establish complete inventory/provenance and commit any proposed
dynamic reservations before runtime use. It does not discover ownership or
perform memory writes and is not yet called by probe_main.

### Embedded-image geometry experiment — 2026-09-10

The actual audited kernel (SHA-256
`920d7b7a0270b99272d16f51059ed0de6c808d80c615dacad288c6dad2ebc3a8`)
was embedded in two fresh diagnostic builds. At 0x2100000 the full loader extent
was [0x2100000,0x31b0990), overlapping the earlier 0x3004000 kernel destination.
Placing the kernel later instead failed the host planner because bootstrap
mapping begins at the kernel's containing block, leaving the retained loader
below the mapping. Thus placement must account for source lifetime as well as
simple source/destination non-overlap.

Build `build/rpi5/bl33-probe-k192o56f` at 0x6000000 supports this **synthetic**
host-planner geometry, using the actual embedded image and BSS sizes:

| Object | Start | Exclusive end |
| --- | --- | --- |
| Kernel destination | 0x3004000 | 0x4078000 |
| Boot arguments | 0x4078000 | 0x4078480 |
| Apple-tree capacity, contents not supplied | 0x407c000 | 0x408c000 |
| Loader including source kernel, scratch and stacks | 0x6000000 | 0x70b0990 |
| FDT capacity, not an observed allocation | 0x8000000 | 0x8400000 |

With a hypothetical reservation-free [0x2000000,0x10000000) RAM extent, the
planner accepts these live ranges and reports mapping [0x2000000,0xe000000),
four translation-table pages, entry 0x34c8488 and topOfKernelData 0x8400000.
The RAM premise deliberately is NOT inferred from the Linux map. Dynamic CMA,
firmware ownership, exact FDT placement/length, real Apple-tree contents and
entropy remain unverified. This is a layout candidate, not an approved boot
configuration or runtime handoff. No physical writes were performed.

Native cross-check: `compare_native_macho.py` now accepts `--probe-build` to
reinspect the actual ELF/binary, require the exact encoded kernel container,
derive the full live extent, and compare C versus Python handoff arguments,
entry, top and physical mapping for this explicit experimental layout. It
accepted `bl33-probe-k192o56f` and rejected the overlapping lower build
`bl33-probe-kv33e_12`. The same run validated 18 kernel segments, 93292 local
relocations and 17252352 bytes of copy/zero-fill in a host buffer. These are
host-executed native routines, not execution on the Pi.

Reproduce from the project root:

```sh
python3 tools/rpi5/compare_native_macho.py build/rpi5/obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712 --probe-build build/rpi5/bl33-probe-k192o56f
```

Firmware initrd preservation: `/chosen/linux,initrd-start` and `linux,initrd-end`
are now decoded as a pair, with exclusive end. The narrow loader profile accepts
matching 4- or 8-byte big-endian values and a nonempty range below the 40-bit
physical limit. Missing both is allowed; partial, duplicate, mismatched-width or
malformed pairs fail without publishing a range. Runtime diagnostic planning
adds a present range to fixed exclusions (or stops if full). It never reads or
reclaims its contents and does not use it as a Darwin init image. Before adding
the exclusion, runtime planning requires its whole range to be covered by
advertised RAM and disjoint from ATF, the full probe extent and the FDT. This
does not establish actual readability or complete firmware ownership. Binding reference:
[Linux chosen binding](https://android.googlesource.com/kernel/common/%2B/fb73974172ff/Documentation/devicetree/bindings/chosen.txt).

Pinned TF-A source confirms that its secondary mailboxes at 0x100/0x108 and
BL31 region starting at 0x1000 lie inside the existing [0, 0x80000) exclusion.
Its FDT mapping window is an accessibility mapping, not an allocation of all
4 MiB. This source review does not enumerate GPU/framebuffer/other firmware
allocations or replace runtime FDT and boot-configuration evidence.

The resolver now returns two distinct views: `available` excludes live buffers
and is the candidate view for new allocations; `reservation_free` retains live
buffers but excludes fixed and proposed dynamic reservations. The latter can
support a contiguous bootstrap mapping containing those buffers, but is never
allocation input or proof of ownership. Both outputs are published atomically.
All firmware exclusions must be included in `plan.fixed` before using the second
view for handoff. The diagnostic probe now appends the pinned ATF exclusion to
fixed reservations, failing closed if that table is full. Overlap with existing
FDT reservations is allowed. This removes ATF from both views but does not prove
that every firmware allocation has been identified. The actual runtime
mapping/ownership integration remains unfinished.

Native reservation-plan decoding is now implemented: fixed exclusions and up to
eight well-formed dynamic requests are returned separately, with at most eight
allowed windows per request. Malformed lengths/alignment/ranges fail atomically;
static reg overrides size/alignment/alloc-ranges. The static-only wrapper refuses
unresolved dynamic requests. The original malformed CMA property remains rejected
without repair.

The pure native resolver now subtracts fixed reservations and caller-supplied
live extents, then places requests in input order at the lowest aligned fit.
Every placement is excluded before the next request. It returns the full plan
and remaining RAM only on success; it does not write allocated memory, change
the firmware tree, or claim ownership. It supports at most 24 live extents in
addition to 32 fixed exclusions and eight requests. First-fit can reject a set
that a different ordering could fit; no backtracking is attempted. The caller
must establish a complete live-image inventory before using the result. Runtime
allocator integration remains pending. The probe now exercises this path only
for diagnostic proposals, excluding the pinned ATF range, the complete probe
linker extent (including all stacks), and the runtime FDT. All remaining ranges
are labeled incomplete live inventory, not allocator input. No request is
committed or written back to the tree. The fresh probe builds and all 85 host
tests pass; this is not on-device evidence.

Implementation checkpoint: native ranges_find now finds an aligned lowest fit
inside available RAM and explicit allocation windows, without writing memory or
committing an allocation. Its sanitizer test checks 1,000 generated cases against
an exhaustive-address oracle. The caller still must decode/validate the request,
subtract complete exclusions first, and reserve the returned range before handling
another request. The pinned CMA encoding mismatch is not bypassed by this helper.

Dynamic CMA is an OS allocation request, not evidence of a pre-existing fixed
firmware allocation. It must not be mistaken for a physical reservation with an
unknown base. The [Devicetree reserved-memory binding](https://devicetree-specification.readthedocs.io/en/latest/chapter3-devicenodes.html#reserved-memory-node)
distinguishes static reg ranges from size/alignment/alloc-ranges requests. It
also specifies that reg overrides size when both exist. Both project parsers
now honor that precedence; reusable static pools remain excluded.

[Linux v6.12 reserved-memory initialization](https://github.com/torvalds/linux/blob/v6.12/drivers/of/of_reserved_mem.c)
allocates dynamic regions during OS initialization. Its size decoder requires
the property's length to match the declared size-cell count. This is relevant
evidence about Linux behavior, not code being imported into the loader.

The local pinned firmware DTB declares two size cells but contains the four-byte
CMA size 04000000. The [inspected Raspberry Pi rpi-6.18.y source](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/arch/arm64/boot/dts/broadcom/bcm2712.dtsi)
instead has an eight-byte size for 64 MiB, with a permitted allocation window
below 1 GiB. That branch is not the provenance of our pinned blob and does not
authorize silently replacing it. Runtime firmware mutation remains unobserved.

Next policy work: inspect the runtime size encoding; require well-formed dynamic
requests; then integrate resolution against complete static/live exclusions before
any XNU placement. Any compatibility correction needs a narrow, recorded provenance
rule and tests. No blanket ignore of CMA or other dynamic reservations is enabled.
The pinned malformed-property rejection remains despite the new resolver. This is a
loader policy/encoding issue, not proof that firmware already owns the entire
alloc-ranges window.
