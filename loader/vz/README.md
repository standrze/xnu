# Generic EFI XNU loader

This source-built ARM64 EFI application is separate from the Raspberry Pi boot
path. It discovers ACPI GICv3/PSCI/timer/PCI information and drives a modern
virtio PCI console directly; it does not depend on firmware Serial I/O, QEMU,
Linux guest code or proprietary macOS boot components.

The console-only diagnostic has executed through the fork's
`container darwin run` command. It exited boot services, disabled firmware
translation/cache state, printed through its own split virtqueues, and requested
PSCI HVC shutdown. The host observed a clean stop and captured 113 serial bytes.
Small evidence is under
`experiments/darwin-container/results/2026-10-12-native-console/`.
That test did not run XNU or exercise receive input.

The later full-handoff trials 7 and 8 booted the source-built VZGENERIC XNU
kernel and RAM root, received serial commands, preserved nonce-bound exit
statuses 0 and 1, and shut down cleanly. Trial 7 also executed `sleep 1` and
read `/etc/motd`. Small evidence and exact input hashes are under
`experiments/darwin-container/results/2026-10-12-xnu-trial-7/` and `...trial-8/`.

Initial scope is one vCPU, polled console, 16-KiB kernel pages and the measured
36-bit physical-address environment. Console rings have explicit retained RAM
ownership and are rebound, not reset, by the kernel. No block/network driver,
SMP, writable filesystem, full PTY or general-purpose container runtime is
established by this diagnostic.

The current full-handoff status and next acceptance test are recorded in
`experiments/darwin-container/STATUS.md`. DC2 requires captured source-built XNU
startup and a real RAM-root command response; a packaged EFI image, linked
kernel or successful preflight is insufficient.
