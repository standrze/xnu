# Gate 4 write trial and missing-admission recovery

Current 2026-10-12 15:14 UTC: Gate 4 remains incomplete. See the
[requirement-by-requirement exit audit](GATE4-EXIT-AUDIT.md). Independent Gate 5
has since replaced `probe.bin` with a storage-disabled topology image, preserving
W3 and full snapshots. Its recorder is finished; old W1/W2/W3 wait handles below
are historical, not live. The latest FAT baseline is
`b200d1fcc91a2e36ba700b9967a8c5efc79c43a616575e7ce6286f98b98ade60`.
Do not rerun an old installer/control or assume the Pi is currently in SSD Linux.
The unresolved cache-state evidence still prevents write admission. No new
storage test, reboot, media operation or cache-state fallback is warranted.

## Linux control after W3 — completed comparison

Completed once at 13:09:49 UTC on 2026-10-12. Automatic SSD return was verified
at 13:08:02 UTC and independently over fresh SSH (new boot
`36ac234c-2a31-4b30-bb5d-de87fa5bd8e2`); the RX recorder was stopped deliberately
and preserved. Both old handles below are now terminal. Local plan
`sd-extension-linux-control-plan-20261012` passed, and distinct execution
`sd-extension-linux-control-20261012` exited 0. Its result SHA256 is
`15f963e70a6b29085e6c88a59345c09d4a8e727d7a5ca02763ac7cc63974debe`.

Linux returned R1 `0x900` and the same complete 512 zero bytes as W3, with the
sentinel replaced. All 20 backups and complete protected MBR/FAT/HFS hashes
passed before and after the one userspace CMD48 read. Zero writes/mounts;
cache admission/durability remain false. Linux `ext_perf=00` is not independent
cache-absence proof: its parser can skip feature parsing for zero extensions.
Next is independent protocol/card evidence, not another W3 boot or repeated
control read. Preserve all outputs and keep unknown-cache writes refused.
The original commands and recovery sequence below are retained as history;
do not execute them again merely because they are shown here.

W3 has already been installed and booted once. Its preserved trial ended at
12:07:00 UTC on 2026-10-12 with zero input/batch/mount. Actual SCR
`0205848700000000` decoded as SD6; the completed General Information read was
512 zero bytes. Do not rerun W3 or reinterpret that as absent cache.

Keep existing RX-only/SSD waiter handles **14191 / 23351**. After the waiter
reports ready, freshly verify exact SSD root/card/layout/new boot. If its saved
ready report has aged beyond 30 minutes, capture new readiness with
`wait_nvme_linux.py` in a fresh directory; do not reboot just to refresh it.
The old Linux boot before W3 was `8aeee895-7393-4bb8-bc00-a0ff23a54c8f`.
Stop the RX recorder deliberately only after current exact SSD return is proven,
preserving its original raw/state and the stop reason; do not leave it holding
the probe when another authorized trial eventually needs exclusive access.

Validate the new control locally:

```sh
python3 tools/rpi5/capture_sd_extension_reference.py \
  --installed build/rpi5/hfs-cache-diagnostic-installed-20261012 \
  --trial build/rpi5/mac-hfs-cache-diagnostic-trial-20261012/state.json \
  --linux-ready build/rpi5/wait-nvme-after-hfs-cache-diagnostic-20261012/state.json \
  --output build/rpi5/sd-extension-linux-control-plan-20261012
```

After it passes, use `--execute` and a distinct fresh output directory such as
`build/rpi5/sd-extension-linux-control-20261012`. The fixed program independently
checks exact current SSD/card/unmounted/unheld media/no automounter, all 20 NVMe
backups, and complete MBR/full FAT/full HFS hashes before and after one userspace
CMD48/FNO0/page0/offset0/LEN511 read. Full HFS equality to the original clean
fixture establishes the clean reference before that ioctl, without mounting
or repeating the completed XNU read-only milestone. It uses only an O_RDONLY
whole-card descriptor and write_flag=0. No cache toggle/flush, write, retry,
repair, mount, staging, reset, reboot or serial operation. Linux internal
transport behavior is not an exact wire-command-count claim.

Inspect complete actual returned bytes and R1 against W3's saved all-zero block.
A differing Linux register reply points to an XNU-path difference to investigate;
a matching zero reply alone still cannot prove cache absent/disabled. Preserve
both outcomes and do not relax admission without independent protocol/card
evidence. A timeout preserves an unknown-outcome marker and raw stdout/stderr;
inspect it, never automatically issue a second ioctl. This control cannot pass
Gate 4: the full admitted write/reboot/fsck/RO-persistence/protection chain below
remains required.

## Historical W2 cache failure and W3 preparation — 2026-10-12

This sequence is retained as installation history, not current instructions.
W3 has already run and failed closed. The old handles below are obsolete;
use the Linux control sequence at the top of this document next.

W2 physically failed at `CACHE_PROBE RC=-5 CMD=13` before admission. The original
33150-byte capture/state remain immutable; zero TX/batch/HFS mount. `-5` is an
unsupported observation, not a transport diagnosis; CMD13 was the last command,
and cache/spec output remains atomic on failure. Do not infer absent cache.

Keep live RX-only/SSD waiter handles **78529 / 58883**; poll those same processes
until a new boot of exact SSD Linux is verified. W2's Linux boot before the SD
trial was `920d20af-a50c-46c1-baa6-fda846f07820`; the return must differ. No serial
input, SD access, manual restart or repeated soak while XNU still runs.

Recapture the two complete clean HFS reference reads using the command below.
Create a new initial-style current-input bundle with that reference, the new
Linux-ready report, unchanged RO history/userland and the freshly inspected
W3 package `bl33-probe-ra00dsr1/write-preflight.json`. W3 only adds precise
cache stage/completed-buffer diagnostics; it does not claim to fix decoding.
New outer bundle (template, not authority to reuse stale references):

```json
{
  "current_inputs": "build/rpi5/hfs-cache-diagnostic-current-inputs-20261012.json",
  "previous_plan": "build/rpi5/hfs-write-diagnostic-installed-20261012/plan.json",
  "previous_result": "build/rpi5/hfs-write-diagnostic-installed-20261012/result.json",
  "previous_trial": "build/rpi5/mac-hfs-write-diagnostic-trial-20261012/state.json"
}
```

```sh
python3 tools/rpi5/stage_hfs_cache_diagnostic.py \
  --inputs build/rpi5/hfs-cache-diagnostic-inputs-20261012.json \
  --output build/rpi5/hfs-cache-diagnostic-plan-20261012
```

Default is local-only; execute only with a distinct fresh output directory and
`--execute`, after the complete current checks pass. The exact installed W2 FAT
must equal `f9e89a9531b749c949c22cf3c57948735322dd05cf9df45e64f76cd461325dc8`.
Full MBR/FAT/HFS backups precede replacement, and W2 is saved as
`hfs-write-cache-probe-failed.bin` on NVMe and
`probe.hfs-write-cache-probe-failed-20261012.bin` on SD. W1, RO and every older
image/full snapshot are reverified/preserved. No HFS mount, repair, partition or
configuration change, automatic retry/rollback or reboot is performed by staging.

Then arm a fresh `serial_hfs_write_trial.py` output with the new outer bundle and
actual completed `write-cache-diagnostic` installation before one software SD
reboot. It selects the complete new validator; no failure can authorize input.
If admission is still absent, preserve the complete decoder-stage/raw-buffer
capture and diagnose that actual observation. If a batch passes, the unchanged
full physical persistence chain below remains mandatory. The capturer retains
20 NVMe records covering both failed write images and all snapshot generations.

## Historical W1 failure and W2 installation sequence

The first write image booted, but no complete
`WRITE_ADMITTED` prefix appeared. The recorder's 600-second wait ended with
zero input, zero batch attempts and no filesystem mount. This is not an
identified cache/transport/matching failure or a write pass. Preserve the failed
state/raw capture and the installed image. Exact artifacts/hashes are in STATUS.md.

The serial guard only admits intact fresh terminal/write loader lines, an exact
250347520-sector card / `[1050624,1312768)` extent / nonzero epoch / cache absent
or disabled, HFS registration, then a subsequent shell-ready line. HFS and
storage service matching can complete in either order. Old images, enabled or
unknown cache, missing/torn admission, duplicate startup, panic and explicit
initializer failure all prevent TX. There is no implicit resume or cleanup.

## Resume after the current automatic SSD return

Keep the existing RX-only recorder and SSH waiter handles. An observation
timeout is not a process failure; poll the same handles. Do not start another
soak/trial, send serial commands or ask for a manual power cycle. On actual
SSD return, require hostname `kamidana`, exact root
`/dev/nvme0n1p2 ext4 04570742-280b-43cb-9564-73d454243b1c` and a boot ID different
from `54b2ad20-73c0-4dc2-a6b7-c96506b04a0a`. Stop RX deliberately only after
verification, preserving its state/raw bytes and recording the stop reason.

Recapture two full clean HFS reads without mounting or writes:

```sh
python3 tools/rpi5/capture_hfs_reference.py sandrzej@192.168.4.23 \
  --fixture build/rpi5/hfs-read-fixture-h9wpku5p/reference.json \
  --sd-baseline-reference build/rpi5/sd-linux-reference-99_23_zu/reference.json
```

Both complete 128-MiB hashes must still equal
`168c89cb97645ba07b353b3584087e5770d9c2793c6e86b7a8bc3471cbb477e1`.
The original W1 installation/bundle/failure artifacts remain immutable.
Create a **new** initial-style write input bundle, retaining the RO history but
using the new Linux-ready state, fresh reference (30-minute freshness gate),
and `bl33-probe-p8k9tahf/write-preflight.json`. Reuse the unchanged write userland.

Then create a diagnostic evidence bundle with exactly these keys (template;
`current_inputs` names the newly created fresh bundle, not the old W1 bundle):

```json
{
  "current_inputs": "build/rpi5/hfs-write-diagnostic-current-inputs-20261012.json",
  "previous_plan": "build/rpi5/hfs-write-installed-20261012/plan.json",
  "previous_result": "build/rpi5/hfs-write-installed-20261012/result.json",
  "previous_trial": "build/rpi5/mac-hfs-write-trial-20261012/state.json"
}
```

Validate locally before any network/media action:

```sh
python3 tools/rpi5/stage_hfs_write_diagnostic.py \
  --inputs build/rpi5/hfs-write-diagnostic-inputs-20261012.json \
  --output build/rpi5/hfs-write-diagnostic-plan-20261012
```

This does not connect or open a device. Actual execution requires `--execute`
and a distinct fresh output directory. It pins the actual old installation and
zero-input failure hashes; historical artifacts are not falsely rescreened as
fresh against later modified sources. The **new** package still undergoes all
actual linked-byte/build/source checks. New SSD boot, unchanged identity/RO
prerequisites and linked startup diagnostics are mandatory.

The remote wrapper verifies identity, no mounts/holders/automounters, existing
backups, and fresh complete MBR/FAT/HFS snapshots on NVMe. The complete current
FAT must equal W1's post-install baseline
`012f02a8f4759038a93f92551e98d5705fdba84166cd4a6b4206044bce9e0f77`
before any SD filesystem write. All full backups and the passed RO NVMe image
are rechecked. It preserves W1 as `hfs-write-no-admission.bin` on NVMe and
`probe.hfs-write-no-admission-20261012.bin` on SD, retaining
`probe.hfs-read-passed-20261012.bin` and every older backup. It changes only
the normal boot image via readback-verified temporary publication. No HFS mount,
partition/config change, reboot, retry, repair, forced unmount or power-loss
atomicity claim. Any unknown outcome requires inspection of the existing run.

Arm `serial_hfs_write_trial.py` with the diagnostic bundle and successful
diagnostic installation directory **before** the one-shot software SD reboot.
The recorder selects the full diagnostic plan validator based on the installed
profile and rejects failure markers before TX. Do not reuse the old failed
recorder/output directory or bypass missing admission. New startup diagnostics
identify handoff, identification, allocation, cache probe/refusal, MBR/primary/
alternate read, authorization, mapping, properties and worker-start failures.
Stored diagnostic printing adds no MMIO/card operations or admission retry.

## Required eventual physical write and persistence proof

One admitted boot runs only one fixed five-file `hfswrite exercise` batch,
including empty, partial, cross-page, overwrite/truncate and append cases.
Each operation fsyncs and same-boot reads; the recorder independently hashes
all five complete serial file dumps, then requires normal unmount and verified
covered-root restoration. Failure does not send cleanup or retry commands.

Even success is `batch_passed_not_durability`. Keep Gate 4 active until an
intervening actual reboot is established, complete card/partition identity and
protected MBR/FAT/image backups are independently reverified, filesystem
consistency/fsck succeeds without repairs, and a verified read-only remount
returns every byte/hash of all five written files plus the unchanged fixture
files. Linux currently has no HFS fsck tool; a hash-verified complete partition
image can be attached **read-only** on the Mac, fscked without repair, mounted
read-only and fully checked, then detached with unchanged raw-image hash.
Those post-reboot capture/fsck tools are now implemented and host-tested, but
have **not executed against a Pi-written partition**. The fixed-vector helper,
synthetic image smoke and host tests do not prove physical durability.
Do not repeat the already passed RO mount cycles, cold boots or Gate 3 soak.

## Post-batch capture and Mac audit (only after an actual admitted batch)

`capture_hfs_persistence.py` requires the actual successful write recorder's
state and complete raw transcript. It independently parses the cache-off
admission, fresh shell nonces, one writable mount/status/batch, all five
complete serial file frames, normal unmount and covered-root restoration.
Exact transmitted-byte coverage and installation/source hashes are required.
The original launch time is used only for historical evidence validation;
it does not authorize installation or writes using a stale reference today.
The actual W1 failed/zero-input state is rejected before network/output/media
access, including with `--execute`.

Local validation first (replace placeholder artifact names with the actual
successful trial and its installation; none currently exists):

```sh
python3 tools/rpi5/capture_hfs_persistence.py \
  --inputs build/rpi5/ACTUAL-WRITE-INPUTS.json \
  --installed build/rpi5/ACTUAL-WRITE-INSTALLATION \
  --trial build/rpi5/ACTUAL-PASSED-WRITE-TRIAL/state.json \
  --output build/rpi5/hfs-persistence-local-plan
```

Execution uses `--execute` and another fresh output. It requires a fresh SSH
answer on the exact NVMe root with a different Linux boot ID, then checks the
exact card/layout, unmounted/unheld SD and disabled automounters before and
after capture. All preserved NVMe backups are fully rehashed twice. The entire
512-byte MBR and 512-MiB FAT must match the **latest installation's post-install
baseline** (not an older W1 baseline if a successor was installed). This full
FAT equality covers every boot image/configuration/backup byte, not just a
sample or directory entry.

The HFS partition is read completely three times; the middle pass creates
`hfs-partition.after-write.img` exclusively on fresh verified NVMe, fsyncs it,
and verifies a complete readback. All three 128-MiB digests must agree and
differ from the original fixture. Every SD descriptor is read-only; there are
no SD mounts, repairs, staging, serial input or reboots. The artifact is copied
to a new local directory, its complete hash/header are checked, and exact Linux
boot/root is rechecked after transfer. Unknown outcomes preserve existing
artifacts without retry. `capture.json` remains `captured_not_durability`.

Then validate the **captured image**, never a device path:

```sh
python3 tools/rpi5/audit_hfs_persistence_image.py \
  --image build/rpi5/ACTUAL-CAPTURE/hfs-partition.after-write.img \
  --expected-sha256 ACTUAL-CAPTURE-JSON-IMAGE-SHA256 \
  --fixture build/rpi5/hfs-read-fixture-h9wpku5p/reference.json \
  --output build/rpi5/hfs-persistence-mac-local-plan
```

Again, `--execute` needs a distinct fresh output. Only the validated local
regular image can be attached. Pre-existing attachments are never disturbed.
The first attachment is verified read-only/unmounted for `/sbin/fsck_hfs -fn`;
the second is independently verified read-only HFS at the exact mount/device.
All five original fixture files and five write vectors are read fully twice,
with no-follow paths, same-device/type/length/hash guards and original modes.
The utility logs every command/output hash, refuses repairs/force/retry, and
detaches only an unambiguous attachment of its own image. Both detachments,
unchanged full image/header and unchanged audit/helper source hashes are
required. A local audit alone never sets `durability_verified` to true: bind
it to the real capture/new-boot/write evidence for the final Gate 4 audit.

At 05:24 UTC the new 27-test host group passed, as did the earlier 123-test
focused storage/installer/provider group. Native Mac synthetic smoke
`hfs-persistence-audit-smoke-xp2vaz9x/smoke.json` reports successful no-repair
fsck/read-only remount/all ten files/two detachments/unchanged image. Its audit
result SHA256 is
`626fe06d143c22c1a454864bee53654e479f80c266a2eeb7fee388f42953f8b1`;
synthetic image SHA256
`1faef5619151652486b96a734d1c81b552a72c6871a15c80461d877e58231f77`.
This is genuine Mac virtual-filesystem execution on a generated image, **not
physical SD writes, a Pi reboot, or Gate 4 exit**. All 29 prepared W2 package
checks were rerun and exactly match the preserved preflight; W2 is still not
staged/booted. Keep the existing RX-only capture/SSD waiter while XNU runs.

## Final evidence-chain check

`check_hfs_persistence.py` performs no network, serial, mount or device access.
It revalidates the actual admitted write transcript/installation, captures the
hashes of every trial/capture/Mac log/image artifact before and after checking,
and requires exact write → new Linux boot → capture → Mac audit chronology.
It checks all 15 Mac commands and their actual stdout/stderr hashes, the exact
read-only attachment ownership/geometry at each stage, no-repair fsck flags,
normal detachments, both diskutil volume records, all ten file records,
unchanged image/header/fixture and unchanged source hashes. It does not accept
an unrelated image audit, stale boot, success boolean, changed evidence, repair
flag, forced detach, writable attachment or mixed partial runs.

Only after the real capture and image audit both succeed:

```sh
python3 tools/rpi5/check_hfs_persistence.py \
  --inputs build/rpi5/ACTUAL-WRITE-INPUTS.json \
  --installed build/rpi5/ACTUAL-WRITE-INSTALLATION \
  --trial build/rpi5/ACTUAL-PASSED-WRITE-TRIAL/state.json \
  --capture build/rpi5/ACTUAL-POST-REBOOT-CAPTURE \
  --audit build/rpi5/ACTUAL-CAPTURED-IMAGE-MAC-AUDIT \
  --output build/rpi5/ACTUAL-PERSISTENCE-ACCEPTANCE.json
```

The output proves the persistence portion only; review all original Gate 4
requirements separately before marking the goal complete. No successful
physical acceptance artifact currently exists. At 05:34 UTC, 36 focused
capture/Mac/transcript/final-chain tests pass. The actual synthetic Mac smoke's
15 command logs/ownership/full-ten-file records were independently revalidated,
still explicitly `durability_verified=false`. Combining that smoke with the
actual failed W1 trial is rejected **before output/external access**. Capturer
state/raw evidence is also rehashed after backup validation so a mid-validation
change cannot be bound as if it were the originally parsed transcript.
