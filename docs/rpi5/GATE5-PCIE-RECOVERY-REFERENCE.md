# Fresh installed boot / recovery configuration reference — 2026-10-12

The Pi is verified on SSD Linux, root `/dev/nvme0n1p2`, ext4 UUID
`04570742-280b-43cb-9564-73d454243b1c`, boot
`8512e93e-ec70-4715-bb02-d118afe393ed`. The exact SD remains inserted. A new
read-only collector verifies its current boot image and protected files, whole
MBR/FAT bytes before and after a read-only FAT mount, and unchanged root/boot/
EEPROM identity. Both SD partitions are unmounted afterward. This supersedes
the earlier statement that current SD configuration/image bytes were unverified.

## Actual fresh results

| Evidence | Observation |
| --- | --- |
| Current installed `probe.bin` | SHA256 `f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536`, the physically tested zsh/socket image |
| Complete 536,870,912-byte FAT partition | SHA256 `1ad719c6ab914b4b24c2f478ac31f83e052e750ee9a68b588060d415e562d3ff`, equal before/after and the accepted installation receipt |
| Complete 512-byte MBR | SHA256 `c5e2c9b892f23d51d496e09363f872882a18e55fb1530080e38a511b93324b4a`, equal before/after and the accepted receipt |
| Current SD config | SHA256 `aaccab184135aca272db4123fcba34e20874ae0959a90aed1ef6fd4d5e18ed28` |
| Persistent EEPROM order | `BOOT_ORDER=0xf461`, SD → NVMe → USB → repeat |
| Current SD next-reset order setting | `set_reboot_order=0xf6`, NVMe-only → repeat |
| Current SD firmware watchdog request | `kernel_watchdog_timeout=60`, **not 15** |
| Current Linux firmware boot properties | `boot-mode=6`, `partition=1`, `tryboot=0` |
| Alternate boot selectors/images | No `autoboot.txt`, `tryboot.txt`, `boot.img`, `tryboot.img` or `recovery.bin` |
| RO mount | Actual mount ID 88, `/dev/mmcblk0p1`, `vfat`, `ro,nosuid,nodev,noexec`; ownership checked before cleanup |

The remaining protected Gate 3/shell/HFS/topology/zsh/statprobe/Apple-network
images, TF-A `bl31.bin` and Pi5 DTB also match every expected file hash. No
image, configuration, EEPROM, firmware, SD data, HFS mount, Pi power/reboot or
serial operation changed. Metadata queries may read HFS identity; HFS contents
were not rehashed and no durability test was performed. The existing NVMe
backup chain was not reverified by this collector, so it does not admit an
installer. The accepted IRQ/controller kernel pins and all 35 checks on the
unchanged tested zsh/socket package also revalidate.

The boot-order interpretation follows the official
[EEPROM BOOT_ORDER definitions](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#BOOT_ORDER).
The official [Pi5 `set_reboot_order` documentation](https://www.raspberrypi.com/documentation/computers/config_txt.html#set_reboot_order)
specifies a reset-safe, one-use override that is cleared after use. The current
SD file therefore **configures** the intended next NVMe boot after that SD boot;
it does not expose or prove a currently latched register value from Linux.

The [firmware watchdog option](https://www.raspberrypi.com/documentation/computers/config_txt.html#kernel_watchdog_timeout)
requests an OS-handoff watchdog. Its numeric request is not a hardware timing
measurement. The existing standalone access diagnostic independently requires
an already-running, full-reset PM route, then makes its own one-time 15-second
reload with 14..15-second readback and observed decrement. A firmware request
of 60 seconds must not be relabeled a 60-second bare-metal countdown or turned
into an invented requirement to rewrite config to 15. Keep the measured PM
route/countdown/readback requirements separate from boot-order configuration.

## New tool, immutable live evidence and tests

```
python3 tools/rpi5/capture_pcie_recovery_reference.py \
  --linux-boot-id VERIFIED_CURRENT_SSD_BOOT_UUID \
  --output-dir build/rpi5/pcie-recovery-reference-NEW
python3 tools/rpi5/capture_pcie_recovery_reference.py \
  --linux-boot-id VERIFIED_CURRENT_SSD_BOOT_UUID \
  --output-dir build/rpi5/pcie-recovery-reference-OTHER-NEW --execute
PYTHONPATH=tools/rpi5/tests:tools/rpi5 python3 -m unittest \
  tools.rpi5.tests.test_pcie_recovery_reference \
  tools.rpi5.tests.test_pcie_lifecycle_reference \
  tools.rpi5.tests.test_probe_install_core \
  tools.rpi5.tests.test_socket_identity -v
```

Default is a local plan with no SSH or device access. The collector validates
the pinned accepted installation history, exact SSD boot/CID/layout, holders,
unmounted state and inactive automounters using the unchanged original capture
identity helper. It hashes the whole MBR/FAT before mounting, checks root/boot
again, mounts only fixed FAT read-only, and verifies the exact source/type/
mount ID/options. Protected files use bounded regular, nonlinked, no-follow
descriptors. It then checks mount ownership before unmounting, and rechecks
complete MBR/FAT, root/boot, EEPROM and boot properties. It never remounts RW,
mounts HFS, discovers a writable target, writes mailbox controls, controls the
watchdog, repairs, installs or reboots.

Only the three named bootloader properties are read, filtered before access;
the rest of `/chosen`, seeds and identity properties are never enumerated.
The conservative config evaluator supports only `[all]`, `[pi5]` and `[none]`,
rejects includes/unknown filters/overlength/duplicate selected settings for its
configuration conclusion, and distinguishes requested timeout from next order.
Unknown/missing state is not silently promoted to a recovery proof.

Final evidence: `build/rpi5/pcie-recovery-reference-20261012-final/`:

- `plan.json` SHA256 `87bdfbc69c3aefa6a98aa554855a93f6911b10b463a785a61e5d82ae6747ccf5`.
- `result.json` SHA256 `43045772c182bd6eac08964dc17d70261c73d33ee4f843355fe4877d4b742aa6`.
- `remote.stdout` SHA256 `b56c775b0c3f60abdbb3db13656a07103d9875830196ae25dc279b11b1acf6f2`.
- `source-snapshots.json` SHA256 `0f1bc582ee6f52daf648c8a4acdb4d001cee5af810b025c75b046b7c7968ec84`.

All current and archived source hashes match. Exact source copies are retained
alongside each final capture, not only hashes into a changing checkout. A
separate final SSH check confirms the same SSD root/boot and no SD mounts.

The first successful read-only capture at `pcie-recovery-reference-20261012/`
is preserved with its exact source snapshots. Its initial combined conclusion
incorrectly required the configured timeout to be exactly 15 seconds; it
reported false despite separately recording the correct `0xf6` setting. That
was a local assessment limitation, not a failed hardware recovery trial. The
final implementation separates these settings and has a timeout-60 regression
case; no SD config was changed to satisfy the old local assumption.

All **48 selected tests pass in 10.452 seconds**, including 12 new parsing/
RO-mount/source/timeout tests, lifecycle checks, protected installation-core
tests and actual saved physical zsh/socket replay. Tests cover full hash/boot
drift before mount, wrong source/RW options/ambiguous mount, no-follow symlinks,
alternate boot files, both timeout requests, typed claim validation, own-mount
cleanup on file failure, refusal to unmount a replaced mount, busy cleanup,
property filtering/endianness, source archives, plan-only/overwrite/source drift
and preserved unknown SSH timeout with no automatic retry. These tests do not
measure hardware watchdog timing or execute a new XNU image. The prior 286-test
kernel regression result remains separate; it was not rerun in this turn.

## Next actual recovery / PCIe sequence

The configured return path is now freshly established; **physical watchdog
reset and SSD return remain unproven for the new diagnostic lease**. Do not
claim the boot-order latch, running PM countdown, inherited domains, full IRQ/
endpoint/DMA quiescence or PCIe access permission from this reference.

1. Prepare a distinct **watchdog-only** standalone diagnostic: same validated
   primary-only firmware/FDT/UART/PM entry, no PCIe/reset/calibration/GIC/DMA
   access. Verify prior running full-reset route, reload once for 15 seconds,
   drain timestamped ARMED/STOP markers and stop servicing. Reuse the existing
   actual PM implementation carefully; preserve the accepted access candidate.
2. Add a baseline-aware guarded trial that verifies the current image and all
   44 inherited preserved artifacts, takes fresh complete snapshots and backs
   up the currently working zsh image before any staging. Old installers must
   keep rejecting this new baseline. Do not rewrite config/EEPROM or touch
   NVMe Linux boot configuration merely because the request is 60 seconds.
3. Arm one image-bound continuous recorder before one software SD boot. Require
   actual PM admission/readback/decrement, the non-servicing markers, observed
   reset/boot sequence and a different verified SSD Linux boot/root plus mode
   6. SSH silence, elapsed time, a capture gap or a manual power cycle is not
   that evidence. Inspect any unknown outcome; no blind second install/boot.
4. After recovery qualification, guardedly trial the existing exact read-only
   access candidate, then concrete shared-domain/interrupt/endpoint/DMA
   admission and the real controller composition, RP1/config/BAR discovery,
   IRQ/DMA/GEM and packets. No synthetic COMPLETE state or source-only test
   substitutes for that board evidence.

Real serial zsh/TTY, Ethernet, network services/SSH, Apple CLI tools/Darwin
layout and recovery stay in the full active objective. Gate 4's durable-write
hold remains separate; this verification did not require another SD card.
