# Apple-source IPv4 configuration in the Darwin VM

The opt-in `/bin/dhcpctl` now runs selected original Apple `bootp-268.1`
routines in the real XNU VM. One short boot acquired a DHCP lease, installed
the IPv4 address and acknowledged default route, and wrote the lease's DNS
address to `/data/resolv.conf`. A fresh guest DNS lookup and resolved TCP echo
were independently witnessed on the host NAT interface. Normal zsh exit
unmounted HFS+ and powered the guest off.
[Preserved source and execution evidence](../results/2026-10-12-apple-bootp/verification.json).

No terminal/GPU proof was repeated, no soak ran, and no physical Pi was accessed.
The frozen `0.1.0` package and earlier qualified checkpoints remain unchanged.

## Original source versus project adapter

The official Apple checkout is pinned to `bootp-268.1`, commit
`b470df0907d7a641d2f41b5c3bb38e93ed4602fe`. The builder refuses a dirty or
different checkout and preserves notices and hashes.

Original Apple routines actually retained and called include DHCP option
creation/parsing and lookup, reply transaction/hardware matching, BPF device
open/filter/interface/write/close, IPv4/UDP checksums and packet transmission,
and IPv4 interface attach/automatic-address/address configuration. The complete
IPv4 prefix of `IPConfiguration.bproj/ifutil.c` is compiled without algorithm
edits; its following IPv6/CGA section is not selected. Original Apple Libinfo
enumerates the real en0 MAC/index. Original Apple Libc supplies `bcmp` and
`arc4random`, using real kernel entropy. The executable is static and has no
unresolved imports or installed host runtime linkage.

Project code remains explicit:

- Bounded two-stage DHCP orchestration: randomized transaction ID, three tries
  per stage, receive timeouts, offer/ACK address/server consistency and required
  mask/router/DNS/lease checks. This is **not Apple's complete DHCP state machine**.
- Length/overload preflight before calling the historical original DHCP parser;
  it prevents a trailing one-byte option tag from reaching an unchecked length
  read. One ASan/UBSan host check covers truncation, overload and option bounds.
- Default-route `PF_ROUTE` request/acknowledgement and resolver-file writing.
  Neither is represented as the original Apple `route` or `ipconfig` command.
- C-format diagnostics are redirected to real guest stdio. CF-format/service
  paths are discarded, not satisfied with fake Core Foundation implementations.

The full Apple DHCP service depends on Core Foundation run loops/timers,
SystemConfiguration, ARP conflict detection and lease/service persistence. There
is no renewal/rebinding daemon here, nor multicast/search-policy integration.
The historical source tag is a bootstrap candidate, not a claim of current
macOS security or behavior parity. Only en0/IPv4 on this single-NIC VM was tried.

## Build and narrow trial

```sh
python3 experiments/darwin-container/userland/build_apple_resolver.py \
  --libinfo --bootp --output-dir experiments/darwin-container/userland/build/NEW_BOOTP
```

Install `NEW_BOOTP/dhcpctl` in a new root using `userland/build.py
--network-config-binary .../dhcpctl --network --storage`, together with the
qualified original Libinfo `resolverctl`, Apple zsh and framed PTY options.
Package using the unchanged qualified VM network kernel and `build_loader.py
--storage --network`. Use only copied data/variable images.

`configuration_trial.py` accepts `--cli --boot-disk --data-disk
--variable-store --output-dir`. It performs only the new configuration and a
fresh local DNS/TCP integration exchange, then exits. Its temporary explicit
DNS fixture override is restored to the DHCP value before shutdown. This is
not proof of external-internet access or a replacement for earlier PTY/GPU tests.
`preserve_configuration.py` verifies this narrow trial independently; it does
not relax `preserve_network.py`'s earlier combined-test requirements.

The private checkpoint is `build/apple-bootp-working-2026-10-12/`, with ten
hashed artifacts, including `dhcpctl` SHA256
`6d50ed6008e56037357676365ee48a54063228897b266534b42d5b1646ac3361`.
EFI/variables contain entropy; do not publish them or assume seed reuse is safe.

## Original Apple route command: subsequent VM proof

The newer `build_apple_resolver.py --libinfo --route` profile compiles the
complete original `network_cmds-396.6/route.tproj/route.c` with its original
keywords header and `INET6` enabled. The official checkout is pinned to commit
`f8c87f3c5eccdeb95e414c6b1b0c3b9dca4233ca`; no command parser or routing-socket
algorithm was rewritten. Original Apple Libc supplies getopt, error reporting,
hostname/IP/link-address helpers, and original Libinfo supplies its lookup
wrappers and `thread_data` implementation. A labeled static-entry adapter
passes actual argc/argv and supplies bounded single-thread key storage; it is
not a general pthread runtime. One focused host check covers that new ABI glue.

One subsequent short VM boot used original Apple `route -n delete default`,
`route -n add default GATEWAY` and `route -n get default`. The real kernel reply
reported the expected gateway and en0, and fresh guest DNS/TCP traffic passed
afterward. It exited/unmounted/powered off normally. The trial proves numeric
IPv4 route operations, not IPv6 connectivity, every route subcommand or reverse
DNS/network-database services. No unchanged PTY/GPU proof or soak was repeated.
[Exact route/source/execution evidence](../results/2026-10-12-apple-route/verification.json).

Install using `userland/build.py --route-binary .../route --network`; run the
narrow `configuration_trial.py --apple-route` and preserve using
`preserve_configuration.py --route-build ...`. The existing `dhcpctl` still
has its project default-route fallback; this trial explicitly replaced that
route with the original Apple command rather than relabeling the fallback.

The latest private checkpoint is `build/apple-route-working-2026-10-12/` with
11 hashed artifacts. Original route SHA256:
`d2311ac51658f7a8397b6005560be889063ef5036d5db3dc4ee13c6c619c4916`.
EFI/variables remain private. The selected Libc-167 files retain their original
APSL 1.1/BSD notices; that historical archive has no top-level license file.
This is a private experimental checkpoint, not a distribution-license review.

The subsequent ifconfig checkpoint below supersedes this next-step note.

## Original Apple ifconfig: subsequent VM proof

The full original `network_cmds-396.6/ifconfig.tproj` command and all nine
published modules now compile unchanged against source-built Apple Libc/Libinfo.
The same official source pin as route is used. Original XNU userland-private
headers supply the actual ioctl ABI; no successful ioctl results are fabricated.
`PRIVATE` is scoped to the original ifconfig modules, not leaked into the resolver.

Static executables have no dyld initializer dispatcher. Labeled project startup
code therefore calls the linked original constructors before the original main.
A linked-image check verifies all nine pointers against their original named
constructors and executable mappings. Actual module execution is witnessed by
the guest command, not inferred from compilation or pointer inspection.

Additional original source includes Libinfo's Ethernet-address helpers, Libc's
`inet_makeaddr`, `strtok`, `sscanf`/scanner and modern `strtofp`. The latter uses
its supported C-locale/nearest-rounding-only switches; its unused `strtod` export
is renamed to avoid colliding with the selected old Libc formatter dependency.
No installed host runtime is linked. Broader locales/rounding are not claimed.

One short VM boot changed en0 MTU to 1400, read back that actual kernel state,
restored/read back 1500 and displayed the DHCP-leased IPv4 address through the
original command. Original route delete/add/get and fresh independently witnessed
guest DNS/TCP passed afterward, followed by normal zsh exit/unmount/poweroff.
Only the new constructor linkage and this narrow configuration integration were
checked; no unchanged native guard, PTY/GPU proof or soak was repeated.
[Exact source, constructor and execution evidence](../results/2026-10-12-apple-ifconfig/verification.json).

Build with `build_apple_resolver.py --libinfo --ifconfig --output-dir NEW`;
install using `build.py --ifconfig-binary NEW/ifconfig --network` in a new root.
Use `configuration_trial.py --apple-ifconfig --apple-route` with copied VM disks
and preserve using `preserve_configuration.py --ifconfig-build NEW --route-build ...`.
Latest private checkpoint: `build/apple-ifconfig-working-2026-10-12/`, twelve
hashed artifacts. Original ifconfig SHA256:
`73bb8b54bd73e1239a6a6e609f02e7df13c271c23db3570202c70bb1b82a202b`.
The newly rebuilt route also passed in this boot; previous checkpoints remain
untouched. EFI/variable entropy stays private.

Compiled bridge/bond/VLAN/IPv6 modules are not qualification of those devices,
all private ioctls, every subcommand or IPv6 connectivity. Remaining Apple
configuration-service dependencies and lease lifecycle are separate future
work. The [final aggregate audit](../COMPLETION-AUDIT.md) proves the documented
PTY/network/shared-compute endpoint without repeating these unchanged checks.
