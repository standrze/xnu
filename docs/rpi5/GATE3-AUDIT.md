# Gate 3 audit — 2026-09-26

Gate 3 is open. Gate 2's XNU PID 1 runs on one core; the loader's earlier
secondary-core EL1/timer observations are not evidence that XNU registered or
scheduled those cores. The current kernel still has no BCM2712 `IOCPU` driver
that can safely register secondaries. On the non-AppleARMSMP path,
`ml_processor_register()` begins their boot synchronously, so registration
must wait for a verified PSCI reset trampoline, physical CPU-data handoff,
banked GIC setup and SGI/IPI delivery. A boot-CPU-only registration shim would
not establish SMP.

First checkpoint changes:

- XNU's topology parser keeps physical MPIDR Aff1 for reset lookup and
  per-CPU offsets, while publishing one homogeneous logical SMP group rather
  than claiming each Aff1 value is a separate scheduler/cache domain.
- The Pi platform expert validates the exact 32-bit affinity of every CPU nub
  against the parsed topology, rejecting duplicates, omissions and unknowns
  before publishing those services.
- Each core entering `fiq_context_init()` now programs its own banked GICv2
  virtual-timer PPI and CPU interface. Shared distributor/watchdog mappings
  remain initialized once. This is preparation for secondary cores, not SGI
  delivery.
- `GATE3-VERIFICATION.md` defines the runtime evidence and
  `check_gate3_serial.py` inventories exact serial PASS/FAIL markers without
  converting host tests or loader observations into an SMP pass.

The first checkpoint kernel built in
`build/rpi5-xcode27/run-c0c4lilt/manifest.json`, but its Pi regression boot
`build/rpi5/serial-capture-k63foag7/serial.bin` failed: it initialized the
boot CPU's GIC twice, reached the PID 1 success marker, and then PID 1 exited
with signal 10 before the first timed tick. The kernel panicked because PID 1
exited; the diagnostic watchdog returned the board to NVMe Linux. The new
`fiq_context_init()` call is now secondary-only, preserving boot-CPU GIC setup.

The corrected kernel built with unchanged source in
`build/rpi5-xcode27/run-a9odyca5/manifest.json`; SHA-256 is
`7ad3d3c4beeec8fa6ce4a42097aded32e1d5d4822a84a287c9278b26fa5d9544`.
The packaged image is `build/rpi5/bl33-probe-azouwbdd/probe.bin` (SHA-256
`c00b01259499a22e9bb8eb399725d5593622314c325e350eafc0587f6db622ae`).
Host Mach-O/container validation passes (18 segments, 93,932 relocations),
and the host tooling suite passes 214/214, including the topology checks.
Its Pi regression capture `build/rpi5/serial-capture-4t4j4ont/serial.bin`
shows one boot-CPU GIC setup, `bsd_init: done`, PID 1 success and 105
one-second timed ticks without a panic. The finite diagnostic watchdog then
returned the Pi to NVMe Linux. This validates preservation of the Gate 2 path,
not SMP execution.

Second checkpoint: `osfmk/arm64/rpi5_secondary_trampoline.s` now provides a
BCM2712 DEVELOPMENT-only, stackless physical EL2 entry for a future PSCI
CPU_ON64 call. It validates EL2 and a page-aligned nonzero reset-vector
physical address in `context_id`, requires the EL2 MMU/caches off, installs
park vectors, and enters XNU's physical `LowResetVectorBase` in EL1h with
interrupts masked. The source is selected by `osfmk/conf/files.arm64` and a
full Xcode 27 kernel build passed (`build/rpi5-xcode27/run-fvfk2vhg/manifest.json`).
The linked kernel exports `_rpi5_secondary_trampoline` and
`_LowResetVectorBase`; the 214 host tests and `git diff --check` passed.
No CPU_ON caller or Pi boot
uses this trampoline yet: firmware entry conditions, physical code visibility,
reset-handler data publication, and second-core lookup still need end-to-end
verification before enabling it.

Third checkpoint (in progress): a physical-handoff publisher now validates and
cleans the secondary CPU data, reset data, boot args, reset vector and EL2
trampoline to PoC. A BCM2712-only PSCI CPU_ON64 wrapper and explicit GICv2
SGI1 send/receive primitives are linked but not invoked. An opt-in
`bcm2712_register_secondaries=1` IOKit CPU path registers CPU objects without
starting secondaries; the default CPU registration behavior remains off. The first integrated
build, `run-faqdp02l`, passed link and 216 host tests, but was incorrectly
invoked without `--with-crypto-candidate --activate-crypto
--with-pthread-provider`. Its Pi regression capture
`build/rpi5/serial-capture-8qel4_uh/serial.bin` reached XNU then panicked in
`crypto_random_kmem_ctx_size` because the crypto provider was not registered.
The diagnostic watchdog returned the board to `/dev/nvme0n1p2` Linux. This is
a failed build-configuration trial, not a Gate 3 runtime pass. A fresh build
with those provider flags passed as `run-wko_oi9e`; its host-buffer native
copy check passed for `bl33-probe-x3cxwmig`. The corrected probe SHA-256 was
`dda91fe297e3266ff96b75b29b9821d27892e9647d05dfd4d9d518c29e67849c`,
verified locally, after transfer to the Pi, and on SD before boot selection.
The corrected default-off Pi capture
`build/rpi5/serial-capture-ae1qfk3z/serial.bin` reached `bsd_init: done`,
PID 1 success and 128 one-second PID 1 ticks without panic. The 180-second
capture ended before the watchdog reset, but a subsequent SSH check confirmed
the board had rebooted to `/dev/nvme0n1p2` Linux. This restores Gate 2's
one-core regression baseline; it does not demonstrate any XNU secondary core.

An opt-in registration-only loader image, `bl33-probe-5wk72yo1`, passed native
host-copy validation and had SHA-256
`2bd842173dd3a8869a55d2c3dbdfaef2568b28069c1c0ca424e2951d47896cbc`.
Its Pi capture `build/rpi5/serial-capture-ruesbpvh/serial.bin` shows boot-CPU
`cpu_start()`, PID 1 success, then PID 1 exit with signal 10 before the first
timed tick; the kernel panicked and the watchdog returned to NVMe Linux.
No XNU secondary started, and the panic path could not signal CPUs 1–3.
Registration had incremented `real_ncpus` for these offline CPUs, a plausible
but unproven cause of the PID 1 fault. The capture lacks its user fault
PC/FAR/ESR, so the exact cause is open. The SD boot file was restored from
the verified 128-tick `probe.before-register.bin` backup (SHA-256
`dda91fe297e3266ff96b75b29b9821d27892e9647d05dfd4d9d518c29e67849c`).
The next isolated trial registers only the boot CPU to distinguish that
lifecycle transition from premature secondary registration.

That isolation trial used fresh provider-enabled kernel build
`build/rpi5-xcode27/run-j5ymfgee/manifest.json` (source unchanged, 216/216 host
tests), loader `bl33-probe-zxkcy9zv` (SHA-256
`4b4bcbc8d1630563b5540bd6bd15ff55e80a290dedc6679869f1787bac37dc18`),
and raw serial `build/rpi5/serial-capture-yf22lbcj/serial.bin`. It too logged
`cpu_start() cpu: 0`, reached PID 1 success, and lost PID 1 to signal 10 before
the first tick. Thus the three offline registrations are not necessary for
this failure; the boot-CPU registration/lifecycle transition is implicated.
No user fault PC/FAR/ESR was emitted, so the causal instruction remains
unknown. The watchdog returned to NVMe Linux and the SD boot file was again
restored to the 128-tick image (SHA-256
`dda91fe297e3266ff96b75b29b9821d27892e9647d05dfd4d9d518c29e67849c`). A BCM2712
DEVELOPMENT-only first-unhandled-user-abort serial report has been added for
the next diagnostic trial; it is not a fix.

The diagnostic trial used fresh provider-enabled build
`build/rpi5-xcode27/run-4hmlgl6m/manifest.json`, packaged boot-CPU-only image
`build/rpi5/bl33-probe-pepz9nm1/probe.bin` (SHA-256
`f0dd53c012400544f641fb8ecd791975a180c5d78c696a14e921a16aae589271`),
and raw serial `build/rpi5/serial-capture-y2wpkvl8/serial.bin`. Host tests
passed 216/216; native host-buffer load verification passed. On the Pi,
`cpu_start() cpu: 0` again occurred, but PID 1 produced 111 one-second ticks
through the 180-second capture, with no panic or user-abort marker. This
contradicts treating the prior boot-CPU-only SIGBUS as deterministic. The only
intentional source change between the two fresh builds was the pre-signal
diagnostic print, but the outcome could be timing-sensitive or reflect
another uncontrolled variable; no causal fix is established. CPU_ON remains
uninvoked and the secondaries remain offline.
The watchdog returned the Pi to `/dev/nvme0n1p2`; the SD `probe.bin` was
restored from `probe.before-register.bin` and verified at SHA-256
`dda91fe297e3266ff96b75b29b9821d27892e9647d05dfd4d9d518c29e67849c`.

`BCM2712CPU::startCPU` now connects the secondary-only path to the validated
physical handoff and PSCI CPU_ON64 wrapper, passing the trampoline PA as the
entry and reset-vector PA as context. It rejects the boot CPU and reports
handoff or PSCI failure on serial. Fresh provider-enabled build
`build/rpi5-xcode27/run-dxj7r8p_/manifest.json` linked these symbols in the
kernel, and 216 host tests passed. This path remains dormant because the Pi
registration mode does not call `processor_boot` for a secondary. No CPU_ON
hardware trial or SMP claim follows from the successful link.

The same diagnostic kernel was then packaged with
`bcm2712_register_secondaries=1` as
`build/rpi5/bl33-probe-vlrgbl2i/probe.bin` (SHA-256
`5e43be4cf23f7253b355b0efaef71b7c82a7c2118d068517ac5854a6a8dfe510`).
Native host-buffer verification again passed. Raw serial
`build/rpi5/serial-capture-u68z4zg_/serial.bin` shows `cpu_start() cpu: 0`,
PID 1 success, and 130 one-second ticks in 180 seconds without a panic or
unhandled-user-abort marker. The three secondary `BCM2712CPU` objects were
registered but never booted; there is no evidence of CPU_ON, secondary
`cpu_start`, cross-core IPI, or SMP correctness. The earlier all-CPU SIGBUS
is therefore not deterministic with this rebuilt kernel. After the watchdog
returned to NVMe Linux, the SD boot file was restored and verified against
the same known-good SHA-256 above.

An explicit `--gate3-cpu-on-1` mode now registers all CPU objects, arms the
GICv2 SGI1 path on a CPU when it initializes, and calls `processor_boot` for
logical CPU 1 only. `BCM2712CPU::startCPU` publishes the physical handoff and
calls PSCI CPU_ON64 with the discovered affinity, trampoline PA, and reset PA.
Fresh provider-enabled kernel build
`build/rpi5-xcode27/run-qi11g4hu/manifest.json` linked; 217/217 host tests
passed. Native host-buffer validation passed for
`build/rpi5/bl33-probe-7_zziys4/probe.bin` (SHA-256
`05fb72164db9f80f22b55be54972e6d3f8fbfbd5b2607183cfb8de8f8a04c52c`).
The bounded Pi capture `build/rpi5/serial-capture-qgavo4_q/serial.bin` shows
boot CPU SGI target bit 0, `CPU_ON:REQUEST CPU=1`, `cpu_start() cpu: 1`, raw
PSCI return 0 (success), and an interleaved `M` pre-MMU marker from the
secondary reset path. PID 1 continued on CPU 0 for over 100 timed ticks.
There is **no** CPU 1 `arm_cpu_init`/SGI-local/online marker or cross-core
execution evidence. The warm path intentionally omits the post-MMU UART marker,
so `M` alone does not localize a failure to the SCTLR transition. The secondary
may be in reset lookup, translation setup, trampoline, or later init; it is not
counted as online. The watchdog returned to NVMe Linux and `probe.bin` was
restored to the known-good SHA-256 above.

Warm-path markers `v`, `t`, and `k` were added around MMU enablement and the
KVA trampoline. Trial kernel `build/rpi5-xcode27/run-uhzucao1/manifest.json`
and `build/rpi5/bl33-probe-7xz_tr8x/probe.bin` (SHA-256
`2d4fc3bab2dd96fdbd9303a0b9fc02fb975699254d02e71b09cb77a84e567f94`)
passed build, 217 host tests, and native host-buffer validation. Raw serial
`build/rpi5/serial-capture-iz8vkyhw/serial.bin` again showed only the
secondary `M` marker and PSCI success, with no `v`/`t`/`k` or CPU 1 online
report. This narrowed the failing interval but still could not distinguish
MMU enablement from the first identity-mapped UART access. The Pi returned to
NVMe Linux and the known-good SD image was restored.

The physical handoff was then extended to flush the bootstrap TTBR0 tables,
the dedicated UART sub-tables, and the `cpu_ttep` TTBR1 pointer to PoC before
CPU_ON. Provider-enabled kernel build
`build/rpi5-xcode27/run-6yrnd79c/manifest.json` linked, 217/217 host tests
passed, and native host-buffer validation passed for
`build/rpi5/bl33-probe-hem5nrii/probe.bin` (SHA-256
`88138eb2f65a3327078d71634cc36eb4dbfc0a991c25b340b619d1eaa37518aa`).
Raw serial `build/rpi5/serial-capture-rh4ibzxr/serial.bin` records a valid
TTBR0 root (`0x7134000`, nonzero root entries) and TTBR1 PA (`0xb018000`),
PSCI success, then heavily interleaved two-CPU output. The interleaved bytes
include the warm checkpoints, secondary GIC PPI27 configuration, and CPU 1's
`SGI1:LOCAL` report with target mask `0x2`. PID 1 produced 128 one-second
ticks with no panic. This is the first hardware evidence that CPU 1 reached
post-MMU kernel initialization, but concurrent UART writes prevent treating
the capture as clean proof of `processor_up`, IPI delivery, or TLB correctness.
The flush and changed timing co-occurred, so causality is not yet isolated.
After watchdog recovery, the Pi ran `/dev/nvme0n1p2` Linux and SD `probe.bin`
was restored and verified at the known-good SHA-256 above.

A boot-CPU-only observation of `ml_cpu_up_processors` was then added. Fresh
provider-enabled build `build/rpi5-xcode27/run-h1tdktr9/manifest.json`
passed 217/217 host tests and native host-buffer validation for
`build/rpi5/bl33-probe-87i0x19w/probe.bin` (SHA-256
`7b60219d8eccb72a891f33886f06e6492fe3385dc13ee8450633406ea7ac0509`).
Its raw serial `build/rpi5/serial-capture-z_9qrf06/serial.bin` contains a
clean `RPI5XNU:CPU_ON:ONLINE_MASK=0x3`, proving CPUs 0 and 1 reached XNU's
online mask. PID 1 then printed `OK` but exited with signal 10 (`SIGBUS`)
before its first tick; the ensuing panic ran on CPU 1 and nested during panic
handling. No `USER_ABORT_UNHANDLED` report appeared, so the earlier abort
probe did not identify the signal source. This is a real two-core failure,
not a Gate 3 pass. The watchdog returned the Pi to NVMe Linux, and the SD
image was restored to the verified known-good SHA-256 above.

A BCM2712 DEVELOPMENT-only PID 1 SIGBUS trace was added at the Mach
exception-to-UNIX-signal boundary because neither the earlier unhandled EL0
abort probe nor the two-core panic exposed a fault address. Provider-enabled
kernel build `build/rpi5-xcode27/run-jkxbya9a/manifest.json` linked, 217/217
host tests passed, and native host-buffer validation passed for
`build/rpi5/bl33-probe-zo4tvhhr/probe.bin` (SHA-256
`dad4bb95c8ca2eab56979cadecef83c319f24c000e233cda43c2304dc503f0aa`).
Raw Pi serial `build/rpi5/serial-capture-82z6sj0f/serial.bin` again contains
clean `ONLINE_MASK=0x3`, followed by 122 PID 1 one-second ticks with no
SIGBUS, panic, or new exception marker during the 180-second capture. The
immediately preceding two-core build failed before its first tick, so this
is short-run success, **not** reproducible stability or proof that the trace
fixed anything. The watchdog returned to NVMe Linux, and the SD image was
restored to the verified known-good SHA-256 above.

The first one-shot XNU `SIGPtest` trial used provider-enabled build
`build/rpi5-xcode27/run-2lgdg3ag/manifest.json` and raw serial
`build/rpi5/serial-capture-wfxfvn4z/serial.bin`. It reported CPU 1 online,
then caught PID 1's SIGBUS at the exception boundary:
`EXC=1 CODE=0x103 SUB=0x16fdffe68`. Code `0x103` is `EXC_ARM_SP_ALIGN`, and
the reported SP is 8 mod 16. The freestanding PID 1 entered directly from
the raw Mach-O without a crt/dyld prologue and later subtracted only 16 from
SP, preserving any initial 8-byte misalignment. Its `_start` now aligns SP
down to 16 bytes before syscalls or stack access; disassembly confirmed the
`mov/and/mov` prologue. This addresses the measured userspace fault but does
not establish that all two-core faults are gone.

The aligned PID 1 RAMDisk is
`build/rpi5/pid1-agent-aligned/ramdisk.bin` (SHA-256
`0791e8414193094d1ac7e68959a929ebc17af948beeb6daee11ed0ce766e1236`).
With kernel build `build/rpi5-xcode27/run-3e9h9o1c/manifest.json`, the Pi
again reached `ONLINE_MASK=0x3` and over 100 PID 1 ticks without SIGBUS,
but the cross-core test returned `IPI:SEND CPU=1 KR=5` in raw capture
`build/rpi5/serial-capture-zlvw_5u2/serial.bin`. XNU's legacy startup path
can publish the online bit before `SIGPdisabled` clears, so an online mask
alone is insufficient proof that `cpu_signal` is ready.

CPU 1 now queues a local SGI1 during `BCM2712CPU::initCPU`, while interrupts
are masked. Its normal first SGI handler clears `SIGPdisabled` after startup
enables interrupts. Provider-enabled build
`build/rpi5-xcode27/run-0san9sjp/manifest.json` passed 218/218 host tests;
native host-buffer validation passed for
`build/rpi5/bl33-probe-6c6cjd2a/probe.bin` (SHA-256
`d650c983a33126e73269a816e3b930a1aa041765bf613ff38bf21a56d2f084fa`).
Raw Pi serial `build/rpi5/serial-capture-2ecifjv_/serial.bin` has clean
`ONLINE_MASK=0x3`, `IPI:SEND CPU=1 KR=0`, and `IPI:ACK CPU=1 COUNT=1` markers,
then 124 one-second PID 1 ticks without panic during the 180-second capture.
This proves one CPU 0-to-CPU 1 SGI through XNU's signal handler and callback,
not sustained IPI stress or TLB-shootdown correctness. The watchdog returned
the Pi to `/dev/nvme0n1p2` Linux, and SD `probe.bin` was restored to the
verified known-good SHA-256 above.

An opt-in `--gate3-cpu-on-all` image now requests PSCI CPU_ON for CPUs 1-3,
without changing the verified CPU-1-only mode. Provider-enabled build
`build/rpi5-xcode27/run-1r_7q1h9/manifest.json` completed; host-buffer
native validation passed for `build/rpi5/bl33-probe-0htlpjcp/probe.bin`
(SHA-256 `1ff660fa881e7f8c32f3c500603f4ac1c8f045e14e9e1234134b89ff0dd6a0f0`).
The 180-second receive-only capture
`build/rpi5/serial-capture-27tzk3lv/serial.bin` (SHA-256
`92149f95aad4c8f531450b09e95f8d2926c0e19375e9c9485740bee0d735e557`)
shows `ONLINE_MASK=0xf`, local SGI targets 0x1/0x2/0x4/0x8,
`IPI:SEND CPU=2 KR=0` and `CPU=3 KR=0`, and one ACK from each of CPUs 2
and 3. CPU 1's ACK is visibly interleaved with concurrent UART writes, so
that particular line cannot be counted as a clean result; the prior two-core
capture has a clean CPU 1 send/ACK pair. This run recorded 102 PID 1 ticks
without a panic. Follow-on serial `build/rpi5/serial-capture-11yagl9g/serial.bin`
recorded Linux boot. SSH verified `/dev/nvme0n1p2`, and SD `probe.bin` was
restored to known-good SHA-256
`dda91fe297e3266ff96b75b29b9821d27892e9647d05dfd4d9d518c29e67849c`.
This is first four-core online/SGI evidence, not concurrency or memory-ordering
validation.

A bounded CPU 0-driven follow-up sends one outstanding `SIGPtest` at a time
to each secondary until 64 callbacks have been acknowledged per core. The
provider-enabled build `build/rpi5-xcode27/run-ea6jec4e/manifest.json`
completed; native host-buffer validation passed for
`build/rpi5/bl33-probe-1yjacntt/probe.bin` (SHA-256
`8a93eaaa7e063c73f27c2b72ca069e8de850cfa5c2f3941335f44dc67b9cde54`).
The unfiltered 210-second receive-only capture
`build/rpi5/serial-capture-jjygx5ri/serial.bin` (SHA-256
`4a8bf39ac90156754b8a9deace68be5cf3cf86f6ba318268dfaafb0174a4222d`)
contains clean initial `IPI:SEND CPU=1/2/3 KR=0` and corresponding
`IPI:ACK CPU=1/2/3 COUNT=1` lines, followed by
`RPI5XNU:IPI_STRESS:PASS CPUS=1-3 ACKS=64,64,64`. PID 1 emitted 127 ticks
without panic; the serial tail shows Linux boot. SSH confirmed Linux rooted
at `/dev/nvme0n1p2`, and the SD boot image was restored and verified at the
known-good SHA-256 above. This tests repeated SGI routing and visibility of
the atomic ACK counters; it does not test concurrent IPI producers, TLB
shootdowns, cache visibility of arbitrary data, or an eight-hour soak.

The next four-core build added a bidirectional payload handshake to each
of the 64 SGIs per secondary: CPU 0 publishes a non-atomic 64-bit payload
before a release sequence store, the target validates it after an acquire
load, writes a transformed response, then release-increments its ACK; CPU 0
acquire-loads that ACK and checks the response before issuing the next SGI.
Provider-enabled build `build/rpi5-xcode27/run-ur3j87x5/manifest.json`
completed; host-buffer validation passed for
`build/rpi5/bl33-probe-_1p8ntzw/probe.bin` (SHA-256
`b09bb9c57a263bfb6e96933d68e76a0fd366cc5c911904b8492f00a7642e721d`).
Raw receive-only serial `build/rpi5/serial-capture-ba0s1h8c/serial.bin`
(SHA-256 `e6d02bb7754eb3e184c9c88181bbf1014ea1ea1fceaef631ee54845b3ff7b9ac`)
records `ONLINE_MASK=0xf`, `IPI_STRESS:PASS CPUS=1-3 ACKS=64,64,64`,
and `CACHE_VIS:PASS ROUNDS=64 ERRORS=0`, with 127 PID 1 ticks and no panic.
The watchdog returned to Linux on `/dev/nvme0n1p2`; SD `probe.bin` was
restored and verified at the known-good SHA-256 above. This proves the
bounded release/acquire data exchange on all three secondary cores in this
run. It does not yet prove concurrent writers, unsynchronized accesses,
DMA coherency, or cross-core TLB invalidation.

The non-SPTM ARM64 pmap path uses inner-shareable broadcast TLBI instructions
(`tlbi ...is`) with `dsb ish`/`isb` completion, not an SGI-based software
shootdown. A separate test must change a mapping while another core has
cached that translation and verify the new translation or permission there;
the SGI/cache payload handshakes do not cover this requirement.

An opt-in `--gate3-tlb-trial` now starts a boot-CPU-bound kernel worker only
in the four-core image. It allocates two distinct wired kernel pages with
different values, uses a cross-call to make CPUs 1-3 read the first page's
VA, then alternates that VA's pmap mapping between the two physical pages
for 16 rounds. After each `pmap_remove`/`pmap_enter`, cross-calls force all
three secondary cores to load the VA and compare with the newly selected
value. The worker restores the original mapping before releasing memory;
its timeout path deliberately retains the mapped pages because a delayed
callback may still reference them. This tests actual remote loads after
the pmap broadcast-TLBI path, not merely page-table contents.

Provider-enabled build `build/rpi5-xcode27/run-m6fftc8o/manifest.json`
completed and host-buffer validation passed for
`build/rpi5/bl33-probe-4c9y0vdm/probe.bin` (SHA-256
`e3da2a86cbb5741ee2c6c4288f40239c978dca9a22b134c1507e8f445b54d48d`).
Raw receive-only capture `build/rpi5/serial-capture-fi3hldmc/serial.bin`
(SHA-256 `9570c631042012106b92d187d86d921f37e7a4cba62f677f947dfb0bbd5d805c`)
records `ONLINE_MASK=0xf`, `RPI5XNU:TLB:PASS ROUNDS=16 CPUS=1-3`,
`IPI_STRESS:PASS CPUS=1-3 ACKS=64,64,64`, and
`CACHE_VIS:PASS ROUNDS=64 ERRORS=0`, with 132 PID 1 ticks and no panic.
The serial tail shows Linux boot; SSH confirmed `/dev/nvme0n1p2`, and SD
`probe.bin` was restored and hash-verified to the known-good image. This is
one successful cross-core kernel-VA remap test. It does not cover ASID-scoped
user mappings, permission downgrades, concurrent remappers, or sustained
TLB stress.

XNUPOST is compiled into this DEVELOPMENT kernel. An opt-in `kernPOST=4`
inventory image `build/rpi5/bl33-probe-68wcbepl/probe.bin` (SHA-256
`713070cece9b98c82330bbd01f1b219e6ee477bf7394694a2c88bf68345ccb34`)
listed the board's actual table in raw serial
`build/rpi5/serial-capture-7qhww_gg/serial.bin` (SHA-256
`10ead0f2b8004306eb33fe42ad461e06b07d27b1fde47cd44caf7b85f2ffe920`):
`xnu.pmap_test` is #30 and `xnu.ipi_test` is #32. It did not run tests;
the watchdog returned to Linux and SD was restored.

The first #32 image used `kernPOST_config=32`. XNU's `get_range_bounds`
leaves the upper bound at 999999 for a bare number, so this selected #32
and later tests. More importantly, `xnu.ipi_test` immediately panicked on
CPU 0's self-xcall with `error 5` (`KERN_FAILURE`): raw serial
`build/rpi5/serial-capture-f9u_hgrh/serial.bin` (SHA-256
`5c44a6ea759339ecd0a7639a1ce608ed0ad94255675e75e5c690c1bf2ecf72dd`).
Source review showed XNU initializes every CPU with `SIGPdisabled` and its
normal platform path sends a first self-IPI to clear it. BCM2712 had sent
that first SGI only on secondary cores. The Pi platform now queues it on
CPU 0 as well. The watchdog recovered and SD was restored after the failure.

With the boot-core self-SGI fix, provider-enabled build
`build/rpi5-xcode27/run-ai_1d30q/manifest.json` completed; host-buffer
validation passed for `build/rpi5/bl33-probe-qxu5iyal/probe.bin` (SHA-256
`e4c54b7123803b0528f2838a2910e518e1f1fa95ddf90948922b450270db924f`).
Raw serial `build/rpi5/serial-capture-mbeksgbi/serial.bin` (SHA-256
`49a9134417b7846d05d42481bbc61a3843f182511c6868ebee1281874e8279e9`)
shows upstream `xnu.ipi_test` running on CPUs 0, 1, 2 and 3 and emitting
`PASS`/`Done running IPI tests`. The selector also ran the later `copyio`
and boot-argument tests, so this is not claimed as a one-test run. The
loader now emits an exact range such as `kernPOST_config=30_30`.

The exact #30 image `build/rpi5/bl33-probe-r4vi3qxp/probe.bin` (SHA-256
`85e1ded4ba26d72a91b62f65e47d8f15f1d20fd1f895e136f2eed32e68f35b1f`)
passed host-buffer validation and ran only `xnu.pmap_test` on board. Raw
serial `build/rpi5/serial-capture-goezzxsv/serial.bin` (SHA-256
`c2bd5cd7437564167f2e0b5005210fc4edbaafd7bcb5dbc87c363ea31e270cec`)
shows the 4 KiB and 16 KiB configurations completing with `PASS` and no
panic. The finite watchdog left only 11 PID 1 ticks in this longer POST
boot, so this is a pmap-test result, not a stability run. The Pi returned
to `/dev/nvme0n1p2` Linux, and SD `probe.bin` was restored and verified
at known-good SHA-256
`dda91fe297e3266ff96b75b29b9821d27892e9647d05dfd4d9d518c29e67849c`.

Remaining Gate 3 work: repeat the aligned-PID1 boot enough times to
test that the SP alignment fault is gone; test concurrent IPI producers,
ASID/user-mapping invalidations, concurrent remappers, and broader
cache visibility; expand applicable XNUPOST coverage; complete 20
true power-off cold boots and an uninterrupted eight-hour timer/IPI/SMP soak.
The finite Gate 2 diagnostic watchdog needed an opt-in extension before
longer soak trials; the initial extension and board results follow.

An opt-in watchdog-backed soak path now accepts `--gate3-soak-seconds`
(`60`–`28800`) only with all three secondaries requested. The kernel extends
the recovery deadline, keeps feeding the 15-second hardware watchdog only
while CPU 0's timer observes four online cores, ongoing per-secondary SGI
ACK progress, and zero payload errors, and stops feeding after a timed
`SOAK:PASS` or heartbeat failure. A source-level GIC/watchdog model covers
the extended reload count, deadline, and unhealthy-at-deadline ordering.

The first 300-second image (`build/rpi5/bl33-probe-6ewu0phg/probe.bin`,
SHA-256 `d2729ced7c2b32e45e827c89a27523e3b6292b80371052fa904551a2b86a70cd`)
passed host-buffer validation but failed early on board with
`RPI5XNU:SOAK:FAIL STAGE=HEARTBEAT`, after one ACK from each secondary and
12 PID 1 ticks. Raw serial is
`build/rpi5/serial-capture-wyxizkci/serial.bin` (SHA-256
`d37e5bac0686501665001d903683025a0f8ac597af9dfa4504ae7293ae7c80bc`).
The watchdog recovered to NVMe Linux and the SD fallback was restored and
hash-verified. This is a failed stability trial, not a pass.

A one-shot counter snapshot was added to distinguish missing ACK progress
from payload corruption. The first 60-second retry lost its initial serial
stream because the previous receiver still held the port; it is not used as
evidence. The repeated 60-second image
(`build/rpi5/bl33-probe-k5n7phlj/probe.bin`, SHA-256
`811502f6f6867d53f8ec79140208eddd1c8eaa3ab8f8aa105085d13ca24e71f6`)
was captured in `build/rpi5/serial-capture-jinnm0vi/serial.bin` (SHA-256
`b7a76d0d6e8031a49663a0c6c1432769ba92da3532114b0e643b3a1f517a711c`).
It recorded four cores online, a healthy five-second snapshot with sends
`5,4,4`, ACKs `4,3,3`, and errors `0,0,0`, then a later heartbeat with ACKs
`10,9,9` and `RPI5XNU:SOAK:PASS SECONDS=60`. The watchdog returned to
`/dev/nvme0n1p2` Linux; SD `probe.bin` was restored to the known-good
SHA-256 `dda91fe297e3266ff96b75b29b9821d27892e9647d05dfd4d9d518c29e67849c`.
This proves a bounded one-minute healthy run and timed recovery only; the
300-second early failure is unresolved, and the eight-hour soak remains open.

The instrumented 300-second repeat used
`build/rpi5/bl33-probe-c9goe33h/probe.bin` (SHA-256
`37832b3af2d6f4649e8fb7ae1aace3c6de445bb396a48972ecda02a5f7c46112`).
Raw serial `build/rpi5/serial-capture-lj8mkcbq/serial.bin` (SHA-256
`12a888ee5238938f6293868acdb153917c9603373d3fc3718a8a71865e7e0fe1`)
records `SOAK:ARM SECONDS=300`, the first heartbeat at ACKs `1,1,1`,
14 PID 1 ticks, and then Linux boot, but neither the five-second CPU 0
counter snapshot nor `SOAK:FAIL`. The receiver was stopped after Linux
recovery, so its metadata status is `failed` despite the preserved raw
bytes. SSH verified NVMe Linux and SD `probe.bin` was restored to the
known-good hash. The absence of later CPU 0 monitor output is consistent
with CPU 0's timer not firing while other cores still run PID 1; that is a
hypothesis, not yet a proven root cause. The current timer-IRQ-driven soak
monitor was therefore not suitable for an eight-hour claim.

The monitor was moved to a high-priority XNU delayed thread call scheduled
every second. The timer-IRQ probe remains for non-soak images; the soak
callout alone sends SGIs, checks each response and progress timestamp, and
feeds the hardware watchdog. It stops scheduling after the deadline or a
heartbeat failure. This removes dependence on incidental CPU 0 timer
interrupts while keeping hardware reset as recovery if the callout stops.

The callout kernel built in
`build/rpi5-xcode27/run-uonuuuh8/manifest.json`; host-buffer validation
passed. Its 60-second image `build/rpi5/bl33-probe-a7s629iv/probe.bin`
(SHA-256 `804cf68dd3cd7a4c75103d050e3fbe412ba6ebd1a748584b8234cf4d76d339ed`)
ran on all four cores and logged `SOAK:PASS SECONDS=60` in raw serial
`build/rpi5/serial-capture-4w_tn0k2/serial.bin` (SHA-256
`118cbb0a978e4153a277216760713a1e9e0804c75427ad012726cd0265f22a71`).
The watchdog returned to NVMe Linux and SD fallback hash was restored.

The same kernel's 300-second image
`build/rpi5/bl33-probe-7svuu0gr/probe.bin` (SHA-256
`470b7e3c4247d3fae1389be1618c00d93cd23f9cda3941999941ac7bc751f206`)
passed host-buffer validation. Complete receive-only serial
`build/rpi5/serial-capture-_6wkrm3l/serial.bin` (SHA-256
`7f9fc12b8d820a04c693820b37c5550398008a10dff88e9c62115608b0f72729`)
records `SOAK:ARM SECONDS=300`, the 64-IPI milestone on CPUs 1–3,
`CACHE_VIS:PASS ROUNDS=64 ERRORS=0`, minute-scale heartbeats with ACKs
`62,61,61`, `122,121,121`, `182,181,181`, and `242,241,241`, then
`SOAK:PASS SECONDS=300`. Linux returned on `/dev/nvme0n1p2`; SD `probe.bin`
was restored and verified at the known-good SHA-256. This establishes a
five-minute four-core timer/IPI/cache-payload run, not an eight-hour pass,
20 true power-off cold boots, or full concurrent-writer/ASID coverage.

An eight-hour image using the same verified kernel was packaged as
`build/rpi5/bl33-probe-6c7ibywk/probe.bin` (SHA-256
`136dd556fb1ff0ec062420734247783404b2b4088ac64e97f61d22a1a538c078`)
with `--gate3-soak-seconds 28800`; host-buffer validation passed. A
receive-only, independently running serial recorder on the 4090 was
dry-run and then started at
`sandrzej@192.168.4.42:/home/sandrzej/xnu-gate3-soak-20260926`
(process 37098, requested capture 29100 seconds). The Pi was rebooted
with the image after verifying NVMe Linux, SD label, backup hash and staged
image hash. Initial live serial shows the 28800-second soak arm marker
(one character is interleaved by concurrent UART output) and heartbeat
ACKs `2,1,1`; a subsequent live sample at receiver elapsed 2:35 shows
ACKs `62,61,61`, `IPI_STRESS:PASS` at `65,64,64`, and
`CACHE_VIS:PASS ROUNDS=64 ERRORS=0`. This run is **in progress**; no
eight-hour pass or recovery
claim follows until the recorder finishes, its raw hash and timed markers
are inspected, the Pi returns to NVMe Linux, and the SD fallback is
restored and hash-verified.
This is an early endurance qualification image, not the final Gate 3 exit
image: four-core concurrency, cross-core invalidation, the selected XNUPOST
suite and 20 cold boots have not yet passed on it. The final eight-hour soak
must be repeated on the unchanged image that passes those prerequisites.

At receiver elapsed 6:17, process 37098 was still live and the latest
heartbeat had advanced to ACKs `302,301,301`, with intervening minute
markers. `tools/rpi5/check_gate3_soak.py` was added and tested against
synthetic contradictory captures and the completed five-minute capture; it
will be run on the finished eight-hour raw/metadata pair. Its passing result
alone will not close the other Gate 3 requirements.

A separate opt-in four-CPU concurrency trial was prepared while the soak
continues. Four kernel workers bind to XNU processors 0–3, synchronize at
start and midpoint barriers, each perform one million increments of a
shared atomic counter, and check peer progress in the second half. The
coordinator checks distinct observed CPU IDs, all per-worker counts, the
four-million global total, overlapping execution intervals, and bounded
completion before emitting an exact `SMP_CONCURRENCY:PASS|FAIL` marker.
Provider-enabled build `build/rpi5-xcode27/run-51fyqx_u/manifest.json`
and host-buffer validation passed for
`build/rpi5/bl33-probe-9mgdlq30/probe.bin` (SHA-256
`0ccccda001971af881a38a45e21e2edcf9a89ad3b735fe0736f10c48b3f43f7b`).
This image is **not board-tested** and is not staged on the SD card; the
eight-hour soak image remains in place until its run ends and recovery is
verified.

Pre-board review found a race in that trial's peer-progress witness: at the
three-quarter checkpoint, a fast core could immediately fail while another
healthy core had not yet advanced from the midpoint. The worker now waits,
bounded by ten seconds per peer, for the peer's release-published progress
to advance, and publishes its exact final count. The revised kernel links in
provider-enabled `build/rpi5-xcode27/run-v303vbwz/manifest.json`; 19 targeted
Gate 3 host tests and `git diff --check` pass. The previously packaged
`bl33-probe-9mgdlq30` image predates this correction and must **not** be
mistaken for the revised trial. The revised image is
`build/rpi5/bl33-probe-joy3g4ty/probe.bin` (SHA-256
`949cc758e6a180c6673f3602992619eb5c73340eb6e57e2a82daae09ecbe200b`);
native Mach-O/container host validation passed with 18 segments and 94,262
local relocations. It has **not** run on the Pi. The soak image remains in
place until that run ends and the board returns to Linux.

A subsequent failure-path review found that the coordinator could inspect
plain per-worker fields after a completion timeout while that worker was
still writing them. It now reads those fields only after acquiring the
worker's `done` flag and reports `UINT32_MAX` for an unfinished CPU. The
superseding provider-enabled build is
`build/rpi5-xcode27/run-cas5rz6_/manifest.json`; the host-validated image is
`build/rpi5/bl33-probe-p106tb73/probe.bin` (SHA-256
`bf1f10db257bf2ce3d6d4703f4bbb3e1df7c342d85347e16dd3e2c38caa58093`).
The earlier `joy3g4ty` image is obsolete and **must not** be used for the
board concurrency trial. Neither revised image has run on the Pi.

For later XNUPOST suite qualification, the probe builder now accepts an
explicit comma-separated range selector. Host-only image
`build/rpi5/bl33-probe-60vojazt/probe.bin` (SHA-256
`a2bb58fe272628672c86f036abdce92b9bda0aacf07e0bbce661cbe486c278da`)
contains the tested command line
`kernPOST_config=16_16,23_24,28_28,30_30,32_32`; native container validation
passed. Those indices are from the **older** board table and are an example,
not an approved current-kernel suite. The current image must first print its
own inventory on the Pi. This host-only image has not been staged or booted.

The Pi's opt-in exact XNUPOST selector now prints an aggregate result after
both kernel and BSD POST phases, because upstream `xnupost_run_tests()`
returns success even when an individual test records a failed assertion.
Provider-enabled build `build/rpi5-xcode27/run-37s9ufc2/manifest.json`
links this summary path. Its host-validated inventory image
`build/rpi5/bl33-probe-wb2wzwwo/probe.bin` has SHA-256
`b45ba0c8bca563c07afcdedb22a7a6b392d439ccc4d224922c0ffbc2fb51c2a3`.
It is not staged or board-tested; after the soak, its table must be captured
before a suite is selected. The raw-log checker independently rejects the
older broad-selector IPI capture due to three VFP assertion failures and
accepts the clean exact `pmap_test` capture, so the aggregate cannot erase
contradictory test evidence.

The 20-power-off-boot requirement is not started. Its evidence protocol is
now explicit in [GATE3-COLD-BOOTS.md](GATE3-COLD-BOOTS.md): one immutable
candidate image, proof that 5 V was actually removed on every attempt,
complete raw serial for each boot, four-core/PID 1 assertions, and a streak
that resets on any failure or unverifiable attempt. No warm reset or current
watchdog recovery is counted toward the 20.

`tools/rpi5/check_gate3_cold_boots.py` now machine-checks a prospective
ledger/capture set: continuous attempt numbering, one candidate image and
kernel, finished hash-matching serial files that span each recorded power
cycle, at least ten seconds off, four-core and PID 1 markers, no explicit
failure, and an ending streak of 20. Synthetic tests prove a failed attempt
or changed image breaks the streak. This is preparation only; physical
power removal and ledger completeness still require independent human
evidence and **zero** cold boots have been credited.

The earlier board TLB trial covered remaps only. An opt-in successor now
uses XNU's non-faulting `mmu_kvtop_wpreflight()` on CPUs 1–3 to check a
test VA as writable, downgrade it to read-only with `pmap_protect()`, verify
remote write translation fails, then restore read/write through
`pmap_remove()`/`pmap_enter()` and verify it succeeds again, for eight rounds.
The existing 16 alternating physical-page remaps remain. Provider-enabled
build `build/rpi5-xcode27/run-9h6hw3zz/manifest.json` linked; host-validated
image `build/rpi5/bl33-probe-0hn167yi/probe.bin` has SHA-256
`1b59bf93d2ae2d45328b699411e159f46a220c9889c85bd9dd749a9d3756f235`.
It has **not** run on the Pi, and the soak image is still in place. Even a
future PASS from this successor would not cover user ASIDs or concurrent
remappers; do not promote its `TLB:PASS` to full Gate 3 invalidation evidence.

The opt-in TLB trial now also adds 64 live remap rounds under three pinned
kernel reader threads. CPU 0 marks the mapping epoch odd while changing it,
publishes the expected physical page only after `pmap_enter()` completes,
and waits for every remote reader to observe the new even epoch through
`mmu_kvtop()`; stable-epoch stale translations fail. Reader termination is
checked before freeing the mapped pages, and a timeout retains those pages
until watchdog reset. This is a hardware translation probe, not merely a
software page-table walk: `mmu_kvtop()` executes `AT S1E1R` and reads
`PAR_EL1` in `machine_routines_asm.s`. It is still not a concurrent data load
through the changing VA; the earlier serialized remote callbacks perform the
actual dereferences. Provider-enabled build
`build/rpi5-xcode27/run-a0ejphpf/manifest.json` linked, and host-buffer
validation passed for `build/rpi5/bl33-probe-0rc9z9fw/probe.bin` (SHA-256
`cadc3b4e4d546d5384606fffa9995b6588fe4eb52dcd661cb9c723df122e5d04`).
It supersedes the untested `0hn167yi` image and has **not** run on the Pi.
Even a future PASS is kernel-VA evidence only; user-ASID invalidation remains
to be implemented and tested.

A failure-path review then made an ambiguous `cpu_xcall()` enqueue failure
retain the callback's VA/pages until watchdog reset, just as a callback
timeout does. This avoids freeing a mapping if a late callback might still
use it. Provider-enabled build `build/rpi5-xcode27/run-rgim2xuu/manifest.json`
and native host-buffer validation pass for the superseding opt-in image
`build/rpi5/bl33-probe-edx309mf/probe.bin` (SHA-256
`c6eeda5da420dc3c4834053e35cc4e2f2b79fcdc90d3430778fa738f69e9d67b`).
The earlier `0rc9z9fw` image is obsolete; this new one is **not board-tested**.

The concurrency and TLB trials now expose acquire-read terminal status
(`0` idle, `1` running, `2` pass, `3` fail) for a future sequential Gate 3
qualification image. Both emit an unambiguous terminal `PASS` or `FAIL`
marker, including early launch/allocation failures and TLB callback timeouts.
The provider-enabled native kernel build passed at
`build/rpi5-xcode27/run-ii6geosa/manifest.json`; the Python Gate 3 checker
suite passed 29 tests and `git diff --check` passed. This status plumbing has
**not** been board-tested and does not qualify the running soak image.

The later source audit also corrected the TLB terminal marker to emit an exact
`RPI5XNU:TLB:PASS` line, with round counts on a separate `DETAIL` line. The
previous metadata-suffixed PASS was not accepted by `check_gate3_serial.py`.
Twelve targeted marker/topology tests pass; this output correction is not yet
present on a board-tested image.
The corrected provider-enabled kernel build
`build/rpi5-xcode27/run-8io3dvgt/manifest.json` linked; its opt-in TLB image
`build/rpi5/bl33-probe-o5wzip9z/probe.bin` has SHA-256
`5abfb856025fbbbcd25588c036959ed0d1e838d6dcb3d770fcf5e6652c83b355`.
Native Mach-O/container host-buffer validation passed. This image is
**host-only** until the in-progress earlier soak finishes; no SD media was
restaged for it.
The same kernel also packages as the opt-in concurrency image
`build/rpi5/bl33-probe-z_i1wyme/probe.bin` (SHA-256
`7be1e89d58b4007a6f5dae4e8473744c2d41334eb0730d397c11e54a23d155b6`).
Its native Mach-O/container host-buffer validation and 12 targeted host tests
pass. Like the corrected TLB image, it remains **unbooted** while the earlier
soak continues; packaging is not board qualification.
The matching XNUPOST inventory-only image is
`build/rpi5/bl33-probe-mjeab223/probe.bin` (SHA-256
`955809abcc8912b34d5a1809d50ad403790bd4fc41b0a4da8dae7209674fb4b4`),
also host-buffer validated against kernel SHA-256
`13bcbf845eaf975a1511ec6602359598b563116c54e129142b4800b2155050bc`.
It has not been board-run; no selected-suite indices should be inferred from
the older kernel's inventory.
For watchdog-window measurement, the concurrency and TLB trials now print
hardware-counter elapsed ticks and frequency on separate `TIMING` lines.
The provider-enabled build `build/rpi5-xcode27/run-2w711t9_/manifest.json`
linked and 12 targeted host tests pass. Its replacement TLB image is
`build/rpi5/bl33-probe-1pqhjyn4/probe.bin` (SHA-256
`e4604f14b4edd6d883245ba098d06df7e9231e6fdb3710356a1469a4f421fffa`);
the replacement concurrency image is
`build/rpi5/bl33-probe-glv4eudu/probe.bin` (SHA-256
`23a225df78a789b3d4b0116e84eae674b1b2acf7c865271c15f4cf70eba2d8dc`).
Both pass host native/container validation but remain unbooted. These supersede
the same-kernel `o5wzip9z` and `z_i1wyme` images for their respective trials;
the in-progress earlier soak is unchanged.
XNUPOST selected-suite summary now also records elapsed counter ticks and
frequency. The provider-enabled kernel build
`build/rpi5-xcode27/run-p4hf7hd2/manifest.json` linked, and 15 targeted host
tests passed. Its exact-build inventory image is
`build/rpi5/bl33-probe-6cqxy5ux/probe.bin` (SHA-256
`81100449e23c9f6512002d41c19b0798409bcb8f72cca62a94a004be89cde085`),
validated against kernel SHA-256
`99fd806c6da9708f43bdcb9893b3ffb3bf0adb55926c73144b35c4922b07bd07`.
It supersedes unbooted inventory image `mjeab223`; it has not run on the Pi.
An assembly review found `mmu_kvtop_wpreflight()` read `PAR_EL1` immediately
after `AT S1E1W`, unlike the adjacent `mmu_kvtop()` path's intervening `ISB`.
The write preflight now uses the same synchronization sequence. Arm's
[address-translation guide](https://documentation-service.arm.com/static/68e680a2587fd957f5efd742)
identifies `PAR_EL1` as the result of an `AT` instruction; applying the read
path's barrier to the write path is a local consistency/safety inference, not
board proof that the permission trial works. Provider-enabled build
`build/rpi5-xcode27/run-w2iu3o1g/manifest.json` linked and 10 targeted tests
passed. Earlier host-only trial images predate this change.
The resulting host-validated opt-in images are TLB
`build/rpi5/bl33-probe-hqdcdh8n/probe.bin` (SHA-256
`5ed69083b2048e343a0fbccc7eed55e973a544edd2cc798197f5872b71ccaa7a`)
and concurrency `build/rpi5/bl33-probe-a6w7hyby/probe.bin` (SHA-256
`2bdf32bb324d618c7229bc3d3403ae9fff562314c86406704cbc6c355af570ae`).
Neither was written to SD or run on the Pi while the earlier soak is active.
The matching current-kernel XNUPOST inventory image is
`build/rpi5/bl33-probe-6b04vwy8/probe.bin` (SHA-256
`447053c25920ecd5c488f6a62bcb3a50e84886cad594b9730aa957865cc2805a`),
host validated against kernel SHA-256
`06ceb071570d95723e13c91abf25862f2016abfbff4af3f1f9643f6b0d4fa4ea`.
It supersedes unbooted `6cqxy5ux` and remains board-untested.
The selected XNUPOST suite now publishes an acquire-read completion status
(`0` idle, `1` running, `2` pass, `3` fail), matching the other two trial APIs.
It is set terminal only after the selected-case summary and timing marker have
been emitted. Provider-enabled native build
`build/rpi5-xcode27/run-pznq_h3l/manifest.json` linked and 16 targeted host
tests passed. This status wiring is not board-tested; existing inventory and
trial images remain artifacts of the preceding kernel build.
An opt-in qualification coordinator now sequences the selected XNUPOST
aggregate, concurrency, TLB, then soak arm; it does not start standalone modes
concurrently. Provider-enabled build
`build/rpi5-xcode27/run-b1w367cu/manifest.json` linked, 20 targeted host
tests passed, and `git diff --check` passed. A host-only container
`build/rpi5/bl33-probe-9x8owx78/probe.bin` (SHA-256
`66fbd4057e45b57e88610124bd9eb9df18ac9e5e9b39600b03f25a96186ac1fa`)
passed native/container validation with placeholder `kernPOST_config=1_1`.
That placeholder is **not a selected Gate 3 suite** and the image must not be
staged or booted for qualification; exact-case inventory and standalone board
trial timings are still missing.
The qualification/XNUPOST builder now rejects overlapping and out-of-order
test index ranges rather than accepting each range independently; 21 targeted
host tests pass. This prevents ambiguous selected-suite manifests but does not
establish case applicability or board execution.

The opt-in user-ASID TLB trial now accompanies the kernel-VA trial. Three
workers pinned to CPUs 1-3 translate a user VA through a temporary user pmap
while CPU 0 repeatedly replaces its backing page; the coordinator requires
both TLB statuses before declaring cross-core invalidation pre-soak success.
The raw-capture checker requires the exact 64-round user-TLB detail, one
positive timing record, four online CPUs, and PID 1 before the PASS line.
This is source and host-build evidence only, not a Pi result. A review aligned
the temporary-pmap critical section with XNU's own pmap access test by
disabling interrupts as well as preemption around the switch. Provider-enabled
build `build/rpi5-xcode27/run-8ornnrkk/manifest.json` linked with unchanged
source and kernel SHA-256
`3f828c510d5a2b74153c63218ee0b5519ca2f9d3e302bea7a6a3d7d37b30c13c`.
The earlier standalone image `build/rpi5/bl33-probe-5pq7m9sm/probe.bin`
predates that critical-section change and must not be treated as the current
user-TLB trial image. No new image was staged while the existing eight-hour
soak was running.

The native build wrapper had rejected the prepared SDK solely because the
current Python dropped an optional `-Mach-O` suffix from its macOS host string.
The provenance comparison now normalizes only that suffix; all other toolchain
fields, the host OS/architecture, and the lock SHA-256 remain exact. The
initial sandboxed build could not read macOS `sysctl`, while the native build
above completed successfully. Twenty-three targeted Gate 3 checks and the
new provenance regression test passed; `git diff --check` was clean.

The refreshed standalone user-TLB container is
`build/rpi5/bl33-probe-g6579o24/probe.bin` (SHA-256
`0c32314ee5b7a0e3b1a8e488451627511c542bfd0588d874cb99a86ceaa0424e`).
It embeds the kernel SHA above and the aligned PID 1 RAMDisk SHA-256
`0791e8414193094d1ac7e68959a929ebc17af948beeb6daee11ed0ce766e1236`.
`compare_native_macho.py --probe-build` agreed with the host-buffer copy;
its layout verdict explicitly does not establish physical placement or boot.
The image remains unstaged and board-untested while the earlier soak runs.

The exact-kernel XNUPOST inventory image is
`build/rpi5/bl33-probe-2girap2d/probe.bin` (SHA-256
`a96768f1f1e05cd1444d6f48f3435ab57876b688a237810c878b1be9bc0fdc88`).
It passed the same host native/container comparison and is likewise unstaged.
The printed board inventory, not source guesses or an older image's indices,
must drive selected-suite configuration after the running soak finishes.

The same current kernel and PID 1 RAMDisk also produced refreshed standalone
concurrency `build/rpi5/bl33-probe-prqaw8ht/probe.bin` (SHA-256
`68d83412ea12966106d8d0308cee71f0ae3162401badddc4a72532cb70500ae4`)
and kernel-TLB `build/rpi5/bl33-probe-2gkl7iy6/probe.bin` (SHA-256
`51270e3f2fafe017cfbd2cc2fc53961b5017427dd0c8ec143921d910d678e0de`)
images. Both passed native/container comparison. Alongside the user-TLB and
inventory images, these are a coherent host-validated set, not board results.

The combined qualification now has a raw-capture checker at
`tools/rpi5/check_gate3_qualification.py`. It composes exact named XNUPOST,
concurrency, kernel-TLB, user-TLB and timed-soak checks and requires the
qualification sequence exactly once, in order, within the first XNU boot.
Synthetic reordered, cross-boot, failing and missing-case captures are rejected;
44 targeted host tests pass. This checker does not replace selected-case
applicability review, image-hash provenance, or the separate 20 physical cold
boots. No combined qualification capture exists yet.

A source-order review of `bsd_init.c` established that the XNUPOST aggregate
prints its summary before its timing record. The combined checker now enforces
that actual order, keeps all `[KTEST]` records before the summary, and requires
each trial's detail and timing lines within its own start/PASS interval. Its
synthetic reversed-order and out-of-stage cases are rejected; 45 targeted
host tests pass. This remains a host-side verifier, not board evidence.

The user-ASID trial's temporary `pmap_switch()` was reviewed against the
non-monitor `pmap_switch_internal()` path. That path can locally invalidate on
software-ASID collision, shared-region change, or mixed-page-size commpage
change; an unobserved flush at each switch would make a stale-translation
trial falsely pass. A BCM2712 DEVELOPMENT-only per-CPU witness now counts
those switch-induced TLBI paths. After the initial warmup observation, each
reader rejects any locally flushed switch before testing `AT S1E0R`. This can
conservatively fail if unrelated scheduling changes pmap state, but a PASS
cannot be explained by those counted local switch flushes. Provider-enabled
build `build/rpi5-xcode27/run-kjrzeokp/manifest.json` linked with unchanged
source; kernel SHA-256 is
`bc60f21116acd3bbc568f1ca5f8d1aef65323a66fbd01d87ca6f9ba0c62103af`.
The refreshed standalone user-TLB image is
`build/rpi5/bl33-probe-msd9e3e5/probe.bin` (SHA-256
`73e8d38513992ff8de2aa5077bf36639c7c876da6193ee8134c6e7a6fbc9b052`).
Native/container comparison passed, but the image is unstaged and unbooted.
The earlier four-image host set embeds the preceding kernel and must not be
misrepresented as this instrumented build.

The other three standalone images were refreshed against the instrumented
kernel SHA above: XNUPOST inventory
`build/rpi5/bl33-probe-49e8e0bk/probe.bin` (SHA-256
`9441952c618f984dd7120deac66ab61c48da95812b82f605da44050ee974e59a`),
four-core concurrency `build/rpi5/bl33-probe-mojmo3m_/probe.bin` (SHA-256
`c47acde73082fb6a2cdc0417b242b013c6c3e52279807c7a50165281144d718d`),
and kernel-TLB `build/rpi5/bl33-probe-ciimi988/probe.bin` (SHA-256
`08de1e1106735539cada107f2ea0c05cfd443103a9f97c0f8cca6bd96b8ff191`).
Their manifests each embed kernel SHA
`bc60f21116acd3bbc568f1ca5f8d1aef65323a66fbd01d87ca6f9ba0c62103af`
and the intended single opt-in flag. All four current images pass native/
container comparison but remain unstaged and unbooted during the active soak.

The old broad-selector board capture
`build/rpi5/serial-capture-mbeksgbi/serial.bin` showed `xnu.vfp_state_test`
thread 0 pass but threads 1-3 fail. Its source wrote those threads' unique
FPCR patterns into Stride[21:20]. Arm's
[FPCR definition](https://documentation-service.arm.com/static/6526e1bd9e189a266cef8412)
places RMode at [23:22] and Stride at [21:20]; Stride has no AArch64 execution
function and may read as zero on this CPU. This is a source-backed explanation
for the pattern, **not** a confirmed board diagnosis. On BCM2712 only, the test
now clears RMode and assigns its four architected values to the four threads,
leaving the upstream pattern unchanged elsewhere. Provider-enabled build
`build/rpi5-xcode27/run-6ikyko6x/manifest.json` linked. The exact-kernel
inventory image `build/rpi5/bl33-probe-vq1xsci1/probe.bin` has SHA-256
`3b148ec398be1988000d4513d1730bb39ebe00a5cfe8c92576f5700c2c57e047`
and embeds kernel SHA-256
`0114dfea843ec022e8a839ed6c28657ba2b4fc689452a2f88e54461d410e3982`.
It passed host native/container validation but remains unstaged. The exact
`vfp_state_test` case still needs a board run and its failure must not be
silently excluded from applicable Gate 3 XNUPOST coverage.

The three current standalone trial images were refreshed against that same
VFP-adjusted kernel SHA: four-core concurrency
`build/rpi5/bl33-probe-78ja4d_e/probe.bin` (SHA-256
`f319a140c0ecf290fc586c6e680b9072ba120245dd26ee1f4938d823f700bef0`),
kernel-TLB `build/rpi5/bl33-probe-zuhv94e9/probe.bin` (SHA-256
`95d38b73523053107916a228f97304f53949420589617fc0db91ab483a5e6dc0`),
and user-ASID TLB `build/rpi5/bl33-probe-xoy08ghw/probe.bin` (SHA-256
`a90beaa9103dea49bb6e29de485c607a7ad834ffafce1b203313946eabb58303`).
All four current images, including inventory `vq1xsci1`, embed kernel SHA
`0114dfea843ec022e8a839ed6c28657ba2b4fc689452a2f88e54461d410e3982`
and pass native/container comparison. None has been staged or booted.

`tools/rpi5/check_gate3_package_set.py` now checks this four-image set as one
unit: actual image and input hashes, same embedded kernel and RAMDisk, exact
exclusive opt-in per role, and no other selected trial or soak flag. The
current set passes; synthetic mixed-kernel, wrong-flag, changed-image,
missing-selector and wrong-manifest-path cases fail. It is host identity
evidence only, not a Pi result.

The 20-cold-boot checker now credits four-core and PID 1 evidence only in the
first `BOOTSYS` segment of each capture. Previously a later warm boot in the
same capture could satisfy the chain; a synthetic regression now rejects that
case while allowing the expected later Linux watchdog-recovery banner. Fifty-
six targeted host tests pass. Physical 5 V removal remains human-reviewed and
no cold-boot attempt has been credited.

The checker additionally rejects byte-identical serial captures reused under
different directory names; a synthetic copied-capture ledger now fails even
when its metadata and per-attempt hash are edited to match. Fifty-seven
targeted host tests pass. This tightens machine chain of custody but cannot
verify physical power removal or omitted attempts.

The soak checker now keeps arm, heartbeat, IPI/cache and timed PASS markers
within one first-boot segment, and requires a later recovery BOOTSYS before
crediting Linux serial. A synthetic reset between arm and PASS is rejected;
the archived 300-second board capture still passes with its actual two-banner
sequence and unchanged raw SHA-256. Fifty-nine targeted host tests pass. The
current preliminary eight-hour capture has not yet finished or been checked.

The final 20-cold-boot streak now has a stricter machine gate: each boot of
the **same combined qualification image** must complete the ordered XNUPOST,
concurrency, kernel-TLB, user-TLB, cross-core invalidation, soak-arm and
`QUALIFICATION:PRE_SOAK_PASS` chain before it counts. The operator can then
remove power for the next cold boot without waiting eight hours; the final
unchanged-image run alone must complete the timed soak. Synthetic boots that
reach PID 1 but lack pre-soak PASS or report incomplete XNUPOST are rejected.
Sixty-one targeted host tests pass. No physical cold boot has been credited.

The kernel-TLB stress trial now checks remote write permission on every
concurrent observation, not just translation. Its 64 remaps alternate
read-only and writable mappings, giving 32 permission downgrades under load;
the standalone capture checker requires the corresponding detail marker.
Provider-enabled native build
`build/rpi5-xcode27/run-74pi15k5/manifest.json` linked, producing kernel
SHA-256 `bebd85f3b15e74e01d8e7139673ecfbe147fc98e77d33ff86389e1f6d9bc4ae3`.
The new exact-kernel host package set is inventory
`build/rpi5/bl33-probe-57ks6q98/probe.bin` (SHA-256
`8deae38b79666519c2b964c8cceafada73fc7c991dbd4d84e0ac960467ed34b9`),
concurrency `build/rpi5/bl33-probe-2twl0pf7/probe.bin` (SHA-256
`5fc01ab036e8cefdcaf83b68ca186c8d54ed40c9f8abdfe05f2990a3875286d0`),
kernel TLB `build/rpi5/bl33-probe-oed998pi/probe.bin` (SHA-256
`50b9b4aa4c074b39ecd240c8eb172ba308cfdc14f746899ecea8c90d72b4e782`),
and user TLB `build/rpi5/bl33-probe-ybhvm4zh/probe.bin` (SHA-256
`418756dd30ff72b1af0f47b60a5762f726fdc22e1545dcc280f9b2807a4cd352`).
The four-package identity check and each native/container comparison pass;
61 targeted host tests pass. The preceding package set is historical and
must not be staged as the current-kernel set. These images remain unstaged
and unbooted while the preliminary soak is running.

The combined-qualification checker now matches the standalone soak checker's
single-character UART interleave tolerance on the `SOAK:ARM SECONDS` line.
It still requires the exact duration and unique ordered marker, and rejects
two inserted characters. A synthetic regression covers both cases; 62
targeted host tests pass. This changes only evidence parsing, not the running
soak image or any Gate 3 runtime result.

The standalone selected-XNUPOST checker now rejects strict suite evidence
assembled across multiple BOOTSYS segments. A synthetic second-boot injection
fails, while the normal first-boot capture passes; 63 targeted host tests
pass. The combined checker already constrained its KTEST records to first
boot, so this closes the same gap in separately bounded suite captures.

The preliminary 28,800-second soak finished in a 29,100.016-second receive-only
capture at `build/rpi5/gate3-soak-20260926/serial.bin` (SHA-256
`448bb99c1c14d42972611c6eca725820ad305a1d8689b8d2ae2f21c7036b5329`).
`check_gate3_soak.py --seconds 28800` passed every check: 479 monotonic
heartbeats, first/last ACKs `2,1,1` and `28742,28741,28741`, IPI/cache
markers, timed PASS, no failure and subsequent Linux serial. SSH confirmed
NVMe root `/dev/nvme0n1p2`; SD `XNU_PROBE` retained the fallback SHA
`dda91fe297e3266ff96b75b29b9821d27892e9647d05dfd4d9d518c29e67849c`.
This is early endurance evidence, not the immutable final Gate 3 exit soak.

The current-kernel XNUPOST inventory image (SHA
`8deae38b79666519c2b964c8cceafada73fc7c991dbd4d84e0ac960467ed34b9`)
booted four CPUs and printed TOC indices 1–34 in
`build/rpi5/gate3-inventory-20260927/serial.bin` (raw SHA-256
`e0dbce8765f1b4d6ed238437374c7429747beb778d5d7670b66b0b0bc611d877`).
Index 23 was `xnu.vfp_state_test`; its separately selected image
`build/rpi5/bl33-probe-y07rn7zv/probe.bin` (SHA
`60bc6abd21aa8a2f11f8c696241e34aa8aa53d60188fb5e3aca6dc7de540bc30`)
passed all eight assertions in
`build/rpi5/gate3-vfp-20260927/serial.bin` (raw SHA-256
`207863423d38a84ed9d8526c7cc2979f8dc6cc623d87b9a56369efce6ba262d0`).
The prior thread-1–3 VFP failure is therefore resolved on this image, subject
to the final same-image suite and soak.

The 1–34 XNUPOST image `build/rpi5/bl33-probe-3kcgp5wh/probe.bin` (SHA
`a618547549ff72796caaa0b9086babc4279efa3f07f559fb0739005071cb96b5`)
ran on the Pi and reported `SELECTED=34 PASSED=34` in
`build/rpi5/gate3-xnupost-full-20260927/serial.bin` (raw SHA-256
`c60f40437a954e2be1fde7524e712832c80ab4b54997d04eaf8b2c1c2b169d61`),
with 6.699 seconds of XNUPOST timing and no runtime failure marker. The
named-case checker passes all 34 when given the one exact, source-reviewed
`xnu.vm_tests` MTE subtest skip. Without that explicit exception it
conservatively fails, because the case logged one `TESTSKIP` despite an overall
PASS. The checker and combined-run checker now accept only exact named skip
messages; two added regression tests bring the targeted host suite to 65.
All three board runs returned to NVMe Linux, and the SD fallback was restored
and hash-checked after each. At this checkpoint standalone concurrency,
kernel/user TLB and the combined final image were still untested on this kernel.

The subsequent standalone board trials all passed on that exact kernel:

| Trial | Image SHA-256 | Raw serial capture and SHA-256 | Board detail |
| --- | --- | --- | --- |
| Four-core concurrency | `5fc01ab036e8cefdcaf83b68ca186c8d54ed40c9f8abdfe05f2990a3875286d0` | `build/rpi5/gate3-concurrency-20260927/serial.bin` — `cce513f5f1367023728d3239831e6b6a3c0b76362f690e035c66c82335fb13ec` | CPUs 0–3, 4,000,000 operations, overlap 1; PASS in 0.18373 s |
| Kernel TLB | `50b9b4aa4c074b39ecd240c8eb172ba308cfdc14f746899ecea8c90d72b4e782` | `build/rpi5/gate3-kernel-tlb-20260927/serial.bin` — `e2d428970d7484bc7cd2f24b00ed1f31eb4f3b67bb762dec2029e3e76575eb00` | 16 remaps, 8 permission rounds, 64 stress remaps, 32 stress permission rounds on CPUs 1–3; PASS in 0.19407 s |
| User-ASID TLB | `418756dd30ff72b1af0f47b60a5762f726fdc22e1545dcc280f9b2807a4cd352` | `build/rpi5/gate3-user-tlb-20260927/serial.bin` — `0f386465045caa8056eca963306345cd1452620e9657739242c13a20dedc3f2a` | 64 remap rounds on CPUs 1–3; PASS in 0.06409 s |

Each trial passed its strict `check_gate3_trials.py` mode and returned to
NVMe Linux. The SD fallback was restored, hash-checked and unmounted after
each. The concurrency capture's first intact PID 1 tick followed its very
fast PASS in the same XNU boot; the checker now correctly accepts that order
while still rejecting evidence from a later BOOTSYS. Sixty-five targeted host
tests pass.

The combined 1–34 qualification candidate is
`build/rpi5/bl33-probe-c9pktv1a/probe.bin` (SHA-256
`f3d01913e9eea7c1e15f6c874f66a5b688ef31ff3871ca70e14c1ef8b339e75e`).
It uses the same kernel and RAMDisk as the board-passing standalone packages;
its native Mach-O/container comparison passed. It has **not** been staged or
booted. It will run the selected suite and three trials sequentially, then
arm an eight-hour soak. No physical 5 V-off cold boot of this image has been
credited, and no final unchanged-image soak has begun. The next transition
needs a power-off method that can be observed and recorded for 20 consecutive
same-image boots; a reboot or watchdog reset does not qualify.

The combined checker now supports `--pre-soak-only`, so each short cold-boot
capture can be checked against the complete ordered suite/trial/pre-soak chain
before another 5 V-off cycle. It deliberately rejects a timed `SOAK:PASS` in
that mode; it neither credits eight hours nor proves physical power removal.
The 34 exact TOC names are recorded in
`tools/rpi5/gate3_selected_cases.txt` and consumed via
`--require-case-file`, alongside the one exact VM MTE-only skip exception.
Sixty-eight targeted host checks and `git diff --check` pass. No combined
image boot or cold-boot attempt is claimed by these host-only changes.

The cold-boot ledger checker now invokes the same strict 34-name pre-soak
inspection for *each* capture. An aggregate `SELECTED=34 PASSED=34` line
cannot hide an omitted or renamed case, missing workload details/timings, or
an unapproved skip. A synthetic ledger with a renamed VFP case and unchanged
aggregate now fails. Physical 5 V removal remains independently reviewed;
the machine checker does not infer it from serial. The targeted suite now has
69 passing host tests.

The first **combined** image boot used
`build/rpi5/bl33-probe-c9pktv1a/probe.bin` (SHA-256
`f3d01913e9eea7c1e15f6c874f66a5b688ef31ff3871ca70e14c1ef8b339e75e`).
The 4090's receive-only 300-second capture is
`build/rpi5/gate3-combined-cold-01-20260927/serial.bin` (raw SHA-256
`45d2b65122301becc070fb25e02ad10721cb50d2f1808e896a0f89c7e7420721`,
278731 bytes; matching finished `state.json`). A true 5 V removal was performed
by the operator, but this run is **not credited** to the required 20-pass
cold-boot streak. It reported XNUPOST `SELECTED=34 PASSED=34`, then separate
concurrency, kernel-TLB and user-TLB PASS, cross-core invalidation PASS, soak
arm and `QUALIFICATION:PRE_SOAK_PASS`. The strict checker correctly failed:
the first `QUALIFICATION:START` was byte-interleaved with PID 1's `OK`, the
kernel-TLB PASS printed after the next stage's START, and most importantly the
subsequent soak emitted `CACHE_VIS:FAIL ROUNDS=64 ERRORS=0`. Its raw capture
must remain diagnostic evidence rather than be normalized into a PASS.

Source inspection found a concrete one-shot IPI reporting race: the timer
path could observe the 64th ACK after its response-validation load, set
`all_acked`, and print `CACHE_VIS:FAIL` with zero errors because the 64th
response had not yet been checked. The source now waits for at least 64
*verified* responses before its initial cache result. It also initializes the
new delayed soak callout's liveness baseline at arm time and publishes each
trial's terminal status only after logging its PASS/FAIL, preventing the next
stage from printing before the prior result. A 250 ms gap after XNUPOST gives
PID 1's first console line time to finish before the first stage marker.
These fixes require a fresh image and a new board capture; they do not
retroactively validate this run or establish an eight-hour soak.

The revised native build `build/rpi5-xcode27/run-8ksyiakb/manifest.json`
linked with kernel SHA-256
`564aa144bc3c50f7e7a231c8c2a32e164885603182e983048a5d2ba4bc3c300f`.
The replacement combined image is
`build/rpi5/bl33-probe-ci45m9zs/probe.bin` (SHA-256
`454906aa802f013549ef936a9d15bcc42b10638ed73d6759a276797737b1d06c`),
using the unchanged PID 1 RAMDisk SHA-256
`0791e8414193094d1ac7e68959a929ebc17af948beeb6daee11ed0ce766e1236`.
The native Mach-O/container comparison passed; the SD fallback backup stayed
at SHA-256 `dda91fe297e3266ff96b75b29b9821d27892e9647d05dfd4d9d518c29e67849c`.

Its first board capture,
`build/rpi5/gate3-combined-cold-02-20260927/serial.bin` (raw SHA-256
`28fd36c682d0ed9253d197033d89cc45ead3249e22e428634d2f4abfcad1bcb9`),
finished after 300 seconds with matching recorder state. The strict
`--pre-soak-only` 34-case checker passed every ordered check. XNUPOST took
6.696 s, concurrency 0.166 s, kernel TLB 0.147 s, user TLB 0.010 s; the
first cache-visibility result was `PASS ROUNDS=64 ERRORS=0`. This proves the
revised integrated pre-soak path on the board but is not the final eight-hour
run. Its power-cycle timestamps were not captured conservatively, so it is
not credited toward the 20-boot streak.

The first *formal* power-off attempt is captured in
`build/rpi5/gate3-streak-01-20260927/{serial.bin,state.json}` (raw SHA-256
`5d380afc87d4920bd323f57f8c02a27c3c09d7bb8cfcb7a020afd13165fb9511`,
240 seconds, 279141 bytes). The operator reported USB-C power unplugged,
the agent waited 12 seconds before instructing reconnection, and the operator
confirmed reconnection. Conservative confirmation/instruction timestamps and
the independent-power-review caveat are in
`build/rpi5/gate3-cold-boots-20260927/ledger.json`. The raw capture passes
the exact 34-case ordered pre-soak checker and includes cache-visibility PASS
with no runtime failure. The ledger checker reports one machine-passing
attempt and ending streak 1; the full 20-boot requirement remains open, and
physical 5 V absence is still subject to human review. Seventy-two targeted
host checks and `git diff --check` pass.

Formal power-off attempt 2 used the same revised image and is preserved in
`build/rpi5/gate3-streak-02-20260927/{serial.bin,state.json}` (240-second raw
SHA-256 `2df41f1486d7ce07d884f3e9931dd6f5b575e740cd6f786ee2b4bf9bab1b091a`).
The operator confirmed unplugging; the agent waited 12 seconds and allowed
reconnection only after a conservative 21-second confirmation-to-instruction
interval. A fresh BOOTSYS banner proves subsequent restoration. All seven
strict 34-case pre-soak checks passed, with cache-visibility PASS and no
runtime FAIL. The same-image ledger now contains two machine-passing attempts
and ending streak 2; the separate physical-power review and remaining 18
boots are still open.

Formal power-off attempt 3 used the unchanged revised image and is preserved
in `build/rpi5/gate3-streak-03-20260927/{serial.bin,state.json}` (240-second
raw SHA-256 `f07234fe387f420ab47b23fec0f831bbb8d570e683f88cbe8f7d4f795d474131`,
276767 bytes). The operator confirmed the USB-C supply remained unplugged
from at least 15:33:05Z through 15:33:46Z, then restored power and started
the Pi. A new BOOTSYS banner, all 34 named XNUPOST results, three ordered
workload PASS markers, cache-visibility PASS and live PID 1 are in the raw
capture. The strict pre-soak checker passed all seven checks with no runtime
FAIL. The ledger reports three machine-passing same-image attempts, ending
streak 3, and still marks physical 5 V evidence for human review. Its overall
20-boot result is correctly false; `sd_image_sha256_after` remains unset.

At the operator's request, stop manual power cycles here and proceed to the
interactive serial-terminal milestone. The 17 remaining cold boots and final
unchanged-image eight-hour soak remain outstanding; the prior preliminary
eight-hour soak used a different image. This is a development-sequencing
decision, not a formal Gate 3 exit claim.

On 2026-09-27 at about 15:58Z, while attempt 3's same image was still
running, a separate receive-only recorder began on the 4090 host as PID
77461, writing `/tmp/xnu-gate3-soak-tail-20260927/{serial.bin,state.json}`.
The process was verified live and the raw capture grew from 1240 to 4446
bytes with fresh PID 1 ticks. An hourly quiet follow-up checks for the
recorder's terminal result. This recorder started about 25 minutes after the
boot, so it cannot supply an uninterrupted external eight-hour transcript;
even a later `SOAK:PASS` marker must be reported with that limitation.
The strict full-soak checker requires the first boot banner, arm marker,
near-zero initial acknowledgements, and a complete capture; this tail cannot
pass it. A separate `check_gate3_soak.py --tail-only` mode now checks the
late-start transcript's hash, duration, monotonic bounded heartbeats, absence
of reset/failure before PASS, and the timed PASS marker. Its result is named
`tail_support_pass` and explicitly keeps `formal_soak_exit_proven=false`.

The operator then chose to stop this non-qualifying tail run so the 4090 host
could be rebooted and development could move to the interactive-terminal
trial. The receive-only recorder was interrupted at 18:46:20Z after 2h47m;
its final raw capture and state are preserved in
`build/rpi5/gate3-partial-tail-20260927/`. The copied 317,736-byte raw file
matches the recorder's SHA-256
`5e484bc5d29bbfeed5a14dc98516fd75badd1454c567b2f3c57203678da12b4c`.
The recorder's `status=failed` reflects intentional SIGINT interruption (the
script still wrote final metadata); it is not evidence of an XNU soak failure.
No `SOAK:PASS` or formal eight-hour exit is claimed from this partial run.
The hourly soak follow-up was stopped as a soak monitor and repurposed to
wait quietly for the 4090 and Pi's NVMe Linux fallback, then resume the
guarded interactive-terminal trial. It does not restart or repeat the soak.

At 23:59:58Z–00:01:08Z, after moving the Debug Probe USB cable to the
MacBook, a 70-second receive-only capture was preserved in
`build/rpi5/mac-soak-transition-20260927/`. It contains live PID 1 ticks and
`SOAK:HEARTBEAT ACKS=484,484,484`, whereas the same image had reached
ACKS=2944 at 16:23Z. This reset of the monotonic ACK count is evidence that
the Pi rebooted the SD XNU image again rather than staying in NVMe Linux;
the expected automatic fallback with the SD inserted was an incorrect
assumption. No boot banner was captured during this 70-second interval, so
the precise reset instant and preceding `SOAK:PASS` remain unobserved. The
Pi cannot be staged remotely while XNU is running; a controlled power-off,
SD removal, NVMe Linux boot, and SD reinsertion are needed for the terminal
transition. Do not remove the SD while the Pi is powered on.

The operator performed that transition on 2026-09-28. The Pi's Linux root
was verified as `/dev/nvme0n1p2`, the reinserted card as `/dev/mmcblk0p1`
labelled `XNU_PROBE`, its Gate 3 `probe.bin` as SHA-256
`454906aa802f013549ef936a9d15bcc42b10638ed73d6759a276797737b1d06c`, and
its original fallback as
`dda91fe297e3266ff96b75b29b9821d27892e9647d05dfd4d9d518c29e67849c`.
The full Gate 3 image was copied to
NVMe and retained on the SD as `probe.gate3-20260927.bin`. The separate
terminal package passed all 12 host preflight checks, transferred to NVMe,
and was staged as SD `probe.bin` at SHA-256
`e01a90bb18b1210661ac26398b55a144956faeb8570b971cbdfbf0ae0f23b48f`;
the SD was remounted read-only before the Pi reboot.

The first marker-guarded Mac trial is
`build/rpi5/mac-terminal-trial-20260928/` (64,071 raw bytes, SHA-256
`5f5cb7e7bccb2d8b8cfe1a152f6cae44557fdb0a22fb2b8d98f3b5db92ca3c8e`).
It captured the terminal loader's UART binding marker, XNU's `Serial
keyboard started`, CPU online mask `0xf`, and text from PID 1, but concurrent
CPU UART writes tore the one-time banner and prompt. The old strict banner
guard timed out after transmitting **zero** bytes. The watchdog returned the
Pi to NVMe Linux. This is not a usable terminal pass or a Gate 3 result.

The trial guard was revised to require the terminal-only loader marker and
keyboard marker, then recover a clean prompt with a bounded echo command if
the first banner was torn; seven focused host tests passed. A second Mac
attempt, `build/rpi5/mac-terminal-trial-retry-20260928/`, captured **zero**
bytes and transmitted zero. macOS blocked for over a minute inside the serial
`tcsetattr` ioctl before the tool reported ready. A normal Linux reboot
returned directly to NVMe; an official one-shot `vcmailbox` reboot-order
request of `0xf61` then caused SSH to disappear and return later to NVMe,
but the Mac capture still contained no boot output, so the intervening boot
path cannot be proven from serial. The Pi and staged SD image remained
intact. The immediate next step is to re-enumerate the Debug Probe USB on the
Mac and confirm receive-only serial traffic before another board trial.
