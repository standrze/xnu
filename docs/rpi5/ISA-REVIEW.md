# Cortex-A76 artifact review — in progress

The `31c860a0` candidate was physically booted on 2026-09-25; see the exact
probe and raw capture identities in `GATE1-AUDIT.md`. It reached the known
IOKit platform-driver panic after crypto/PRNG registration. This directly
exercises the added ISB and ordinary startup path. The bounded ACTLR/hint
disposition below closes Gate 1 for this artifact without claiming exhaustive
future-path coverage.

## Gate 1 control-state disposition — 2026-09-25

For the exact hardware-tested image, `_get_aux_control` and
`_set_aux_control` remain linked at `0xfffffe00074dbef0` and
`0xfffffe00074edff8`. A source-wide search of `osfmk`, `pexpert`, `bsd`, and
`iokit` finds only their definitions and header declarations, not call sites;
the linked disassembly has no direct branch to either helper. They are not a
required part of the demonstrated boot path. This is a bounded reachability
conclusion, not proof that no future indirect caller or module can invoke an
implementation-defined ACTLR access. Any use added later requires a separate
BCM2712 value/permission review.

The exact image has two `hint` instructions. Source places `hint #0x45` in
`panic_with_options` as a Fastsim debug-port signal and `hint #0x4f` in
`PE_arm_panic_hook` as a Fastsim trace signal. Neither is a boot prerequisite.
Arm describes A64 hint-space encodings as NOPs on implementations without
their optional behavior ([Arm architecture blog](https://developer.arm.com/community/arm-community-blogs/b/architectures-and-processors-blog/posts/p2-enabling-pac-and-bti-on-aarch64));
the hardware capture additionally shows the panic path continuing to serial
output rather than trapping at the first signal. These signals are not used as
functional diagnostics or synchronization. This resolves the Gate 1
instruction-compatibility concern, while retaining later panic/debug path
testing as a separate task.

The inventory has no PAC, AUT, or BTI mnemonic, no range-TLBI operand, and
its sole apparent `subg` word is the byte-verified SHA-256 constant described
below. The feature-sensitive LSE/RCpc/FP/SIMD/SHA2 families match the recorded
ID registers; the Pi-only CPACR ISB was exercised in the current boot. This
is an artifact-specific Gate 1 review, not a certificate for all execution
paths, hardware drivers, or a future compiler/configuration.

Latest candidate (2026-09-12): `31c860a0ad7de4e29bdc6226eb0cd7aff8ac7a259c393fa77ebcf6d4ef208b7b`,
from `fresh-me76tvee` and byte-identical `fresh-pa7er_07`. Adds the required
BCM2712 ISB after FP/SIMD enablement. Exact file comparison proves executable
bytes outside [0xfffffe00074da5a0,0xfffffe00074da628) match the older artifact
below, with identical segment/section geometry. Thus byte-backed annotations
outside that range carry forward; changed startup instructions need their own
review. New inventory: `build/rpi5/isa-inventory-controls-31c860a0.json`.
All unknown-word records are unchanged; one ISB is added. Full build and
validation details are in GATE1-AUDIT.md. The hardware execution recorded above
supersedes the earlier untested-candidate status.

Artifact: reproducible kernel SHA-256
`971d44c3f649e743ed58c6ab43dad631ca5b718d2fe012054d480a118a7bc486`,
from `fresh-gidd72lh`. Do not apply address annotations to a different image.

`tools/rpi5/inventory_isa.py` performs structural Mach-O validation, disassembles
the exact file, verifies it did not change, and records the tool version,
mnemonic counts and each unknown word with its nearest printed label.
Report: `build/rpi5/isa-inventory-971d44c3.json`.
It inventories 1,777,036 disassembled words and 487 unknown words across 22
nearest-label groups. A label is **not** a proven function boundary. The tool
always reports manual_review_required; recognized instructions may still need
feature/privilege review. This is not a compatibility certificate.

## Current ISA audit status — 2026-09-12

### Newer ID slots and floating-point operand review

Decoded the original instruction words, not just objdump register names:
ISAR2 at `0xfffffe00074e44f4` is `d538064c`, with
(op0,op1,CRn,CRm,op2)=(3,0,0,6,2); PFR2 at `0xfffffe00074e47a0` is
`d5380448`, encoding (3,0,0,4,2). Both are in the architecturally reserved-zero
ID space when unimplemented. Arm's clarification permits EL2 trapping via
HCR_EL2.TID3; `probe_entry.S:98–99` explicitly sets HCR_EL2 to `0x80000000`,
which clears TID3. Thus these reads do not require the newer feature to exist
under this loader's EL2 contract. This resolves the suspected unsupported-read
issue, without claiming a new hardware measurement of either value.
Source: [Arm architecture known issues L.b, issue 02, page 145](https://documentation-service.arm.com/static/6894bc07e7f7ce6150e88fca%3Ftoken%3D).

The exact artifact's scalar floating-point arithmetic/conversion operands use
S/D registers, and FNEG.2D uses V registers. All three apparent scalable FMLS
words are data: `0xfffffe00074ed800`, `0xfffffe00074ed834`, and
`0xfffffe00074edfd0` fall entirely inside the byte-verified IRQ/FIQ/MDSCR panic
strings listed below. Together with the earlier FMOPA/FNMLS mapping, none of
these apparent scalable floating-point instructions is executable.

Recorded PFR0 has FP[19:16]=1 and AdvSIMD[23:20]=1; ISAR0.SHA2[15:12]=1.
These advertise FP/Advanced SIMD and the SHA-256 instruction family (A76 TRM
B2.62/B2.67). The inventory contains 24 SHA256H, 24 SHA256H2, 16 SHA256SU0 and
16 SHA256SU1 words. The linked startup writes CPACR_EL1=`0x300000` at
`0xfffffe00074da59c`; the loader sets CPTR_EL2=`0x33ff` before entering EL1.
Feature availability is established for these families; synchronization,
state preservation and numerical/crypto correctness are separate checks.
Source: [Cortex-A76 TRM](https://documentation-service.arm.com/static/5f562083235b3560a01e03bc).

A source-wide search finds no get_aux_control/set_aux_control callers beyond
their definitions and declarations. The linked disassembly contains no direct
B/BL to either helper. This narrows ACTLR review but does not prove absence of
indirect references; retain that distinction before signing off the helper.

### Linked conditional register paths verified

The following checks use the exact `971d44c3` image, rehashed during structural
inspection. Addresses are not transferable to another build.

**SME:** `_commpage_init_arm_optional_features_smfr0` calls `_arm_sme_version`
at `0xfffffe00074e4e18`, then CBZ at `0xfffffe00074e4e1c` skips the SMFR0 read
to the return path at `0xfffffe00074e4ea4`. The getter loads the four-byte
`sme_version` at `0xfffffe00071cc5a0`; its linked initial bytes are zero.
The original `osfmk/DEVELOPMENT/sme.o` defines only the getter and the two
SME state variables (plus assembler local symbols), not `arm_sme_init`.
Source `sme.c` puts the version probe and writer behind HAS_ARM_FEAT_SME;
the source initializer is zero. This resolves the apparent SMFR0 access for
this configuration's ordinary initialization path. It is not an SME runtime test.

**Debug slot limits:** linked `_machine_do_debugid` at `0xfffffe00074da670`
reads DFR0. Its vector shift constant at `0xfffffe0007009840` is exactly
(-20, -12), followed by nibble masking and +1, matching source discovery of
watchpoint/breakpoint counts. Both debug setters subtract one and check the
unsigned index against 15 before loading a signed jump-table entry. Direct
reads of all four tables give these destinations for the A76's documented
six breakpoint/four watchpoint pairs:

| Setter | Table / relative base | Count | Destination / first slot |
| --- | --- | --- | --- |
| 32-bit breakpoint | 0xfffffe00074eeff8 / 0xfffffe00074eec58 | 6 | 0xfffffe00074eed34 / BVR5 |
| 32-bit watchpoint | 0xfffffe00074ef038 / 0xfffffe00074eedc4 | 4 | 0xfffffe00074eeec4 / WVR3 |
| 64-bit breakpoint | 0xfffffe00074ef4b8 / 0xfffffe00074ef118 | 6 | 0xfffffe00074ef1f4 / BVR5 |
| 64-bit watchpoint | 0xfffffe00074ef4f8 / 0xfffffe00074ef284 | 4 | 0xfffffe00074ef384 / WVR3 |

The source's descending fallthrough handles lower slots. Slot-15 words do not
imply unconditional slot-15 access. Hardware DFR0 itself is not in the retained
loader feature record; this is linked dispatch verification against the TRM
counts, not a claim of a hardware debugger session. Arm documents those counts
in B2.60 of the [Cortex-A76 TRM](https://documentation-service.arm.com/static/5f562083235b3560a01e03bc).

**Auxiliary ID:** the named AIDR_EL1 read in `ml_feature_supported` is a bitmask
query, not a write. A76's AIDR is read-only with reserved-zero fields (TRM B2.14),
so it does not advertise Apple's auxiliary features. ACTLR caller/value review
remains separate.

**Simulator hints:** source `debug.c:1358` and `hwtrace.c:454` identifies #0x45
and #0x4f as Fastsim panic notifications. Their presence has a source explanation;
this does not substitute for the outstanding architectural hint-space check.
Unconditional ISAR2/PFR2 reads and FP/crypto operands remain open as above.

### Operand inventory and board feature comparison

Re-ran the inventory against the unchanged `971d44c3` kernel with control
operands retained: `build/rpi5/isa-inventory-controls-971d44c3.json` contains
1,210 control/system words. This remains a linear inventory, including data;
it does not silently certify instructions or treat labels as function extents.
Three inventory parser tests pass, including operand preservation.

Raw capture `serial-capture-a8bp8q85`, line 141, reports
ISAR0=`0000100010211120`, ISAR1=`0000000000100001`,
MMFR0=`0000000000101122`. Lines 256/259/262 report matching secondary values.
Decoding these fields against Arm's Cortex-A76 TRM sections B2.62–B2.64:

| Field | Observed value | Relevant support |
| --- | --- | --- |
| ISAR0.Atomic [23:20] | 2 | LSE atomic families, including CASP |
| ISAR1.LRCPC [23:20] | 1 | LDAPR, LDAPRB, LDAPRH |
| MMFR0.TGran16 [23:20] | 1 | 16 KiB translation granules |
| MMFR0.PARange [3:0] | 2 | 40-bit physical addresses |

These match the selected atomic/load instruction families and board memory
profile. Atomic availability does not establish peripheral atomic access or
memory-order correctness. Source: [Arm Cortex-A76 TRM, 100798_0401_00_en](https://documentation-service.arm.com/static/5f562083235b3560a01e03bc).

All 28 inventoried TLBI words use ASIDE1/ASIDE1IS, VAAE1IS, VAALE1IS,
VAE1IS, VALE1IS, VMALLE1/VMALLE1IS. No range-TLBI operand appears.
No raw `S3_*` implementation-defined register spelling appears in this output;
named ACTLR_EL1 and AIDR_EL1 accesses still require caller/value review.

Concrete remaining control-path checks identified by the new inventory:

- `commpage_populate` includes ISAR2 at `0xfffffe00074e44f4` and PFR2 at
  `0xfffffe00074e47a0`. Establish the A76 behavior of those reserved/newer ID
  register slots before accepting their unconditional reads.
- SMFR0 at `0xfffffe00074e4e20` is behind an `arm_sme_version() == 0` return
  in source; confirm the actual linked branch and SME-version initialization.
- Debug register accesses through slot 15 are behind breakpoint/watchpoint
  count switches in `pcb.c`; confirm discovery and linked dispatch bounds.
- HINT #0x45 and #0x4f occur at `0xfffffe00072f1ff4` and
  `0xfffffe00078d66ac`. Review their architectural fallback semantics and callers.
- XNU `start.s:858–859` enables FP/SIMD through CPACR_EL1 after the loader's
  general-register-only phase. Linked ordering and remaining FP operands need
  review before broader FP/crypto execution claims.

These are actionable audit items, not demonstrated faults. No kernel source,
SD contents or board state changed during this pass.

Unknown-word classification is now complete for this image:

- 485 unknown words are compiler-generated data tables/pools/strings.
- 2 unknown words are intentional undefined-instruction debugger traps
  (`e7ffdeff`/`e7ffdefe`), not AArch64 `brk` encodings.

That means `GATE1` unknown-word pressure is now closed; remaining work is
explicit architecture-compatibility review.

Recognized-instruction classes in this kernel are already partitioned in the
existing sections below, with the following coarse counts from this snapshot:

- Atomic/RMW + ordering families: CAS* (including `casp*`, `casa*`, etc.),
  `ldadd*`, `ldclr*`, `ldeor*`, `ldset*`, `ldsmax*`, `ldumax*`, RCpc loads
  (`ldapr*`) and exclusive ops.
- Crypto/hash classes include `sha256*`. The apparent `fnmls`/`fmopa` words
  were mapped to exact data ranges in the recognized-extension first pass below.
- System-register/control families: `mrs/msr`, `at`, `dc`, `ic`, `tlbi`,
  barriers (`dmb/dsb/isb`), and `hint` instructions.
- SIMD/floating/compare families are present and currently treated as existing
  compile-profile instructions until board-feature confirmation is complete.

Open items are therefore feature/runtime validation, explicit `BCM2712` support
assumptions, and board-path exercise, not unknown-word triage.

llvm-objdump's Mach-O data-in-code inventory has zero entries. Consequently,
linear disassembly treats constants, strings and jump tables as instructions.
Neither dropping all unknown words nor accepting all recognized mnemonics is a
valid way to close the architecture audit.

## Exact ICMPv6 table mapping — 2026-09-12

The largest group, 123 unknown words under nearest label `_icmp6_reflect`,
is now mapped to compiler jump table `lJTI4_0`, not excluded as a whole function.
The object is `fresh-gidd72lh/obj/DEVELOPMENT_ARM64_BCM2712/bsd/DEVELOPMENT/icmp6.o`,
SHA-256 `3cd07729e546b0bef0a883964959ebd2a66dde1052a7e2ad48ae47596ea37d3d`.

Object symbols: `_icmp6_reflect`=0x750, `lJTI4_0`=0x11f0,
`_icmp6_input`=0x1420. Kernel `_icmp6_reflect`=0xfffffe000766ca70;
the mapped table starts at 0xfffffe000766d510. Object text file offset is 2008;
kernel text VA/file offset are 0xfffffe00072a8000/2768896. Thus object file
offset 6600 maps to kernel file offset 6722832. Direct comparison of the full
560-byte table/alignment region succeeds (SHA-256
`1332cb6725061b6b6c540dfb08d9ed7b34b92bf0152c48cdb36b143ae9796e1a`).

Compiler assembly `build/rpi5/icmp6-isa-review.s` explicitly contains 137
`.long LBB4_*-Ltmp434` offsets after `lJTI4_0`. Dispatch loads the signed
32-bit entry with LDRSW, adds the code base Ltmp434 and branches through it.
The source location is icmp6.c:2494 (icmp6_ifoutstat_inc). The table occupies
exactly [0xfffffe000766d510,0xfffffe000766d734); three NOPs follow before
`_icmp6_input` at 0xfffffe000766d740. All 123 unknown addresses in this group
fall inside the table (first d520, last d708), not the padding or next function.

Assembly was generated using the recorded compile arguments, with output/
dependency recording removed and `-S` selected. A literal replay initially
failed because the compilation database expands `-fbounds-safety` to repeated
internal `-fexperimental-bounds-safety` flags that this clang driver rejects.
Those entries were translated back to the public `-fbounds-safety` flag used by
MakeInc.def/CFLAGS_BOUND_CHECKS; bounds checking was not disabled. The assembly
is corroborating semantic evidence; byte identity is proven independently
against the original object and linked kernel, not assumed from that replay.

Result: 123 of the 487 unknown words have exact compiler-table attribution in
this image. The remaining 364 still need classification/validation; this does
not finish recognized-instruction feature review or certify the kernel.

## Source-backed explanations examined

## Exact NECP table mapping — 2026-09-12

The original `bsd/DEVELOPMENT/necp.o` in `fresh-gidd72lh` has SHA-256
`ca2c9fba85e8159a42a8ffd35d9d50bb7463535a26ec8d8e6467a62f92a581f8`.
Object `__TEXT,__text` starts at VA 0/file offset 2488. Three independent
function anchors agree on the linked delta 0xfffffe00075a3560:
session_action 0xb40 -> 0xfffffe00075a40a0; application_find_policy_match_internal
0x5510 -> 0xfffffe00075a8a70; policy_apply 0x1a180 -> 0xfffffe00075bd6e0.

Generated `build/rpi5/necp-isa-review.s` (same bounds-safety replay translation
documented above) names the tables and contains signed `.long LBB-Ltmp` entries
referenced by jump dispatches. Original-object and linked-kernel bytes compare
equal for each exact table, not merely a surrounding nearest-symbol region:

| Table | Object VA | Linked half-open range | Entries / bytes | Byte SHA-256 |
| --- | --- | --- | --- | --- |
| lJTI5_0 | 0xe5c | [0xfffffe00075a43bc, 0xfffffe00075a4404) | 18 / 72 | 26d1bcd4d671e08fdae1f62a0a46bc6b51624fcc18da3d3604f6a9ea8f4f653e |
| lJTI33_0 | 0x893c | [0xfffffe00075abe9c, 0xfffffe00075ac088) | 123 / 492 | 196189525aa4d030ea3004ae322a010f41a71fa16e80abd6c9a741c26d9866c6 |
| lJTI91_0 | 0x1c170 | [0xfffffe00075bf6d0, 0xfffffe00075bf780) | 44 / 176 | 23187d3e071fa33593384b34b1da4eaf8576c906a14c80b781dfb80c59f1cd7c |
| lJTI91_1 | 0x1c220 | [0xfffffe00075bf780, 0xfffffe00075bf7cc) | 19 / 76 | 059ef6f5734ce16934832315047c50a8af07e59c6624fcba77c03dbccf213d04 |

These exact ranges contain all 107 unknown words attributed to
application_find_policy_match_internal, both under session_action, and all six
under policy_apply. The second policy table contains no unknown words but is
also data; recognized mnemonics there must not be counted as executable code.

Cumulative precise attribution: 238 of 487 raw unknown words (123 ICMPv6 plus
115 NECP) are compiler table data; 249 remain. This does not waive CPU-feature
review of the surrounding executable instructions or certify any networking
runtime behavior. No code or board state was changed.

## Exact LZ4 decode table mapping — 2026-09-12

The original `osfmk/DEVELOPMENT/lz4_decode_arm64.o` in `fresh-gidd72lh`
has SHA-256 `8000543e7ecd2fe5a77fdda373e90579c8e7df793e837beab3c20c7d16490546`.
Its text starts at VA 0/file offset 312, with size 0x410 and no relocations.
The `_lz4_decode_asm` anchor maps VA 0 to linked 0xfffffe00074cc580.
ADR instructions at object offsets 0x18 and 0x1c reference 0x200 and 0x400;
source lines 137–138 name these permutation and distance tables. The function
returns at 0x1dc; alignment NOPs precede the tables, not fall-through execution.

Source lines 308–333 explicitly declare 512 permutation bytes and 16 distance
bytes. Parsing those `.byte` declarations yields exactly the original object's
528 bytes at file offset 824. Those bytes also compare equal to the linked
kernel at file offset 5015424, SHA-256
`f7bb30778915b574b63a17573babfdeb97251ae92fb57e7302e69783f454f92a`.
The precise linked half-open ranges are permutation
[0xfffffe00074cc780, 0xfffffe00074cc980) and distance
[0xfffffe00074cc980, 0xfffffe00074cc990). All 100 unknown words in the
`_lz4_decode_asm` nearest-label group fall inside these tables.

Cumulative exact data attribution is now 338 of 487 unknown words; 149 remain.
This classifies table bytes only, not the surrounding executable ISA or LZ4
runtime correctness. No kernel or board changes were made.

## Exact SHA-256 constant mapping — 2026-09-12

Original `osfmk/DEVELOPMENT/sha256_compress_arm64.o` SHA-256:
`7db8153924650829cbc11eac098d57d3ea43bebd6cd4e6ac7c1a925a7ce3a067`.
Its `__HIB,__text` begins at VA 0/file offset 312. K256 is at VA 0;
the compression function begins at 0x100 and references K256 as table data.
Parsing the 64 source `.long` constants as little-endian words produces exactly
the 256 original-object bytes at [312,568), which also match kernel bytes at
file offset 9901488. Table SHA-256:
`74ef7306e7452d6859b6463ce496b8df30925f69e1b2969e1f3f34bbc9c6af04`.

The kernel `__hib_text` section begins at VA 0xfffffe0007974760/file offset
9897824. The precise table range is [0xfffffe00079755b0,0xfffffe00079756b0).
All 32 unknown words under K256 lie inside this range. The apparent SUBG word
at 0xfffffe0007975660 is likewise constant data, not executable MTE use.
Cumulative exact data attribution is 370 of 487 unknown words; 117 remain.
Executable feature review remains required outside the verified data ranges.

## Exact string-operation masks — 2026-09-12

The six unknown words grouped under `_memcmp_zero_ptr_aligned` and `_strlen`
actually belong to the following objects' leading data, not those functions.
Both original objects have text VA 0/file offset 312 and no relocations.
`strnlen.o` defines `_strnlen` at 0x20 and `_strlen` at 0xc0; linked anchors
0xfffffe00074df2e0 and 0xfffffe00074df380 independently give table base
0xfffffe00074df2c0. `strncmp.o` defines `_strncmp` at 0x10, linked at
0xfffffe00074df410, giving mask base 0xfffffe00074df400.

`strnlen.s:62` declares bytes 0..15 followed by 16 zero bytes; `strncmp.s:65`
declares bytes 0..15. Their ADR/LDR references name these masks explicitly.
Those source-declared values match both original object bytes and linked
kernel bytes exactly:

| Object | Linked half-open range | Kernel file offset | Table SHA-256 |
| --- | --- | --- | --- |
| strnlen.o | [0xfffffe00074df2c0,0xfffffe00074df2e0) | 5092032 | 809a4c1bad269d7bc2c9de4a1d7d686b32995114da709324830c99529e5f76b2 |
| strncmp.o | [0xfffffe00074df400,0xfffffe00074df410) | 5092352 | be45cb2605bf36bebde684841a28f0fd43c69850a3dce5fedba69928ee3a8991 |

Original object SHA-256 values are respectively
`f49ab284f4eec4883d3e5ec8bb0dbb1447b871ce9d814acb16cdab3f1905d255`
and `b3c629c7cb9ea14257d9ba325ceab8f7ef1f85582c5cd7f65c75d84852a71bb2`.
Each exact range contains three unknown words. Cumulative data attribution:
376 of 487; 111 remain. This corrects nearest-label ownership without excluding
any executable part of memcmp, strlen, strnlen or strncmp.

## Exact inline panic strings — 2026-09-12

Parsed the eight named `.asciz` declarations from `locore.s` and
`machine_routines_asm.s`, including escaped newlines and terminating NULs.
Each resulting byte sequence occurs exactly once in its original object and
exactly once in the audited kernel. Source references pass their addresses to
panic routines; these are not inferred function-wide exclusions. Exact matched
ranges and fully contained four-byte unknown words are:

| Source label | Linked start | Exclusive end | Object file offset | Unknown words |
| --- | --- | --- | --- | --- |
| Lsp1_irq_str | 0xfffffe00074ed7e4 | 0xfffffe00074ed80b | 6588 | 4 |
| Lsp1_fiq_str | 0xfffffe00074ed818 | 0xfffffe00074ed83f | 6640 | 4 |
| Lsp1_serror_str | 0xfffffe00074ed84c | 0xfffffe00074ed87c | 6692 | 8 |
| L_underflow_str | 0xfffffe00074edab4 | 0xfffffe00074edadb | 7308 | 6 |
| L_preempt_count_notzero_str | 0xfffffe00074edaf4 | 0xfffffe00074edb1d | 7372 | 7 |
| Lupdate_mdscr_panic_str | 0xfffffe00074edfc4 | 0xfffffe00074edfd6 | 548 | 2 |
| L_set_tcr_panic_str | 0xfffffe00074ee044 | 0xfffffe00074ee06a | 676 | 7 |
| L_set_locked_reg_panic_str | 0xfffffe00074ee06a | 0xfffffe00074ee092 | 714 | 5 |

The first five offsets refer to `locore.o`, the last three to
`machine_routines_asm.o`, both under the audited fresh build's osfmk/DEVELOPMENT.
All 43 unknown words are wholly inside string bytes, not alignment padding.
Cumulative exact data attribution is 419 of 487; 68 remain unclassified.
This does not certify exception-path execution or change panic behavior.

## Exact intentional debugger traps — 2026-09-12

Read the original kernel words directly as little-endian uint32 values:
0xfffffe00072f0c1c/file offset 3066908 is `0xe7ffdeff`;
0xfffffe00074e5630/file offset 5117488 is `0xe7ffdefe`.
These match `debug.c:179`/TRAP_DEBUGGER (used at line 759) and
`kdp_machdep.c:568`/kdp_ml_enter_debugger respectively. Both are explicitly
defined in `arm/trap_internal.h:65–72` as debugger trap encodings.
`arm64/sleh.c` recognizes IS_ARM_GDB_TRAP, and the non-PAC path in
`kdp_machdep.c:357–365` advances the saved PC by four for either encoding.

Classify these two words as **intentional executable traps**, never data or
ordinary supported instructions. This source/byte classification does not
claim a completed hardware debugger entry/resume test. Totals: 419 data words,
2 intentional traps, 66 still unclassified out of 487 raw unknown words.

## Checksum diagnostic string — 2026-09-12

`bsd/dev/arm64/cpu_in_cksum.s` declares Lin_cksum_whoops_str as
`os_cpu_in_cksum_mbuf: out of data` plus newline and NUL. The error path
loads its address, calls CKSUM_ERR, and returns before the string.
The exact source bytes occur once in original `bsd/DEVELOPMENT/cpu_in_cksum.o`
and once in the audited kernel. The object's text VA 0/file offset 312 and
linked `_os_cpu_in_cksum_mbuf` anchor 0xfffffe00077ad3e0 independently agree
with the located string address. All five unknown words in this group are
fully contained within those string bytes, not padding or executable code.

Cumulative classification: 424 data words, 2 intentional traps, 61 still
unclassified. Checksum runtime correctness is not inferred from this result.

## Exact LZ4 encoder constants — 2026-09-12

`lz4_encode_arm64.s:403–405` declares two words at L_constant:
LZ4_COMPRESS_HASH_MULTIPLY (2654435761U in vm/lz4_constants.h:34, hex
0x9e3779b1) and 0x80808081. ADR followed by two LDRs at source lines 69–71
loads these as multiplication constants. Original `lz4_encode_arm64.o` text
begins at VA 0/file offset 312, size 0x3e0, with no relocations. Its final
eight bytes, at object VA 0x3d8/file offset 1296, match the two source values
and the linked bytes at file offset 5016936 exactly. Linked half-open range:
[0xfffffe00074ccd68,0xfffffe00074ccd70).

The first word accounts for one unknown; the second misleadingly disassembles
as FMOPA (SME) but is equally data. Neither is executable. Cumulative totals:
425 data words, 2 intentional traps, 60 unknown words still unclassified.
This also removes this particular apparent SME instruction from executable
feature consideration, not other occurrences elsewhere.

## Exact kernel-address literal — 2026-09-12

`machine_routines_asm.s:986` uses `ldr x3, =VM_MIN_KERNEL_ADDRESS` in
Lcopyinframe64. The original object's text VA 0/file offset 408 has an LDR
literal at VA 0x530 targeting VA 0x650, the final eight text bytes. These bytes
equal little-endian 0xfffffe0000000000 and match the kernel's exact range
[0xfffffe00074ee588,0xfffffe00074ee590). Independently decoding the linked
LDR x3 at 0xfffffe00074ee468 confirms its signed PC-relative immediate targets
this same literal. The preceding instruction at object VA 0x64c is RET.

The upper word accounts for the one unknown under `_fill32_nt`; the lower
word disassembles as UDF but is also data. This is a literal pool used by
copyinframe, not part of fill32_nt's executable body. Cumulative totals:
426 data words, 2 intentional traps, 59 unclassified unknown words.

## Final unknown-word groups: console and logging tables — 2026-09-12

Generated `video_console-isa-review.s` and `log_encode-isa-review.s` using
the recorded compile commands and the bounds-safety spelling translation
documented above. Their tables contain contiguous signed `.long LBB-Ltmp`
entries. Exact original-object table bytes compare equal to linked bytes:

| Object / table | Object text file offset / table VA | Linked half-open range | Entries | Unknowns | Table SHA-256 |
| --- | --- | --- | --- | --- | --- |
| video_console.o / lJTI22_0 | 2248 / 0x61b4 | [0xfffffe00074aad94,0xfffffe00074aae5c) | 50 | 38 | 9435194afacfb225752f8eb38c782c9b2140acb9c1c25cf9bfb4ac614d4dc682 |
| log_encode.o / lJTI0_0 | 1688 / 0x79c | [0xfffffe00077e6a7c,0xfffffe00077e6be8) | 91 | 21 | 560c76671fdddbad8d79ba609ba511ab56a1c3b792ca28207f74b86fe62f05b8 |

Mapping anchors: gc_putc_gotpars object 0x59a0 -> kernel 0xfffffe00074aa580;
os_log_context_encode object 0 -> kernel 0xfffffe00077e62e0. All 59 remaining
unknown words are fully contained in these exact tables.

**Raw unknown-word classification is complete for this image:** 485 data words
and 2 intentional debugger traps account for all 487. This is not completion
of the executable CPU-feature review, canonical toolchain validation, or Gate 1.
Recognized mnemonics outside these data ranges still require compatibility
review; additional data tables without unknown words may also exist.

## Recognized extension-looking instructions: first pass — 2026-09-12

Re-disassembled the audited kernel and located every occurrence of the
mnemonics cbge/cbgt/cbhs/cblo, cmla, cmpeq/cmphi, fmopa, fnmls,
ldff1b/ldff1h, stnt1h, sttp, subg and subr (22 words total). All occur in
previously byte-verified data ranges:

- Five SUBR words: LZ4 decode permutation table (74cc830, 74cc868, 74cc8bc,
  74cc8ec, 74cc970; common address prefix 0xfffffe000).
- FMOPA: LZ4 encode constant at 74ccd6c.
- Four FNMLS: panic strings at 74ed7e8, 74ed81c, 74edab4, 74edaf4.
- CMLA: MDSCR panic string at 74edfc8.
- CBGE/CBHS: TCR panic strings at 74ee050/74ee068. The latter word straddles
  the two adjacent verified strings, but all four bytes remain string data.
- CBLO: checksum diagnostic string at 77ad658.
- STTP, CMPHI, STNT1H, CMPEQ, SUBG, CBGT, LDFF1H, LDFF1B: K256 constants
  at 79755bc, 79755d8, 79755f0, 79755fc, 7975660, 7975668, 7975698,
  79756a4 respectively.

These apparent extension uses are not executable. This selected-mnemonic
pass is not exhaustive ISA sign-off: operand-sensitive instructions, system
registers, actual LSE/RCpc/crypto uses and feature availability still need review.

## Other source-backed explanations examined

| Location or nearest label | Evidence | Limit |
| --- | --- | --- |
| K256, including 0xfffffe0007975660 | sha256_compress_arm64.s declares .long 0xd192e819 among SHA-256 constants. It decodes as SUBG when treated as code. | The table is data; this does not waive MTE checks elsewhere. |
| _DebuggerTrapWithState / _kdp_ml_enter_debugger | Words e7ffdeff/e7ffdefe match trap_internal.h and debug.c. kdp_machdep.c recognizes both ARM32-encoded debugger traps and advances PC by 4. | Intentional undefined instructions, not a new CPU feature. Preserve exception-path semantics. |
| _set_tcr / _update_mdscr | machine_routines_asm.s declares the decoded panic strings after terminating branches; inspected set_tcr itself is MSR TCR_EL1, ISB, RET. | Review string extents/branch references before automatically excluding byte ranges. |
| fleh_irq_sp1 / fleh_fiq_sp1 / fleh_serror_sp1 / preempt_underflow / preempt_count_notzero | locore.s contains corresponding inline .asciz panic messages. | Nearest-symbol grouping alone does not delimit the data. |
| _memcmp_zero_ptr_aligned / _strlen | Observed words 03020100, 07060504, 0f0e0d0c form byte-index data. | Complete source/object extent mapping is pending. |
| _lz4_decode_asm | lz4_decode_arm64.s contains explicit byte shuffle tables. | Verify all table extents against the exact linked bytes. |
| _fill32_nt + 0x24 | RET at 0xfffffe00074ee584 precedes the 8-byte literal fffffe0000000000; machine_routines_asm.s uses an assembler literal load of VM_MIN_KERNEL_ADDRESS. | Confirm relocation/literal-pool ownership before a machine-readable exclusion. |

Other groups requiring exact object/source mapping: gc_putc_gotpars (38 unknown
words), os_log_context_encode (21),
os_cpu_in_cksum_mbuf (5), and lz4_encode_2gb (1). They must not be classified as
harmless solely because their values resemble switch tables.

## Remaining work

1. Establish byte-accurate data extents using source/object/relocation evidence;
   keep deliberate traps separate from data and genuine unsupported code.
2. Review executable feature use, implementation-defined system registers and
   Apple/PAC/BTI/MTE/range-TLBI assumptions against the BCM2712 build profile and
   the recorded CPU feature inventory. Early successful boot is not exhaustive
   instruction-path coverage.
3. Reconcile the reviewed artifact with final build provenance. The lock now
   matches installed Xcode 26.6 / 17F113 with macOS SDK 26.5, as confirmed by
   doctor on 2026-09-12. Matching the toolchain alone does not prove every
   retained dependency or hardware-tested artifact matches the current build.
