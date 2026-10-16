# Gate 4 exit audit — incomplete, 2026-10-12 15:14 UTC

Offline update, 2026-10-16: the write policy now accepts a separately compiled,
hash-pinned media profile and carries that profile's exact HFS extent in every
authorized epoch. A local generator binds a profile to two identical complete
partition reads and the qualified fixture. This prepares a future disposable
card without weakening identity, range, cache or durability gates. It adds no
physical evidence: the current card's unknown cache state, admitted write,
post-write reboot, fsck and read-only persistence checks are still missing.

Later recovery update, 2026-10-12 16:40 UTC: a separately authorized Gate 6 zsh
trial superseded the current image/FAT baseline listed in this historical audit.
Current probe is `b3db210c0a880688bfda783e306fb6ad3473431d9a9cc68e25035d3c8fc32fd0`;
FAT is `1fb357e8483a43c92e92d3d0cb4a50aada0116bbb7a9267c35e983b04323277a`.
All historical backups and MBR/HFS/firmware protection were retained. The Pi was
last proven in XNU's recovery shell, with serial released. See
[current recovery evidence](GATE6-PHYSICAL-ZSH.md); do not rerun older installers
or infer that Linux is currently available. No Gate 4 requirement was waived
or satisfied by the independent interactive zsh result.

This audits the original physical write/persistence goal, not the independent
Gate 5 topology milestone. Host tests and earlier read-only success do not
substitute for the missing write or persistence evidence. No exit condition is
waived. This audit performed no Pi, serial, SD or filesystem operation.

## Requirement-to-evidence audit

| Required result | Authoritative evidence inspected | Finding |
| --- | --- | --- |
| Actual SD block IO / BSD partition node / HFS read-only operation | `mac-hfs-stats-corrected-trial-20261012/state.json` | Passed at 03:12:40 UTC: two full mount/read/exec/nonforced-unmount cycles and recovered shell. |
| Actual initialized card with cache proven absent or disabled before RW publication | W3 `mac-hfs-cache-diagnostic-trial-20261012/{state.json,serial.bin}` | Incomplete: stage 7 rejects all-zero General Information; no write admission. |
| One admitted five-file exercise, fsyncs and complete same-boot reads | Same W3 state/raw | Not performed: zero TX, zero batch attempts, no HFS mount. |
| Normal writable unmount and covered-root restoration | Same W3 state/raw | Not performed; no writable mount existed. |
| Intervening reboot **after that admitted write batch** | No successful write batch artifact exists | Missing. Later W3 recovery/Gate 5 reboots cannot satisfy chronology for a nonexistent batch. |
| Independent complete post-write capture, no-repair fsck and RO remount | No actual Pi-written partition capture/audit exists | Missing. Implemented tools/fixtures are not execution evidence. |
| Full written-file and unchanged fixture-file persistence hashes | No admitted batch or post-reboot file audit exists | Missing. |
| Preserved recovery images, card/layout and complete protected media | `pcie-topology-installed-20261012/result.json` | Latest installation check passed: MBR/HFS unchanged and all 20 historical NVMe artifacts verified. This is protection evidence, not write durability. |

Artifact prefixes above are under `build/rpi5/`. The original gate remains
defined by [required physical proof](GATE4-WRITE-TRIAL.md#required-eventual-physical-write-and-persistence-proof).

## Cache blocker: available evidence and rejected shortcuts

W3 state SHA256
`09e287eed22d657f4ea0822070bcef6c05ae19b2bb8037b8631120722638ccb1`;
raw serial SHA256
`7588028a78b77b05209484c44f05e2febfcaab6d97a42f039e4d5e36ca638453`.
The separate completed Linux control result SHA256 remains
`15f963e70a6b29085e6c88a59345c09d4a8e727d7a5ca02763ac7cc63974debe`.
It received the same 512 zero bytes with R1 `0x900`, not valid cache-off state.

The preserved sysfs SD Status operator note SHA256 is
`07331cedf193efe6a209b37f58046552b8e20f1b8c61df5fc9c9c9a70def6fc8`.
Its 64-byte payload hash verifies and advertises cache support at bit 330.
Support is not the enabled-state bit. The note remains operator-transcribed
cached Linux metadata, not an actual XNU cache observation.

Fresh primary-source review confirmed:

- The [Raspberry Pi Linux parser](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/mmc/core/sd.c)
  can finish General Information parsing with zero extension entries, leaving
  feature metadata zero. Its permissive continuation is not absent-cache proof.
- The [Samsung quirk](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/mmc/core/quirks.h)
  matches manufacture year 2023 and OEM ID `0x534d`. This card's preserved CID
  reports January 2022; the quirk does not match or establish its current state.
- The [official indexed SD6 table](https://www.sdcard.org/cms/wp-content/themes/sdcard-org/dl.php?f=Part1_Physical_Layer_Simplified_Specification_Ver6.00.pdf)
  identifies SD Status bit 330 as cache-support indication. The local PDF path
  is an empty failed-download artifact, not a specification copy. No agreement
  was accepted and no unsupported third-party text was used to authorize writes.
- No authoritative, applicable cache-off reset guarantee was established by
  this review. SDHCI host reset and the initializer's CMD0 must not be treated
  as proof that this card's unobservable cache is disabled.

Therefore do not weaken the parser, guess a PEF location, issue a speculative
CMD49/cache toggle, repeat the unchanged W3/control, or claim CMD13 is a flush.
The failure is unresolved card/protocol state; it does not prove a defective
card, and another card is an inspection option rather than a guaranteed fix.

## Current recovery boundary and next safe action

The last recorded board trial is Gate 5's successful software SD boot, not
W3 or a running storage soak. Its 90-second recorder finished/released serial
at 15:03:41 UTC. No live waiter/recorder is established by this audit. The Pi
was last proven running the topology-only XNU image and its unchanged one-hour
watchdog; do not assume current SSD Linux or guaranteed automatic fallback.

Current installed probe SHA256:
`038c2b9bd0b55fa35496632fad7a96e8ffff1f2a7b64006e5709757bd895b895`.
Latest full FAT baseline SHA256:
`b200d1fcc91a2e36ba700b9967a8c5efc79c43a616575e7ce6286f98b98ade60`.
Latest MBR/HFS hashes remain the accepted values. W3 is preserved on SSD in
`/home/sandrzej/xnu-gate5-topology-z4ll1si5/hfs-cache-buffer-failed.bin` and SD
`probe.hfs-cache-buffer-failed-20261012.bin`, along with complete fresh snapshots.
Older installers deliberately expect older probe/FAT states: **do not rerun
them, replace hashes merely to force acceptance, or restore W3 automatically**.

A read-only Mac external-disk inventory found only an unrelated 1-TB APFS disk,
not a spare SD candidate. That disk was not opened, mounted or modified.
The existing spare-card availability question remains unanswered; do not repeat
it on automatic continuations. The next actual Gate 4 hardware step requires a
new disposable card to identify/inspect, or authoritative new evidence resolving
this card's extension/cache state. Any new card needs its own exact identity,
preservation/admission profile and original full persistence/protection chain.

Independent Gates 5/6 may continue under the user's separate authorization,
but their results must never be counted as completion of Gate 4.
