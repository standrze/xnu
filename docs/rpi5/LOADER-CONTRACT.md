# Initial thin-kernel loader contract — work in progress

## Zero virtual slide and local relocations

The initial loader must preserve the kernel's linked virtual addresses. Physical
placement is a separate mapping decision: do not add a physical load delta to
kernel pointers, Mach-O vmaddrs, section addresses or the virtual entry point.
The eventual physical entry transfer and boot_args mapping still need validation
against start.s; this document does not supply a runnable loader.

Evidence from current stripped image SHA-256
`eb6cee20eb0ec2a254aab3487e6279d2e0cba7d3f52e45bb472de6fd8c75957a`:

- __mh_execute_header is `0xfffffe0007004000`, the linked base; virtual entry is
  `0xfffffe00074c8488`.
- All 93,292 local relocation records are ARM64_RELOC_UNSIGNED, non-external,
  non-PC-relative and eight bytes wide. Every site fits in one file-backed
  segment and no site is duplicated. Every stored pointer falls inside a
  nonempty virtual segment of this image.
- `__TEXT,__thread_starts` exists but has size zero.

`osfmk/arm/arm_init.c:arm_slide_rebase_and_sign_image` computes the non-fileset
slide from the mapped header address minus VM_KERNEL_LINK_ADDRESS. It calls
rebase_threaded_starts only for a nonempty threaded-starts section. This path
does not consume LC_DYSYMTAB local relocations. The separate kext sliding path in
libkern/c++/OSKext.cpp uses the first segment's vmaddr as the ARM64 relocation
base and adds virtual slide to the pointed-to value; it is not the main kernel
startup rebasing path.

For the initial zero-slide image, these ordinary local pointers already contain
their desired virtual values. Preserve their bytes. This is not authorization
to discard link-edit data, nor support for nonzero KASLR, split-segment movement,
filesets or chained/threaded fixups. Each would need a separately reviewed
contract. Re-run the audit after changes to the kernel or linker configuration.

## Still open

See [early device-tree consumers](DEVICE-TREE-CONTRACT.md) for the source-backed
property requirements now identified. A well-formed root-only tree will not boot:
chosen DRAM properties, writable fresh seed storage, CPU identity/state and
deliberate SoC address translation are required independently of serialization.

`prepare_with_tree` connects the encoder to the handoff planner. It derives
deviceTreeLength from the exact encoded bytes, checks that allocation alongside
the other live ranges, and returns planned tree/boot_args writes. It rejects a
separately supplied length and catches tree growth into another allocation.
These remain in-memory operations: no writes or CPU transfer are performed.
An encodable root-only test tree is not a bootable hardware description.

`tools/rpi5/apple_dt.py` now encodes the Apple flattened format defined by
pexpert/pexpert/device_tree.h: little-endian node counts, 32-byte property-name
fields, uint32 payload lengths and four-byte payload alignment. It generates
each node's NUL-terminated name property and rejects duplicate child names,
cycles, excessive depth, oversized output and non-byte property payloads.
Wire-layout tests cover nested nodes and padding. This is not an FDT translator
or a valid Pi board description; property values still require source-backed
translation and a native SecureDT parser compatibility test remains pending.

`tools/rpi5/prepare_handoff.py:prepare` now composes the Mach-O inspection,
physical copy/zero operation inventory, live-allocation overlap checks,
bootstrap mapping validation and boot_args serialization. Callers supply the
actual RAM extent, reservations, boot-data positions and all live loader
allocations. It derives topOfKernelData, the initial tree KVA, physical entry
and physical x0 boot-argument pointer. It rejects nonzero-slide/fileset/threaded
fixup inputs and conflicting or unmapped allocations. No copying or transfer is
performed. Source-buffer lifetime and copy ordering must still be implemented
safely; the caller must include the input buffer in live allocations if it is
still needed, not silently overlap it with output destinations.

The current kernel produces ten copy and two zero-fill operations in a synthetic
1 GiB layout, with boot_args at `0x3000000`, tree at `0x3004000`, and explicitly
listed loader/stack allocations through `0x3140000`. These are test addresses,
not an approved boot medium or actual-board placement. The device-tree length
in this experiment is synthetic; no real tree or fresh entropy was supplied.

`tools/rpi5/boot_args.py` provides the headless revision-2/version-2 binary
serializer for this pinned arm64 header. A native arm64 compilation test checks
every serialized field offset and the 1152-byte structure size against the exact
upstream C declarations. Padding, video fields, machineType and bootFlags are
zeroed; command lines are ASCII, bounded and NUL-terminated. This establishes
the byte layout, not the correctness of a proposed handoff. In particular,
complete topOfKernelData coverage and boot version acceptance along the entire
startup path still need validation. The
serializer deliberately does not select physical addresses or supply entropy.

The non-fileset device-tree pointer relationship is now traced in source:
start.s converts the boot_args physical pointer to KVA before calling arm_init,
but does not rewrite the structure's deviceTreeP. arm_init copies the structure
and passes it to PE_init_platform(FALSE), which copies deviceTreeP directly into
PE_state and calls SecureDTInit. Therefore deviceTreeP must already be the initial
linear KVA (`virtBase + treePA - physBase`), not the raw physical address. Later,
arm_vm_init remaps the post-kernel boot-data extent and PE_slide_devicetree adjusts
the pointer for that mapping. `encode_with_physical_tree` enforces the initial
linear conversion and placement after the supplied kernel end but below
topOfKernelData. Callers still must validate the entire allocation against the
bootstrap mapping and actual reservations. Source tracing is not a hardware test.

`tools/rpi5/bootstrap_layout.py` now models these assembly arithmetic constraints
for the initial zero-slide 16 KiB profile. Its `validate` function requires
explicit boot bases, memory size, one usable RAM extent, reserved ranges and all
required early-boot ranges. It rejects unsafe inputs and returns the actual
rounded mapping, table-page demand and unmapped tail. It is not connected to a
loader and does not discover RAM, verify FDT reservations or validate boot_args
serialization. Its required-range list must eventually include more than kernel
segments: boot_args, device tree, init image, stacks and other live loader data.

A synthetic 1 GiB reservation-free extent with header PA `0x1004000` accommodates
the current kernel segments in four table pages and 31 L2 entries per mapping.
This is a host arithmetic example, not an approved Pi physical placement. Its
final 32 MiB is outside the bootstrap mapping. No real-board RAM or reservations
were supplied to this experiment.

Bootstrap source constraints found during start.s review:

- After advancing the boot_args bases to the physical Mach-O header, start.s
  calculates the L2 entry count as the adjusted memory size shifted right by
  ARM_TT_L2_SHIFT (25 for 16 KiB granules). This truncates the remainder.
- The block writer executes its first store before decrementing its count.
  A zero-entry request is therefore unsafe; the loader must reject an adjusted
  extent smaller than one 32 MiB block before transfer.
- Block descriptors round physical addresses down to block boundaries. Safe
  placement must account for the mapped prefix before the header, not just
  the kernel's segment intervals. The truncated tail must not contain any
  data or instructions needed before permanent mappings are established.
- start.s initially clears four page-table pages. Any plan requiring additional
  tables must establish that those pages are initialized before use, or extend
  that initialization; available allocation capacity alone is insufficient.
- The later DEVELOPMENT check in arm_vm_init.c compared a page count to the
  allocation's byte size. It now converts the allocation to ARM-page units.
  That later check does not protect earlier assembly writes.

Physical placement, RAM reservations, segment copy/zero-fill implementation,
boot_args values, bootstrap page-table capacity and the entry machine state
remain unimplemented or unverified. The 32 MiB congruence requirement is only
one constraint; it does not prove safe placement or mapping coverage. Instruction
compatibility, runtime providers and actual-board serial evidence remain gate
requirements.
