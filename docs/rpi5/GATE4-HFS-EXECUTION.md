# Gate 4 HFS read-only execution sequence

**Historical initial-install sequence. Do not rerun now.** It was executed
after Linux returned at 02:00 UTC. The card now has two partitions and the
HFS image; the first actual trial stopped at mockfs statfs64 ENOTSUP before
mounting HFS. See [current status](STATUS.md) and
[the corrective checkpoint](GATE4-MOCKFS-STATFS.md). Correction staging needs
different current-image/backup evidence, not bypassing these initial guards.

The separate correction was prepared as `stage_hfs_stats_correction.py` and
package `bl33-probe-a5wng87t/hfs-stats-preflight.json` (29 checks passed).
It binds the prior installed plan/result and exact raw errno-45 failure,
preserves the failed image under distinct names and rejects the stale current
Linux reference. It executed successfully after fresh Linux returned at 03:06
UTC, using `hfs-linux-reference-fdlatk62`. The unchanged two-cycle trial passed
at 03:12:40 UTC; raw capture SHA256
`9c276399b75fa03d4d3058cd3dada12e73ff82787ee264ff215929e41f4aa315`.
See STATUS.md for the actual installed backup/evidence paths. No additional
read-only repeat/soak is required. Continue separate write durability work;
do not run any historical command below.

Originally prepared 2026-10-12 after the physical SD-read pass. At preparation,
no HFS partition or HFS image had been staged.
Use the current installed SD-only image and preserve all proven-shell backups.
The existing development watchdog is a bounded fallback, not another soak.

## 1. Require fresh SSD Linux

Wait on the existing receive-only `mac-sd-to-linux-fallback-20261012` recorder
and poll SSH sparingly. A live recorder is not proof of Linux. Require:

```text
hostname: kamidana
root: /dev/nvme0n1p2 ext4 04570742-280b-43cb-9564-73d454243b1c
```

`wait_nvme_linux.py` provides a separate bounded, quiet SSH-only wait for this
exact identity and a valid boot ID. Its current run is
`wait-nvme-after-sd-read-20261012`; poll its actual process handle, not merely
the saved state file. It does not access serial/SD, run sudo or reboot. A
successful connection to a wrong/malformed root is an error, not readiness.

Then capture a new one-partition reference using `capture_sd_reference.py`.
Compare its entire identity and all eight sector hashes to
`sd-linux-reference-99_23_zu/reference.json` before any mutation. Keep that
original reference unchanged: the successful SD report binds its exact hash.
Verify unmounted media and the current `82fcac33...` image/backups again.

## 2. Stage only the HFS fixture

The successful physical SD evidence is
`mac-sd-read-link-restored-continuation-20261012/{state.json,serial.bin}`.
It records two explicit capture segments, not continuous RX. All sixteen
ordered sector records are independently reconstructed by the HFS guard.

```sh
python3 tools/rpi5/stage_hfs_fixture.py \
  --fixture build/rpi5/hfs-read-fixture-h9wpku5p/reference.json \
  --sd-baseline-reference build/rpi5/sd-linux-reference-99_23_zu/reference.json \
  --sd-trial build/rpi5/mac-sd-read-link-restored-continuation-20261012/state.json \
  --preflight build/rpi5/bl33-probe-unsh3788/preflight-recheck.json \
  --output build/rpi5/hfs-stage-executed-20261012 --execute
```

Never reuse that output directory or retry an uncertain remote outcome. Inspect
the saved remote run instead. The stager saves/verifies the entire FAT span and
original MBR on NVMe before writing the reserved 128-MiB data extent. It publishes
only the second partition entry after two full data readbacks. It does not
replace a boot image, mount HFS or reboot.

## 3. Capture the complete Linux HFS reference

Use `capture_hfs_reference.py` with the same fixture and original SD baseline.
This reads the whole new partition twice without mounting it. Its new output
reference must be less than 30 minutes old when the HFS trial is armed.

```sh
python3 tools/rpi5/capture_hfs_reference.py sandrzej@192.168.4.23 \
  --fixture build/rpi5/hfs-read-fixture-h9wpku5p/reference.json \
  --sd-baseline-reference build/rpi5/sd-linux-reference-99_23_zu/reference.json
```

Record the returned directory; do not guess it. Re-run the 28-check HFS package
preflight for `bl33-probe-qxmk1ban`, kernel `fresh-det6u9i4`, userland
`hfs-read-userland-v3-20261011` and build manifest `run-orwggdmn`.

## 4. Install only the distinct HFS boot image

`stage_hfs_boot.py` requires the fixture, original SD baseline, successful SD
capture, fresh HFS Linux reference, HFS package preflight, and fixture stager's
actual plan/result. Default mode writes only a local plan. Use `--execute`
only after those actual inputs exist and pass. Its flags are:

```text
--fixture --sd-baseline-reference --sd-trial --reference --preflight
--staging-plan --staging-result --output [--execute]
```

The installer freshly verifies the exact Linux/card/two-partition identity and
reads the complete HFS data twice before any SD mount. It checks inactive
automounters, unmounted media, no holders, the full original 512-MiB FAT backup,
original MBR backup, current image, Gate 3 image, proven-shell backups, BL31,
DTB and configuration. It saves the passed SD image separately to NVMe and SD,
fsyncs/readback-verifies the new temporary image, then renames it to `probe.bin`.
Unknown existing backup/temp files fail closed; nothing is silently overwritten
or automatically rolled back. FAT rename is not claimed power-loss atomic.

After installation it verifies every protected boot file again, unmounts FAT,
and repeats both complete HFS reference reads. It never changes the partition
table, HFS contents, configuration, EEPROM or Pi power. Only a validated
`status=installed` report authorizes the next boot step.

## 5. Arm first, then one software reboot

Stop/release the old receive-only fallback capture only after Linux is verified.
Use the existing `serial_hfs_read_trial.py` with all five evidence inputs and a
3600-second boot-wait window. Confirm its armed output before setting one-shot
SD boot order and rebooting verified Linux. Do not send input to Gate 3 images.

The revised trial requires the distinct HFS loader, SD capacity, intact HFS
registration and shell-ready markers plus preflight proof of the actual linked
all-of IOBSD/encoding-resource dependency before transmitting. The one-time
encoder printf can be torn by SMP chatter; no text is repaired or claimed
observed. The explicit zero-TX continuation preserves the original capture and
records its unobserved gap, then requires fresh shell readiness and nonce.
It performs two
read-only mount/full-file-hash/script-and-binary-exec/unmount cycles in one boot.
No repeated cold starts or soak are required for this step. A host-only check
or prepared fixture is not a physical HFS pass. Write durability remains the
separate final Gate 4 step after this read-only trial succeeds.

## Host validation scope

`test_probe_install_core` uses actual temporary regular files for fixed-name
publication, old-image preservation, symlink/link rejection, existing partial
work, bounded short writes/EINTR and readback failure. `test_stage_hfs_boot`
checks evidence binding, local-only default, rejection before network/mkdir,
unknown-outcome preservation, isolated reference-program globals and the exact
remote wrapper with mocked mount/reference I/O. Its publication path still uses
real temporary files. These tests do not prove FAT power-loss behavior, actual
SD installation, HFS mounting or XNU durability.
