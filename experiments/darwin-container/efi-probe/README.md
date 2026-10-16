# Bounded Apple Virtualization EFI probe

This is an original, dependency-free diagnostic harness beneath the proposed Darwin
container backend. It is **not XNU**, an XNU loader, a macOS guest, or proof that a
Darwin container boots. It tests whether Apple's generic EFI virtual-machine path
executes our own ARM64 UEFI application and can persist an attributable result.

## Safety boundary

- Local Apple-silicon macOS 13 or later; no QEMU or package installation.
- One virtual CPU, 512 MiB RAM, a 30-second deadline plus at most five seconds to
  stop a timed-out guest. A timeout is a failure even if a result was written.
- No network, directory shares, sockets, physical disks, USB passthrough, or Pi access.
- Every build gets its own `/private/tmp/darwin-efi-probe.XXXXXX` directory.
- The host constructs a new 64-MiB GPT/FAT16 image as ordinary bytes. Neither
  preparation nor verification mounts the image. No raw-disk utilities are used.
- Only that new image is writable in the VM; a fresh EFI variable store and serial
  log are also kept in the same run directory. Existing output files are not replaced.
- No long-lived server. The harness exits after success, failure, or timeout.

## Build, inspect, then run

```sh
/bin/bash experiments/darwin-container/efi-probe/script/build_and_run.sh --build-only
```

The default is also build-only. This compiles the freestanding EFI C payload with
Xcode Clang and the repository's existing pinned Zig 0.16.0 LLD, runs Swift unit
tests in an isolated scratch directory, builds/ad-hoc-signs the host CLI with only
`com.apple.security.virtualization`, and prepares the new disk. It does not start
a VM. No preinstalled UEFI SDK or guest libc is needed.

The command prints an exact `run_prepared.sh` command for its preserved directory.
Running that command starts the VM. Alternatively `build_and_run.sh --run` builds
and then runs immediately. Do not run an executable from an untrusted run directory.
No elevated privileges should be necessary for the CLI, though the enclosing
automation environment may require approval for Virtualization.framework access.

## Evidence and pass conditions

### Packaging a real kernel-bearing EFI application

The separate `vz-efi-image` executable creates the same fixed 64-MiB boot disk from
an existing ARM64 EFI PE application up to 32 MiB, including an application that
embeds an XNU kernel and ramroot. Allocation is checked against both FAT and
partition capacity. It never starts a VM, mounts a disk, or overwrites an existing
output. Its packaging result makes no diagnostic-probe or XNU boot claim:

```sh
swift build --package-path experiments/darwin-container/efi-probe --product vz-efi-image
# Use the resulting executable:
vz-efi-image /path/to/BOOTAA64.EFI /path/to/new-disk.img
```

The output's `RESULT.TXT` and `DIAG.BIN` remain blank reserved files; an arbitrary
kernel-bearing EFI payload need not use them. The `efi-probe` executable retains
its separate nonce/guest-stop/report checks and cannot treat packaging as a pass.

### Diagnostic probe only

`BOOTAA64.EFI` is installed at the architecture-defined removable-media path
`EFI/BOOT/BOOTAA64.EFI` on the EFI System Partition. The per-build nonce is compiled
into this payload. `RESULT.TXT` begins as 4096 zero bytes. The application uses
UEFI Loaded Image and Simple File System protocols to overwrite that existing
file on its own boot volume, flushes/closes it, then requests EFI shutdown.

The report contains the nonce, current exception level, architectural counter
frequency, memory feature register, UEFI/firmware revisions, configuration table
count, ACPI 2.0/FDT presence flags, and UEFI memory-map descriptor count/size/version.
The separate preallocated 256-KiB `DIAG.BIN` now captures bounded raw ACPI tables,
memory descriptors, PCI configuration snapshots, and Serial I/O device paths when
firmware exposes them. The host validates and extracts these without mounting the
disk. See [DIAGNOSTICS.md](DIAGNOSTICS.md) for the actual measured VM layout and
the decoded console PCI capabilities. This is not a kernel handoff or AML interpreter.
UEFI console output is best-effort; an empty virtio serial log is not itself failure.

Success requires all of:

1. A fresh blank image that still matches its preparation SHA-256 and nonce.
2. An actual guest-stop callback before the deadline, without a VZ error.
3. A bounded, well-formed result file with that nonce, the explicit
   `uefi-payload-only-not-xnu` scope, successful memory-map retrieval, a positive
   timer frequency, a plausible exception level, and a completion footer.

The CLI then emits `EFI_PROBE_PAYLOAD_PASSED` and writes `verified.json`, the raw
`guest-report.txt`, and result hashes. `prepared.json` alone is never boot proof.
`started.json` records an attempt, `stopped.json` records a clean stop, and
`failed.json` records a start/run failure. The directory is preserved for review.
Host tests use synthetic PE/report fixtures and prove parsing/image construction,
not firmware execution. A successful EFI payload still leaves the XNU loader,
platform port, kernel startup, guest agent, and container integration unproven.

## Source and ABI provenance

All code here is newly authored for this project under BSD-2-Clause; see `LICENSE`.
`guest/efi_abi.h` contains only the minimal public UEFI ABI declarations required
for the probe. Layouts/GUIDs follow the UEFI 2.10 specification, chapters 4, 7, 8,
9, and 13; compile-time offset assertions guard the important 64-bit tables.
No EDK II, Apple firmware implementation, proprietary loader, or third-party
implementation code is bundled. The `results/` directory includes small runtime
ACPI/device-data snapshots from the VM, not firmware implementation source.
Host API contracts are checked against the installed Apple SDK.

- [UEFI specifications](https://uefi.org/specifications)
- [UEFI 2.10 specification](https://uefi.org/specs/UEFI/2.10/)
- [VZEFIBootLoader](https://developer.apple.com/documentation/virtualization/vzefibootloader)
- [VZGenericPlatformConfiguration](https://developer.apple.com/documentation/virtualization/vzgenericplatformconfiguration)
- [Apple containerization](https://github.com/apple/containerization)
