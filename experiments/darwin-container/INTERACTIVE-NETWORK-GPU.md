# VM terminal, networking and shared GPU work

Completed documented follow-on endpoint, 2026-10-12. Preserve private workload `0.1.0` and its
qualified XNU/zsh/storage artifacts. Use new opt-in profiles and copied virtual
data disks; no physical Pi access or deployment belongs to this workstream.

The [final requirement audit](COMPLETION-AUDIT.md) verifies the three numbered
capabilities below, including pinned Apple network userland. Historical progress
notes remain below. Full macOS services/lease lifecycle are separate future
work, not claimed implemented or required to repeat these qualified milestones.

Source policy: prefer official Apple open-source drivers, driver families and
libraries wherever applicable; pin revisions, preserve notices and compile from
source. Check hardware/virtual-device and kernel ABI compatibility before reuse.
Keep project device transports and unavailable-service adapters labeled; an
Apple framework is not evidence that the specific device driver is published.
The official [IONetworkingFamily](https://github.com/apple-oss-distributions/IONetworkingFamily),
[IOStorageFamily](https://github.com/apple-oss-distributions/IOStorageFamily),
[IOGraphics](https://github.com/apple-oss-distributions/IOGraphics) and
[IOHIDFamily](https://github.com/apple-oss-distributions/IOHIDFamily) are source
candidates. Storage-family code is already used; the VM VirtIO transport and
typed shared-Metal bridge remain project code, not claimed Apple GPU drivers.

## Sequence and completion evidence

1. **Full terminal.** Use XNU's real PTY driver, a session leader/controlling
   slave tty, host raw input with restoration, byte-preserving transport,
   terminal size changes/SIGWINCH, foreground/background job control and
   Apple's source-built zsh ZLE. Complete only after a guest run proves arrow
   editing/history, Ctrl-C, Ctrl-Z/jobs/fg, resize and normal history save/exit.
   A host PTY test or a serial prompt alone is insufficient.
2. **Networking.** Opt-in VZ VirtIO NIC with NAT, a VM-only VirtIO net transport
   and XNU ifnet attachment, then guest address/route/DNS setup. Reuse the real
   XNU IP/TCP/UDP stack and pinned Apple userland implementations. Complete
   only after guest-originated DNS resolution and TCP exchange with a known
   host fixture; do not relabel a host HTTP proxy as guest networking.
3. **Shared GPU acceleration, not passthrough.** A bounded guest/host request
   channel and typed guest client/library, backed by real host Metal execution.
   Start with a supported compute operation and extend the usable interface.
   Validate lengths/ownership, isolate VM sessions, bound work/resources and
   return explicit unsupported-operation/error results. Complete only after
   guest-submitted work executes on Metal and its result returns to the guest.
   A display framebuffer, a host-only GPU demo or CPU fallback is not proof.
   This does not promise arbitrary Metal applications or a macOS graphics stack.

Keep verification minimal: focused native checks for changed boundaries and
actual guest trials for each new behavior. Repair demonstrated runtime failures;
no soak or broad repeated test campaign is a prerequisite. Do not mark the
overall goal complete while any of these three capabilities remains unproven.

## Current terminal milestone: passed

The new opt-in DGT1 image passed an actual XNU VM trial and a subsequent
persistence boot. Both proved real PTY/job control, Apple ZLE editing/history,
Ctrl-Z/jobs/fg, Ctrl-C status 130, initial 35×120 sizing, host resize to 47×132
through XNU's actual `SIGWINCH`, and a host→guest→host `0x80`/`0xff` byte
roundtrip. The persistence boot read the prior file and real saved zsh history.
Both exited 0, unmounted HFS+ and powered off. Six focused host checks passed;
there was no soak. [Preserved evidence](results/2026-10-12-framed-terminal/verification.json).

The working private snapshot is
`userland/build/terminal-framed-working-2026-10-12/`. Its signed CLI, EFI,
kernel, RAM root, real zsh and copied writable disk are preserved with hashes.
It is not a versioned release; the original `0.1.0` package is unchanged.
[Protocol, launch flags and limitations](userland/TERMINAL-PROTOCOL.md).

This work exposed console receive and host stdout backpressure failures. The
distinct VM kernel now acquires used-ring metadata after observing its index,
recycles empty receive completions and rejects invalid completions instead of
casting them to fake input bytes. One native ring fixture covered empty/binary,
wrap and bounds cases. Host output now retains partial writes in a bounded
queue and has a bounded post-stop drain. Successful trials are limited evidence,
not a formal stability qualification. Failed trials remain in `/private/tmp/`
as `darwin-pty-framed-trial-1` through `-4`; they are not counted as passes.

## Earlier incremental terminal work (superseded above)

- `DarwinHostTerminal` enters raw mode only for TTY stdin and restores original
  flags/attributes on cleanup. Pipes are unchanged. Input uses the existing
  bounded serial queue, preserving short-write/EAGAIN ordering.
- Two native host checks passed: control/escape bytes arrive before newline,
  settings restore (excluding kernel PENDIN bookkeeping), and pipes stay intact.
- New `userland/build.py --mode zsh --storage --pty` profile uses `/dev/ptmx`,
  real grant/unlock/name ioctls, `setsid`, controlling tty and foreground group.
  A bounded nonblocking relay connects the serial console to the PTY master.
- Actual VM trial `/private/tmp/darwin-pty-trial-1` reported
  `PTY_TTY_OK`, `PTY_PATH:/dev/ttys000:/data`, and interrupt status 130; guest
  `exit` unmounted HFS+ and requested poweroff. This proves the basic PTY and
  Ctrl-C path, **not full terminal completion**. The attempted external sleep
  was absent from that minimal root; job control was not enabled in the old zsh.
- The existing source-build probe explicitly selected `--without-tcsetpgrp`,
  setting `BROKEN_TCSETPGRP` and disabling zsh job control. A distinct
  `--terminal` profile now selects `--with-tcsetpgrp` and static Apple ZLE;
  its dependency/build/runtime work remains in progress.
- Still required: line editor, job-control proof, dynamic window sizing and
  byte-preserving transport. The present console masks high bits, so arbitrary
  bytes must use a framed transport or a corrected VM-only console path.

## Subsequent focused results

The separate Apple-source zsh/ZLE image now passed actual guest arrow-key
editing (`ZLE_EDIT`), up-arrow history recall twice, `monitor` enabled,
Ctrl-Z suspension of `/bin/sleep`, `jobs`, `fg` resume and Ctrl-C status 130.
Normal exit unmounted HFS+ and powered off. The prior list of missing line
editor/job-control proof is superseded by this trial; dynamic sizing and
arbitrary-byte transport are still required. It emitted one nonfatal missing
`zsh/compctl` module warning: completion support is not yet linked.
[Preserved partial verification](results/2026-10-12-terminal-increment/verification.json).

## Network smoke milestone: passed; Apple userland integration remains

The explicit `--network-nat` host attachment, VM-only split-ring driver and
real XNU en0 attachment passed actual guest DHCP/address/default-route setup,
DNS A lookup and TCP nonce echo. The host independently witnessed both socket
exchanges on the NAT interface. The same guest passed all PTY checks and clean
unmount/poweroff. This supersedes the earlier host-only configuration result.
[Preserved evidence](results/2026-10-12-network/verification.json).

The private image is `userland/build/network-working-2026-10-12/`.
`netctl` is a project diagnostic, not Apple ipconfig/Libresolv. Integrating
pinned Apple networking userland remains part of the objective. No general
internet, IPv6, lease renewal or network soak is claimed.
[Profile, transport and honest limits](userland/NETWORK.md).

## Shared GPU smoke milestone: passed

The typed guest client, guest-local datagram relay and nonce/sequence-checked
DGT1 GPU channel now reach the real `DarwinMetalCompute` backend. Two fresh
guest vectors returned correct GPU-computed results; independent host evidence
matched the operands/results. Unsupported operation replies and normal teardown
passed in the same boot as networking and all PTY checks. The old host-only
result is superseded. [Shared-GPU evidence](results/2026-10-12-shared-gpu/verification.json).

Only finite float32 vector addition is supported: 16 elements per request,
1024 requests per VM, one outstanding request, bounded capture and a two-second
host completion deadline. Each VM owns a distinct bridge and no public host
listener is opened. No guest pointers/shaders or CPU fallback are accepted.
Four focused protocol/session/quota checks passed; no soak was run.
This is not arbitrary Metal, an accelerated desktop or production isolation.
[Wire/API contract and launch](userland/SHARED-GPU.md).

## Remaining source-userland integration

The subsequent combined image compiled original pinned Apple `libresolv-96`
wire parser sources and actually executed them on the guest DNS response.
The native boundary fixture covered compressed names, every truncation,
compression loops/out-of-range pointers and wrong IDs. The latest image also
passed the shared-GPU and all terminal/network checks.
[Combined evidence](results/2026-10-12-apple-network-gpu/verification.json).
This is genuine Apple source reuse, not full `res_nquery` or configd integration.
The overall goal stays active for the remaining Apple network configuration
and resolver userland work; do not replace that with a host DNS/HTTP proxy.

The original package and frozen CLI are unchanged. The working development CLI
was rebuilt and ad-hoc signed with the existing virtualization entitlement;
it is preserved separately and is not released as `0.1.0`.

## Original Apple unicast resolver milestone: passed

The later standalone resolver executes real Apple `res_ninit` configuration-file
fallback and original query/send/parser code. UDP and TCP DNS A lookups both
passed against an independently observed fresh-name fixture in an actual XNU
boot. That same boot passed all PTY, DHCP/TCP echo and shared-Metal checks, then
saved history, unmounted and powered off; no soak. The provenance-verified
rebuild is byte-identical to the guest executable. A project numeric IPv4
getaddrinfo packaging adapter still remains, as do unsupported service boundaries.
[Evidence](results/2026-10-12-apple-resolver/verification.json) and
[exact original-source/adapter boundary](userland/APPLE-RESOLVER.md).

The goal remains active for real Apple Libinfo and address/DHCP configuration
userland. Do not relabel the project bootstrap or unavailable service adapters
as complete macOS networking infrastructure. The latest private checkpoint is
`userland/build/apple-resolver-working-2026-10-12/`.

## Original Apple Libinfo public lookup milestone: passed

A new opt-in `build_apple_resolver.py --libinfo` executable replaces the numeric
packaging adapter with original Apple Libinfo-542.40.3 `getaddrinfo`, address
validation/packing/sorting, `getnameinfo`, `getifaddrs` and interface-name/index
lookup. Original pinned libplatform inline atomics supply reference counting.
One short XNU boot proved numeric IPv4/IPv6/error handling, real en0 enumeration,
fresh-name DNS and TCP using the returned sockaddr. The host independently saw
three UDP DNS queries, one TCP DNS query and two TCP nonce exchanges. All PTY
and shared-Metal checks passed, with clean unmount/poweroff and no soak.
[Evidence](results/2026-10-12-apple-libinfo/verification.json).

The static module binding to original Apple libresolv is a bounded project
direct-unicast backend, not Apple's macOS search/cache/mDNS service. Notifyd,
configd, libnetwork dynamic loading and unified logging are unavailable;
single-thread once/mutex adapters are not a general pthread implementation.
Numeric IPv6 parsing is not proof of IPv6 connectivity. Apple address/DHCP
configuration userland remains; keep the goal active. Latest private snapshot:
`userland/build/apple-libinfo-working-2026-10-12/`.

## Selected original Apple DHCP/IPv4 routines: passed

The new `build_apple_resolver.py --libinfo --bootp` profile compiles original
`bootp-268.1` option creation/parsing, reply matching, BPF transport/checksum and
IPv4 configuration routines into `/bin/dhcpctl`. A short actual VM trial
acquired/installed its DHCP lease, wrote DNS configuration, completed fresh
host-witnessed guest DNS/TCP traffic and shut down cleanly. Only the changed
configuration boundary was exercised; PTY/GPU proof was not repeated, and no
soak or Pi operation occurred.
[Evidence](results/2026-10-12-apple-bootp/verification.json).

Project DHCP orchestration, parser preflight and default-route acknowledgement
remain labeled adapters. The full Apple daemon, Core Foundation/service closure,
ARP conflict probing and lease renewal are not implemented. The next finite
source-first increment is the original `network_cmds` route/ifconfig command
closure, then the remaining service dependencies. Downloaded source is not
runtime proof. [Exact boundary and reproduction](userland/APPLE-BOOTP.md).
Latest private checkpoint: `userland/build/apple-bootp-working-2026-10-12/`.

## Original Apple route command: passed

The full original `network_cmds-396.6` route source, built with `INET6`, now runs
as `/bin/route`. A short VM trial deleted/recreated the default route, inspected
the actual kernel reply for its gateway/en0 and completed fresh independently
witnessed DNS/TCP traffic afterward. Only numeric IPv4 operations are qualified;
IPv6 connectivity, reverse/network-database service and every subcommand are
not. Original Libinfo thread-data logic uses bounded project single-thread key
storage; one focused host ABI check passed. No PTY/GPU proof or soak repeated.
[Evidence](results/2026-10-12-apple-route/verification.json) and
[source/build/limits](userland/APPLE-BOOTP.md#original-apple-route-command-subsequent-vm-proof).
Latest private checkpoint: `userland/build/apple-route-working-2026-10-12/`.
The subsequent ifconfig increment below supersedes this next-step note.

## Original Apple ifconfig command: passed

The entire original `network_cmds-396.6/ifconfig.tproj` command and nine modules
are source-built. Project static startup invokes the original module constructors;
a linked-image check verifies their actual pointers, not just symbol presence.
One short VM boot changed/read back en0 MTU 1400, restored/read back 1500 and
displayed the leased IPv4 address. Original route inspection and fresh
host-witnessed guest DNS/TCP passed afterward, followed by clean shutdown.
No unchanged native/PTY/GPU proof or soak repeated. No Pi access occurred.
[Evidence](results/2026-10-12-apple-ifconfig/verification.json) and
[source/adapter limits](userland/APPLE-BOOTP.md#original-apple-ifconfig-subsequent-vm-proof).
Latest private checkpoint: `userland/build/apple-ifconfig-working-2026-10-12/`.
This does not qualify every compiled device module/private ioctl or IPv6.
The final aggregate audit now proves the original three-capability endpoint.
Remaining configuration-service dependencies and lease lifecycle are separate
future work, not implemented by this command milestone. See
[exact completion and limits](COMPLETION-AUDIT.md).
