# Runtime ownership ledger

## Standards-based closure path

Source review: DTSpec sections
[3.4](https://devicetree-specification.readthedocs.io/en/stable/devicenodes.html#memory-node)
and [5.3.1](https://devicetree-specification.readthedocs.io/en/stable/flattened-format.html#purpose)
define memory nodes as physical memory and require reservation of memory the
boot program continues accessing after client entry. Unreserved memory may be
used with client-selected storage attributes, subject to architectural cache
maintenance requirements. The specification's WIMG terminology is not an ARM
MAIR encoding; do not copy those bits into an ARM page-table descriptor.

This supplies an explicit trust contract for the next integration step:
derive candidate Normal RAM from validated runtime memory-node ranges, not
from the 8 GiB envelope or the mere absence of reservations. Intersect the
proposed managed window and its rounded bootstrap mapping with those ranges;
retain the hole and all parsed/proposed reservations. Independently preserve
TF-A, loader/BSS/stacks, payload, FDT, and any initrd. Never infer MMIO is RAM.

An exhaustive reverse-engineered list of every internal firmware allocation is
not required by this interface contract. Its completeness is a firmware trust
assumption, not something the parser can prove. Known contradictions must still
stop deployment; zero framebuffer declarations alone is not evidence of zero
allocations. Earlier statements demanding an exhaustive undocumented buffer
inventory are superseded as an unconditional prerequisite. The firmware's
known property-padding deviation does not by itself establish a memory-map
violation, but neither does successful parsing prove full compliance.

Next implementation: connect the actual resolved runtime ranges to the existing
read-only handoff planner under this stated assumption, validate the rounded
mapping and all live ranges, and inspect its board output before physical copy.
No runtime planner integration or physical write is claimed by this review.

Hardware follow-up: `serial-capture-g_orr2qg` observes probe entry 0x9000000,
FDT 0xb000000, and zero simple-framebuffer declarations. The diagnostic reaches
`STOP BEFORE XNU LOADER` with secondary IRQ evidence. Candidate
`bl33-probe-23dyzrt3` SHA-256 is
`4eec99b2dc9b152370e9f3b447e5ccd7a3bb2e609c8309b864b3eee19a5b7842`;
matching SD config SHA-256 is
`ff9141b6ddca6bc6138f74a26a17fa4064460a46c1ef1e714caeaf5a1fa12090`.
117 tests and native/Python post-CMA geometry validation passed first.
Prior working SD files remain as `probe.before-post-cma.bin` and
`config.before-post-cma.txt`. This supersedes the ledger's earlier statements
that revised probe/FDT placement is not observed. Zero framebuffer descriptors
does not establish absence of undeclared retained firmware buffers.

New diagnostic: `rpi5_fdt_compatible_count` scans all structurally validated
compatible declarations for `simple-framebuffer`, rather than guessing a node
path. It includes disabled declarations and counts duplicate declarations
separately. Other property values, including seeds, are skipped. Tests cover
single/list matches, no match, empty and unterminated compatible values, with
atomic failure output. The probe prints the count as explicitly not an
allocation inventory. Hardware observation and address decoding remain pending.

Scope: candidate handoff window [0x6000000,0x10000000), not all 8 GiB.
Evidence is from the standalone portion of `serial-capture-1awe85cm` unless
otherwise stated. The later Linux boot in that file is a separate allocation
epoch and must not supply addresses for the standalone handoff.

| Object | Evidence | Consequence |
| --- | --- | --- |
| BL31 and secondary mailboxes | Pinned TF-A BL31_BASE=0x1000, BL31_LIMIT=0x80000; mailbox addresses lie below that limit | Retain [0,0x80000); never reclaim it |
| Dynamic CMA | Standalone resolver proposes [0x80000,0x4080000), not committed | Exclude proposed region; old kernel geometry overlaps it |
| Firmware carve-out | Standalone RAM ends at 0x3fc00000 and resumes at 0x40000000 | Never infer the gap is normal or available RAM |
| Firmware reserved record | [0x3fd23200,0x3fd23238) in standalone output | Preserve even though outside managed window |
| Probe and embedded kernel | Current ELF/live range begins 0x6000000; revised candidate begins 0x9000000 | Candidate must be re-observed on hardware; include BSS, stacks, scratch and source payload |
| FDT | Actual current start 0x8000000, length 0x13a32 | Proposed relocation to 0xb000000 is not yet observed |
| Initrd | SD config disables automatic initramfs; standalone log loads no initrd | Continue runtime paired-property validation; do not import Linux recovery's initrd address |
| Framebuffer | Firmware logs framebuffer setup and HDMI hotplug=0, but no allocation extent | No active monitor does not prove absence of retained allocations |
| Other firmware/DMA buffers | No exhaustive retention contract in inspected boot log | Ownership remains incomplete; passing range arithmetic is insufficient |

Next closure work: inspect runtime framebuffer descriptors and documented
headless allocation controls; enumerate any other firmware-owned ranges relevant
to the managed window; validate Normal-memory provenance independently of
reservation subtraction; then perform read-only planning using the actual new
probe/FDT addresses before authorizing physical materialization.

`disable_fw_kms_setup` is not evidence of framebuffer deallocation: the official
[configuration documentation](https://www.raspberrypi.com/documentation/computers/config_txt.html)
describes it as suppressing firmware-selected video-mode parameters for Linux.
Do not use that setting alone to close the framebuffer ownership question.
