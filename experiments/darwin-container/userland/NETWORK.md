# Experimental Darwin VM networking

VM-only opt-in profile, 2026-10-12. Physical Pi devices, SSH, SD media and the
private `0.1.0` package are outside this workstream and were not changed.

Latest increment: selected original Apple DHCP packet/BPF/IPv4 configuration
routines now acquired and installed a real VM lease, followed by a fresh
host-witnessed DNS/TCP exchange. The project state-machine/route adapters and
missing full service/renewal boundary are documented in [APPLE-BOOTP.md](APPLE-BOOTP.md).
Earlier combined proofs below remain historical checkpoints, not repeated tests.
The subsequent original Apple `/bin/route` also passed actual default-route
delete/add/get and a fresh DNS/TCP exchange after replacement. Its full source
is compiled, but only numeric IPv4 route operations are qualified.
[Route evidence](../results/2026-10-12-apple-route/verification.json).
Original Apple `/bin/ifconfig` subsequently changed/read back MTU 1400,
restored/read back 1500 and displayed leased IPv4 in one short VM boot, followed
by route inspection and fresh DNS/TCP. All nine original command modules are
compiled; only this en0/IPv4/MTU slice is guest-qualified, not every module or
private ioctl. [Latest ifconfig evidence](../results/2026-10-12-apple-ifconfig/verification.json).

## What actually ran

[Preserved trial](../results/2026-10-12-network/verification.json): guest en0
reported its real MAC/index through the routing sysctl; guest BPF/UDP performed
DHCP discover/offer/request/ACK and installed its IPv4 address/default route.
Guest UDP resolved a fresh nonce name with a short-lived host DNS fixture;
guest TCP sent/received the same nonce. The host independently recorded both
exchanges on bridge100. All terminal editing/jobs/resize/byte checks passed,
followed by history save, HFS+ unmount and guest poweroff. No soak was run.

`netctl` is explicitly project bootstrap code. It uses XNU's real socket and
network stack, but is not Apple's ipconfig, ifconfig or a general Libresolv
implementation. Pinned Apple networking userland integration remains required.

## Original Apple parser increment

The later `--apple-dns` build uses unmodified `ns_name.c`, `ns_parse.c`,
`ns_netint.c` and `res_comp.c` from Apple's official `libresolv-96`, commit
`e48cd914edc1cb14f8289b8e2dfdaac360481cd2`. The build refuses a different or
modified checkout, records source/command hashes, retains upstream notices and
strips unused code. No installed host libresolv/LibSystem is linked. The link
map identifies the original Apple record/name parser implementations, and the
static executable has no unresolved imports.

One native fixture covered a valid compressed A answer, every truncation,
compression loops/out-of-range pointers and wrong transaction ID. An actual
combined guest boot then used this parser on the fixture DNS reply, completed
TCP echo, shared Metal requests and all PTY checks, and shut down cleanly.
[Original source and execution evidence](../results/2026-10-12-apple-network-gpu/verification.json).
The private checkpoint is `build/apple-network-gpu-working-2026-10-12/`.

This selected wire parser is not the whole Libresolv client. The guest socket,
DHCP and configuration glue remains labeled project code. Full pinned Apple
resolver/configuration userland is still outstanding, not declared complete.

The subsequent standalone resolver now also passed original Apple `res_ninit`
file parsing and `res_nquery`/`res_nsend` over both UDP and TCP in the actual
guest. This supersedes the parser-only boundary for `/bin/resolverctl`, not
for bootstrap `netctl`. [Original-source/adapter contract](APPLE-RESOLVER.md)
and [latest evidence](../results/2026-10-12-apple-resolver/verification.json).

The newer Libinfo profile also executes Apple's original `getaddrinfo`,
`getifaddrs` and interface lookup. Fresh-hostname resolution and a TCP nonce
exchange through its returned address passed in the guest, with independent
host observations. Numeric IPv6 was parsed, not network-qualified. The bounded
direct-unicast module is project glue to original Apple libresolv; macOS
search/cache/mDNS/configuration services are not present.
[Libinfo execution evidence](../results/2026-10-12-apple-libinfo/verification.json).

## Reproduce with distinct inputs

Build a new kernel snapshot with `kernel/build.py --storage --network`, the
verified IOStorageFamily provider and the previous provider-snapshot manifest.
Never resume/upgrade the frozen storage/terminal baseline for this purpose.
The successful network kernel is the distinct `vzgeneric-8c5vzyrd` snapshot,
SHA256 `0501225204ac5711fd409f82e9ff70138d126c002f654bea758827345c023da9`.

Build a new RAM root with `userland/build.py --mode zsh --storage --pty
--framed-terminal --network`, supplying the preserved real Apple-source zsh and
terminfo inputs. Package with `build_loader.py --storage --network --kernel
... --ramroot ... --image-tool ...`. Supply a copied disposable data image and
variables template to `userland/terminal_trial.py --network` along with the
signed development CLI, boot disk and a new evidence directory.

The private working checkpoint is `build/network-working-2026-10-12/`; its
manifest hashes the signed CLI, EFI, kernel, RAM root, real zsh, data disk and
firmware variables. EFI/variables contain entropy: do not publish this folder
or consider repeated seed use production-safe. The previous terminal checkpoint
and frozen `0.1.0` remain separate.

## Driver boundaries

- EFI only discovers modern PCI VirtIO net capabilities and records explicit
  MMIO mappings; it does not initialize queues or give firmware DMA ownership.
- Kernel IOService owns physically contiguous, bounded split-ring DMA, real
  Ethernet ifnet/BPF attachment and a single polling worker. TX callbacks copy
  mbufs into a bounded software queue; no caller buffer is retained.
- Eight descriptors per RX/TX queue, 1500-byte MTU, direct descriptors, no GSO,
  mergeable buffers, multiqueue, packed ring or interrupt-driven operation.
  Optional checksum metadata is completed in software. VZ also emitted bounded
  GSO_NONE packets with DATA_VALID|RSC_INFO; advisory RSC fields are not treated
  as checksum offsets, and XNU still validates the ordinary frame checksums.
- The native ring fixture covers bounds, padding, reclaim, receive bytes,
  partial checksum, observed flags and rejected metadata. It is not VM proof.
- Runtime packet logging must not write unframed kernel diagnostics into an
  active DGT1 stream: a failed trial demonstrated CRC corruption from that.

## Still experimental

DHCP is bootstrap-only, with no renewal daemon. The DNS parser accepts the
bounded known fixture exchange, not general search domains/CNAME/DNSSEC/TCP
fallback. No external internet or IPv6 test was performed. No hot-unplug,
multi-NIC, production isolation or network durability qualification is claimed.
Shared GPU compute and original Apple unicast resolver code now have actual
guest evidence. The full follow-on goal remains active for Apple Libinfo and
address/DHCP userland; no complete macOS network-service stack is claimed.
