# Terminal, network and shared-compute completion audit

2026-10-12. The three-capability VM follow-on endpoint in
[the numbered plan](INTERACTIVE-NETWORK-GPU.md#sequence-and-completion-evidence)
is achieved for its documented experimental profile. This is not completion of
the wider operating-system roadmap, full macOS networking services, arbitrary
Metal compatibility or a graphical desktop.

[Machine-readable audit](results/2026-10-12-followon-audit-final/audit.json).
The audit checked raw guest output, independent host observations, current
source/artifact hashes and the actual verifier coverage. It did not boot another
VM or repeat the unchanged tests. Earlier per-increment reports are retained
unchanged; their historical `not-full-goal` labels predate this aggregate audit.

## Requirement-by-requirement evidence

| Required endpoint | Inspected evidence and result |
| --- | --- |
| Real XNU PTY, controlling terminal/session and foreground/background jobs | Guest tty/monitor checks, actual Ctrl-Z suspension, `jobs`, `fg` continuation, Ctrl-C status 130; relay uses XNU `setsid`/`TIOCSCTTY`/foreground-group ioctls, not synthetic job signals. |
| Apple-source zsh ZLE editing/history | Actual arrow-insertion and up-arrow recall output in the combined guest trial; original pinned source-built zsh executable retained byte-for-byte. |
| Raw host input, restoration and lossless bounded transport | Existing six focused checks cover raw control bytes/restoration, unchanged pipes, corruption/session/sequence validation and partial-write/backpressure ordering. Actual guest input/output roundtripped `0x80`/`0xff`. Host post-exit PTY revocation made restoration unobservable in that guest trial; restoration evidence is explicitly the native host check. |
| Resize and `SIGWINCH` | Host resize 35×120 → 47×132, guest acknowledged both sizes and zsh's actual foreground-group trap printed the new dimensions. |
| Normal history save/exit and restart | Two preserved PTY boots; the second read the prior saved file and real zsh history. Guest exit 0, HFS+ unmount and actual guest-requested stop. |
| Guest NIC and actual IP stack | VZ VirtIO NAT attachment, project VirtIO split-ring transport, real XNU ifnet/BPF/IP/UDP/TCP. Host witnesses recorded traffic from the distinct guest IPv4 address. |
| Pinned Apple network userland | Original libresolv query/send/parser, Libinfo public lookup/interface enumeration, selected original bootp DHCP/BPF/checksum/IPv4 routines and the original route/ifconfig commands are compiled from source and guest-proven. Project static ABI, direct-unicast binding and bounded DHCP orchestration remain labeled. |
| Address, route, DNS and TCP | Actual DHCP lease/DNS configuration; original ifconfig MTU 1400 readback and 1500 restoration; original route delete/add/get kernel reply; fresh nonce-bound guest DNS lookup and resolved TCP exchange independently witnessed on host. |
| Typed guest → real GPU → guest compute | Guest C client over AF_UNIX/relay/DGT1; two fresh vectors executed by the host Metal pipeline on Apple M5 Max. Host operands/results independently matched guest-selected inputs and guest verification. No CPU fallback. |
| GPU ownership, bounds and errors | Per-VM nonce/sequence and one-pending request; finite vectors, 16 elements/request, 1024 requests/session, bounded reports and two-second Metal deadline. Focused session/quota/replay/length checks and actual guest unsupported-operation status 1. No guest shader source or host pointer accepted. |
| Preserve baseline and stay VM-only | All 148 frozen workload immutable hashes and all nine qualified checkpoint manifests match. No physical Pi SSH, serial, SD, firmware or power operation belongs to this goal. |

Evidence sets: [PTY/persistence](results/2026-10-12-framed-terminal/verification.json),
[combined PTY/network/Libinfo/Metal](results/2026-10-12-apple-libinfo/verification.json),
[latest Apple configuration](results/2026-10-12-apple-ifconfig/verification.json),
and [retained existing host checks](results/2026-10-12-followon-audit-final/existing-terminal-focused-checks.log).
Their 26, 127 and 329 evidence-file hashes matched; fourteen current qualified
host-source hashes also matched. Original networking source pins and current
root/build sources were rechecked.

## Latest image and qualification carryover

The private checkpoint is `userland/build/apple-ifconfig-working-2026-10-12/`.
It has twelve hashed artifacts. Its host CLI, XNU kernel, zsh, resolver and all
nineteen files common to the combined passing root are byte-identical. The
latest root adds source-built `dhcpctl`, `route` and `ifconfig`, which passed the
separate narrow configuration boot. This is exact artifact carryover, not a
claim that the latest configuration boot re-ran PTY/GPU tests—it did not.

For an interactive development session, run from the repository root in a real
Mac terminal. This uses fresh copies of the writable media and leaves the
qualified checkpoint untouched:

```sh
darwin_checkpoint="experiments/darwin-container/userland/build/apple-ifconfig-working-2026-10-12"
darwin_session="$(mktemp -d /private/tmp/darwin-interactive.XXXXXX)"
cp -n "$darwin_checkpoint/data.raw" "$darwin_session/data.raw"
cp -n "$darwin_checkpoint/efi-variables-template.bin" "$darwin_session/variables.bin"
"$darwin_checkpoint/container" darwin run \
  --interactive --framed-terminal --network-nat --shared-gpu \
  --timeout-seconds 3600 \
  --boot-disk "$darwin_checkpoint/efi.img" \
  --data-disk "$darwin_session/data.raw" \
  --variable-store "$darwin_session/variables.bin" \
  --output-dir "$darwin_session/run"
```

At the real guest `darwin-zsh#` prompt, configure networking once per fresh boot
with `/bin/dhcpctl`. Inspect it with `/bin/ifconfig en0 inet` and
`/bin/route -n get default`. `/bin/gpuctl selftest 12345` uses the typed shared
compute interface. Type `exit` before the host safety deadline for normal
history save/unmount/shutdown. These commands are not a general network or GPU
benchmark. Files saved to this session's copied `data.raw` remain there; retain
that copy if wanted, and never attach a writable disk to simultaneous VMs.

The private firmware images contain entropy; copying them does not generate a
new boot seed. Do not publish them or call seed reuse production-safe. This
profile requires this Apple-silicon Mac/Virtualization.framework environment;
the broader future target of running anywhere is not claimed complete.

## Separate future work, not hidden success claims

Earlier incremental notes promoted remaining macOS service closure into a reason
to keep this goal active. The original numbered endpoint requires actual guest
DNS/TCP and pinned Apple userland, not a full macOS service stack. The latter
remains useful future work; this audit neither implements nor claims it.

Still absent: full configd/IPConfiguration/Core Foundation service integration,
DHCP renewal/rebinding/ARP conflict detection, mDNS/search/cache policy,
general internet/IPv6 qualification, optional zsh compctl/multibyte locales,
arbitrary Metal applications, desktop graphics and production isolation.
Compiled ifconfig modules do not imply every device/private ioctl is supported.
Official Apple sources remain the preferred reuse path where applicable;
project VirtIO transports and the typed Metal bridge are not called Apple
device drivers. No soak or extra restart campaign is needed for this endpoint.
