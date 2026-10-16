# Gate 1 completion audit — 2026-09-11

## Update — 2026-09-25: corrected kernel exercised on the Pi 5

The exact reproducible kernel `31c860a0ad7de4e29bdc6226eb0cd7aff8ac7a259c393fa77ebcf6d4ef208b7b`
was packaged with the terminal-transfer BL33 probe in
`build/rpi5/bl33-probe-okcrf39o/probe.bin` (SHA-256
`0bc8b552995bf09e9bab29f7ab57ea2cf199ac4af2874f74f27f7325c6c7fa8b`).
The host Mach-O/materialization comparison passed: 18 segments, 93,496 local
relocations, and 17,416,192 materialized bytes. The probe was copied to the
identified `/dev/mmcblk0p1` `XNU_PROBE` partition on the 8-GB Pi 5; its copied
bytes were rehashed and the existing boot config was unchanged. Linux on NVMe
was left as the firmware fallback.

The raw, receive-only UART capture is
`build/rpi5/serial-capture-17808h79/serial.bin` (58,982 bytes, SHA-256
`9b41713052d5d2488e6a06c454a77dd79c2e14020303a5fa0605fdac2d7ae648`).
It records complete kernel-envelope verification, EL1 and virtual timer INTID
27 delivery on all three secondaries and the primary, committed boot data,
and XNU transfer. XNU reaches `BCM2712 crypto and PRNG registered`, then the
expected Gate 2 boundary: `Unable to find driver for this platform:
"device-tree"` at `IOPlatformExpert.cpp:2365`. The 15-second full-reset
watchdog subsequently booted Linux 6.18.34 from the preserved NVMe root;
independent SSH confirmed that state. Thus the Pi-only ISB correction is now
physically exercised through the same startup boundary as the previous image.

Prepared SDK, AvailabilityVersions, libdispatch, firehose, crypto provider,
lockfile, build manifest and embedded-kernel hashes were reconciled to the
recorded inputs. The host suite passes 180/180 tests. This closes the Gate 1
*hardware probe exit* for the recorded board/image. The control-state ISA
review is now dispositioned in `ISA-REVIEW.md`: the linked ACTLR helpers are
not called by this source tree or direct branches in this artifact, and the
panic-only simulator hints have architectural NOP fallback. This closes formal
Gate 0/1 sign-off for this pinned DEVELOPMENT image and the recorded 8-GB
board. It does not certify every latent kernel path or transfer that conclusion
to a different build.
On the final audit, `/Applications/Xcode.app` had changed to Xcode 27.0
(`27A266a`), SDK 27.0. The lock and successful build manifests retain Xcode
26.6 (`17F113`), SDK 26.5. `rpi5.py doctor` therefore correctly rejects a
new canonical build on the present host. This is post-build environment drift,
not a change to the two hashed kernels or raw Pi capture; restoring Xcode 26.6
or deliberately requalifying a new toolchain is required for the next build.
No PID 1, Pi IOKit platform driver, XNU storage, or XNU timer integration is
claimed. Those are Gate 2 and later work.

## Update — 2026-09-12: startup synchronization fixed, canonical builds pass

The BCM2712 common-start path wrote CPACR_EL1.FPEN then returned toward C code
without a subsequent context synchronization event in that assembly path.
Added a Pi-only ISB immediately after the write. Arm's
[barrier guide, page 27](https://documentation-service.arm.com/static/62a304f231ea212bb662321d?token=)
explains why enabling FP/SIMD requires synchronization before dependent use.
This is an architectural ordering correction, not a claimed reproduced trap.

Fresh canonical build `run-ij6q8fa_` exposed a toolchain-pin regression: selecting
canonical Clang 21 stopped applying the existing unused-but-set-variable and
GNU constant-folding warning exceptions. The same compiler previously built
under the exploratory flag. The two diagnostics now remain visible warnings
for BCM2712 independent of pin status; all other -Werror behavior is retained.
No debugger memory-operation behavior was changed to resolve build diagnostics.

Two independent fresh/reproducible builds now pass with source unchanged:

| Run | Output | UTC start–finish |
| --- | --- | --- |
| run-9yqxxc4p | fresh-me76tvee | 21:25:16–21:25:56 |
| run-uki6z6df | fresh-pa7er_07 | 21:25:34–21:26:14 |

Both report canonical Xcode 26.6 / 17F113, SDK 26.5. Full-file cmp passes;
kernel SHA-256 is `31c860a0ad7de4e29bdc6226eb0cd7aff8ac7a259c393fa77ebcf6d4ef208b7b`.
Native Mach-O/host-buffer copy comparison passes (18 segments, 93,496 local
relocations, 17,416,192 materialized bytes). Its synthetic layout result does
not prove a new physical probe placement or boot. The 178 existing tests pass;
two added regressions pass for emitted Pi-only synchronization and board-scoped,
pin-independent warning policy. git diff --check passes.

The new linked CPACR write is at `0xfffffe00074da59c`, immediately followed by
ISB at `0xfffffe00074da5a0`. Compared with `971d44c3`, segment/section geometry
and file sizes are identical. All executable bytes outside
[0xfffffe00074da5a0,0xfffffe00074da628) are unchanged. Unknown-word records are
identical; the mnemonic inventory adds one ISB. Metadata differences also occur
in __TEXT (UUID) and __LINKEDIT, so this is a new artifact identity.

Neither new image was installed. Carry forward byte-backed ISA annotations
only outside that changed startup range, finish control-state review, and
reconcile prepared dependency provenance before full through-Gate-1 sign-off.

## Update — 2026-09-12: newer ID-register concern resolved

Exact instruction encoding checks place ISAR2/PFR2 in the reserved-zero ID
space; Arm's architectural clarification and the loader's HCR_EL2 setting
resolve the suspected unsupported reads. Three additional apparent SVE FMLS
words are verified panic-string data. Recorded FP/SIMD/SHA2 fields support
the corresponding executable instruction families. Evidence and limitations
are in ISA-REVIEW.md. Remaining compatibility sign-off includes control/state
semantics and final artifact provenance. No kernel or board change this pass.

## Update — 2026-09-12: linked SME/debug register paths checked

Verified the actual SME guard/zero initializer and four debug-register jump
tables in `971d44c3`. They avoid the apparent unconditional SME and excess
debug-slot accesses. Recorded addresses, discovery arithmetic and remaining
hardware-evidence limits in ISA-REVIEW.md. The AIDR query also matches A76's
documented reserved-zero behavior. ISAR2/PFR2, ACTLR, hint semantics and remaining
FP/crypto review still prevent full compatibility sign-off. No board change.

## Update — 2026-09-12: operand-aware ISA review

The exact `971d44c3` artifact now has a retained 1,210-word system/control
operand inventory. Recorded primary and secondary feature fields support
the selected LSE/RCpc families, 16 KiB granule and 40-bit PA profile.
No range-TLBI operand appears. Remaining review is now narrowed to specific
register paths, conditional debug/SME accesses, hints and FP/crypto operands;
see [ISA-REVIEW.md](ISA-REVIEW.md). Three focused parser tests pass.
Gate closure remains unproven; there is no user-action blocker from this pass.

## Update — 2026-09-12: canonical toolchain lock aligned to local toolchain

`tools/rpi5/inputs.lock.json` is now pinned to the environment's installed
Xcode (`26.6` / `17F113`) with macOS SDK `26.5`. This removes the previous
canonical-toolchain mismatch blocker from this checkout. `python3 tools/rpi5/rpi5.py
doctor` now reports `canonical: true` when run in this environment.

Remaining open items are now:

- full ISA feature-compatibility review against BCM2712/board runtime evidence;
- reconciliation of that reviewed artifact with the final build/provenance requirements.

Seeded-tree consumption and real XNU transfer have already been observed in
`serial-capture-a8bp8q85`, detailed below. Rechecked the retained raw capture:
SHA-256 remains `7758a3aa9800a82a75fefc8d4e3a7b886bdeecdecdd890f7e13fc45c19c032bd`;
line 268 records committed boot data and transfer, lines 365–366 record provider
startup, and line 380 records the later IOKit platform-driver panic. These are
hardware evidence for the embedded `d0a7d68a` kernel, not proof that the later
`971d44c3` reproducible kernel was installed or exercised.

## Update — 2026-09-12: host contract gate remains green

`python3 -m unittest discover -s tools/rpi5/tests -v` currently passes 177/177.
This is a validation checkpoint for host tooling, loader contracts, and startup
provider constraints, and it supports continued Gate 1 sequencing without
regressions. It does not by itself close ISA feature compatibility or prove
hardware execution. Toolchain and transfer status are reconciled above;
older dated entries below retain their historical state.

## Update — 2026-09-12: ISA unknown-word classification closed

The latest ISA inventory confirms `build/rpi5/isa-inventory-971d44c3.json` has
all 487 unknown words resolved by source-backed evidence in `docs/rpi5/ISA-REVIEW.md`
(`485` data words, `2` intentional traps). This removes the unknown-word-count
remaining-lists pressure for Gate 1.

Gate 1 still remains open for: canonical toolchain reconciliation and explicit
feature-compatibility validation of recognized instructions against BCM2712's
actual feature contract/board path. No gate-closing compatibility claim is made
by this finding alone.

## Update — 2026-09-12: NECP groups mapped to exact compiler tables

Four original-object jump tables match their linked kernel bytes exactly and
are corroborated by compiler assembly and three agreeing function anchors.
They account for another 115 raw unknown words (107/2/6 across the three NECP
groups). Cumulative exact compiler-data attribution is now 238 of 487; 249
remain. Byte ranges, hashes, table lengths and replay limitations are retained
in [ISA-REVIEW.md](ISA-REVIEW.md). No kernel/Pi/SD changes occurred. Gate sign-off
still requires the remaining ISA work and canonical-toolchain reconciliation.

## Update — 2026-09-12: largest unknown-instruction group mapped exactly

Object symbols, generated compiler assembly, and original object/kernel byte
comparison establish `_icmp6_reflect`'s 123 unknown words as entries in a
137-entry signed jump table. The exact table range is
[0xfffffe000766d510,0xfffffe000766d734), followed by three NOPs. This does not
exclude the rest of the function. Provenance and compiler-replay limitations
are recorded in [ISA-REVIEW.md](ISA-REVIEW.md). Of 487 raw unknown words, 364
remain to be precisely classified; recognized-instruction feature review and
the canonical-toolchain issue also remain. No kernel, Pi or SD changes occurred.

## Update — 2026-09-12: repeatable instruction inventory

Added the bounded-artifact `inventory_isa.py` review aid and
[ISA-REVIEW.md](ISA-REVIEW.md), retaining manual_review_required rather than
issuing a false compatibility pass. Exact reproducible kernel 971d44c3 has
1,777,036 disassembled words, 487 unknown words and 22 nearest-label groups.
Its data-in-code table is empty. Source inspection explains examples as SHA-256
constants, intentional debugger traps, inline panic strings and table data;
precise exclusion ranges and remaining executable feature checks are still
required. The parser tests preserve the distinction between nearest labels,
code/data, and recognized/compatible instructions. No Pi state changed.

## Update — 2026-09-12: byte-identical fresh kernels verified

The opt-in reproducible build now also passes `RPI5_REPRODUCIBLE=1` to make;
only BCM2712 enables `-Wl,-reproducible`. The ordinary path explicitly sets 0,
and inherited copies of this setting are scrubbed. No UUID is removed or
post-link patched. The installed ld manual describes this mode as ignoring
incidental input properties such as compilation times. Earlier unstripped
images contain output-dependent OSO paths/times; with the supported linker
mode, the final kernel UUID difference disappears.

Two independent fresh-output builds, with source unchanged throughout, succeed:
`run-vakpd4u3` / `fresh-gidd72lh` (14:11:41–14:12:22 UTC) and
`run-j0vr3m2x` / `fresh-rtg2vhuu` (14:12:00–14:12:41 UTC).
Full-file cmp succeeds and both kernel SHA-256 values are
`971d44c3f649e743ed58c6ab43dad631ca5b718d2fe012054d480a118a7bc486`.
Both corresponding dSYMs and the kernel report UUID
`A2F34340-FC81-3C14-BBBC-0A1B5F97EC16` via dwarfdump. This verifies debugger
identity matching; it does not claim byte-identical dSYM directory contents.

Native Mach-O/materialization validation passes: 18 segments, 93,496 local
relocations, 17,416,192 materialized bytes, entry fffffe00074d8488 and trampoline
target fffffe00074da05c. All 175 tests pass in 40.719 seconds, including real
Make evaluation proving the linker flag is opt-in and BCM2712-only.

This closes the demonstrated same-host fresh-kernel repeatability issue for
the recorded source/configuration with the existing prepared SDK/libfirehose
and Xcode 26.6. It does not close cross-host/full-dependency reproducibility,
the locked Xcode 26.5 mismatch, or the remaining data-aware ISA audit.
Neither new kernel was installed; the Pi's hardware evidence retains its
earlier exact kernel identity. Next continue artifact compatibility auditing
and reconcile canonical-toolchain requirements before full gate sign-off.

## Update — 2026-09-12: controlled repeat builds differ only in UUID

`rpi5.py build --fresh --reproducible` now passes explicit version metadata to
make: UTC date from the pinned XNU commit (2026-06-17 23:28:50 UTC) and logical
root `xnu/DEVELOPMENT_ARM64_BCM2712`. Actual paths, current build times, dirty
source hashes and toolchain are retained in the manifests. The option rejects
reuse of existing output directories. It does not claim reproducibility by
itself or normalize the compiler/SDK, builder identity, or debug information.

Two fresh builds succeed with source unchanged throughout each:

| Run | Output root | Kernel SHA-256 |
| --- | --- | --- |
| run-hnvp239m | fresh-k5e5fr__ | c8674bc88b77cda38ba5e48abf6a29a1f540a9aebab2e6e123366dff557593bc |
| run-1nj_iz8x | fresh-ieigdv4q | 9d3c7c108dde7cf8e858e30b39124440b2eb75c6503699966f561cad9e8a28b6 |

`cmp -l` finds exactly 16 differing bytes at one-based offsets 4801–4816.
These are the LC_UUID payload (load command 20), independently identified in
the Mach-O header. Every other byte matches, including code, data and symbolsets.
The first image passes the native Mach-O/materialization comparison; the pair's
symbolsets share SHA-256 bdbd13d62605910de2112f1b05505e78bd6574a2869ed8a42f1477b6be15bd4c.
All 174 tests pass in 38.072 seconds. No Pi/SD state was changed.

This is not yet byte-identical kernel reproducibility. The installed ld manual
documents content-derived UUIDs by default and `-oso_prefix` for debug-map
path normalization. The aggregate crypto objects also differ across builds;
debug maps/input paths before stripping are a candidate explanation, not a
proven cause. Next inspect the unstripped link/debug map and source-built object
identities, retaining UUID/debugger matching rather than deleting or rewriting
the UUID after the fact. The full ISA audit and canonical-toolchain mismatch
remain open as well.

## Update — 2026-09-12: fresh build and export-metadata correction

Fresh kernel-output build `run-yyp5la27` succeeds (13:59:44–14:00:24 UTC),
source unchanged during the run. Output root `fresh-k5m91njy`; kernel SHA-256
`005d579757709e214c278008268e65fde05a8808afd0486fa710f0516a4ac755`.
This rebuilds kernel outputs, not the prepared SDK/libfirehose dependencies.
Native Mach-O/copy validation passes and nm reports no undefined symbols.
It is not byte-identical to the incremental artifact and uses Xcode 26.6.

Comparison found stale macOS-only entries in the incremental symbolsets.plist:
the Pi platform-export selection had changed, but removing prerequisites did
not invalidate generated metadata. config/Makefile now makes Pi symbolsets
depend on its selection rules, and plist generation depends on its script.
Recipe arguments explicitly contain only Info.plist/export inputs, not the
new rule/script prerequisites. A regression executes the actual Make template
and generator across removal of an input and checks the removed symbol is gone.

Corrected incremental build `run-q1uao7a2` succeeds with source unchanged.
Its symbolsets.plist is byte-identical to the fresh build (SHA-256
`bdbd13d62605910de2112f1b05505e78bd6574a2869ed8a42f1477b6be15bd4c`).
Its kernel SHA-256 is
`8d5a09300e1fe8f45415bbab7d94df42deeb7a68fff69e2b38cb2eb2a2032468`;
native validation agrees on 18 segments, 93,496 relocations and 17,416,192
materialized bytes. All 171 tests pass in 37.897 seconds. Neither new kernel
was installed on the Pi; retained hardware evidence names its earlier image.

Initial instruction scan is not a full compatibility certificate: the apparent
MTE SUBG at 0xfffffe0007975660 in the earlier image is SHA-256 constant
0xd192e819 inside K256, not code. Unknown word 0xe7ffdeff in DebuggerTrapWithState
is the intentional TRAP_DEBUGGER encoding from osfmk/kern/debug.c. Jump-table
data also disassembles as unknown instructions. A complete data-aware audit
remains outstanding; do not blanket-allow unknown executable words.

Remaining reproducibility work: newvers.pl embeds date and output-root identity
and explicitly supports KERNEL_BUILD_DATE/KERNEL_BUILD_OBJROOT overrides. Test
controlled repeat builds rather than attributing all remaining differences to
those fields without comparison. Only Xcode.app 26.6 is installed under
/Applications; the locked canonical compiler remains 26.5. Do not silently
change that pin. Gate completion remains unproven; local audit work can continue.

## Update — 2026-09-12: provider startup hardware evidence obtained

Completed capture `serial-capture-a8bp8q85` (13:56:10–13:57:51 UTC,
63,468 bytes, SHA-256
`7758a3aa9800a82a75fefc8d4e3a7b886bdeecdecdd890f7e13fc45c19c032bd`)
contains both `BCM2712 crypto provider registration` and
`BCM2712 crypto and PRNG registered`. The latter is emitted only after the
coordinator returns: crypto table publication, entropy initialization, boot
generator initialization/reseed, and early-seed clearing are on that call path.
This is startup execution evidence, not an exhaustive runtime crypto or SMP test.

Candidate `bl33-probe-wjv71dbe`, SHA-256
`7151df864c1b842cf31f0fee18a3685edcab3eea36a6aed885b461a22c1c1d9d`,
contains kernel `run-x1hrdcwl`, SHA-256
`d0a7d68a91035543e9da6cc712a9748dee4f94087c1fc0f65150272fbce62d2c`.
Native Mach-O copy/layout comparison passes: 18 segments, 93,496 relocations,
17,432,576 materialized bytes. All 170 tests pass in 38.498 seconds. Installed
SD config hash remains `ff9141b6ddca6bc6138f74a26a17fa4064460a46c1ef1e714caeaf5a1fa12090`.

Current Gate 1 hardware requirement audit against PLAN.md:

| Requirement | Evidence in this capture and supporting implementation |
| --- | --- |
| Pinned firmware/TF-A | Boot reports 6219bf00 and TF-A 332b62e; full firmware identity/source selection guards precede seed consumption. Pinned build identities remain in TF-A/entropy contracts. |
| Runtime RAM/reservations/address translation | Validated FDT records, live probe/FDT extents, explicit Normal map, fixed reservations and proposed CMA exclusion; resolved planner accepts the managed and rounded spans under the documented DTSpec trust assumption. |
| CPU features and EL normalization | Primary EL2 then EL1 records; matching secondary feature records; all three secondaries report EL1, SCTLR 0x30d00800, DAIF 0x3c0, 54-MHz counter. |
| Exceptions/GIC/timer/PSCI | Primary CONFIGURED=1/CLEANED=1/ACK=27/COUNT=1; each secondary IRQ_VERIFIED=1/ACK=27/COUNT=1, distinct targets 2/4/8, then OFF. Exception diagnostics also report the later XNU panic. |
| Checked physical kernel load | Container/segment/relocation checks and full materialized envelope readback succeed before retained boot data and transfer. Host comparison matches the exact embedded kernel. |
| Apple tree, bounded RAM and boot args | Commit precedes XNU markers; XNU consumes chosen memory/seed data, completes VM setup and normal UART setup. No init image is supplied at this gate. |
| Fresh source-qualified seed | Guarded firmware seed selection, isolated consume-once derivation, scratch/source erasure and retained boot-data commit all precede transfer; provider initialization succeeds. Source qualification and entropy-strength limitations remain those in ENTROPY-SOURCE.md. No seed values are logged. |
| UART | Declared-clock programming and nominal 115200 8N1 check succeed; ordinary XNU text is readable. No independent oscillator measurement claimed. |
| Provider startup retained requirement | Explicit before/after messages now observed around the real crypto/PRNG coordinator, after SYSCTL and before IOKit. |
| Recovery | Same capture returns to Linux; independent SSH confirms 6.18.34+rpt-rpi-2712 and NVMe root /dev/nvme0n1p2. |

The subsequent panic is `Unable to find driver for this platform: "device-tree"`
from IOPanicPlatform::start. Headless graphical-progress initialization no longer
panics. A real platform expert and XNU interrupt integration are Gate 2 work;
do not suppress this panic or count standalone IRQ probes as an XNU driver.

Hardware requirements above now have evidence. Full "through Gate 1" sign-off
still needs reconciliation of the retained Gate 0 build/compatibility and
reproducibility requirements: the current successful artifact is incremental
and explicitly uses noncanonical Xcode 26.6 instead of locked 26.5. Next is a
fresh-output build and current artifact/provenance audit, not another unchanged
Pi reboot or implementation of later-gate platform drivers. Goal remains active.

## Update — 2026-09-12: verbose logging exceeds the observation window

Headless candidate `bl33-probe-a0i6ubdg` (probe SHA-256
`3626c452f9d120dd9f5f5371e9b7901311e08c3c222693422e8d5e9c7a283396`)
passes native copy/layout comparison. All 170 tests pass in 38.090 seconds.
Capture `serial-capture-0n57kq2e` (13:51:45–13:53:26 UTC, 233,888 bytes,
SHA-256 `a90c3b945102ec270cd4292ed9b41162384554027fe9e1721b4645a94b0aefdf`)
ends XNU output mid-SYSCTL startup enumeration, then records firmware restart
and Linux recovery. No provider markers or XNU panic appear. SSH independently
confirms Linux on NVMe p2. The volume and truncated line are consistent with
verbose UART output exhausting the unchanged 15-second watchdog, not proof of
a new kernel defect.

Next candidate removes verbose enumeration and makes only the two opt-in BCM
provider boundary messages unconditional kprintf calls. Headless `-noprogress`
remains; watchdog and provider policy are unchanged. The focused option/encoding
tests pass. Gate 1 remains open until this bounded-output pass is verified.

## Update — 2026-09-12: allocator correction passes hardware

Completed capture `serial-capture-vtjbjzna` (13:48:03–13:49:44 UTC, 59,782
bytes, SHA-256 `ddf991871f4d0760e341a6df0702b693614a2ee21a1a0f9e8fd965c606285133`)
advances beyond typed-zone initialization into `PE_init_iokit`. The new panic
is pe_init.c:353, `*delta >= 0`, while sizing graphical progress against the
zero-height headless video state. This supersedes the allocator stop below.
The installed candidate remains `bl33-probe-gd68ywep`.

Source places the opt-in provider coordinator before PE_init_iokit, which is
encouraging indirect evidence, but its log helper requires startup_debug=1.
Do not claim explicit provider startup evidence yet. The next loader adds the
existing `-noprogress` headless option and `startup_debug=1`; neither changes
allocator/crypto policy. Both command-encoding and option-source tests pass.
Gate 1 remains open pending explicit startup evidence and completion audit.
SSH independently confirms recovery to Linux 6.18.34+rpt-rpi-2712 on NVMe p2.
The headless/verbose loader builds as `bl33-probe-a0i6ubdg`; it has not yet
been validated with the native comparison, installed, or booted.

## Update — 2026-09-12: allocator capacity mismatch reproduced

Statistics-only `kt=2` capture `serial-capture-9yn_nm4_` (13:41:34–13:43:15
UTC, 58,807 bytes, SHA-256
`3a476b752d083b88875bf90689ecbe06f1a872427b403b49d871297a6a84b80c`)
shows size 48 receiving 18 signature zones plus 14 type zones. Its shared-zone
slot requires 33 entries, exceeding the assumed 32-entry scratch array.
The loader was `bl33-probe-21sks066`, SHA-256
`2e17307d2bcb0ac0998b0d368f7757ea2c4db0d5c49611665f1778d3e04839d5`.
Linux NVMe recovery is independently verified over SSH.

The new `test_kalloc_policy.py` executes the production distribution functions
under ASan/UBSan against all 29 captured size classes and reproduces their
allocations exactly, including the unchanged 260-zone budget and 33-slot peak.
The BCM2712 correction retains policy and the bounds assertion, using a
MAX_ZONES+1 scratch array in reclaimable startup data, cleared for each class.
It neither reduces type separation nor adds a large array to the boot stack.
Other targets retain their original array. Kernel build `run-jdjedebx` succeeds,
SHA-256 `97598b8646fa6d907fc6eec3febf02e88e7dda6a0712b97531101e19e8cea0cd`;
nm verifies the scratch symbol in `__BOOTDATA,__init`. Hardware validation of
the correction is pending. Gate 1 remains open.

All 170 host tests pass in 37.166 seconds. Candidate `bl33-probe-gd68ywep`
passes native Mach-O validation/copy comparison and is installed on the checked
SD card (SHA-256 `9ecef75a13105ca40750a55e099c5a428f3e423b31abda30d2edc9c08d831e7e`).
The SD config hash remains unchanged. Capture `serial-capture-vtjbjzna` was
confirmed receive-ready before the software reboot; its outcome is pending.

## Update — 2026-09-12: ordinary logging and allocator panic observed

The command-length correction is hardware-verified in completed capture
`serial-capture-r_u667ts` (13:37:19–13:39:00 UTC, 58,120 bytes, SHA-256
`ebf543a7ad0fb06c18ee47ba8586696cc2476a8d3d53b419ef2c4fa87ae184fc`).
The sequence is now `RPUNQ100kprintf initialized`, followed by serial mode 1,
zone initialization, and `VM bootstrap done`. XNU reports the assertion
`n_zones_sig + n_zones_type + 1 <= KT_ZONES_FOR_SIZE_SIZE` at kalloc.c:1810.
The ordinary logging failure is resolved, not the allocator failure.

Candidate `bl33-probe-re8_dz4s`, SHA-256
`41511c2e821da281b70016c8c4edd8e7c6d8baf9141581919db9e7b5c6c94a37`,
uses unchanged kernel SHA-256
`55a4d07f7de151080a22d2ba3c78a855a7bfd4842b50eefcfacedb9fccfcac41`.
Native Mach-O validation/copy comparison passes, as do all 169 host tests
(39.361 seconds). SD config hash remains
`ff9141b6ddca6bc6138f74a26a17fa4064460a46c1ef1e714caeaf5a1fa12090`.
SSH confirms automatic recovery to Linux 6.18.34+rpt-rpi-2712 on NVMe p2.

Next: inspect typed-zone frequency/budget distribution and its bounded scratch
array before changing allocator policy or capacity. Do not suppress the assertion.
The log also reports a missing interrupt-controller node and CPU debug interface;
these remain platform integration gaps, not evidence of successful services.
No crypto/PRNG startup marker is observed. Gate 1 remains open; no physical
intervention or new permission is required.

## Update — 2026-09-12: boot-option length defect isolated

Completed capture `serial-capture-jrc1axys` reaches `RPUNQ111F`: the serial
device exists, both output-disable flags remain true, and the first kprintf
returns. Its SHA-256 is
`6e341d27b412f517de1d54fd085504f3a78dcc637353be7ab785b72250dc76b5`
(52,452 bytes, 13:30:10–13:31:50 UTC). Linux recovery is captured and SSH
independently confirms NVMe root `/dev/nvme0n1p2`.

Source inspection found that the loader passed the console-option string with
an explicit length of zero. TUNABLES runs before KPRINTF, so the disabled flags
are not explained by deferred tunable initialization. The production call now
computes and passes the actual string length. A host regression executes that
production selection/length snippet in both transfer and diagnostic modes and
checks the resulting encoded command line through the resolved handoff planner.
The former source-only assertion incorrectly required zero; it is corrected.
Hardware validation of this correction is pending. Gate 1 remains open.

## Update — 2026-09-12: VM return and serial setup observed

Capture `serial-capture-729mbzi4` reaches `RPUNQ` after all VM checkpoints.
VM cleanup/return, normal I/O mapping, low-global patching, serial_init return
and KPRINTF startup completion are observed. Actual serial selection/output
flags and the first ordinary kprintf call still need localization; no provider
startup is established. Gate 1 remains open. Capture/build details are retained
in `TRANSFER-CONTRACT.md`.

## Update — 2026-09-12: final VM checkpoint reached

Capture `serial-capture-zo0v1fv0` reaches every VM checkpoint through z, including
pmap bootstrap and final low-global patching. The UART-only-root experiment
does not retain RAM mappings and restores the invalid root before VM returns.
That cleanup/return and normal serial setup still need runtime localization;
the last observed marker precedes cleanup. Linux recovery is verified. All 169
host tests pass. No provider-startup evidence yet; Gate 1 remains incomplete.

## Update — 2026-09-12: protection setup advances

The corrected `/chosen/memory-map` node was tested on hardware in capture
`serial-capture-5b36g4tg`. Output advances from g to h, i and j, confirming
protection setup, physical-aperture setup and TTBR1 replacement return. Normal
logging still does not appear. Automatic NVMe Linux recovery is verified.
Remaining scope: TTBR0 invalidation/post-switch VM setup, then provider startup.
Gate 1 remains open. Build and capture identities are in `TRANSFER-CONTRACT.md`.

## Protection initialization contract mismatch (13:33 UTC)

Capture `serial-capture-a24z5p9z` reaches VM marker g but not h, narrowing the
interval to `arm_vm_prot_init`. Source review found that our loader omitted the
`/chosen/memory-map` node required by an assertion there. This is distinct from
the private `rpi5-memory-map` property. The node is now supplied as empty because
no optional trust-cache/AuxKC images exist. Focused host tests and a fresh loader
build pass; the correction has not yet been installed or validated on hardware.
NVMe Linux recovery is confirmed. VM/provider completion remains unproven.

## Early C startup observed (13:28 UTC)

Capture `serial-capture-m1exwn7e` emits `XDAZPMVCISTBDELHKW`, proving progress
through C entry, image setup, boot args, CPU/platform initialization, topology,
thread setup and startup bootstrap to the `arm_vm_init` call. Earlier uncertainty
about entering C is superseded. VM completion/normal serial/provider startup are
not observed. 168 host tests pass; recovery to NVMe Linux is verified. Next:
localize VM initialization while respecting the TTBR0 invalidation boundary.
Gate 1 remains open under the retained provider requirements.

## MMU transition observed (13:23 UTC)

The one-page UART mapping candidate produces `XDAZPMVC` on hardware. XNU
continues executing after MMU enablement and reaches its final cold assembly
pre-return checkpoint. Earlier suspicion of an MMU-switch stop is superseded;
the C-entry/prologue and early `arm_init` stages remain to be localized.
Capture `serial-capture-66xrgmm_`, identities in `TRANSFER-CONTRACT.md`.
166 host tests pass; NVMe Linux recovery is independently verified. No provider
startup evidence yet, so Gate 1 remains incomplete.

## Latest localization (13:17 UTC)

Hardware now confirms boot-argument reads, bootstrap table clearing and mapping
creation, and arrival immediately before MMU enablement (`XDAZPM`). A further
pass with explicit serial/kprintf options produces the same sequence and no
later log. Recovery is verified. See `TRANSFER-CONTRACT.md` for capture and
candidate identities. Next is translation-safe early diagnostics; neither the
MMU transition nor C/provider startup is yet established by evidence.

## First XNU instruction evidence (13:09 UTC)

Capture `serial-capture-y_ub17nq` records successful boot-data commit followed
by the ASCII X emitted at XNU `start_first_cpu`, verified in the linked kernel
disassembly. Actual XNU entry is now observed, superseding the earlier lack of
entry evidence below. Recovery to NVMe Linux succeeds. There is no evidence
yet for later initialization or crypto/PRNG startup, so the retained Gate 1
requirements are still incomplete. Full capture identity and build hashes are
in `TRANSFER-CONTRACT.md`. All 163 host tests pass; the next work is early-XNU
startup localization, not a loader/seed handoff rewrite or manual power cycle.

## Latest entry experiment (13:03 UTC)

The provider implementation/linkage and guarded-transfer work described in
`PROVIDER-STARTUP.md` and `TRANSFER-CONTRACT.md` supersedes the historical
unimplemented-provider status below. All 161 host tests pass; both loader modes
build. Transfer candidate `bl33-probe-abc9hdm6` was installed and tested once.
Capture `serial-capture-h3ftrz58` passes materialization and all CPU/IRQ checks,
then reaches the pre-seed-commit transfer marker with no further experimental
output. Automatic fallback to NVMe Linux is captured and independently confirmed
over SSH. No XNU instruction execution or provider startup is proven. Gate 1
remains incomplete under the retained provider/hardware requirements. Next:
instrument seed-commit/transfer/early-entry boundaries, not another unchanged
diagnostic reboot. No user action or missing permission blocks that work.

Result: **not complete**. The standalone hardware/loader probes have passed,
but the provider startup contract explicitly retains Gate 0/1 requirements.
Do not interpret this audit as permission to jump into the current kernel.

## Evidence against PLAN.md

Primary board evidence is `build/rpi5/serial-capture-lwxg9a9y/serial.bin`,
SHA-256 `ebe822bc2b7802a8ac26a3ce73a78db73ad77dec5f41ce664008bda660193e7f`.
Candidate `bl33-probe-_nzk33nr`, probe SHA-256
`ad23fbc565ddca7b0c3f184243aa63fa9616edad0b0c69f0f1bdf697a50e9d5b`.

| Requirement | Evidence and limit |
| --- | --- |
| Pinned firmware/TF-A chain | Raw boot reports firmware 6219bf00 and TF-A 332b62e. Runtime seed guard checks full firmware identity/timestamp. This is consistency, not attestation. |
| Checked kernel container | Container hash and payload inventory complete before writes. Native/Python validation agrees on 18 segments, 93292 local relocations, entry trampoline and 17252352 materialized bytes. |
| Runtime FDT and reservations | Raw RAM/reservation records, proposed retained CMA allocation, translated MMIO profile match and successful resolver-backed plan. Firmware completeness is the explicit DTSpec trust assumption. |
| Apple tree semantics | CPU/UART/envelope/explicit memory-map properties encoded; seeded tree is 1824 bytes. Physical args/tree readback passes and buffers are erased. XNU consumer compiles and has host tests, but has not run. |
| Identity/features/EL/UART diagnostics | Primary and three secondary feature records match. Raw firmware identity, RAM, FDT and UART setup are captured. |
| EL2 to EL1 normalization | Shared entry assembly sets traps, offsets, vectors and per-core stacks; all four report EL1 with matching SCTLR and timer frequency. This is the cache-disabled firmware contract, not a general dirty-cache shutdown proof. |
| Exceptions, GIC and PSCI | All four acknowledge INTID 27, dynamic target masks are 1/2/4/8, and all three secondaries reach OFF. Fault reporter implementation is present; earlier `serial-capture-_e14lejb` captured an EL1 alignment fault. No claim of exhaustive fault injection. |
| Physical Mach-O load | Full-envelope readback passes. Plan reports header 0x7004000, entry 0x74c8488, end 0x8078000 and rounded map [0x6000000,0xe000000). No kernel instructions execute. |
| Bounded RAM and retained data | Managed span [0x6000000,0x10000000), top 0xb014000 covers retained probe/FDT/data. Loader checks reservations and Normal coverage; XNU independently checks managed coverage. No init image is included in this diagnostic. |
| Fresh seed | Runtime firmware guard and consume-once derivation succeed; source, crypto scratch and diagnostic output erasures pass. RFC 5869 case 1 and independent HMAC derivation tests exist. Trust is in firmware HWRNG; output size is not entropy strength. |
| UART preservation/programming | Raw nominal 115200 8N1 match after programming from declared clock; capture is readable at 115200. No independent oscillator measurement claimed. |
| Recovery | Final diagnostic stop followed by Linux login in the same capture. SSH confirms NVMe root /dev/nvme0n1p2. |

The current 126-test suite and exploratory kernel build `run-e08yk7d9`
support implementation checks, not a boot certificate or canonical toolchain
reproducibility. No new reboot is needed merely to repeat these passing probes.

## Remaining prerequisite, not another hardware-probe failure

`PROVIDER-STARTUP.md` explicitly requires provider registration and hardware
evidence for Gate 0/1. It remains unimplemented: register_and_init_prng calls
entropy_init, whose SHA-512 wrappers dereference g_crypto_funcs. The host-only
BearSSL fixture does not register a complete kernel crypto table or PRNG.
The first ordinary random consumer and a valid registration phase still need
source-level closure. Gate 0 also retains its build/provenance/compatibility
audit; successful linking does not close those requirements.

Next work is the startup-provider dependency path, not more manual power
cycling. Before an actual XNU-entry experiment, also retain (rather than erase)
the final boot data and implement the explicit bounded-watchdog transfer policy
in TRANSFER-CONTRACT.md. A stable kernel watchdog takeover belongs to subsequent
boot work; do not mistake the current recovery timer for one.
