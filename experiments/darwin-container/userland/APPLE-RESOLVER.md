# Original Apple resolver in the Darwin VM

The opt-in Libinfo profile now also runs original Apple public address
lookup and interface enumeration. See the Libinfo section below; the earlier
default resolver-only profile and its checkpoint remain unchanged.

The newer [Apple bootp configuration profile](APPLE-BOOTP.md) now uses selected
original DHCP/BPF/IPv4 routines for address setup. The full configuration daemon
and lease lifecycle remain unfinished; the sections below describe the earlier
resolver/Libinfo milestones and their exact source boundaries.

The standalone `/bin/resolverctl` now executes original Apple `res_ninit`,
`res_nmkquery`, `res_nquery` and `res_nsend` in our XNU guest. Both UDP and TCP
DNS A queries passed against an independently observed, fresh-nonce host
fixture in one short boot. This is actual guest socket traffic through XNU's
network stack, not host DNS resolution on the guest's behalf.
[Preserved execution/source evidence](../results/2026-10-12-apple-resolver/verification.json).

The same boot passed DHCP, TCP echo, real PTY/job control/ZLE/resize/binary
roundtrip and two independently verified host-Metal calculations. Normal zsh
exit saved history, unmounted HFS+ and powered off. No soak was run, and the Pi
and frozen `0.1.0` package were untouched.

## Source and capability boundary

- Original query/configuration/transport/parser sources: official Apple
  `libresolv-96`, commit `e48cd914edc1cb14f8289b8e2dfdaac360481cd2`.
- Original Apple `inet_pton`, `inet_ntop`, `inet_aton` and the `VARIANT_STATIC`
  arc4random branch: `Libc-1752.120.2`. Real kernel entropy supplies randomness;
  this is not the modern corecrypto-backed arc4random configuration.
- Original Apple-391 asprintf allocation/formatting code, with recorded FILE
  extension/unlocked formatter ABI adaptations for the selected Apple-167
  source-built static stdio. All other selected Libc sources remain unchanged.
- Official `configd-453.19` and `Libnotify-121` supply original private headers,
  **not running service implementations**. Unavailable services fail explicitly;
  original `res_ninit` takes its real configuration-file fallback.
- `/data/resolv.conf` is an explicit compile-time path because the root is
  read-only. Configuration-file parsing, query formation, socket transport,
  retries and response matching are original Apple code.
- A labeled project adapter packages numeric IPv4 `getaddrinfo` results using
  Apple's actual `inet_pton`. It rejects hostname, service-name and broader
  requests. It is **not full Apple Libinfo**, and must be replaced as that
  source closure is brought up. Apple `Libinfo-542.40.3` has been downloaded
  for that work, but none of its code is claimed in this executable.
- Process-local resolver state/errno, startup and single-thread lock ABI glue
  remain project-owned. No pthread creation, multicast, notifyd, configd,
  mDNSResponder, dynamic linker or host libSystem/libresolv linkage is claimed.
  Optional monotonic timestamp caching returns ENOTSUP rather than fake time.

The builder verifies clean pinned Git checkouts, the selected original Libc
files against hash-pinned official archives, runtime archives against the
qualified zsh manifest, and a static Mach-O with no unresolved imports. Its
manifest records source/header/command hashes and all ABI adaptations.

## Build and run

Build into a new directory:

```sh
python3 experiments/darwin-container/userland/build_apple_resolver.py \
  --output-dir experiments/darwin-container/userland/build/NEW_RESOLVER
```

Install that executable in a new root with `userland/build.py --mode zsh
--storage --pty --framed-terminal --network --resolver-binary .../resolverctl`
and the existing pinned zsh/terminfo inputs. Optional `--apple-dns --shared-gpu`
retain the prior parser/GPU paths. Package with `build_loader.py --storage
--network` and the separately qualified network kernel.

The original standalone resolver executable and the provenance-verified rebuild
were byte-identical: SHA256
`8f85fa14b9a6d99ebaef881dd8396e8b8cdb1366cb1165271838d118c62a1639`.
The latest private snapshot is `build/apple-resolver-working-2026-10-12/`;
its manifest hashes the images, CLI, zsh, resolver and writable disk. EFI and
variables contain entropy: do not publish them or assume seed reuse is safe.

After guest `netctl dhcp`, a basic explicit-server query is:

```sh
print -r -- 'nameserver SERVER_IPV4' > /data/resolv.conf
/bin/resolverctl udp 53 example.org
/bin/resolverctl tcp 53 example.org
```

Those are usage examples, **not evidence of external internet access**. The
maintained `terminal_trial.py --network --apple-resolver` runs a local fixture
with fresh names and ports; `--shared-gpu --apple-dns` checks the combined image.

## Still required

Full macOS lookup-service integration and Apple address/DHCP userland remain
unfinished; project `netctl` still configures the interface and route.
There is no lease renewal daemon, broad internet/IPv6/CNAME/search-domain/DNSSEC
qualification, accelerated desktop or general Metal ABI. The full goal remains
active rather than treating these adapters as the finished Apple userspace.

## Original Libinfo public lookup: actual guest proof

`build_apple_resolver.py --libinfo --output-dir NEW_DIRECTORY` builds original
`Libinfo-542.40.3`, commit `266295b80361952510d09799a58af6565baf5732`.
The original public `getaddrinfo`/`freeaddrinfo`/`getnameinfo`, SI validation,
address packing/sorting, item/list allocation and `getifaddrs`/interface lookup
are compiled unchanged. Apple's published libplatform-375.120.2 inline atomic
implementations supply real reference counting, verified against its pinned
source archive. Original Libc send/recv and reallocf are also selected.

One actual XNU boot passed numeric IPv4 and IPv6 results, rejected malformed
numeric addresses/unsupported family, enumerated real en0 name/index, resolved
a fresh fixture hostname and completed TCP echo using its returned sockaddr.
The host independently witnessed the added DNS and TCP exchanges; all earlier
UDP/TCP resolver, terminal and shared-Metal checks passed in that same boot.
Normal exit saved history, unmounted HFS+ and powered off; no soak.
[Exact executable/source/execution evidence](../results/2026-10-12-apple-libinfo/verification.json).

The static guest's `si_search` factory is bound to a **project direct-unicast
module**, which calls original Apple libresolv and packages at most 16 A/AAAA
records using original `LI_ils_create`. It is not Apple's mDNSResponder module,
directory/cache search policy or a full DNS service. Named-service lookup,
reverse DNS, multicast and scoped queries are not implemented by this binding.
The trial exercises IPv4 networking; numeric IPv6 is not connectivity evidence.

Project single-thread once/mutex adapters perform real initialization/exclusion
and abort on unsupported contention/recursion. They are not full pthreads.
Unavailable notify registration fails, dynamic loading returns ENOTSUP, unified
logging is disabled, and original Apple code takes its optional fallback paths.
`mach_absolute_time` uses actual kernel-provided Mach uptime through Apple's
syscall assembly. Optional `clock_gettime` caching is still unavailable.
Private socket-address layout/header compatibility and retired range macros
are recorded build adaptations; no ranking algorithm is replaced by constants.

The private checkpoint is `build/apple-libinfo-working-2026-10-12/`, including
resolver SHA256 `dd21555f0f82c27762343feca7978e20f8129b9fbc7e6d22f4beb4f89eda54be`.
Use only copied data/variables for new trials; EFI entropy remains private.
`terminal_trial.py --network --apple-resolver --apple-libinfo --apple-dns
--shared-gpu` reproduces the bounded combined trial with fresh names/ports.
The diagnostic address-to-TCP command is:

```sh
/bin/resolverctl gai DNS_PORT HOSTNAME TCP_PORT ECHO_TOKEN
```

This is an explicit-server diagnostic, not an external-internet qualification
or installation of a complete shared LibSystem for arbitrary applications.
