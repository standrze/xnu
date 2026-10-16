# Gate 4 — SD storage and HFS+ (in progress)

Started 2026-10-11 after the repeatable serial-shell milestone. This is the
original Gate 4 scope: BCM2712 SDHCI, pinned IOStorageFamily, HFS+, repeatable
mount/read validation and separately verified write durability. A host model,
firmware-loaded RAM disk, or register snapshot does not satisfy this gate.

Current goal status: active. Physical XNU SD reads passed at 2026-10-12
01:04:33 UTC: sixteen complete raw sector records (eight LBAs, two passes)
match independent Linux hashes, userspace bounds rejection and the final live
shell passed. SD handoff returned RC=0 STAGE=7 and the published read-only
capacity was 250347520 sectors. Writes and DMA remain disabled. Repeated HFS
mount/read/exec/unmount passed at 03:12:40 UTC in one boot; separately proven
durable writes remain required.

Latest physical HFS checkpoint (03:12:40 UTC): the distinct correction installer
preserved the failed image and all old backups, installed `bl33-probe-a5wng87t`,
and left complete HFS bytes/protected boot files unchanged. After fresh recorder
arming and one software SD reboot, both read-only HFS cycles passed. All five
files were completely reconstructed/hashed twice (134590 bytes); the recovery
script and HFS binary ran twice; missing-file recovery, non-forced unmounts and
the final live shell passed. Independent raw rechecking verified all ten hashes
and mount/status/unmount order. Evidence:
`mac-hfs-stats-corrected-trial-20261012/{state.json,serial.bin}`; raw SHA256
`9c276399b75fa03d4d3058cd3dada12e73ff82787ee264ff215929e41f4aa315`.
This is one-boot repeatability, not a durability/cold-boot/full-Gate-4 pass.
The passed image is retained; next is a distinct write trial with real cache
state/synchronization, writable provider/mount, then reboot/remount/fsck/readback.

Earlier physical HFS checkpoint (02:14 UTC): the guarded fixture/boot installers
executed successfully, preserving full FAT/MBR and known-good image backups.
The distinct HFS image booted, registered HFS and published `/dev/disk0s2`.
The unchanged read-only trial then stopped before mounting because statfs64
on the RAM root returned ENOTSUP: mockfs had no VFS_GETATTR handler. No HFS file
read or exec pass is claimed. The archive-only getter correction and bounds
tests are prepared; the subsequent fresh kernel/package build succeeded and
all 29 corrective package checks pass, including the actual linked VFS getter
pointer. The expanded regression passes all 177 tests in one run.
At that checkpoint the corrected image had not been installed; the
distinct corrective installer required fresh Linux and full HFS reads. The current card
has two partitions and the installed HFS image, so the original first-time
stagers must not be rerun. See [current status](STATUS.md) and
[the correction checkpoint](GATE4-MOCKFS-STATFS.md). Earlier paragraphs below
describe their original checkpoints, including before HFS staging occurred.

## Resumed physical SD trial — 2026-10-12

The user confirmed U-to-UART wiring and returned SSD Linux. A fresh marker
reached the Mac at 00:57:52 UTC (44 bytes received; Pi TX 533 to 577; host TX
zero). Original card identity/eight sector hashes, installed `82fcac33...`, both
`bf01b0ee...` shell backups and Gate 3 backup were freshly checked. All 22
package checks passed again. FAT was inspected read-only and unmounted.
The recorder was armed before the 00:59:12 UTC one-shot SD software reboot.
No SD image rewrite was needed. XNU initialized the controller/card and exposed
the actual BSD raw disk, then produced valid sectors through the real driver.

The first recorder stopped on `list index out of range`: an exact nonce text
arrived at the end of one host read before its terminating newline. The old
split-line presence check ran ahead of its complete-line regex. The command
receiver now waits for complete output lines before inspecting matches/prompt;
chunk-boundary regressions pass. This was not an XNU or SD error.

`continue_sd_read_trial.py` permits only that specific recent host failure,
with exact image/reference/preflight/raw bindings, clean prior readiness,
independently reconstructed ordered sector prefix and a completed nonce/prompt.
It rejects device errors, missing/changed/stale evidence and observed reboots.
It recovered the third completed record from raw bytes, challenged the existing
shell with a fresh nonce, then collected only the remaining thirteen reads.
The original failed run stays unchanged. The new raw file preserves its whole
prefix byte-for-byte and appends a second capture segment; metadata explicitly
records the closed-port interval as unobserved, not continuous RX.

Successful run: `mac-sd-read-link-restored-continuation-20261012`;
original run: `mac-sd-read-link-restored-20261012`;
Linux baseline: `sd-linux-reference-99_23_zu/reference.json`.
The successful raw capture independently passes the existing HFS evidence guard.
`hfs-stage-plan-after-sd-pass-20261012/plan.json` was generated locally only:
no network/media access, HFS partition creation, HFS mount or boot-image change.
The SD checkpoint passed 141 focused host tests. Next execution requires
fresh verified SSD Linux; no new soak or shell cold-boot qualification is needed.

The separate HFS package also freshly passes all 28 checks. Its guarded boot
installer is now prepared in `stage_hfs_boot.py` and `probe_install_core.py`.
Twelve focused host tests cover evidence binding, native regular-file install
faults, partial-work rejection, isolated reference execution, exact remote
workflow ordering and timeout preservation. It requires the fixture stager's
successful result/full FAT backup and a fresh whole-HFS Linux reference before
any SD mount. Neither installer nor fixture stager has run on the Pi.
The expanded focused Gate 4 regression passes all 155 tests, including the
unlinked write-admission policy's two sanitized/native/freestanding tests.
The receive-only fallback recorder remains live, with readable watchdog reload
markers observed; no additional soak or SD boot was started. See
[HFS execution sequence](GATE4-HFS-EXECUTION.md).

## Linux returned; UART link diagnosis — 2026-10-12

SSH verified NVMe Linux at 00:22:15 UTC after the user's restart. The empty
`mac-sd-read-powerbit-restart-20261012` recorder was deliberately interrupted
at 00:25:55 UTC for diagnostics, not restarted on an observation timeout.
Its final state records zero received/transmitted bytes and no reads.

Linux binds `/dev/ttyAMA10` to the physical debug UART at `0x107d001000`,
115200 8N1, with its serial getty active. A bounded Linux marker increased the
kernel UART TX counter from 204 to 249, yet the Mac capture received nothing.
A separate receive-only Mac diagnostic tested normal open, explicit DTR and
CDC rearming; each Linux marker advanced the TX counter, ending at 360, but
all three phases received zero bytes. DTR was already asserted (`modem_bits=6`);
there is no demonstrated DTR-only fix. Mac settings were restored and the port
released. No host serial data, Pi reboot or firmware change was issued.
The [tagged probe firmware](https://github.com/raspberrypi/debugprobe/blob/debugprobe-v2.3.1/src/cdc_uart.c)
gates its UART task on CDC connection/DTR; this check ruled out simply omitting
that assertion, not every possible probe/cable fault.

`sd-linux-reference-q4vicnpw/reference.json` matches the original identity and
all eight sector hashes. A read-only FAT inspection confirms installed image
`82fcac33...`, SD/NVMe shell backups `bf01b0ee...`, and unchanged configuration,
BL31 and DTB hashes; FAT was unmounted afterward. No partition or HFS action
was performed. Full diagnostic observations are saved in
`build/rpi5/linux-uart-diag-20261012/observations.json`.
Keep Linux up and inspect the probe/UART cable path before another boot trial.

## Independent raw SD evidence guard

HFS staging now independently reconstructs all sixteen ordered sector frames
from the prior raw capture and compares complete bytes/hashes with the Linux
reference, after checking the report/hash binding and readiness-before-read
ordering. A rehashed readiness-only/truncated/reordered/extra/corrupt capture
cannot authorize media writes. The SD frame parser accepts LF, CR-LF and the observed
CR-CR-LF only; embedded carriage returns and interleaved frame chatter fail.
Unrelated torn SMP logs outside frames are retained without normalization or
being used as sector evidence. The focused host regression passes 141 tests, including these synthetic fault
cases. These tests are not physical SD-read or HFS acceptance.

## HFS fixture staging tool — prepared, not executed

`tools/rpi5/stage_hfs_fixture.py` now provides a separate, explicit `--execute`
path for the future HFS fixture. Default mode generates only a local plan.
Both modes require a successful physical SD-only trial and its unchanged raw
capture, original card reference, actual package preflight and validated Mac
fixture. The successful segmented SD capture above passes these guards; failed
or incomplete trials cannot authorize HFS staging.

The remote path requires freshly verified NVMe Linux, exact original card and
one-partition layout, unmounted media, no holders and inactive automounters.
It saves the original/planned MBR and a complete, readback-verified 512-MiB FAT
backup in a fresh NVMe directory before opening the exact SD card for writing.
Only the reserved 128-MiB data extent and the MBR sector can be written. The
data must hash correctly in two complete readbacks; the protected boot span and
original MBR are checked again before publishing the new partition entry.
Boot data is hashed again afterward. No boot image, HFS mount or reboot is
performed. A partial publication or observation timeout requires inspection of
the existing backup/run, never automatic rollback or a blind retry.

Eighteen focused synthetic tests pass for the bounded copy/publication core,
backup readback, protected ranges, short I/O, source/data/boot/MBR faults,
evidence guards, local-only default, result coverage, early remote rejection,
the full remote-wrapper ordering/close paths and timeout diagnostic preservation.
The complete focused Gate 4 host regression now passes 130 tests. Actual
current failed SD evidence is also rejected before network/device action.
These are host fault models, not physical staging or durability evidence.
The tool has not been executed against the Pi and no HFS partition is claimed.

## Corrected power-bit physical trial — started 2026-10-11 23:51 UTC

After the user returned the Pi to SSD Linux, SSH verified the exact NVMe root
and original inserted, unmounted SD card at 23:49:42 UTC. Independent captures
`sd-linux-reference-sbvl6ffg` and `sd-linux-reference-eq89is1q` bracketed staging;
the full identity and eight sector hashes match each other and the preserved
reference. The exact corrected package `bl33-probe-unsh3788` passes all 22
fresh preflight checks (`preflight-recheck.json`).

Recorder `mac-sd-read-powerbit-20261011` was armed before staging and the
one-shot SD software reboot. Staging completed at 23:50:53 UTC with both
working-shell backups matching `bf01b0ee...`, the failed register diagnostic
preserved separately, and the FAT remounted read-only. At 23:51:19 UTC the
script verified root/image again, unmounted FAT and requested one SD boot.
No HFS partition or EEPROM change was performed by the agent. The software-boot
capture received no UART data. A UART-lead check and one physical restart were
requested, but no confirmation was received within the capture window.

The existing recorder exited at 2026-10-12 00:00:43 UTC with a boot-marker
timeout. `mac-sd-read-powerbit-20261011/state.json` reports `status=failed`,
zero received bytes, zero transmitted bytes and an empty reads list. Empty raw
capture SHA256 is `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
This is a failed observation/inconclusive physical trial, not evidence of an
SD-controller failure or successful XNU boot. The port is released; the latest
SSH probe reports no route to host. No new recorder was started solely because
the observation expired. The installed image remains unchanged. Resume after
confirmed hardware/connectivity state, and arm a fresh bounded recorder before
any further requested boot; allow a full one-hour window for manual actions.

The user subsequently confirmed another restart and reported an SD-card boot.
The separate one-hour recorder `mac-sd-read-powerbit-restart-20261012` is now
running; its live process handle and open probe/capture descriptors were checked.
At this checkpoint its capture remains empty and SSH times out. No serial
input, additional power operation, media modification or HFS action has occurred.
The reported boot source is retained as operator context, not treated as an
observed XNU startup or a storage result. The existing recorder remains the
observation handle; do not start a competing reader or restart merely to refresh
an observation window.

## Complete-file verification tooling — 2026-10-11

`tools/rpi5/hfs_read_results.py` verifies complete hex-dumped bytes for the
five whitelisted fixture files. Its caller must first establish package,
physical-media reference and fresh HFS/SD/shell boot readiness. Unique nonce
lines bracket each read; exact row syntax, byte counts and complete SHA256
matching reject partial, interleaved or corrupt results. Empty files and
partial final rows are handled explicitly. File size is capped at 64 KiB and
serial response size at 256 KiB; the generic command helper retains its old
64-KiB default unless a caller explicitly opts in. Native sanitizer-backed
tests execute the unchanged target hexdump utility and feed its output into
this parser, including the 33,034-byte cross-page fixture. This verifies host
format compatibility, not physical HFS reads or target syscall behavior.

`tools/rpi5/capture_hfs_reference.py` is a separate read-only Linux capture
profile; the existing one-partition SD capture has not been relaxed. It checks
the original CID/CSD/capacity, NVMe root UUID, FAT partition identity and exact
future second partition (type `af`, start 1,050,624, size 262,144 sectors,
label `XNU_G4_READ`, PARTUUID `5ae1f07e-02`). It rejects a mounted second
partition before opening only `/dev/mmcblk0p2` with O_RDONLY/O_NOFOLLOW,
cross-checks its block descriptor/capacity, and hashes all 128 MiB twice. Both
passes must equal the independently checked Mac raw-image hash. Identity is
checked again afterward, and local image/reference changes are rejected.
It never formats, partitions, mounts, stages, reboots or sends serial input.
This profile cannot pass against the current one-partition SD card.

Host regression now passes 104 tests, including mocked wrong-root/layout,
mounted-media, descriptor/capacity, short-read, replacement and unstable-data
faults. The existing local Mac fixture also passes the new immutable-image
validation. No physical two-partition reference exists, no HFS recorder is
armed, and no SD partition has been created. The isolated SD diagnostic below
remains the next physical trial; real mount/read acceptance and separately
verified write durability remain required.

## Register diagnostic physical outcome — 2026-10-11 23:18 UTC

NVMe Linux returned and root `/dev/nvme0n1p2` / UUID
`04570742-280b-43cb-9564-73d454243b1c` was freshly verified. Independent SD
captures `sd-linux-reference-gac25ncf` and `sd-linux-reference-iijtllhd`
bracketed staging; identity and all eight sector hashes were unchanged.
The exact diagnostic package `bl33-probe-qkovucms` passed 22 checks, was
staged with both working-shell backups matching their original hash, and
software-booted once with the established one-shot SD override. No EEPROM,
partition layout or data-filesystem change was made.

`build/rpi5/mac-sd-read-registerdiag-20261011/state.json` reports failure,
zero transmitted bytes and no reads; serial SHA256
`6fec0176736eae3c5d1cdd81e329d4a1fcf94021a7d0bb845eecb142c76b78b7`.
The complete first-failure line is:
`RPI5XNU:SD:READBACK BANK=0 REG=0x28 MASK=0xff00 WANT=0x0 GOT=0xe00`.
Thus the bus-power-enable bit cleared but the voltage-selection field remained.
The standard register definitions distinguish power-on `0x01` from the
3.3-V selection `0x0e` in the byte at `0x29`:
[upstream register definitions](https://raw.githubusercontent.com/torvalds/linux/master/drivers/mmc/host/sdhci.h).
These register facts are referenced, not GPL implementation code copied.

The correction preserves voltage selection and clears/checks only power-on
(`0x0100` in our 32-bit access at `0x28`). It does not infer actual rail voltage
from the host register or bypass external GPIO power-off/dwell/readback checks.
The native model now retains the captured voltage field and requires all
non-power bits to remain unchanged. A stuck power-enable bit still fails
before any GPIO rail change and records the exact first mismatch. The fix
passes focused host tests. A fresh full kernel now builds/links successfully:
`build/rpi5-xcode27/run-orwggdmn/manifest.json`, exit 0, source unchanged;
`build/rpi5-xcode27/fresh-det6u9i4/obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712`,
SHA256 `8055890c1fb379cb618b0dfddf046edc686e86525eb3fa93b4847405d58159ce`.
Storage compile screen `gate4-build-audit-r1mcr8e_` compiles all 61 units.
The next **SD-only** candidate is `build/rpi5/bl33-probe-unsh3788/`, SHA256
`82fcac33c8cc25e79aad1d8af1c0759d165b72ca8bc7fc63e82d9bc1780519dd`;
all 22 preflight checks pass. The separate HFS candidate is
`build/rpi5/bl33-probe-qxmk1ban/`, SHA256
`38c4f0e1bf927f4960a85493429a24be1119b9c00e94b29e2a2974b0e3c8d832`;
all 28 checks pass. At this build checkpoint both were unstaged/unbooted.
The corrected SD-only trial was subsequently staged/software-rebooted at
23:51 UTC as recorded above; the HFS image remains unstaged/unbooted.
The earlier register-diagnostic recorder exited and released the port, leaving
the Pi at the RAM shell before the later return to SSD Linux.

## Guarded HFS recorder — prepared, not armed

`tools/rpi5/serial_hfs_read_trial.py` validates five immutable evidence inputs
before creating output or opening serial: the HFS preflight, Mac fixture,
original SD reference, successful prior physical SD trial plus its raw capture,
and the fresh Linux two-partition full-image reference. It binds reference
hashes/source/host and rejects references older than 30 minutes, unexpected
future timestamps, changed images or incomplete SD read coverage. Fresh
distinct HFS loader, SD capacity, encoding-ready, HFS-registered and shell
markers are required before transmission; SD handoff/init failures abort.

One boot runs two ordinary read-only mount/status/directory/read/unmount
cycles. Each verifies all five full-file hashes, runs the HFS script, executes
the static HFS binary, checks missing-file recovery and verifies the mount is
gone after non-force unmount. Failure sends no cleanup commands into an
unknown kernel, only drains incoming diagnostics briefly before closing.
The physical diagnostic capture shows userspace CR-CR-LF line endings; the
hex/script parsers now accept these, CR-LF and LF exactly, while rejecting
embedded, torn or overlong carriage-return sequences. No blanket CR stripping
can conceal a corrupted hex row.
Eight synthetic recorder tests cover provenance/freshness, SD-only no-TX,
complete two-cycle sequencing and fail-stop behavior. The combined host
regression passes 112 tests; no HFS board acceptance is claimed and the
recorder is not armed because physical SD reads have not yet passed.

## Preserved working system

`build/rpi5/shell-userland-20261011/probe.bin` remains unchanged:
`bf01b0eedcce48249a7358772f74613d0b0453217f35576369945de25d50374f`.
The first physical trial below was staged and software-rebooted after fresh
NVMe-root, whole-card layout and boot-file hash checks. The known-good image
is preserved as `/mnt/xnu-probe/probe.shell-passed-20261011.bin` on the Pi SD
and `/home/sandrzej/xnu-shell-passed-backup-20261011.bin` on NVMe, both matching
the hash above. Only the explicitly identified disposable FAT boot image was
replaced; no partition table, firmware, NVMe filesystem or Mac disk was erased.

## Kernel adapter and physical read trial — 2026-10-11

`iokit/Kernel/BCM2712SDStorage.cpp` derives from the pinned real
IOBlockStorageDevice. It validates native DT properties, exclusively opens its
provider, maps exact Device pages, runs the bounded handoff, and serializes
read requests on one retained kernel worker. One mutex protects its bounded
queue; descriptors and completion records are retained/copied, completions
run outside the mutex, and stop drains cancellations. Rejected submissions
return an error without a duplicate completion. Writes, format, unmap, DMA,
cache enable, fake flush success and automatic reinsertion are not offered.
Host models do not prove that lifetime/concurrency contract under load.

The build opt-in remains `--with-storage-provider`. The distinct loader flag
`--gate4-sd-readonly` additionally requires `--gate4-storage` and the separate
serial recovery image; only it supplies `bcm2712_sd_readonly=1`. The old
snapshot-only flag still sends no SD commands. Matching entries for the real
block-storage driver, FDisk partition scheme and IOMediaBSDClient are now
present. HFS service matching/registration now has a separate build described
below; its physical execution, mounts and durability remain unproven.

The first adapter kernel built with 61/61 integration units and no undefined
symbols. Package `build/rpi5/bl33-probe-yj_k3qq_/probe.bin`, SHA256
`e78dbcef7a9206b3361c181e94d3a16c80ee54bf8206df3acb8250e70a0c0286`,
was staged and software-booted once. It reached XNU but IOCatalogue panicked
on a configuration syntax error **before the SD driver started**. Recorder
`build/rpi5/mac-sd-read-trial-20261011/` sent zero bytes; raw serial SHA256
`3aa727d0150de65f3dd6d919e88f51429120224977f7bf6ec52a2571296f32ad`.
The board automatically returned to freshly verified NVMe Linux. This is
failure evidence, not a storage or shell acceptance pass.

The actual OSUnserialize lexer permits letters/digits/hyphens in unquoted
strings, not underscores. All partition content labels are now quoted.
`kernel_config_syntax.py` uses the unchanged XNU grammar/lexer with inert host
object builders, and preflight resolves the actual linked
`gIOKernelConfigTables` pointer/string. It rejects the failed kernel and
accepts the corrected kernel. This syntax screen does not emulate OSObject
allocation, property-type semantics or IOKit matching.

The first boot also captured actual C0 initial registers: host CAPS
`0x55eec832`, VERSION `0x10020000`, PRESENT `0x1fff0000`, CONTROL
`0x00800f06`, CLOCK `0x000e0207`, CONTROL2=0, CQ_VERSION=`0x510`,
CQ_CONFIG/DOORBELL/PENDING=0, GPIO DATA=`0x16257`, DIRECTION=`0x1fde3`,
ODEN=0, AON mux=`0x76`, CFG pins=0. The initial synthetic model had wrongly
assumed CQHCI major 1. The exact board guard now requires captured 5.1.0
(`0x510`); the model exercises this captured digital profile as well as its
existing faults. This is not measured voltage, clock or firmware ownership.

Corrected full-kernel evidence:
`build/rpi5-xcode27/run-jjza__pd/manifest.json`, exit 0, source unchanged;
`build/rpi5-xcode27/fresh-imnxilse/obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712`,
SHA256 `c13064b37f92eb28233d1e94aa090300c9e43628affee4d1a79050083906917a`.
Corrected package `build/rpi5/bl33-probe-h5dd170l/probe.bin`, SHA256
`d9bcba80ea2e02054f0277e61d3e0b03f72168adf6d5200d24f89b413d3ec098`,
passes 22 preflight checks. Separate RAM userland includes `/bin/sdread`, which
opens only a whole `/dev/rdiskN` read-only, queries block size/count/write
protection, bounds a single 512-byte pread and emits exact indexed rows for
independent host SHA256 comparison. No private raw-I/O bypass is used.

68 focused host tests pass, including queue/binding bounds, actual producer-
consumer native property compatibility, source/header/object tamper guards,
real grammar syntax, read-only syscall faults and strict sector-output parsing.
The guarded recorder requires fresh storage-loader, driver capacity and shell
readiness before transmitting, then compares two reads of eight reference
sectors. Its userspace bounds check is explicitly not driver fault injection.

Fresh Linux references before/after corrected staging are
`build/rpi5/sd-linux-reference-2ivjm1l1/reference.json` and
`build/rpi5/sd-linux-reference-588dra0l/reference.json`: identity and all eight
sector hashes match. Staging log: `build/rpi5/bl33-probe-h5dd170l/stage.log`.
The corrected recorder `build/rpi5/mac-sd-read-configfixed-20261011/` captured
XNU startup and repeated RAM-shell readiness. The SD adapter reported
`HANDOFF RC=-4 STAGE=2 CAPS=0x55eec832 GPIO=0x14257` (the prefix was torn by
SMP UART writes). Stage 2 identifies a readback failure after stopping the
clock, before completing card power-off; it does **not** identify which
register failed. No card command/read occurred, and the recorder sent zero
bytes because SD readiness was absent. It was stopped after this explicit
failure, not rerun/soaked. Serial SHA256:
`ff8d239da6a7f3644cf0ee1f8c06d0ba9d40064b6e478e2c8bb1e13fa35f19bd`.
The port is free and the Pi was left at the RAM shell. The next source change
records the first mismatching bank/register/mask/expected/observed value without
weakening the guard; best-effort cleanup cannot overwrite that first failure.
The diagnostic kernel now builds/links successfully (exit 0, source unchanged):
`build/rpi5-xcode27/run-ywjzdmpn/manifest.json`, with 61 integration units;
kernel SHA256 `8889c71b6dd41f2ab1339ce1889df76bd4db4cd832027782a93e45964284f3ef`.
Its separate package is `build/rpi5/bl33-probe-qkovucms/`, probe SHA256
`cd920787529426f6d32130f067e6d153f59de263e4e6d1dd0d5a53f293262f96`;
22 preflight checks passed before the subsequent physical boot documented
above. Its diagnostics are checked
against injected masked-write faults, including retaining the first mismatch
across cleanup. The recorder now aborts on explicit boot/SD initialization
failure, receives diagnostic bytes for two more seconds, then releases the
port; no transmission is allowed without driver/shell readiness. The focused
regression command below, extended with personality, SD-read, shell and
serial-shell modules, now passes 69 tests. A separate serial-terminal-related
regression also passed 24 tests; these counts overlap, not additive coverage.

Do not stage until fresh NVMe Linux root/card identity are verified again.
The Pi was left at the second candidate's RAM shell, so absent SSH is expected
and not a new diagnosis. No immediate manual cycle has been requested.
No physical SD read, HFS mount or durable write is claimed. Older compile-only
evidence below is history and does not override this current trial status.

## Built-in HFS service ordering — offline integration 2026-10-11

Fresh SSH checks still timed out; no serial access, SD staging or power action
was performed during this integration. The prepared SD-only diagnostic
`bl33-probe-qkovucms` remains unchanged and still passes all 22 package checks.
It remains the next physical trial, isolating the failed power-handoff register
before adding filesystem activity.

`hfs-builtin-service.patch` applies after the existing configuration/startup
patches to a fresh HFS copy only. Its SHA256 and all adapted input hashes are
recorded in the storage compile manifest and verified before provider linking.
The actual built-in HFS and encoding classes now have BCM2712 DEVELOPMENT /
storage-provider-scoped IOResources personalities. Each start also requires
the separate `bcm2712_hfs=1` boot argument, absent from the SD-only diagnostic.
This does not mount a filesystem or enable any disk write operation.

The encoding service publishes `RPI5HFSEncodingsReady` only after the real
`hfs_converterinit`. HFS matches both this resource and `IOBSD`, not personality
text order. XNU's actual `IOResourcesMatchPropertyTable` iterates all resource
array elements; its `startCandidate` deliberately skips `checkResources` for
IOResources providers. `IOBSD` publication follows `vfsinit` in `bsd_init` /
`bsd_autoconf`. This gives an explicit dependency in place of the upstream
kext loader's ordering. Atomic claims prevent repeated initialization, even
following a failed registration. HFS zones are initialized before `vfs_fsadd`
can expose mountable operations. Only successful registration publishes
`RPI5HFSRegistered` / `RPI5XNU:HFS:REGISTERED`. Built-in service termination is
refused; defensive stop paths leave permanent converters, VFS state, zones
and early SYSCTL nodes intact rather than freeing live global state.

Host ASan/UBSan tests execute the actual patched service start/stop bodies
against doubles, checking missing/zero/invalid boot flags, super-start failure,
registration failure, exact initialization order, no false ready marker,
duplicate-start rejection and permanent lifetime. A second test executes
XNU's unmodified resource-matching function against host objects, requiring
both dependencies independently. These are not native IOKit scheduling,
VFS mount or physical card tests. The full focused regression command with
`tools.rpi5.tests.test_hfs_builtin_services` now passes **71 tests**.

All 61 storage/HFS/adapter units compile. The separate fresh full kernel build
completed successfully with source unchanged during the build:

- Build: `build/rpi5-xcode27/run-0ix3pyum/manifest.json`.
- Provider screen: `build/rpi5/gate4-build-audit-de5sxa_n/manifest.json`.
- Kernel: `build/rpi5-xcode27/fresh-hmifohd3/obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712`.
- Kernel SHA256: `5dfe83c8a69349224c2362ec883664eae7a9aed887c4b09f131528d22f329e57`.
- Both HFS service metaclasses are defined; no unresolved kernel symbols.
- Actual linked configuration passes the unchanged XNU grammar/lexer; table
  SHA256 `62528b28603e457c7fd07517331cd2e1b38d0f8c51ba67b11c76420d3e6c0942`.

This Xcode 27 build remains exploratory/noncanonical, not toolchain
qualification. The separate packaging below does not prove physical execution.
Physical HFS registration,
partition publication, read-only mounts and write durability are still open.

## Prepared read-only HFS trial package — 2026-10-11

`build_probe.py --gate4-hfs-readonly` requires the SD read-only/storage/serial
recovery flags and records its own compile switch, manifest field and fresh
loader marker. Only this distinct variant adds `bcm2712_hfs=1`; it retains the
SD driver's read-only gate. Existing SD-only and working shell binaries remain
unchanged. This is not the next image to stage: first isolate the controller
handoff with the existing SD-only diagnostic and prove physical sector reads.

`build_userland.py --hfs-read-trial --sd-read-trial` adds `/bin/hfsro` and a
fixed `/mnt/hfs` directory to a separate immutable RAM root. The pinned pristine
Apple `hfs_mount.h` is checked against its locked archive before compilation.
The actual public SDK headers supply mount, disk-ioctl and statfs definitions;
compile-time LP64 layout assertions and source/header SHA256 records guard the
argument ABI. An explicit SDK sysroot is required for these public headers.
The freestanding executable has no unresolved symbols or libc dependency.

The utility accepts only `mount|status|unmount /dev/diskNs2`, canonical N=0..31;
partition 1, whole/raw disks and arbitrary mountpoints are rejected before any
syscall. Mount requires the fixed path still be on the immutable mockfs root,
then opens the partition read-only, verifies 512-byte geometry and device
write protection, closes it, and calls the real Darwin mount syscall with
MNT_RDONLY/NOSUID/NODEV. No forced mount, update, journal override, formatting
or raw write is offered. It checks statfs64's exact HFS/source/mountpoint/flags
before emitting success. Status and unmount also require that exact identity;
unmount is non-forced and verifies return to the RAM root. Failed calls and
malformed/unterminated statfs results never emit a success marker. A clean
fixture will be required: read-only flags are not permission to replay a dirty
journal, and the underlying driver continues rejecting every write request.

Prepared artifacts (all local only):

- Userland: `build/rpi5/hfs-read-userland-v3-20261011/`; RAM-root SHA256
  `a10cfedbf2a07429bf8fa6e06d0166914f454937eb1f9493d1b9bbec9a847d5a`.
- Package: `build/rpi5/bl33-probe-ckh5_4dt/`; probe SHA256
  `c320892dfbec6b40f0a907710851f2a9619a28785a90ce6cabb92c14db5ec209`.
- Host identity evidence: package `hfs-preflight.json`, **28 checks pass**.
  This includes SD/shell baselines, actual linked configuration, both HFS
  service classes, converter-ready dependency, reviewed adaptation provenance,
  HFS compile/boot gates and distinct utility/mountpoint entries.

The first userland attempt lacked an SDK sysroot; the second exposed a
compiler-generated bzero from large aggregate initialization. Both failed
outputs remain separate and were never packaged/staged. The third uses an
explicit sysroot and bounded freestanding initialization stores. ASan/UBSan
syscall doubles exercise valid mount/status/unmount and open/ioctl/geometry,
mount, statfs identity/flags, interruption and unmount failures. Synthetic
package tests reject missing/changed flags, classes, dependency, adaptation,
screen hash, utility, mountpoint and base SD evidence. Together with the
existing focused modules and RAM-root tests, **84 tests pass**; this remains
host-only evidence, not filesystem acceptance.

**Not staged or booted. No HFS partition has been created on the SD, no serial
HFS recorder is armed, and this preparation made no SD changes.** A clean local
data image is now prepared below. Before
this package can run, prove the SD read-only transport, prepare/revalidate a
distinct partition 2 without changing partition 1 or its backups, capture an
independent file reference, and arm a fresh-marker-guarded recorder requiring
SD capacity, HFS registration and shell readiness before transmitting. Batch
repeat mount/read/unmount and executable-loading checks in that changed boot.
Write support and durability remain a separate subsequent acceptance step.

## Clean local HFS+ data fixture — 2026-10-11

`prepare_hfs_fixture.py` creates a fresh project-local image with Apple's
formatter (`HFS+`, layout NONE, UDTO raw format, 128 MiB); it never receives a
physical device as a formatter target. It validates standalone primary and
alternate H+ headers, exact geometry, clean unmount state and absence of
journaling/content protection/inconsistency. Alternate free-space counters can
lag the primary under Apple's `hfs_flushvolumeheader` / `altflush` rules; both
remain bounded and their actual values are recorded rather than required to
be identical. Neither geometry nor clean-state validation was relaxed.

The generated image is attached **read-only and unmounted** for native
`fsck_hfs -fn`, then detached and separately attached read-only for file
verification. Each device is resolved from hdiutil's unique exact image-path
mapping, reviewed single whole-virtual-device layout and 512-byte geometry.
Raw layout-NONE media may have an empty content hint; headers, fsck and the
mounted diskutil filesystem type establish HFS instead of inferring it from
that hint. Attachment ownership is checked again immediately before each
non-forced detach, including failure cleanup. No unrelated virtual/physical
device is formatted, mounted, repaired or detached.

Successful fixture: `build/rpi5/hfs-read-fixture-h9wpku5p/`.

- Raw image: `hfs-read.cdr`, 134217728 bytes / 262144 sectors, SHA256
  `168c89cb97645ba07b353b3584087e5770d9c2793c6e86b7a8bc3471cbb477e1`.
- Independent file/reference evidence: `reference.json` and native command
  logs. Mac fsck_hfs 715.160.9 checks extents/catalog/hierarchy/xattrs/bitmap and
  reports the non-journaled `XNU_G4_READ` volume appears OK, exit 0. The command
  was passed its authorized block-device alias and completed despite a raw-alias
  access warning. That warning is retained; no raw-alias validation is claimed.
- Read-only mounted files are each hashed twice: `/etc/proof.txt` (32 bytes),
  `/etc/empty`, `/etc/cross-page.bin` (33034 bytes), `/etc/recovery.sh` (69 bytes)
  and the real static arm64 `/bin/echo` (34160 bytes, Mach-O inspected but **not
  executed** during Mac validation). Modes and sizes also match the source.
- The complete raw-image hash is unchanged after both read-only attachments;
  both are detached. A fresh hdiutil inventory confirms no attachment for the
  successful fixture remains.

Earlier local attempts remain isolated: the first rejected unequal alternate
free counters; the second learned fsck needs device ioctls rather than a regular
file; the third rejected an empty unpartitioned-media content hint and cleaned
up its own attachment. These are fixture-tool diagnostics, not Pi attempts.
Five pure host tests cover header flags/geometry, stale backup counters,
symlink rejection and virtual attachment ownership/layout/read-only guards.
The expanded focused regression at fixture creation passed **89 tests**;
the later complete-file/recorder/handoff regression above passes 112.

**No Pi SD change, partition creation or HFS board trial occurred.** After the
controller diagnostic and physical sector-read acceptance, the planned data
partition can be a distinct 128-MiB partition 2 containing this exact raw image;
the existing FAT partition and backups must remain unchanged. Fresh Linux
readback must bind its full image hash and layout to the exact card before
booting a serial HFS test. The recorder now captures bounded complete file
bytes (not just `wc` counts), compares hashes, tests executable/script loading
and repeats mount/read/unmount as described above. Hex output for the
cross-page file and executable explicitly opts into the bounded 256-KiB
capture path; the generic shell-command default stays 64 KiB. Physical SD
read acceptance and a real Linux two-partition reference remain prerequisites.

## Exact input pins

`tools/rpi5/gate4-storage.lock.json` pins the Apple `macos-265` release
manifest at commit `83390100289cedfe669c31a96c94326d31afa1ed`. It names our
actual `xnu-12377.121.6` and the following components:

| Component | Tag | Commit |
|---|---|---|
| IOStorageFamily | 337.100.1 | `7edb88fbae296fb7c8ce2f64e115e116e566d51c` |
| hfs | 715.120.4 | `124b970fd5390f1c2cd6f985478616a04f6eeb1f` |

Archive SHA256 values and URLs are in the lock. Pristine sources are extracted
under `build/rpi5/gate4-sources/` and remain unchanged. Reviewed adaptations
are applied only to new isolated copies; an experimental kernel now links
them as described below. Preserve upstream license notices. Public availability
does not by itself settle distribution obligations.

Primary references:

- [Apple release manifest](https://github.com/apple-oss-distributions/distribution-macOS/blob/83390100289cedfe669c31a96c94326d31afa1ed/release.json).
- [Pi 5 board wiring](https://github.com/raspberrypi/linux/blob/43c132e8863c3bff3647033b6a7d2bf87b15501c/arch/arm64/boot/dts/broadcom/bcm2712-rpi-5-b.dts),
  [SoC register bindings](https://github.com/raspberrypi/linux/blob/43c132e8863c3bff3647033b6a7d2bf87b15501c/arch/arm64/boot/dts/broadcom/bcm2712.dtsi),
  and [controller-specific register facts](https://github.com/raspberrypi/linux/blob/43c132e8863c3bff3647033b6a7d2bf87b15501c/drivers/mmc/host/sdhci-brcmstb.c).
  Linux GPL implementation code is not imported into the transport.
- [SD host standards](https://www.sdcard.org/developers/sd-standard-overview/host-controllers/)
  and [FreeBSD protocol/register definitions](https://github.com/freebsd/freebsd-src/blob/main/sys/dev/mmc/mmcreg.h).
- [Pinned GPIO register facts](https://github.com/raspberrypi/linux/blob/43c132e8863c3bff3647033b6a7d2bf87b15501c/drivers/gpio/gpio-brcmstb.c),
  [C0/D0 pad layouts](https://github.com/raspberrypi/linux/blob/43c132e8863c3bff3647033b6a7d2bf87b15501c/drivers/pinctrl/bcm/pinctrl-bcm2712.c)
  and [CQHCI register facts](https://github.com/raspberrypi/linux/blob/43c132e8863c3bff3647033b6a7d2bf87b15501c/drivers/mmc/host/cqhci.h).

## Hardware contract and first implementation

The pinned board DTB has two enabled BCM2712 controllers. The removable card
slot is `/soc@107c000000/mmc@fff000`, not the non-removable SDIO controller at
`/axi/mmc@1100000`. New `rpi5_fdt_sdhci` checks the exact translated host span
`0x1000fff000..0x1000fff260`, config span `0x1000fff400..0x1000fff600`,
`host,cfg` register order, fixed 200-MHz clock graph, GIC SPI 273 / INTID 305,
4-bit wiring and both regulator references. It rejects malformed/duplicate
phandles, changed bindings, disabled paths and unsupported power sequences.
It publishes output atomically and performs no MMIO.

`rpi5_board_tree_sdhci` publishes native little-endian physical ranges under a
new root-level `sdio1` node. The host is outside the existing real `arm-io`
range: do not enlarge that bus or pretend the host lies in its window.

`iokit/Kernel/rpi5_sdhci_core.{c,h}` implements a bounded synchronous read-only
PIO transport: host reset, <=400-kHz 1-bit identification, CMD0/8/55/ACMD41,
CID/RCA/CSD/select/status and CMD17 single-sector reads. It decodes SDHC/SDXC
capacity up to 2 TiB, checks response/controller errors, bounds waits even if
the clock stalls, preserves output on failed reads, and invalidates state
until successful reinitialization after I/O errors. Its command allowlist
excludes writes and erases; DMA and interrupt signals are disabled. SDSC,
MMC, SDUC, UHS and CQE are not implemented in this initial transport.

**The transport is not yet registered or linked as an XNU storage driver.**
Its future caller must serialize access and establish exclusive controller
ownership, CQE shutdown, correct pin selection, actual rail state, and a card
power cycle into stable 3.3-V VDD and I/O before reset/identification. Firmware
may have left the card in 1.8-V UHS mode. FDT regulator declarations and the
SDHCI power register do not establish the external GPIO regulator's state.
Do not call the PIO transport on the board until this prerequisite is closed.

## Host evidence and separate diagnostic image

Run:

```sh
python3 -m unittest tools.rpi5.tests.test_sdhci -v
```

Five focused tests cover the pinned DTB with consumed-property mutations,
native-endian root attachment/atomic rejection, an actual freestanding
Cortex-A76 compile, and ASan/UBSan register models. The transport model exercises
command ordering, OCR retries, CSD conversion/capacity, unaligned output and
guard bytes, first/last reads, range checks, stuck reset/clock/commands/busy,
CRC/card errors, missing data/completion, clock stall and reinitialization.
These are not emulation or physical media evidence.

### Digital power/pin handoff and live Linux reference

`rpi5_fdt_sd_power` now validates exact GPIO3 voltage selection, GPIO4 card
power and active-low GPIO5 card detection, including the regulator state table,
settling declaration and both default pin groups. C0 and D0 pad controllers
must be a matched pair; their pad offsets and card-detect alternate functions
differ. These are binding checks, not rail measurements or GPIO ownership.

`iokit/Kernel/rpi5_sd_handoff.{c,h}` is a separately implemented, bounded
digital sequencer. It rejects unknown clocks/capabilities, mis-owned power
pins and outstanding host/CQE work; an enabled idle queue must acknowledge
halt before being disabled. It stops SD clock/signals, requests host/card
power off, waits 100 ms, selects 3.3-V I/O, waits 5 ms, sets SD pads/pulls,
then powers the card on and waits 10 ms. Masked readback is checked at each
step. Only SD control bits may change; the AON interrupt controller, RP1,
PMIC and UART pins are untouched. No card commands or sector writes occur.
Power-stage errors attempt power-off rather than restoring an inherited UHS
state. Failed writes cannot be claimed undone. This sequencer is now linked
and was called by the corrected adapter trial above, which failed at stage 2.
Exclusive controller/GPIO RMW ownership,
electrical discharge/voltage and actual source clock remain integration/board
requirements; digital readback alone does not close the transport precondition.

Sanitized model checks cover both pad variants, unrelated-bit preservation,
ordering/delays, pending work, CQE halt acknowledgement/timeouts, ignored
register writes, stuck/backwards time and absent/removed cards. Both handoff
and transport compile freestanding for Cortex-A76. No model is a board test.

Fresh independent Linux evidence:

- `build/rpi5/sd-linux-reference-x23iicwj/reference.json` verifies root
  `/dev/nvme0n1p2`, the preserved FAT partition identity/layout, card CID
  `1b534d474432533530654f68d1a16100`, CSD-derived capacity and block-device size
  **128177930240 bytes / 250347520 sectors**. Eight selected LBAs (MBR, FAT
  boundaries, first free, middle and last card sector) were read twice with a
  read-only descriptor and matching SHA256 results. These are Linux reads,
  potentially cached, not XNU PIO or durability evidence. No SD data was written.
  Reference JSON SHA256:
  `bb97b04c29cd8078d96904cad0f8ca40eb418eb68a466669dd8128568ef4114f`.
- Linux's MMC diagnostics report 200-MHz SDR104 with **1.8-V signaling**.
  `pins.json` in that directory records `pinctrl -v get` for exactly the three
  named SD pins: GPIO3 high, GPIO4 high, GPIO5 low/alternate 6 on C0.
  This confirms the current digital configuration, not a measured rail voltage
  or a promise about the next firmware boot's state. No `pinctrl set` was used.
- `build/rpi5/linux-filtered-tree-0v4vbuxx/filtered.dtb` passes the actual
  sanitized SD binding/mutation harness, including the power/pin graph. The
  filter excludes `/chosen`, seeds and unrelated root nodes. It is a Linux
  binding snapshot, not the original firmware FDT or an ownership proof.
  Filtered DTB SHA256:
  `94e4bd1a605a458aa3184d6f6c68465c8c32033d5c1c8842ea236706e2ff24ee`.

Capture tooling: `capture_sd_reference.py` verifies root/card/layout before
opening `/dev/mmcblk0` with `O_RDONLY|O_NOFOLLOW`, then rechecks identity after
reads. It refuses changed/short/unstable data and validates CSD versus capacity.
Five mocked host tests exercise these guards; they do not replace the actual
Linux evidence above. `capture_linux_tree.py --storage` opts into the additional
binding properties without broadening the ordinary capture by default.

The updated separate diagnostic package is
`build/rpi5/bl33-probe-yyibi61l/`, probe SHA256
`9a6af0a8490a41fa0097201f0958f5252d2e5d563f4cb0036ab3ab4bf0c32974`.
It retains the experimental storage kernel below and proven RAM shell, adds
native GPIO/pad range/variant/timing metadata, and records read-only GPIO/CQE
snapshots. Exactly three additional containing Device pages cover the pad/GPIO
spans; this is not blanket peripheral access. Binding call-chain stack bound is
7824 bytes plus 512 bytes headroom within the 16-KiB early stack. All 14 shell
package identity checks pass. **Unstaged/unbooted; no power change, controller
reset or SD command is issued by its loader.**

The opt-in build is:

```sh
python3 tools/rpi5/build_probe.py --load-address 0x9000000 \
  --kernel build/rpi5/shell-userland-20261011/kernel.development.bcm2712 \
  --init build/rpi5/shell-userland-20261011/ramdisk.bin \
  --transfer --serial-terminal --gate3-cpu-on-all --gate4-storage
```

Latest output: `build/rpi5/bl33-probe-0ho32rka/`, probe SHA256
`d2fdc1181c7df0b2578122388a91e9267a48216259052adb71a5ef38ac4f2187`.
The manifest records inputs, commands and an SD binding stack bound of 6896
bytes plus 512 bytes headroom in the 16-KiB early stack. It reuses the proven
kernel and shell; it does not contain a block-device driver. All 14 existing
shell package identity checks pass. That preflight does not validate SD I/O.

`--gate4-storage` requires the separate serial-terminal image. It validates
the runtime FDT before reading only host/config snapshot registers, publishes
the SD tree node and adds exactly the host/config containing 16-KiB Device
page to the memory-type contract. No card commands are sent by this image.
Without the flag, the old tree/MMIO behavior remains unchanged. This candidate
has **not** been staged or booted. Preserve it separately from the shell baseline.

## Apple integration and fresh kernel build

```sh
python3 tools/rpi5/audit_storage_build.py --adapted --all-units
```

The tool verifies archives, every pristine extracted source file and the
matching distribution manifest, then copies public SDK headers into an
isolated include overlay. It reuses real BCM2712 compiler settings, preserves
every command/log, hashes source/object inputs, and never modifies the SDK.
Warnings remain recorded but are not errors for these upstream integration
units. The latest screen records 767 warnings; this is an experimental build,
not a clean production warning policy or a correctness/ABI proof.

The initial `gate4-build-audit-9h44595v` sample compiled 8/11 units. Its three
failures are now closed using actual providers and configuration adaptations:

- Generate both the DriverKit header and implementation from Apple's pinned
  `IOUserBlockStorageDevice.iig` using the installed IIG tool and public XNU
  definitions. Compile the generated implementation and actual kext class.
- Guard the AppleKeyStore header, declarations and all key-service helpers
  with `CONFIG_PROTECT`. This ordinary-HFS configuration disables protection
  and rejects protected mount requests and protected volume headers with
  `ENOTSUP`, before journal/metadata changes. No key success is fabricated.
- Call the real `ubc_create_upl_external` paging wrapper, matching the BSD
  export alias, and the real `kernel_sysctlbyname` API. Use `vnode_vtype`
  instead of reaching through an opaque vnode. Built-in HFS has no independent
  unloadable-kext load tag; its real mount accounting remains.
- Import the kernel's generated QUOTA policy (disabled) rather than redefine
  it. Include the actual HFS encoding provider; namespace its allocation counter
  separately from the ordinary HFS counter, as the original separate kexts do.
- Built-in HFS SYSCTL declarations use XNU's permanent early startup entries.
  Do not also run the external-kext constructor chain or late register/unregister
  calls. The resulting object contains early entries and no references to the
  omitted late HFS registration functions.
- Enable the actual XNU decmpfs implementation for the isolated link screen.
  The final kernel enables FS_COMPRESSION globally in an isolated configuration
  and compiles decmpfs normally; the screen-only decmpfs object is not linked
  into the final provider. The default baseline configuration is unchanged.

`build/rpi5/gate4-build-audit-1m9nuvn5/manifest.json` records **57/57 units
compiled**: 15 storage units including generated IIG code, 38 present HFS core
units, three encoding units and the actual XNU decmpfs implementation. The
upstream project also references unavailable `hfs_key_roll` files; those guarded
protected paths are disabled, not reconstructed or claimed supported.
Relocatable linking passes, required real definitions are present, and remaining
references are found in the reference kernel's full symbol inventory. This
inventory alone does not establish runtime compatibility.

Fresh experimental kernel build:

```sh
python3 tools/rpi5/rpi5.py build --profile xcode27 \
  --allow-toolchain-mismatch --fresh --with-crypto-candidate \
  --activate-crypto --with-pthread-provider --with-storage-provider --jobs 6
```

The opt-in storage build requires fresh outputs and the real runtime providers.
`build_storage_provider.py` rejects changed sources/objects, incomplete screen
evidence and changed patches. A copied MASTER profile enables compression and
CONFIG_RPI5_STORAGE without modifying the baseline profile or installed SDK.
Two fresh builds completed successfully; no reproducibility claim is made.
Latest evidence: `build/rpi5-xcode27/run-j7q7v42b/manifest.json`, exit 0,
source unchanged during the build. This uses noncanonical Xcode 27.0 / 27A266a.

Latest kernel:
`build/rpi5-xcode27/fresh-h725vrt8/obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712`,
SHA256 `58d52c5cbeb491c7104fa337f4b5dbbd1e27c3feb61852ecdf2a79f567c3afeb`.
Its link map includes the source-built storage/HFS provider. Actual kernel
symbols include HFS vfsops, IOMedia and IOBlockStorageDriver metaclasses, the
HFS service metaclass and executable decmpfs initialization; `nm -u` is empty.
The selected Private.exports/Private.arm64.exports triage audit reports zero
missing providers and zero global absolute-zero definitions. Full make also
completed its normal packaging/symbol-set steps. None of this proves a mount.

Separate package `build/rpi5/bl33-probe-92uyxlqc/` includes this new kernel,
the proven shell/RAMroot, and the SD binding/register-snapshot loader. Probe
SHA256 `ff9ec37d55f074f1b59b7477fbcf78bc6640d271e497f2cf76ad8bd60f8dbbe7`;
all 14 shell-package identity checks pass. It has **not been staged or booted**.
No SD command is issued by its loader. Storage/HFS code is linked but matching,
VFS registration, SD media publication and physical I/O remain unverified and
are not yet wired into a functioning storage path.

Focused regression command (43 tests passed after the power/reference work):

```sh
python3 -m unittest tools.rpi5.tests.test_sdhci tools.rpi5.tests.test_sd_reference \
  tools.rpi5.tests.test_native_fdt_reg tools.rpi5.tests.test_board_tree_gic \
  tools.rpi5.tests.test_board_tree_ramdisk tools.rpi5.tests.test_probe_build \
  tools.rpi5.tests.test_tree_stack tools.rpi5.tests.test_storage_build_audit \
  tools.rpi5.tests.test_exports -q
```

Tests cover pristine/adapted source isolation, object tamper rejection, opt-in
configuration preservation and build prerequisites, real paging-wrapper selection,
and the actual volume-header validator under ASan/UBSan with protected media
rejected. These host checks do not replace board evidence.

## Remaining execution sequence and exit evidence

1. Close GPIO/pin/voltage, clock and CQE handoff using fresh board evidence;
   integrate a serialized BCM2712 kernel adapter over the PIO transport.
2. Read known sectors repeatedly under XNU and compare with independent Linux
   hashes from the exact disposable card. Record card identity/capacity and
   errors/timeouts/removal behavior; no writes yet.
3. Finish registering the now-linked real pinned IOStorageFamily, publish SD media and
   its partitions through IOMedia/BSD. Close all undefined providers and
   matching/lifetime/completion contracts; do not bypass this with a private
   raw-disk-only interface and call Gate 4 finished.
4. Verify the separately built HFS+ registration/lifecycle and matching on the
   board, prepare a distinct disposable test partition
   without overwriting the preserved boot partition/backups, and prove
   read-only mount, file hashes, reads and executable loading from SD.
5. Repeat the mount/read checks with captured serial evidence. Batch tests in
   one relevant boot per changed image, not unchanged qualification loops.
6. Add the separately guarded PIO write path only after buffer ownership,
   address and error-recovery checks. Verify create/write/fsync/unmount,
   reboot/remount and independent readback/durability on disposable data.
   DMA remains disabled until its cache/mapping/lifetime requirements are
   implemented and separately tested.

Before any media mutation, freshly verify NVMe Linux root `/dev/nvme0n1p2`
and exact SD identity (`XNU_PROBE`, UUID `4FA7-3725`, PARTUUID
`5ae1f07e-01` for the preserved FAT partition); inventory the whole card and
existing layout. Prior authorization covers this disposable card, not an
inferred device, Mac disk or the NVMe fallback. Do not request a physical
cycle until a specific candidate and recorder are ready. No Gate 3 soak is
a prerequisite for these storage trials.

Gate 4 remains active/incomplete: the later physical SD-read pass is recorded
at the top of this document; HFS mount/exec repeatability and durable writes
have not yet been demonstrated. The offline
[write admission policy](GATE4-WRITE-POLICY.md) adds partition/identity/epoch
guards without being linked into the current kernel or enabling any writes.
The separate offline PIO engine and buffer-execution helper are also unlinked;
the current expanded host regression passes 161 tests. Real descriptor/worker
integration and synchronization remain future work after HFS read-only acceptance.
