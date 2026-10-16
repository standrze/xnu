# Reusing original Apple networking utilities on the Pi

20:20 UTC physical continuation: the `/sbin` image is now installed; both
commands ran in a separately guarded same-boot diagnosis, with zsh/recovery
preserved. Strict fresh-mount acceptance remains failed due to corrupted
startup logging; Ethernet/SSH remain unproven. [Physical evidence](GATE6-APPLE-NETWORK-PHYSICAL.md).
The preparation-only receipts below retain their historical false runtime claims.

2026-10-12. The user explicitly requests reuse of applicable Apple open source,
including zsh and command-line utilities. **Reuse is the default:** select/pin
and build original components before writing replacement parsers, utilities,
protocols or generic IOKit infrastructure. Keep necessary board/ABI adapters
small and labeled. Availability is not portability or runtime acceptance.

The Pi already has physically tested Apple-source zsh 5.9; see
[the accepted script/interactive trial](GATE6-METADATA-PHYSICAL.md).
This continuation additionally prepares a **distinct, unstaged** Pi RAM root
with the original Apple `ifconfig` and `route`, byte-identical to their preserved
source-built executables. No command algorithm or frozen capsule is changed.

## Current artifact and provenance

`build/rpi5/apple-network-root-darwin-20261012/ramdisk.bin` is 1,867,776 bytes / 27 nodes,
SHA256 `0fdb95400e7a6421602a39851eaaa6f20e43836e33c390740774165053548b7e`.
The additive preparation preserves every byte and mode of the physically
accepted 25-node Pi root, including init, recovery shell, frozen zsh, original
smoke script, terminfo and statprobe. Only `/sbin/ifconfig` and `/sbin/route` are
added, mode 0555. No VM init, shutdown command, EFI/variable/data disk or VM
kernel is imported. Default startup is unchanged. No boot package or staging
is claimed.

These locations follow the pinned Apple project's install settings. The prior
`apple-network-root-20261012` artifact (SHA256 `faaed35c...`) remains untouched
as historical evidence of the earlier `/bin` layout; it is superseded, not a
staging candidate. The physically accepted Pi image is also unchanged. See
[Darwin filesystem contract](FILESYSTEM-CONVENTIONS.md) for remaining bootstrap
exceptions and the support required for `/private` aliases and writable state.

Both commands come from official
[network_cmds-396.6](https://github.com/apple-oss-distributions/network_cmds/tree/network_cmds-396.6),
commit `f8c87f3c5eccdeb95e414c6b1b0c3b9dca4233ca`. Binary SHA256:

- ifconfig: `73bb8b54bd73e1239a6a6e609f02e7df13c271c23db3570202c70bb1b82a202b`.
- route: `c7baaf0b511ed4519aa48493626472136db10487989d740b3475500bbe2b5c6a`.

`tools/rpi5/prepare_apple_network_root.py` verifies the exact saved build
receipts, all recorded source/private-header/runtime-archive hashes and pristine
pinned Apple Git checkouts. It captures 151 distinct inputs, including its own
packaging/audit helpers. It checks selection of all nine ifconfig C units and
route.c, static arm64 executable structure, and the existing original-nine-
constructor pointer validator. Original source/notices remain in the preserved
source capsules. Mixed historical source licenses need per-file review before
redistribution; top-level license presence is not blanket clearance.

The existing static instruction/trap auditor is reused, not rewritten. A76
disassembly covers all 36,753 ifconfig and 31,305 route instruction words;
37 and 40 trap sites have locally resolved immediates, with no unknown decodes.
This is not feature/ISA, call-path, installed-provider or syscall-semantics
proof. The preparation manifest retains explicit false Pi/network/ABI claims.

Existing [VM execution evidence](../../experiments/darwin-container/userland/APPLE-BOOTP.md)
is separate. These binaries include original Apple Libc/Libinfo selections and
labeled static-entry/single-thread adapters; they are not complete libSystem,
pthread, configd, DNS/search, DHCP renewal or full macOS command qualification.
The historical release is not a current-security equivalence claim.

## Verification and next reuse steps

`python3 -m unittest tools.rpi5.tests.test_apple_network_root -v` checks exact
additions/recovery preservation, wrong hashes, dynamic binaries, collisions,
unexpected command sets, actual source receipts/constructors, and overwrite
refusal. It does not execute either command on the Pi or configure a NIC.

Before a Pi trial, review actual startup/TSD, signals/VM/FP, socket/sysctl/ioctl
contracts against the installed Pi kernel. Prepare a separately guarded image
and first run finite read-only enumeration/usage probes; actual interface/route
changes require a usable interface and a separate test. Existing zsh remains
the recovery baseline. No repeated soak is required.

Next command candidates are Apple's
[file_cmds](https://github.com/apple-oss-distributions/file_cmds) and
[shell_cmds](https://github.com/apple-oss-distributions/shell_cmds). These are
discovery candidates, not imported/pinned/compiled here. For networking, prefer
original [IOPCIFamily](https://github.com/apple-oss-distributions/IOPCIFamily/blob/main/IOPCIConfigurator.cpp)
and [IONetworkingFamily](https://github.com/apple-oss-distributions/IONetworkingFamily/blob/main/IOEthernetController.cpp)
for generic configuration/resources and Ethernet interfaces. Select versions
and close XNU/kernel-library dependencies before claiming integration. Their
reviewed generic implementations do not supply BCM2712 PCIe/reset/clock or RP1
GEM hardware access. That board-specific backend remains necessary.

No Pi/serial/SD/firmware operation was performed. Gate 4 durable storage remains
held, independently of this Apple-source userland and Ethernet work.
