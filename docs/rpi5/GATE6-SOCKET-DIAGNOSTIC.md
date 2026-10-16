# Socket data-path diagnostic

2026-10-12. A separate static Cortex-A76 diagnostic and boot package are prepared,
**not installed or Pi-executed**. Original Apple zsh/ifconfig/route and the
accepted recovery root remain byte/mode identical. This advances socket
prerequisites for SSH, not the physical Ethernet driver or SSH itself.

## Implementation and placement

`tools/rpi5/user/socketprobe.c` uses the existing small Darwin raw-SVC runtime.
It is a project diagnostic, not a replacement Apple utility or network stack.
It installs at `/usr/local/libexec/xnu/socketprobe`, mode 0555, following the
[Darwin placement contract](FILESYSTEM-CONVENTIONS.md). Apple's unchanged zsh
stays `/bin/zsh`; ifconfig/route stay `/sbin`.

- `unix`: anonymous AF_UNIX stream socketpair; three distinct 32-byte transfers,
  both directions, SHUT_WR/EOF and continued reverse-direction transfer.
- `inet`: two UDP sockets bound to literal 127.0.0.1/ephemeral ports, bidirectional
  payload and source-address/port checks; then nonblocking TCP listener/client/
  accept, bidirectional payload, SHUT_WR/EOF and continued reverse transfer.

Sockets are nonblocking, with verified flags and SO_NOSIGPIPE. Each poll has a
200-ms timeout; each stream direction has at most 16 I/O steps. At most 256
diagnostic data-path syscalls are permitted. Normal host runs take 26/62
operations for unix/inet; two-byte partial I/O reaches 206/242. Positive short
stream transfers are accumulated without dropping or duplicating bytes.
EINTR/EAGAIN, invalid lengths, damaged guards, incorrect payload/peer, poll
timeout/error, bad SO_ERROR and wrong EOF fail without retry. Owned fds close
once; close is never retried even if it reports EINTR. Invalid descriptor
returns never authorize closing stdio or duplicate ownership. Damaged
descriptor-buffer guards refuse further use of the returned descriptors;
that is not proof of recovery from an arbitrarily corrupt kernel.

No DNS, external destination, interface/route modification, persistent socket
path, fork or thread. Console-output writes are outside the data-path counter;
a syscall that hangs inside the kernel is **not** contained by a poll timeout
or finite call count. Physical execution still needs a guarded recorder/recovery
boundary, not a new soak or unbounded retry loop.

## Local evidence and limits

`tests/socketprobe_native.c` maps the raw-call interface to native Darwin calls.
The data transfers really execute on the Mac, not through Pi SVC entry or its
kernel. The adapter enforces literal-loopback addresses and accepted operation
profiles, tracks fd ownership and reports leaks/invalid/double closes. Injected
uncertain-close results release the native fd before reporting EINTR: this tests
no-retry handling, not the Pi kernel's close-on-error semantics.

Ten socket-specific tests cover real Unix/UDP/TCP transfers, half-close,
two-byte partial transfers, refused 16-step one-byte transfer, all **448**
partial-I/O-path syscall failure positions, 27 malformed/error scenarios,
invalid mode with zero syscalls, immutable additive roots/path collisions,
actual A76 static linking, changed pins and overwrite refusal. Native IPv4
tests need local-bind permission; sandbox EPERM is not a Pi failure.

```
python3 -m unittest tools.rpi5.tests.test_socketprobe -v
```

All **127 selected regression tests pass**, including the ten new tests,
existing Apple-command/physical-replay, zsh metadata, protected installation
and PCIe suites. This is a selected suite, not all XNU tests or board acceptance.

Preparation binds all 17 reviewed data-path syscall IDs to real handlers in
the unchanged accepted kernel's linked `_sysent`. This is selected-call wiring
evidence, **not** runtime semantics or complete binary syscall closure: the
shared raw dispatcher accepts a dynamic syscall number and contains other
support functions. Actual source/compiler commands and compiler-discovered SDK
header hashes are recorded and rechecked for build-time stability.

## Distinct artifacts

`build/rpi5/socketprobe-root-20261012/ramdisk.bin`:

- 1,900,544 bytes / **32 nodes**, SHA256
  `ce5c8d7ecd9f55ea9cbd988af6ffcf308252065e591a1fd66c1233bfcb566ab7`.
- Diagnostic SHA256
  `c60c81856e469bbeddc8e493f1464c63aa2c6687ebff446fbf70ebbf95f1d68d`.
- Manifest SHA256
  `f02aeb071d9fb4caa2e5c18a7abe11b264ae7c38637015ed7b5cffb532265fba`.
- Adds only the helper file and four derived parent directories to the 27-node
  Apple-network root. This reaches the existing 32-node limit; more utilities
  need a separately validated root/kernel capacity change or different root
  selection, not silent replacement of existing files.

`build/rpi5/bl33-probe-tt7iq4m9/probe.bin`:

- 19,367,616 bytes, SHA256
  `ccb961bc36be8befad08b5a1b1dbc0d0bff4dc5a2fa25e27f341336770105d04`.
- Unchanged accepted `674e6a76...` kernel and recovery startup. Storage off,
  topology declarations only; no PCIe/NIC/DMA access enabled.
- `check_socketprobe_package.py` passes **34** package checks; report
  `build/rpi5/socketprobe-preflight-20261012.json`.

## Physical next step, not yet performed

Fresh read-only SSH to 192.168.4.23 timed out. Last proven Pi state remains the
earlier XNU recovery session; a timeout establishes neither OS nor power.
No serial/media/power/firmware/reboot operation occurred for this work.
Installed `b67b8013...` and its preservation chain are unchanged.

When SSD Linux is actually verified, preserve the current image and **40**
existing backup artifacts plus fresh exact-card snapshots under a new baseline-
aware installer. Old installers must keep rejecting newer baselines. Arm an
image-bound recorder before one software boot. Resolve earlier SMP-torn mount
identity framing explicitly; do not waive that failed trial or request repeated
lucky boots. Exercise unix, then inet, recording actual outputs, exit statuses
and return to recovery. No acceptance is inferred from preparation.

The earlier `ifconfig -l` proved the name lo0, **not** its IPv4 address/up state
or loopback route. If inet returns EADDRNOTAVAIL/ENETUNREACH/another error,
preserve the diagnosis and inspect configuration before considering a separately
tested setup change. Do not silently turn this into interface configuration.

Ethernet still needs physical PCIe provider/recovery/access, RP1 discovery/BAR/
interrupts, GEM/PHY/DMA and IONetworkingFamily integration. Loopback would not
prove those. OpenSSH needs original-source build/runtime and service/security
work in addition to a NIC. Gate 4 durable storage/history remains held.
