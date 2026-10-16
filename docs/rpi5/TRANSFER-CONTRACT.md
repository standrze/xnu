# Terminal primary entry contract

## Post-VM serial checkpoints (2026-09-12)

After `arm_vm_init` returns, the candidate maps UART10's containing 16-KiB page
through normal `ml_io_map` and emits R. Further checkpoints cover low-global
patching (P), debug inheritance (U), `serial_init` return (N), and completion of
STARTUP_SUB_KPRINTF (Q). The old low identity mapping is not reused.
Kernel `run-3ivs11ph`, SHA-256
`c758cf87b2a0eddd21b588c284aec2379324254beeea50f30761754490226268`;
loader `bl33-probe-wker8plq`, SHA-256
`e59eac3f848029ffeddb835653ad2e966965c25486f6eb3db344941080da7de7`.
169 tests and native layout validation pass. A comment-only wording correction
followed the kernel build; it did not change executable behavior.

Capture `serial-capture-729mbzi4`, 13:24:51.993906–13:26:32.420418 UTC,
55051 bytes, SHA-256
`dba1675ee7fa91a7dc7879971026f4d27240ae6184ce05edc604cec1d7e6479f`,
prints the full VM sequence followed by `RPUNQ`. Thus VM returns and normal I/O
mapping plus serial/KPRINTF initialization return. No ordinary kprintf text is
observed before Linux recovery. Serial return success and the two disable-output
flags have not yet been logged; Q alone does not prove the serial driver was
selected or output enabled. Next localize the first `kprintf` call and inspect
those states without bypassing initialization or suppressing assertions.

## Temporary UART-only root for post-switch diagnostics (2026-09-12)

The BCM2712 DEVELOPMENT path now prepares a dedicated aligned L1 root with
only slot 1 populated, pointing at the existing UART-only L2/L3 pair. No RAM
entries are retained from the bootstrap root. It replaces TTBR0 during the
remaining VM setup, allowing markers k (root switch/flush), l (pointer remap),
m (segment-bound checks), n (pmap bootstrap), o (VM page-table work complete),
z (final low-global patch returned). Before enabling preemption and returning,
it restores the normal invalid TTBR0 and flushes translations. No user execution
is possible during this diagnostic lifetime; leaf access remains EL1-only.
If startup stops, the recovery watchdog bounds the remaining mapping lifetime.

Kernel `run-qoxj0nq_`, SHA-256
`05bd4be808f56f92afd8370be54b80e5668d63a1981e655b78d50ebf867055ff`;
loader `bl33-probe-3iwdpr7y`, SHA-256
`5d6ac6646f7834a4e07a35fe0db299e4c1656489dca218e2ecfabe8c90f9908d`.
169 tests pass, including root contents/alignment/profile rejection and cleanup
ordering checks. Kernel build and native layout validation pass. Installed
candidate was captured in `serial-capture-zo0v1fv0`,
13:19:45.888278–13:21:26.311029 UTC, 54377 bytes, SHA-256
`037ccf7bdca71d2eb8a230a8873b32af6a3b79572dd49c063205f09a0cbcb4b5`.
The complete sequence `XDAZPMVCISTBDELHKWabcdefghijklmnoz` is observed.
Thus pmap bootstrap and the remaining VM setup reach the final pre-cleanup
checkpoint. The invalid-root restoration, return from VM and subsequent serial
initialization are not yet individually observed. Recovery to Linux 6.18.34
with root `/dev/nvme0n1p2` is independently confirmed by SSH.
Next consider a normal `ml_io_map` UART mapping immediately after VM returns,
then checkpoints around low-global patching and serial initialization. Do not
reuse the low identity address after its explicit cleanup. Provider startup
remains unproven and Gate 1 stays open.

## Required tree-node correction verified (2026-09-12)

Installed loader `bl33-probe-93mu9xxi`, SHA-256
`7cac69cbb5faa3c6fe3c1d0423ffae6a8fb9a4a5cd36c9b9db36673d8c422567`,
with the previously validated VM-checkpoint kernel. Capture
`serial-capture-5b36g4tg`, 13:13:58.809674–13:15:39.568254 UTC,
53022 bytes, SHA-256
`51c777354bdd6608122e60313924713ab624c96a8a20a6db01220e849c117375`,
emits `XDAZPMVCISTBDELHKWabcdefghij`. Adding `/chosen/memory-map` therefore
clears the previously observed protection-init stop: protection mapping,
physical-aperture mapping and the TTBR1 switch now return. No later normal log
is observed. Linux 6.18.34 and NVMe root `/dev/nvme0n1p2` are confirmed by SSH.

Remaining diagnostic scope begins with TTBR0 invalidation and post-switch VM
setup. Do not infer VM completion from j or reuse the now-unmapped identity
UART. A possible bounded diagnostic is a dedicated UART-only TTBR0 root (no
RAM mappings, EL1-only Device page), explicitly restored to the normal invalid
root and flushed before leaving VM initialization. This is not implemented;
review its temporary ownership/lifetime before use. Provider startup and Gate 1
completion remain unproven.

## VM initialization checkpoints (2026-09-11)

`arm_vm_init` now emits a entry, b after physical-aperture randomization,
c after bootstrap geometry validation, d after invalid/root table allocation,
e after kernel-range tables, f after aperture table setup, g after segment and
page-size setup, h after protection mappings, i after physical-aperture mappings,
j after TTBR1 replacement. All checkpoints stop before TTBR0 invalidation.
The final-table switch may itself fail; j is evidence only if observed.

Kernel `run-i24ne7kh`, SHA-256
`9ca7c998a51031609c410d36398ecfa28984f086adba4903b6b1e175246e5690`;
loader `bl33-probe-epg_dzvo`, SHA-256
`736db233936c1eff44eac2da56f20d0901bef1a142f6ab0d52b945177d1e4f65`.
169 host tests pass, native copy/layout validation passes. The identity-checked
SD image was updated and read back. Capture `serial-capture-a24z5p9z`
completed 13:31:55.899442–13:33:36.358693 UTC, 53825 bytes, SHA-256
`5815935fef2f7778c8b48fd2dc5fadbe385bf27018b74524bca41a9b6abce9b9`.
It emits `XDAZPMVCISTBDELHKWabcdefg`, then recovers to Linux. SSH confirms
6.18.34 and NVMe root `/dev/nvme0n1p2`. The interval before h contains
`arm_vm_prot_init`; no table-switch checkpoint is reached.

Source inspection identified a definite tree-contract mismatch:
`arm_vm_prot_init` asserts successful lookup of `chosen/memory-map`, but our
board tree provided only the separate `rpi5-memory-map` property. The latest
loader adds the required empty child node, with no fabricated TrustCache or
AuxKC entries. Seed-tree tests check its shape; handoff and seed encoding tests
pass. The initial direct handoff-test invocation had a test-import path error;
discovery-based invocation passes. Candidate `bl33-probe-93mu9xxi` builds but is
not installed. Hardware must verify whether fixing this mismatch resolves the
observed stop; it is not yet evidence of VM completion.

## Early C checkpoints (2026-09-11)

`rpi5_boot_uart.h` adds bounded volatile UART polling for early C startup only.
`arm_init` stages: I entry, S image rebase returned, T static-if returned,
B boot args copied, D CPU data initialized, E platform expert returned,
L topology parsed, H initial thread installed, K startup bootstrap returned,
W before `arm_vm_init`. No checkpoint uses the bootstrap identity UART mapping
after VM takeover. A missing marker is not alone proof of its preceding call
faulting: UART timeout and earlier prologue failures remain possible.

Kernel `run-uewu00o6`, SHA-256
`b54baecff26c8189f919df9174c4dc645e696d8b503b1e5edf7d1927e813be23`;
loader `bl33-probe-gw28ih2e`, SHA-256
`ebded2f96c7ff571b73551fda75c0241322e0fab7ba9d7dbb4c2ee402360a769`.
168 host tests pass, including success/TX-full/drain-timeout helper cases and
no-post-VM-call source checks. Kernel disassembly confirms the entry checkpoint
after its stack prologue. Native copy/layout comparison passes. Candidate was
installed on the checked SD. Capture `serial-capture-m1exwn7e` completed,
13:27:02.215731–13:28:42.982183 UTC, 55019 bytes, SHA-256
`9002e49d116fefaf1dbdc363c2f531c943cafa29f79356674b81e1e7d5f6c9c9`.
It prints `XDAZPMVCISTBDELHKW`: every early C checkpoint through the call to
`arm_vm_init` is observed. No ordinary kernel logging follows before recovery.
Linux 6.18.34 and root `/dev/nvme0n1p2` are confirmed by SSH. This excludes an
early C-entry/prologue stop for this image, but does not establish VM completion
or provider startup. Next localization scope is `arm_vm_init` and its immediate
successors. It switches TTBR1 then invalidates TTBR0; the bootstrap identity
UART must not be accessed after that invalidation without a new valid mapping.

## One-page early UART translation (2026-09-11)

The BCM2712 cold path now uses separate `rpi5_boot_uart_tables` storage
(two aligned 16-KiB pages in the kernel) for UART10. It requires unused
TTBR0-root L1[1], clears its private tables, populates L2[62] and L3[1024],
then publishes the root link after a store barrier. Only
`[0x107d000000,0x107d004000)` is mapped, EL1 read/write, EL0 inaccessible,
Device-nGnRnE, outer-shareable, AF set, PXN/UXN. This does not consume or change
the allocation size of the RAM bootstrap tables. The final pmap need not retain
this identity mapping. `V` is emitted immediately after MMU enablement on the
cold path; `C` immediately before the cold assembly return to `arm_init`.

Kernel `run-nhn2ot0h`, SHA-256
`f102625d4dc04bea82ff4a87e0613302366f92192ed187dcc3b11703e3b45a7f`;
loader `bl33-probe-2uxe4tjw`, SHA-256
`f9a77983d506f60c724500a4f4ccf3c678813cf56d59026242d3f5b3fdca01b6`.
166 host tests pass. Linked symbol/disassembly inspection and native copy/layout
validation pass. The map test decodes intended descriptor/indices and checks
source ordering/storage; it does not simulate architectural translation.
The candidate is installed. Capture `serial-capture-66xrgmm_` completed,
13:21:55.848885–13:23:36.594518 UTC, 54831 bytes, SHA-256
`039523444c23318a3f8f1f24dabca757cf18abe99d742524aeb1a94648130c07`.
It prints `XDAZPMVC`: translated UART access succeeds after the MMU switch,
and cold assembly startup reaches its final pre-return checkpoint. This proves
neither the subsequent return target/prologue nor the C initialization steps.
The capture and SSH confirm automatic recovery to Linux 6.18.34 with NVMe root
`/dev/nvme0n1p2`. No ordinary XNU log or provider initialization appears.
Next: bounded checkpoints in early `arm_init` (entry, image rebase, static-if,
boot-argument copy, CPU data, platform expert, topology and startup bootstrap),
only while this bootstrap UART mapping remains active. Do not use it blindly
after `arm_vm_init` changes translation tables.

## Logging-enabled pass (13:17 UTC, 2026-09-11)

Loader `bl33-probe-rm7yxrdo`, SHA-256
`75563654d1f24dea92de153b7d206c1ca971d71628d6ca4c967bae5906dc5283`,
uses the unchanged six-checkpoint kernel and the explicit serial/kprintf
command line. Build, native copy/layout comparison and nine focused tests
passed before deployment; an additional source-contract test now verifies the
flag values against the kernel's definitions. Capture `serial-capture-7og8e3kt`
completed 13:15:56.237120–13:17:36.886112 UTC, 54621 bytes, SHA-256
`0a1f9ad1b4522c3932bacd6de331819163012533bcb55202218db55930525d0c`.
It still ends the experimental output at `XDAZPM`, then boots Linux. SSH
confirms kernel 6.18.34 and NVMe root `/dev/nvme0n1p2`.

Normal logging options alone did not produce later output. This does not prove
the precise fault instruction or exclude a stop before serial initialization.
Next: a narrow Device mapping of UART10's single 16-KiB containing page for
post-MMU checkpoints, with explicit owned table storage, architecture attributes,
and no broad peripheral block mapping. The existing reviewed RAM bootstrap
contract allows only four table pages; do not silently consume extra pages from
that allocation or overwrite existing L1/L2 entries. Translation/C-entry and
provider startup remain unproven, so Gate 1 remains open.

## Pre-MMU localization (13:14 UTC, 2026-09-11)

Kernel build `run-9txtlhvg`, SHA-256
`63a3d7509daa2cac875a742dd8d266d311e2f7c3e5d13e3225253135d36bad46`,
loader `bl33-probe-odvxog2d`, SHA-256
`6b5ea598c3bc6e9bf79636bcb463783cba71bcdeea217cbaf089f054ed6681bd`,
produced all six checkpoints `XDAZPM` on the Pi. They cover entry, debug unlock,
boot-argument loads, page-table clearing, mapping construction and the final
pre-MMU point respectively. No physical UART checkpoint is used after MMU enable.
Capture `serial-capture-pdz3wya0`: 13:12:25.527385–13:14:06.419357 UTC,
54636 bytes, SHA-256
`8176b9c544fc8237b10d51bcc626e0b9b311ee5d30cad5b571d1806d55b118e1`.
It also records automatic recovery to Linux login. 164 host tests pass.

Silence after M is not proof of an MMU failure: source review found that the
empty boot command line does not enable normal serial console/kprintf output.
The next, not-yet-built loader revision supplies
`serial=1 debug=0xa -enable_kprintf_spam` for transfer builds only. These enable
serial output, DB_PRT/DB_KPRT and DEVELOPMENT kprintf output. This is not a
debugger/input mode or watchdog disable. Check this visibility change before
assuming a translation failure. Gate 1 provider startup remains unverified.

## Entry-boundary checkpoints (2026-09-11)

The next candidate adds `BOOT_DATA_COMMITTED TRANSFER_NEXT` only after the
seed transaction, physical publication/readback and redundant-buffer erasure
succeed. UART output/drain failure sets transaction failure and clears retained
args/tree before stopping. The fixed marker contains no seed-derived values.
XNU's BCM2712-only `start_first_cpu` begins with a bounded stack-free UART10
ASCII `X` marker, preserving x0. Disassembly of the linked kernel confirms it
precedes OSLAR and normal startup. Observing X proves that entry code ran, not
that VM, C startup or crypto initialization succeeded. Absence remains ambiguous
if UART itself failed.

Kernel build `run-plw5r_f5`, kernel SHA-256
`68c10aad2e22a62014b81953e05d4fecf8216468dc1d95129591f0783fbd9bdd`;
loader `bl33-probe-xo1z9onl`, SHA-256
`b86f8c882d7759784e084be1361545beceb850f5e6aaab5a67b1c6ad6b1abb94`.
163 host tests pass, and native copy/layout comparison passes. Candidate was
installed on the same checked SD card. Capture `serial-capture-y_ub17nq`
completed, 13:07:20.674684–13:09:01.507106 UTC, 54775 bytes, SHA-256
`ec8aae7eb6b365783a0d9f94feaa4b6dca39286e754b69ae4dbc2ec23dd394e8`.
It contains `BOOT_DATA_COMMITTED TRANSFER_NEXT` followed by the entry `X`.
This is the first observed execution of XNU's `start_first_cpu` on this board.
No later XNU startup output appears before automatic recovery. SSH confirms
Linux 6.18.34 and NVMe root `/dev/nvme0n1p2`. Provider startup and a working
kernel remain unproven. Next observation boundaries should cover pre-MMU
initialization, the translation transition and C entry; physical UART accesses
must not be blindly reused once translation is enabled.
This supersedes the prior no-post-commit-logging policy below.

## Opt-in bounded entry implementation (2026-09-11)

`build_probe.py --kernel <image> --transfer` now enables the terminal call;
the default remains diagnostic. After materialization/readback, secondary OFF
verification and primary timer IRQ cleanup, the primary requires an already
armed full-reset watchdog, prints and drains its final pre-commit marker, and
reloads a single 15-second observation window. It then consumes the fresh
firmware seed, commits verified boot data while erasing redundant scratch,
and calls `rpi5_transfer` without another fallible logging operation. A seed
transaction failure stops; the watchdog remains running. This is an expected
reset experiment, not XNU watchdog takeover or stable boot.

Both build modes compile; 161 host tests pass. Transfer candidate
`bl33-probe-abc9hdm6` passed native kernel-copy/layout comparison and was
installed on the identity-checked SD card. Probe SHA-256:
`8d69bf9d747fc63c6711875a56ae647224b271e6c72b6d5665925d69674a8340`.
Hardware capture `serial-capture-h3ftrz58` completed: 2026-09-11
13:01:46.735421–13:03:27.105712 UTC, 54213 bytes, SHA-256
`dbc2c86de5ab75d806d59d2837d00057aa8504dbad1637a8f7d3781e9c2dd735`.
Kernel readback, secondary IRQ/OFF checks and primary IRQ cleanup pass. The
last experimental marker is `XNU_TRANSFER_PENDING WATCHDOG_15S SEED_COMMIT_NEXT`.
There is no subsequent XNU output or seed failure message. The capture then
shows firmware selecting BOOT_ORDER override 0xf6 and Linux booting; SSH confirms
Linux 6.18.34 and root `/dev/nvme0n1p2`. This proves automatic recovery, not
successful seed commit, branch execution or XNU entry. The next diagnostic must
separate those stages with bounded observability and post-commit cleanup on
any logging failure; no repeated unchanged boot is useful.
The historical “not called” description below applies to earlier diagnostics.

## Post-hardware audit: retained CPUs and watchdog

The current `probe_secondary_entry` returns from its C diagnostic into
`probe_stop`, an infinite WFE loop. It does not issue PSCI CPU_OFF. Therefore
the secondary cores remain powered/on in the monitor's state and depend on
retained probe instructions, vectors and stacks. Their diagnostic `ready`
publication proves the recorded checks completed, not that they are powered
off or ready for a second CPU_ON. Keep the entire probe allocation live and do
not treat these cores as XNU-startable without a separate transition protocol.

The SD enables the recovery watchdog. The hash observer reloads it only during
bounded progress, and `runtime_cpus` clears its servicing pointer after payload
inspection. `rpi5_transfer` neither disables nor services it. Thus an eventual
branch to XNU under this configuration inherits a countdown, not an unlimited
boot window. A captured early entry followed by reset is not a stable boot.
Before transfer integration, explicitly choose and implement either a bounded
first-entry test that expects reset, or a verified kernel takeover of watchdog
servicing. Do not silently disable the recovery mechanism that removed manual
power cycles. No watchdog ownership policy has yet been implemented in XNU.

`loader/rpi5/transfer.S` is linked but not called by the diagnostic probe. It
accepts boot_args PA in x0 and validated physical kernel entry in x1. The pinned
XNU `osfmk/arm64/start.s:start_first_cpu` saves x0 before installing its vectors
and reading boot arguments. No secondary XNU startup is implemented here.

The actual kernel entry is `__start` at 0xfffffe00074c8488, whose emitted
instruction is a direct B to `_start_first_cpu` at 0xfffffe00074ca05c.
`compare_native_macho.py` now checks the entry symbols and decodes that branch
from the audited file-backed executable segment. A changed instruction/target
requires review rather than silently assuming this trampoline contract. This
host check is specific to the current plain-ARM64 profile, not all XNU builds.

The routine masks DAIF, checks EL1 and SCTLR M/C/I clear, and rejects misaligned,
low-firmware or out-of-profile physical addresses. These numeric checks do not
validate the contents or ownership of either buffer. It selects SP_EL1 without
using the stack, installs stack-independent terminal vectors, disables both EL1
timers and clears the diagnostic TPIDR_EL1/EL0/RO state. Faults park silently.

After completing cache-disabled stores with DSB SY, it invalidates EL1 TLBs and
instruction caches (IC IALLUIS), completes maintenance and executes ISB on the
primary. It then branches without a return address, preserving x0 and clearing
x1–x3. The whole probe extent must remain live, including terminal vectors.

This is specifically NOT a live cache/MMU shutdown routine. Firmware must have
made inherited dirty cache state coherent before the accepted cache-disabled
entry, and all loader writes must remain cache-disabled. EL2 must retain the
established non-VHE contract. Other CPUs must stay parked and devices must not
modify handoff buffers. Future cache-enabled operation needs a different review.
Arm's [instruction synchronization explanation](https://developer.arm.com/community/arm-community-blogs/b/architectures-and-processors-blog/posts/caches-self-modifying-code-implementing-clear-cache)
describes the store/maintenance/barrier ordering; an ISB on the executing CPU is
still necessary. None of this constitutes on-board cache-coherency evidence.

Before wiring a call: finish runtime materialization, ownership and exclusion
checks, Apple tree/boot arguments with fresh qualified entropy, kernel startup
providers, and board validation. Build/disassembly tests verify emitted structure,
not exception behavior, cache effects, register transitions or an XNU boot.
# Secondary shutdown board evidence

Run `serial-capture-fbjnq5um` verified candidate `bl33-probe-q4xdz_el`:
CPU_OFF feature result zero, then AFFINITY_INFO state 1 (OFF) after each
secondary's successful EL1/timer IRQ record, targets 0x100, 0x200, 0x300.
Primary timer IRQ also passed, followed by `STOP BEFORE XNU LOADER`.
Watchdog reset selected NVMe using BOOT_ORDER override 0xf6; SSH subsequently
confirmed `/dev/nvme0n1p2` as root. No XNU entry or secondary restart tested.

Capture: 2026-09-11 01:41:17–01:42:58 UTC, 53071 bytes, SHA-256
`f8f45dfb70318be437d9fa95cf557d40dfda73155e4efd47ba7dac0f7e6f4ce2`.
Installed probe SHA-256:
`4e614c5f0a37b8ae896d87f0ce5c91d258d3dc19c70d8f53b9cb7b127d603257`.
The capture tool itself is receive-only; reboot was requested separately by
the orchestrator after its READY marker. This supersedes the candidate-only
deployment status below and the older normal-path parked-core description.
Fault paths still park; loader memory remains reserved, including the primary.

Candidate `bl33-probe-q4xdz_el` replaces the normal secondary return-to-WFE
with PSCI CPU_OFF. CPU_OFF support is required before starting any secondary.
The primary separately polls AFFINITY_INFO for OFF with both a one-second
counter deadline and finite poll budget; publication of the diagnostic record
alone is not accepted as shutdown. Unknown states and timeout stop the pass.
If CPU_OFF returns unexpectedly, the secondary parks without retrying and the
primary cannot report OFF success. Fault-vector paths remain terminal parks.

The pinned TF-A Pi 5 build uses common `rpi3_pm.c`, which supplies domain-off
and power-down callbacks. This source evidence and host control-flow tests do
not establish board shutdown or subsequent restart. Retain loader memory until
the hardware lifecycle is verified. OFF is now observed on hardware; a later
CPU_ON restart and actual XNU handoff remain unverified.
