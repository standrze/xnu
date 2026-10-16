# Darwin container workstream status

## Packaged VM-backed workloads complete (2026-10-12)

Runtime/package version 0.3.0 implements the user-directed goal without adding
broader userland work. A declared entrypoint, literal arguments/environment/cwd
and read-only `/app` payload run under our source-built XNU kernel and official
Apple-source zsh, in one exclusive VM per invocation. Named HFS+ volumes, exact
separate logs, status, managed stop and nonzero exits are integrated.

Five short real VM runs proved fresh boot entropy, offline/no-NIC startup,
persistence, exit 7, cancellation/cleanup/actual stop and two overlapping VMs
with independent data. A concurrent writable-volume attachment was rejected.
One additional NAT package run proved explicit DHCP setup and an independent
disposable disk. Six focused native controls passed; no soak or full suite was
added. [Usage](WORKLOADS.md) and [rechecked evidence](results/2026-10-12-packaged-workloads/verification.json).

The first offline trial exposed an unconditional NIC requirement in the VM-only
platform driver. A separate kernel build now allows an absent NIC while still
rejecting a present invalid device. The workspace 0.2.0 package/kernel and all
earlier images remain unchanged. An initial build-path provenance failure and
example-script failure are retained, not counted as passing trials.

This is a local Darwin package/VM runner, not OCI/Docker compatibility, a Linux
or Intel host port, a complete macOS runtime, or hostile-tenant isolation.
The qualified profile remains one vCPU, 512 MiB VM RAM, 320 MiB kernel arena,
32 RAM-root nodes, an 8 MiB root, EOF stdin and a 1 MiB combined output cap.
Broader Apple-source userland was deliberately not pursued for this goal.

## Persistent workspace complete (2026-10-12)

The latest PTY/network capabilities are now integrated into a normal named
workspace launcher. Two actual launches proved automatic DHCP, real Apple-source
zsh, a foreground interrupt, host-witnessed DNS/TCP, same-name locking, saved
files/history across a clean restart and different per-boot entropy. An independent
workspace disk remained unchanged. The new isolated VM kernel fixes the inherited
seed-buffer clearing size; earlier kernels and workload 0.1.0 remain preserved.
[Launch and evidence](WORKSPACE.md). No soak or repeated GPU campaign was added.

## Completed follow-on endpoint: terminal, network and shared GPU (2026-10-12)

The documented three-capability goal is **complete for the experimental VM
profile**, separate from the completed frozen `0.1.0` workload package below.
[The final requirement audit](COMPLETION-AUDIT.md) checks actual guest/host
evidence and exact latest-artifact carryover. Full macOS services, lease renewal,
arbitrary Metal and production readiness remain future work, not completion
claims. The chronological progress notes below are superseded where they say
the goal remains active. The terminal milestone now passes in the real XNU
guest: controlling PTY, Apple-source ZLE editing/history, Ctrl-Z/jobs/fg, Ctrl-C
status 130, host resize through XNU SIGWINCH, high-bit input/output roundtrip,
and normal HFS+ unmount/poweroff. A subsequent boot loaded the saved file and
real zsh history. Six focused framing/raw-mode/write-queue checks passed.
This is experimental terminal support, not Unicode/compctl completeness or
production isolation. [Terminal protocol and limits](userland/TERMINAL-PROTOCOL.md).

The distinct network image now passes an actual guest en0/DHCP/DNS/TCP trial:
real XNU ifnet/IP/UDP/TCP, a DHCP lease/default route, and a nonce-bound DNS A
lookup/TCP echo independently witnessed on the host NAT interface. All PTY
checks passed in that same boot, followed by clean unmount/poweroff.
This uses project bootstrap `netctl`, not Apple ipconfig or Libresolv; pinned
Apple network userland integration remains required. No general internet,
IPv6, lease renewal or production network qualification is claimed.
[Network evidence](results/2026-10-12-network/verification.json) and
[implementation/launch limits](userland/NETWORK.md).

A typed guest shared-GPU bridge now passed actual execution: two fresh vectors
were submitted from Darwin, computed on host Metal (Apple M5 Max), returned to
the guest and verified there. Unsupported operations returned an explicit error.
Four focused host protocol/quota checks passed. This is bounded float32 vector
addition, not an arbitrary Metal ABI, accelerated desktop or GPU passthrough.
[GPU contract and launch](userland/SHARED-GPU.md).

A subsequent combined boot also executed unmodified, pinned Apple
`libresolv-96` DNS wire-name/record parsing code. Its native fixture rejected
truncated, looping, out-of-range and wrong-ID responses. Full Apple resolver and
network configuration userland still remain; this does not relabel the selected
parser as macOS DNS services. The goal stays active.
[Latest combined evidence](results/2026-10-12-apple-network-gpu/verification.json).
A later boot supersedes the parser-only limit: standalone original Apple
`res_ninit` file configuration and `res_nquery`/`res_nsend` completed both UDP
and TCP DNS A queries, independently witnessed with a fresh nonce. All prior
terminal/network/shared-Metal checks passed in that same boot and it shut down
cleanly. The verified source rebuild produced the identical executable; no
installed host runtime is linked. Project numeric-IPv4 address packaging and
unavailable service adapters remain explicitly labeled. Full Apple Libinfo
and address/DHCP userland integration are still outstanding, so the goal stays
active. [Resolver source/runtime limits](userland/APPLE-RESOLVER.md) and
[latest preserved evidence](results/2026-10-12-apple-resolver/verification.json).

The latest opt-in executable now also runs original Apple Libinfo public
`getaddrinfo` and interface enumeration. Numeric IPv4/IPv6 validation/errors,
en0 name/index roundtrip, a fresh hostname lookup and TCP through the returned
sockaddr passed in one actual boot, along with all PTY and shared-Metal checks.
No host runtime is linked. The direct-unicast module binding and single-thread
capability adapters remain explicitly project code, not macOS DNS services.
Apple address/DHCP userland is still outstanding; the goal remains active.
[Latest Libinfo evidence](results/2026-10-12-apple-libinfo/verification.json).

The newest opt-in configuration executable now uses original Apple
`bootp-268.1` DHCP option/match/BPF/checksum and IPv4 interface routines. One
short VM boot acquired and installed a lease, wrote DHCP DNS configuration,
completed a fresh independently witnessed guest DNS/TCP exchange and shut down
cleanly. Project bounded orchestration, input guard and route adapter remain;
this is not the full Apple DHCP daemon or lease renewal. No unchanged PTY/GPU
proof was repeated. [Source boundary and next step](userland/APPLE-BOOTP.md) and
[configuration evidence](results/2026-10-12-apple-bootp/verification.json).

Original Apple `network_cmds-396.6` route is now source-built and guest-proven:
delete/add/get of the real default route reported its gateway/en0, followed by
fresh independently witnessed DNS/TCP traffic and clean shutdown. The command
source is unchanged; argv/key-storage ABI glue remains labeled project code.
One focused new ABI check passed; no PTY/GPU proof or soak was repeated.
The full configuration/lease services remain unfinished.
[Route evidence](results/2026-10-12-apple-route/verification.json).

Original Apple ifconfig and all nine published command modules are now also
source-built. One short VM boot changed/read back MTU 1400, restored/read back
1500 and displayed the leased en0 IPv4 address. Route inspection and fresh
host-witnessed DNS/TCP passed afterward, followed by clean shutdown. A linked
image check verifies the original module constructor pointers used by project
static startup. No unchanged native/PTY/GPU proof or soak repeated. Compiled
device modules are not blanket device/private-ioctl or IPv6 qualification.
[Latest ifconfig evidence](results/2026-10-12-apple-ifconfig/verification.json).
Remaining macOS service dependencies and full lease lifecycle are future work.
They are not claimed by the completed PTY/network/shared-compute endpoint.

The Pi, frozen `0.1.0` and earlier terminal/network checkpoints are unchanged.
[Sequence and exact remaining work](INTERACTIVE-NETWORK-GPU.md).
[Preserved terminal milestone](results/2026-10-12-framed-terminal/verification.json).

## Workload environment achieved (2026-10-12)

The requested three-part milestone is complete for the narrow experimental VM
profile: managed real Apple-source zsh; writable HFS+ files, scripts and shell
history across clean VM restarts; and a private versioned `0.1.0` package with a
straightforward launcher. [Launch instructions and scope](userland/WORKLOAD.md).
[Preserved evidence](results/2026-10-12-workload/verification.json).

The packaged launcher ran zsh 5.9, read the saved file, executed the saved script,
and read the history saved by the preceding interactive VM's normal `exit`.
It captured exit 0 with both stream EOFs and verified cleanup, acknowledged
shutdown and actual guest stop. The interactive trial separately loaded the
earlier history and unmounted HFS+ before poweroff. No power-loss durability,
full PTY, networking, GPU, complete LibSystem/OCI or production isolation is
claimed. Images contain private entropy and retain the seed-reuse limitation.

Managed Apple-source zsh integration is now boot-proven: command 1 printed
`MANAGED_ZSH:5.9`, evaluated arrays/arithmetic, ran `/bin/uname`, and emitted
separate stderr. Command 2 returned 7; the agent captured that status and the
CLI correctly returned 7 after acknowledged guest shutdown. Both commands had
verified cleanup and stream EOFs. See [the preserved focused trial](results/2026-10-12-managed-zsh/verification.json).
The known-working interactive image and earlier DC3 evidence remain unchanged.

The optional host RAW data disk is separate from the read-only EFI disk.
The distinct VM-only VirtIO block driver and pinned Apple HFS+/IOStorageFamily
provider are now linked and boot-proven. Three focused host preflight checks
passed; failed runtime attempts and their fixes are preserved in the report.
No new soak or broad test campaign was added. The prior interactive/DC3 artifacts
and frozen CLI remain unchanged.
No physical Pi inputs, installed container services, or GPU features are involved.

## Earlier outcome: real Apple-source zsh prompt achieved (2026-10-12)

The dedicated XNU VM booted source-built Apple zsh 5.9, printed its real version,
evaluated arrays/arithmetic, executed `/bin/uname`, returned to the prompt, and
powered off cleanly. A static no-import image, exact archive/build provenance,
raw serial and repeatable launch are preserved in [the milestone](userland/ZSH-TRIAL.md).
No new soak or broad campaign was run. Pi deployment and the full DC4 workload
scope remain separate. The DC3 results and limitations below describe that
earlier managed-agent image, which was not replaced.

## Earlier DC3 outcome: passed, narrow managed-command target (2026-10-12)

**User-directed next step:** stop broad/repeated testing and speedrun a real
Apple-source zsh using the smallest necessary source-built runtime dependencies.
One build/boot smoke check is the handoff bar; do not add new soak gates.

The opt-in managed Darwin guest agent now runs real source-built commands under
our XNU kernel in disposable Apple-silicon VZ VMs. Parallel guest/host work and
independent review produced the [wire contract](agent/PROTOCOL.md),
[golden frames](agent/wire-vectors.json), separate binary streams, direct argv,
ordered commands, bounded cancellation/descendant cleanup and shutdown.
The [recheckable final report](results/2026-10-12-dc3-verification.json) records
the final inputs and fresh-image trials. This is not OCI or production isolation.

| Actual final-kernel trial | Result |
| --- | --- |
| All 256 byte values on each stream, then a second command | Exact binary files, both exit 0, actual guest stop |
| `false`; direct missing executable | Status 1 and 127 respectively; neither reported success |
| Public API task cancellation, TERM-blocked leader and `setsid` descendant | Accepted ACK, leader signal 9, both EOFs, cleanup verified, actual stop in 2.39 s |
| Leader exits with escaped orphan still holding pipes | Orphan cleaned before terminal record and next command; both commands exit 0 |
| Overall deadline with TERM-blocked workload | Timeout preserved as failure; acknowledged cleanup and actual stop |
| 2 MiB flood, repeated twice | Exactly 1 MiB retained, truncation flagged, next command not started, cleanup and actual stop |
| Managed runner against non-agent shell image | No managed command sent; bounded host-stop fallback in 6.12 s, no false success or guest-initiated-stop claim |
| Legacy shell + timer-driven sleep | Exit 0 and actual stop; original default shell RAM root remains byte-identical |

Final kernel SHA-256: `b3a0d9f49e2af4bfe28ac716111b05a030d1c8fb273c1e4ffe103e2a36582d53`.
Managed RAM-root SHA-256: `42804e015930e1af5b0e6ba1341813a754dbe5351b893c4efcc4104f8ad7e342`.
Raw serial, separate output, lifecycle records, loader hashes and independent
audits are preserved in the report's linked directories. Firmware variables,
private EFI payloads and seed material are deliberately not copied into results.

Focused native checks: 42 host-library tests, 14 CLI tests, 18 userland tests
(ASan/UBSan adapters), four independent-auditor controls, three VM IRQ/overlay
regressions, and 768 harness observer checks. Native mocks are not VM evidence.
Run `python3 experiments/darwin-container/agent/verify_matrix.py` to recheck the
preserved final matrix without starting a VM. Host build/test logs and the guest
source/ABI manifest are under `evidence/dc3-*`.

Two real failures were retained, not erased from the record:

- [Initial flood](results/2026-10-12-dc3-cap-failed-timer/) panicked because the
  VM IRQ handler assumed an acknowledged timer request always still had its
  timer-status bit set. A VM-only correction tolerates stale PPI27, services
  only a currently pending timer and synchronizes timer rearm before EOI.
  Unexpected real IRQs still panic. The corrected kernel passed both flood
  repetitions and all final trials. Pi source/build outputs were not changed.
- [Initial API-cancel harness](results/2026-10-12-dc3-api-cancel-harness-timing-failed/)
  failed to detect CRLF STARTED lines, so the overall deadline—not API task
  cancellation—ended that trial. Byte-based observation fixed the harness;
  the final API trial then passed. The production protocol parser was unaffected.

No managed stdin, PTY, network, persistent disk, zsh, LibSystem or hostile-root
authentication is claimed. Per-image entropy and the inherited kernel seed-clear
defect remain hardening limitations. The intended next userland must use pinned
official Apple-source implementations, including zsh, under the PRD's source
requirements; this bootstrap is not their replacement. All fork implementation
changes remain local/uncommitted and unpushed. No installed container services,
Pi media, serial readers or power were touched.

## Earlier DC2 outcome (2026-10-12 UTC)

**DC0, DC1 and DC2 passed for the narrow experimental Apple-silicon VM target.**
The fork's `container darwin run` booted our source-built XNU VZGENERIC kernel,
mounted its source-built RAM root, executed
`uname -a && cat /etc/motd && sleep 1 && echo timer-ok`, captured the fresh
nonce's exit status 0, and observed a clean guest-requested shutdown. The full
session took 1.375 seconds. [Successful trial](results/2026-10-12-xnu-trial-7/)
preserves the serial capture, host result and exact loader/input hashes.
A second fresh image ran `false`, preserved exit status 1, shut down cleanly,
and correctly returned CLI status 1 rather than claiming command success.
[Negative control](results/2026-10-12-xnu-trial-8/) took 0.358 seconds.

This is `container darwin run`, not ordinary `container run` or a Darwin OCI
runtime. It uses Virtualization.framework, not QEMU. One CPU, 512 MiB VM RAM,
320 MiB kernel-managed RAM, read-only RAM root and polled serial are qualified
only by these bounded trials. No zsh, LibSystem, proprietary macOS services,
networking, persistent guest disk, full PTY or production isolation is claimed.
Per-build entropy and the inherited seed-clear issue are explicit hardening
limitations; see [kernel notes](kernel/README.md) and [scope](README.md).

## Diagnostic history (earlier failures, superseded by trials 7–8)

Measured ACPI, memory and PCI inventory is preserved in
`efi-probe/results/2026-10-12-platform/`. The firmware exposes GICv3, HVC PSCI,
and a modern virtio PCI console, but no firmware Serial I/O protocol.
The local fork's bounded `container darwin run` runner is built and tested.
A separate VZGENERIC XNU snapshot completed `make all`, with no undefined
symbols and no linked Pi UART/watchdog/secondary-start implementation. The
source-built VM bootstrap userland and RAM root build reproducibly; five native
tests passed. Neither build alone proves guest execution. The full source EFI
handoff now reaches XNU and its bootstrap shell. The native virtio console passed an actual VM run after
ExitBootServices and disabling the firmware MMU/cache, followed by clean HVC
PSCI shutdown. [Captured serial and result](results/2026-10-12-native-console/)
contain 113 serial bytes; no shell marker was emitted or claimed.
The first full XNU trial reached the loader's final handoff marker (boot args
`0x72000000`, entry `0x714a3488`, managed arena `0x70000000`/320 MiB), then timed
out after 45 seconds without kernel serial output. [Preserved failed trial](results/2026-10-12-xnu-trial-1/)
contains 177 serial bytes. No command was sent and no shell was claimed.
The second diagnostic trial captured `XDAZPM`: source-built XNU executed its
entry, debug unlock, argument reads and bootstrap page-table setup through the
last pre-MMU checkpoint. It then timed out without a shell.
[Preserved second trial](results/2026-10-12-xnu-trial-2/) is partial kernel-entry
evidence, not completed startup. Next: trace the MMU transition and early C
initialization, then execute a RAM-root command. **DC2 remains unproven.**

The third trial captured `XDAZPMVCISTBDELHKW`, confirming the MMU transition
and initial C setup through the call to `arm_vm_init`. It timed out after
20 seconds without normal kernel serial output. [Third-trial evidence](results/2026-10-12-xnu-trial-3/)
narrows the next diagnostic to final VM mapping / post-VM serial registration.

The fourth trial reached `arm_vm_physmap_init` and captured an assertion trap:
ESR `0xf200bffc`, ELR `0xfffffe00078d4064`. The exact linked assertion descriptor
identifies the final physical-map extent check, not a compiler bounds failure.
The large-memory configuration reserved no headroom for block-alignment holes;
the VM-only correction reserves the existing non-large-memory policy's bounded
virtual headroom without increasing managed physical RAM or removing the check.
Three focused arithmetic regressions passed, including a reproduced old-budget
failure and every 16-KiB slide offset across a 32-MiB alignment period. The
corrected kernel builds; a fresh VM trial is next.
[Fourth-trial evidence](results/2026-10-12-xnu-trial-4/) is a diagnosed startup
failure, not a shell pass. **DC2 remains unproven.**

The fifth trial booted the corrected kernel through BSD initialization, mounted
the 737,280-byte read-only RAM root, executed PID 1 and started `/bin/sh`.
The capture contains `DARWIN:INIT:READY` and `DARWIN:SHELL:READY`. The host parser
did not recognize the doubled carriage returns produced by guest TTY output
processing, so it correctly withheld all command input and reached its bounded
20-second timeout. [Fifth-trial evidence](results/2026-10-12-xnu-trial-5/)
proves kernel and bootstrap-shell startup, but not command execution or a clean
guest-requested shutdown. The host parser correction and live command test are
next. **DC2 remains unproven.**

The sixth trial recognized the corrected framing and executed
`uname -a && cat /etc/motd && sleep 1 && echo timer-ok` from the RAM root.
It captured the Darwin version, MOTD, `timer-ok` and its fresh nonce's own-line
`EXIT:0`. Thus XNU startup, console input, process execution, file reads and
timer-driven wakeup are now demonstrated. The subsequent `poweroff` exposed a
bootstrap PID-1 bug: XNU's normal shutdown `SIGTERM` killed init, triggering its
mandatory init-exit panic and a VM reset. The host correctly reported timeout
and `commandSucceeded:false`, despite preserving `commandExitStatus:0`.
[Sixth-trial evidence](results/2026-10-12-xnu-trial-6/) establishes real command
execution but not clean lifecycle completion. Fix PID-1 shutdown signal handling;
do not bypass normal shutdown or disable the kernel invariant.

The source-built bootstrap init now blocks SIGTERM only in PID 1, checks the
pending mask before fork/respawn, and quiesces during shutdown. Shell children
restore the saved mask before exec. The actual Darwin syscall implementation's
pointer ABI was checked (not its stale scalar-mask comment). Six ASan/UBSan
native userland tests pass, including four PID-1 control-flow scenarios. The
corrected RAM root is 737,280 bytes, SHA-256
`bdb9d228af349178288e1a88fa39620f3ce87f5e4812b11a31c93465b770225d`.
The kernel remains unchanged at
`a8048424c4fb7c223fb3d90bc52f6bc5fe67aa28d6407f431899471a3b2257c9`.
Trials 7 and 8 subsequently confirmed this correction in the real VM, without
changing the kernel shutdown implementation or its init-exit invariant.

Verified 2026-10-11 America/New_York (EFI run: 2026-10-12 01:47:06 UTC).

The forked CLI's real
preflight separately validates the probe's files; preflight does not boot them.

## Delivered

- Reused the existing `standrze/container` fork without changing its remote work;
  created `standrze/containerization`. Downloaded pinned official Apple source
  into independent sibling checkouts on local `darwin-guest-bootstrap` branches.
- Added `ContainerizationDarwin` with host/resource/file checks and real generic
  EFI Virtualization.framework configuration validation.
- Added `container darwin preflight`, JSON/text reports and focused tests. Invalid
  inputs fail; `bootProven` is always false because this command does not execute
  a guest. The local run script signs its development binary for VZ validation.
- Added a standalone, source-built ARM64 EFI execution probe and bounded Swift
  VM harness. This does not substitute a Linux loader header or use QEMU.
- Added the real source-built EFI handoff, modern virtio console, isolated
  VZGENERIC kernel target and source-built bootstrap RAM root. Actual command
  execution and guest-requested shutdown passed; this is not Apple launchd/zsh.

The implementation changes are **local and uncommitted, not pushed to GitHub**.
The fork URLs exist, but do not yet contain these downstream changes. The nested
checkouts are independently versioned and excluded from the parent XNU index;
preserve both when saving this work. Exact starting revisions are in
[sources.lock.json](sources.lock.json).

## Verification

| Check | Result | Evidence |
| --- | --- | --- |
| Containerization host build, `make containerization` | Passed | `evidence/containerization-build.log` |
| Container CLI build with warnings as errors | Passed | `evidence/container-build.log` |
| Backend focused tests | 15 passed | `evidence/containerization-tests-final.log` |
| CLI focused tests | 8 passed | `evidence/container-tests-final.log` |
| EFI probe unit tests | 5 passed | `evidence/efi-probe-tests-final.log` |
| Actual EFI payload VM run | Passed; nonce matched, guest stopped without VZ error | [Preserved reports](results/2026-10-11-efi-probe/verified.json) |
| Real signed CLI preflight against stopped probe disk/store | Passed; configuration valid, boot not proven | [CLI report](results/2026-10-11-efi-probe/container-preflight.json) |
| Focused Swift formatting, shell syntax, Git whitespace | Passed | Local checks |
| Serial command protocol incl. CRCRLF and echo rejection | 10 passed | `evidence/darwin-serial-crcrlf-tests.log` |
| Source-built userland, ASan/UBSan native tests | 6 passed, including four PID-1 scenarios | `evidence/userland-init-shutdown-tests.log` |
| Physmap-aperture arithmetic regressions | 3 passed | `kernel/test_physmap_aperture.py` |
| Conservative CPU defaults, backend + CLI | 2 + 2 passed | `evidence/darwin-cpu-default-tests.log`, `evidence/container-cpu-default-tests.log` |
| XNU/RAM-root commands + timer wake + clean shutdown | Passed in real VM | [Trial 7](results/2026-10-12-xnu-trial-7/result.json) |
| Command failure status + clean shutdown | Expected exit 1 preserved; CLI exit 1 | [Trial 8](results/2026-10-12-xnu-trial-8/result.json) |

The XCTest host emitted duplicate private UniversalHID class warnings with the
installed SDK; focused tests still passed. Full upstream Linux integration tests
were deliberately not run because they manipulate installed/global services.
Switching the upstream release dependency to our pinned sibling checkout has not
been Linux-runtime regression tested.

## Initial standalone EFI probe evidence (DC1)

The VM used one CPU, 512 MiB RAM and a newly generated 64-MiB GPT/FAT16 disk.
No network, shared directories, physical disks, USB passthrough, Pi access or
long-lived service was configured. The deadline was 30 seconds plus bounded stop
cleanup; the guest completed normally before that deadline.

- Nonce: `ba3e2739ed53491fa63ac4088b60958f`.
- Payload SHA-256: `eb75f68e082bda3eaeb8f93e4e9f6bf887893b68f31644226be050bf3930da65`.
- Blank disk was hash-checked before execution. The payload wrote only its
  preallocated result file, flushed/closed it and requested EFI shutdown.
- Result: EL1, 24-MHz architectural timer, ACPI 2.0 table present, no FDT table,
  23 UEFI memory-map descriptors of 48 bytes each; memory-map retrieval succeeded.
- Empty `serial.log` is not a serial-driver pass. Evidence came from the guest's
  result file and the host's clean-stop callback, not serial output.
- Preflight left both disk and EFI-store SHA-256 values unchanged. Disk:
  `b5b9f8b752ca91cf4675c79ad19f0e055bab5312ab1b7d7eb40a59ee727c21a8`;
  EFI store: `09ef3977e4635c9067c4a1c2a612b59d0ee7df2cea549fe06f8e27ef01f78015`.

Full temporary artifacts remain at `/private/tmp/darwin-efi-probe.4gyTPe`.
Small reports, source/binary hashes and timestamps are copied into
`results/2026-10-11-efi-probe/` so the outcome survives temporary-directory cleanup.
Large disk/binary files and build logs are not included in the parent Git index.

## Completed DC2 sequence

1. Captured actual ACPI tables and memory/PCI/device layout, identifying GICv3,
   virtual timer 27, HVC PSCI and the modern virtio PCI console.
2. Built a distinct, isolated VZGENERIC XNU target; retained the physical Pi path
   and kept its MMIO, affinity and watchdog implementation out of the VM target.
3. Built the EFI Mach-O loader, exclusive RAM ownership, boot args/device tree,
   source-built RAM root and ExitBootServices/MMU transition.
4. Demonstrated console input/output, scheduling and timer wakeup, RAM-root
   process execution, exact success/failure status and normal guest shutdown in
   two bounded VZ trials. No proprietary macOS components were assumed available.

## Next: DC3, managed Darwin command lifecycle

Implement a Darwin guest agent and versioned host/guest transport for output,
exit status, cancellation, command boundaries and shutdown. The nonce-backed
serial proof is deliberately not that managed RPC contract. After DC3, package
versioned Darwin workloads and build selected official Apple libraries from
their published source (DC4). Do not substitute installed macOS binaries or
claim Linux OCI compatibility. Harden entropy and fix the inherited seed-clear
size mismatch before production/security qualification.

No physical Pi, its storage, serial readers or installed container services were
changed in this workstream. No claim of portable non-Mac host support is made.
