# Autonomous watchdog recovery and zsh restore — 2026-10-12

The distinct watchdog-only image **physically passed** its PM protocol on the
Pi, stopped servicing the countdown, and autonomously reset into a different
normal NVMe Linux boot. One continuous receive-only Mac capture spans the SD
boot, exact image-tagged diagnostic, reset and NVMe boot. The working XNU/zsh
image was then explicitly restored to the SD; the Pi remains in SSD Linux.
No manual power cycle, repeated trial, soak, config/EEPROM change, HFS mount or
PCIe diagnostic access occurred.

## Observed board results

- Exact image/tag: [watchdog-only candidate](GATE5-WATCHDOG-ONLY.md),
  SHA256 `a616420b2c243182aeed6d04b49f0ebab416f88a54303b9805aaa82ab90d8ba2`,
  tag `ccee459ca4bb49e4a45c1cfeffe8aeef`.
- Actual frequency **54 MHz**, PM_RSTC route **0x222**, prior countdown
  **980,539**, armed **983,040** (15 fixed-point seconds), checked **981,157**.
  The independent short wait measured **108,173 ticks**, at least two ms.
  Actual `RESULT`: RC 0, one watchdog write attempt, 12 lease callbacks.
- Exact tagged `STOP NO_RELOAD WAIT_FOR_RESET` precedes a new `RPi: BOOTSYS`,
  then bootloader, actual `BOOT_ORDER override: 0x000000f6`, and
  `Boot mode: NVME (06)`. The reset log reports
  `AON_RESET: 00000003 PM_RSTS 00000020`; its cause bits are retained raw, not
  independently decoded by this tool.
- Host UART arrival intervals: ARMED→BOOTSYS **16.6315 seconds**;
  ARMED→BOOTLOADER **19.9019 seconds**. These include firmware startup and
  UART arrival latency; they are not exact hardware-expiry measurements.
- Linux boot changes from `8512e93e-ec70-4715-bb02-d118afe393ed` to
  **`2407dd80-a11d-47f0-9ae0-57f5c47345ef`**. Independent fresh SSH verifies
  `/dev/nvme0n1p2`, ext4 UUID `04570742-280b-43cb-9564-73d454243b1c`, boot
  mode 6, partition 1, tryboot 0 and both SD partitions unmounted.
- Capture: **44,111 bytes**, zero serial TX, no recorder interruption or
  disconnect; the complete byte-offset/monotonic-time journal replays.

The low-level serial parser deliberately still returns no reset/destination
proof from diagnostic markers alone. The new aggregate evidence checker adds
continuous subsequent boot events, timing, independent new SSD identity and
verified restoration before accepting this single recovery trial. This is not
general PCIe/shared-domain/IRQ/DMA ownership or Ethernet acceptance.

## Preserved installation, cleanup diagnosis and restoration

The new guarded installer verifies the exact card/root/layout, every one of
**44 inherited NVMe artifacts**, complete fresh MBR/FAT/HFS snapshots and a
new working-image NVMe backup before modifying only FAT image files. Fixed
filenames, no-follow descriptors, exact hash/readback and repeated mount-ID/
source/options/descriptor/root/boot guards protect publication and cleanup.

The first publication completed, but cleanup failed because its directory
descriptor was still open during Linux unmount. The image was **not installed
again**. Read-only inspection proved the exact published candidate, preserved
zsh backup and owned RO mount; a separate, source-archived finalizer rehashed
all inherited/fresh backups and protected files, closed SD descriptors and
unmounted that inspected mount once. It then verified complete raw extents and
generated the completed receipt. The initial error/raw source is preserved.
The installer now closes the descriptor before cleanup; a real-FD regression
test enforces that order. Corrected code subsequently completed physical
restoration without that failure. Unknown or partial outcomes never trigger
automatic reinstall, reboot, retry or rollback.

After the successful reset/SSD return, explicit restoration verifies **48
inherited artifacts**, takes another full snapshot set, preserves the watchdog
image on both NVMe and SD, and restores working `probe.bin` SHA256
**`f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536`**.
Protected MBR/HFS hashes remain unchanged; config/TF-A/DTB and every older
protected image match. New complete FAT SHA256 is
**`0999f771c93c0747efaf262b8ce5232762628497a9db4e2bc2f2c648917c76eb`**.
This differs from the old FAT because the new backup files are retained.
The next installer must inherit **52 artifacts** and this restored receipt,
not mistakenly use the old same-image/different-FAT baseline.

## Evidence and reproducibility

- Installation: `build/rpi5/watchdog-recovery-installed-20261012/`, including
  original source snapshots, failed output, separate finalizer source/output
  and completed receipt. Plan SHA256
  `d9fc2e230ecba051faba423b40016e1016dff063c0348841afbddf483a4fc6e6`;
  result `2220db0f24336b6d9805336db8d73b05efdff4274dba3962bd1f4ec9b3c63b44`.
- Capture/return/replay: `build/rpi5/mac-watchdog-recovery-trial-20261012/`.
  Serial SHA256 `1fbd98b1b8c94a25867bf11be24b3547a881bf8a2b9a8d069ef09e175ce7990a`.
- Restoration: `build/rpi5/watchdog-recovery-restored-20261012/`.
  Plan SHA256 `3662df934079044577eb5147c4b907118587e32f42e82fa8f88084505c8d4468`;
  result `bd0f0e29a6d6c11a7f4df372880fb05866d7d6d3686100e0ccd070f06181212f`.

```
python3 tools/rpi5/check_watchdog_recovery_evidence.py
python3 -m unittest tools.rpi5.tests.test_watchdog_recovery_install \
  tools.rpi5.tests.test_watchdog_recovery_serial \
  tools.rpi5.tests.test_watchdog_recovery_evidence -v
```

Preserve accepted sources, receipts and exact archives. Future changes need
distinct output/profile/source where required by those evidence pins. The
unchanged zsh/socket package and earlier IRQ/controller kernels remain separate
artifacts; this trial did not activate or boot those newer Ethernet kernels.

All **78 focused regressions pass in 19.650 seconds**, including the actual
saved physical recovery/install/restore replay, new mount/publication failure
and zero-TX recorder tests, original PM/access/reference/installer tests and
saved physical zsh/socket replay. All 2,435 accepted IRQ-transport and 2,411 IRQ
kernel source/output pins still match, and the unchanged physically tested
zsh/socket package retains all 35 checks. This is separate from the earlier
complete 286-test kernel run; it was not repeated here.

## Next actual network step

Prepare the existing distinct read-only PCIe-access candidate against the
**restored** baseline/52-artifact chain and arm its own continuous capture
before one bounded access trial. This recovery observation validates the PM/
boot-return mechanism used as a prerequisite; it does not itself authorize
reset/calibration/controller/DMA writes. Continue concrete shared-domain/
endpoint/IRQ/DMA admission, controller/RP1/BAR discovery, GEM and wire packets.
Full zsh/TTY, sockets/SSH, Apple CLI tools/Darwin layout and recovery remain in
scope, with persistent storage/durability independently held at Gate 4.
