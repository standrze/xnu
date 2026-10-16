# Gate 4 write admission — distinct experimental profile

## Offline media-profile continuation — 2026-10-16

The write-admission core no longer requires editing C policy logic for every
qualified disposable card. `rpi5_sd_write_profile` seals capacity, CID/CSD,
MBR signature, boot and HFS extents, request ceiling and HFS allocation
geometry. The live policy copies only the authorized HFS range into its epoch
lease; failed authorization and quarantine clear that geometry. The provider
reads both HFS headers using the selected profile and calls the explicit
profile authorization entry point.

`tools/rpi5/build_sd_write_profile.py` accepts only an already captured SD/HFS
reference with at least two identical complete reads bound to the qualified
fixture. Its generated C source is selected only by the distinct
`RPI5_SD_WRITE_EXTERNAL_PROFILE` compile opt-in. The generator never opens a
device, connects to the Pi, stages an image or grants cache/write authority.
Mutation tests reject changed read hashes, partition geometry and any nonzero
recorded SD-write count. The existing Samsung profile remains the default for
historical reproducibility.

The generated `sd-write-profile-20261016-v1` is therefore a software-only
reproduction of the prior card/fixture expectation, not a new candidate or a
reason to repeat W3. The unresolved cache-state requirement below remains
unchanged; a future card still needs fresh identity/read/cache qualification
and the full write/reboot/fsck/read-only-remount durability sequence.

13:18 UTC: independent SD Status does not establish cache absence on this card.
Official SD6 PERFORMANCE_ENHANCE Table 4.10.2-2 and section 4.17 define bit 330
as cache support (zero means unsupported). Existing Linux sysfs SSR byte 22 is
`fc`, so that bit is one. No new card ioctl was used; the preserved operator
note binds the 64-byte cached register and control-result hash. This is not an
XNU enabled-state observation. Do not add an absent-cache branch for this card
or substitute Linux `ext_perf=00` for valid capability/state discovery.
[Official indexed SD6 protocol source](https://www.sdcard.org/cms/wp-content/themes/sdcard-org/dl.php?f=Part1_Physical_Layer_Simplified_Specification_Ver6.00.pdf).
The full PDF remains undownloaded; no legal agreement was accepted. A different
disposable card is a hardware option to inspect, not authority to waive any
admission/persistence/protection invariant or erase an unidentified new card.

13:12 UTC: the one guarded Linux comparison has now executed successfully after
verified automatic SSD return. R1 is `0x900`; complete CMD48 payload is the same
512 zero bytes as actual W3. All 20 backups and full protected MBR/FAT/HFS bytes
passed before/after checks. No SD write/mount/reset/reboot; no cache admission.
Preserve `sd-extension-linux-control-20261012/result.json` (SHA256
`15f963e70a6b29085e6c88a59345c09d4a8e727d7a5ca02763ac7cc63974debe`).
Linux sysfs reports `ext_perf=00`, but the
[Raspberry Pi Linux 6.18 parser](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/mmc/core/sd.c)
can leave features zero when no extension entries are parsed. Thus it is not an
independent observation of absent/disabled cache. Matching transport results
reduce an XNU-only explanation; do not relax the malformed-header refusal or
rerun W3/control without a new justified hypothesis. Next: independent
protocol/card evidence. The original full write/persistence gate is unchanged.
Older timed checkpoints below describe their then-current state.

12:13 UTC: W3 physically captured valid SD6 SCR followed by a completed all-zero
512-byte General Information read; the failure is at decoder stage 7, with zero
TX/batch/mount. This is not cache-absence proof. The CMD48 argument layout was
cross-checked against [upstream Linux protocol facts](https://raw.githubusercontent.com/torvalds/linux/master/drivers/mmc/core/sd.c).
A separate one-read Linux control is prepared using the
[MMC ioctl ABI](https://raw.githubusercontent.com/torvalds/linux/master/include/uapi/linux/mmc/ioctl.h)
and [command flags](https://raw.githubusercontent.com/torvalds/linux/master/include/linux/mmc/core.h).
It must run only after fresh exact SSD/card checks; it is not executed yet and
cannot authorize XNU writes. The independent source uses an O_RDONLY whole-card
descriptor and write_flag=0, not a raw-write tool. See STATUS.md for exact evidence
and live fallback handles. Do not retry W3 or infer absent/disabled cache.

06:10 UTC: the diagnostic-only W3 kernel now has a successful source-stable
fresh build and all 29 actual package checks. It is not staged or a proven fix.
The cache trace is separate private heap storage, records completed buffers
only at the decoder boundary and never supplies admission state. Traced versus
untraced models check identical MMIO counts and complete command/argument lists
across all 512 PEF alignments and transport failures. No cache parser rule,
unknown-state refusal, write extent or card opcode was relaxed. The new fixed-name
successor installer preserves W2/W1/RO/full snapshots and requires new SSD Linux
plus fresh complete HFS evidence. STATUS.md and GATE4-WRITE-TRIAL.md are current.

06:00 UTC: W2 is now physically booted, not merely prepared. It failed closed
with `CACHE_PROBE RC=-5 CMD=13`, zero serial input, no batch and no HFS mount.
The result narrows failure to an unsupported cache observation, not CMD13
transport: CMD13 is the last-command field, and atomic output is unchanged on
failure. Separate diagnostic storage now records the exact failed stage and
completed buffer without changing decoding, commands or admission. It remains
unbuilt/unstaged. Existing RX-only/SSH handles observe automatic SSD fallback;
no manual restart or repeated soak. See STATUS.md for original immutable evidence.

05:00 UTC: the first write image reached XNU/HFS/the RAM shell but produced no
write-admission prefix. Its guarded trial ended with zero TX and no batch; the
startup cause is not established. Preserve its original capture. A distinct
first-failed-stage diagnostic kernel/package now passes a fresh source-stable
build and all 29 actual package checks, but is not staged/booted. The successor
installer requires new SSD Linux/full clean HFS evidence and preserves both
the failed write image and the passed RO image with distinct fixed filenames.
Full prior FAT hash verification precedes replacement. Live RX-only/SSH waits
observe the current automatic fallback; no extra soak or manual restart.
See [GATE4-WRITE-TRIAL.md](GATE4-WRITE-TRIAL.md) and STATUS.md. No admitted write
or durability acceptance is claimed.

04:40 UTC: the guarded write image is now installed, preserving the passed RO
image and full MBR/FAT/HFS snapshots in NVMe run
`/home/sandrzej/xnu-gate4-hfs-write-qvwac13_`. The exclusive write recorder was
armed before a one-shot SD reboot; the distinct loader is observed. Cache-off
hardware admission, actual writes and durability remain unproven at this
checkpoint. See STATUS.md for exact artifacts. The pre-install description
below is retained as an earlier host-build checkpoint.

Current 2026-10-12 checkpoint: the read-only HFS prerequisite passed physically
at 03:12:40 UTC. The distinct write adapter and foundations now compile and
link into an opt-in kernel profile, never the default/read-only provider.
Actual-source worker/cache/descriptor models and isolated real-header builds
are host evidence only. The final fresh build `run-93r3j3i2` exited 0 with
unchanged source; `bl33-probe-ybis0sa6/write-preflight.json` passes all 29 checks.
Its image SHA256 is
`dd8eecb8f6fd989d8d29ce8c5b2837a3c6c49dd67a62bb0b40bec67f90397506`.
Earlier full builds were correctly rejected because a separate container
experiment changed concurrently. Their rejection is not waived/reinterpreted.
No write kernel/package has been installed or booted. The Pi returned to SSD
Linux automatically, with two complete HFS hashes matching the clean fixture;
see STATUS.md for exact identity/reference/capture evidence.

`--storage-write-trial` requires the existing fresh Xcode 27 all/runtime-provider
gates and `--with-storage-provider`. It selects exactly the write class and its
nine implementation units/eight headers; the RO class is forbidden in that
provider. Without this flag the original RO adapter is selected and CMD24 is
forbidden in its symbol screen. Both configurations pass the actual XNU
grammar/lexer check. Inherited `RPI5_STORAGE_WRITE_TRIAL` is scrubbed before
make; it cannot silently enable a write build. The separate loader requires
`--gate4-hfs-write-trial --gate4-storage`, forbids RO flags and supplies the
exclusive `bcm2712_sd_write_trial=1` argument plus a distinct marker.

Actual CMD2/CMD9 response observation supplies CID/CSD without new commands
or changes to the original start/read opcode list. The new cache observer
uses only CMD13/CMD55/ACMD51/CMD48. It recognizes known SD 2..6 SCR layouts,
bounded revision-0 General Information/Performance Enhancement descriptors,
and distinguishes absent/disabled/enabled cache. Unknown revisions, malformed
or overlapping chains, unsupported command-queue/maintenance states and
transport errors fail closed. Unaligned extension-register sets are read in
exact page-bounded chunks; fixed 512-byte wire dummy tails are not interpreted
as registers. No CMD49, cache toggle or cache flush is issued.

The provider publishes writable media only after actual mapped-controller
ownership, identity, exact MBR and both clean HFS headers pass admission, and
cache was actually observed absent or disabled. A heap-bounded 16-KiB write
snapshot and real descriptor bridge run on one worker serializing reads,
writes and synchronization. Caller callbacks occur once, outside locks, after
descriptor cleanup. Sync is a queued barrier plus bounded card-ready checking
with cache proven off; enabled/unknown cache is rejected, not pretended flushed.
Failed sync, ambiguous writes, transport errors and removal quarantine the
instance. No DMA, retry, format/erase, hot re-admission or boot-extent write.

The actual worker source passes an ASan/UBSan model with explicitly doubled
IOKit threading/API and transport, including queued shutdown, completion
reentrancy, partial writes, prepare/copy/cleanup/read/sync failures and cache
refusal. Initial card/cache state is injected by the model: it does not prove
real initialization, actual IOKit lifetime or hardware writes/cache behavior.
All 512 extension-register alignments are tested by the cache protocol model.

`build_userland.py --hfs-write-trial` now adds only `hfsrw` and `hfswrite`,
mutually exclusive with read trials. Real static builds verify default/RO/write
archives and dispatch symbols are disjoint. `check_hfs_write_package.py` is a
separate screen, not a relaxation of RO checks. It checks actual linked
configuration, exclusive provider, unchanged sources, build-bound kernel hash,
embedded utility bytes and mockfs getter wiring, preserving known-good images.
Its markers still explicitly say `DURABILITY_VERIFIED=0`. Guarded installation,
actual write batch and independent reboot/fsck/remount/readback remain next.

The sections below retain earlier foundation checkpoints; statements about
unlinked or future integration describe those historical checkpoints, not
the current experimental host build. None is a physical write acceptance claim.

`iokit/Kernel/rpi5_sd_write_policy.{h,c}` is a pure admission/range/epoch module.
It is not listed in the current kernel/provider build, has no MMIO or storage
commands, and cannot enable writes in the running SD-only image or prepared
HFS read-only image. The HFS read-only hardware trial remains the next step.

The future write trial must preserve boot media independently of filesystem
behavior. Admission accepts only the captured disposable card's capacity,
canonical CSD and first fifteen CID bytes. SDHCI omits the CID CRC/end byte;
the module deliberately does not represent that missing byte as a verified
identity bit. CID is not cryptographic authentication. It validates the exact
MBR disk ID and two nonoverlapping partition ranges, including the protected
FAT span and the reserved 128-MiB HFS data span. Extra partition entries fail.

Both observed volume headers must be H+ v4, clean/unmounted, unjournaled,
unlocked, unprotected and the fixture's exact 4096-byte/32768-block geometry.
The unused-node-fix bit from the actual Mac fixture is allowed; unknown state,
inconsistency, journaling, locking and expanded-time flags fail closed. Primary
and alternate free-space counters need not be equal, matching Apple's alternate
header update behavior. These header/geometry checks do not replace fsck,
complete independent hashes, backup verification or actual read-only acceptance.
Attribute definitions come from pinned Apple `hfs_format.h` (hfs-715.120.4).

Every admission attempt revokes the previous lease and advances an epoch.
Requests must present the current nonzero epoch, exactly matching byte count,
and 1..32 sectors wholly inside `[1050624, 1312768)`. MBR, FAT, overlaps,
overflow, card-end addresses, zero-sized and stale requests are rejected.
An ambiguous write/I/O error permanently quarantines that policy instance;
neither revocation nor re-admission can rearm it. Epoch exhaustion also
quarantines it. The caller must serialize every operation and must not reset
the policy while old requests can retain a lease.

Host evidence: two tests pass, covering ASan/UBSan native fault models against
synthetic headers and the actual local Mac HFS fixture, plus dependency-free
freestanding Cortex-A76 compilation. Identity-byte, MBR, header, range, stale
lease, revocation, quarantine and overflow mutations are covered. No SD write,
HFS mount or durability result is claimed.

## Separate PIO write engine — offline only

`iokit/Kernel/rpi5_sdhci_write.{h,c}` implements one CMD24 sector followed by
bounded CMD13 ready/state polling. It is **not integrated or enabled** in any
kernel/provider/package. The existing read-only opcode list remains unchanged.
The caller must exclusively own/serialize the controller and policy. It copies
the complete 512-byte payload into owned storage before accessing MMIO, accepts
only an active policy epoch and one in-range sector, and rejects IRQ ownership.
It temporarily enables buffer-write-ready status and restores the original
status-enable register. Hardware errors, removal, premature transfer completion,
timeouts or failed restoration invalidate the card and quarantine the lease;
there is no retry, reset, DMA, erase or multi-block command. The ready helper
does not imply cache flush or durable storage.

Two additional host tests pass: an ASan/UBSan register model covering unaligned
payloads, boundary LBAs, caller-buffer mutation after entry, admission failures,
CMD13/CMD24 flags, inhibit/response/FIFO/transfer/program timeouts, a stalled
clock, removal and error quarantine; and freestanding Cortex-A76 compilation
with only the three admission helpers as unresolved dependencies. These are
synthetic transport tests, not actual card writes or HFS durability evidence.

Register/protocol constants were checked against the primary FreeBSD
[SDHCI definitions](https://raw.githubusercontent.com/freebsd/freebsd-src/main/sys/dev/sdhci/sdhci.h)
and [MMC/SD definitions](https://raw.githubusercontent.com/freebsd/freebsd-src/main/sys/dev/mmc/mmcreg.h).
The downloaded copies have SHA256 `ce63fba74acdf3d6442d3ffb7ffccfbdd6be38dda8b93fc33ba374ae122309ce`
and `1e782e73c04e8cd570a433b2cadc585237e5f8593c3b5a3c8fef92e57a2c7353`.
Only register facts were used; the engine/model implementation is new.

## Descriptor execution boundary — offline only

`rpi5_sd_transfer.{h,c}` prepares one buffer in the operation's direction,
snapshots the **entire** write request (at most 16 KiB) into caller-supplied
kernel-owned scratch before any sector call, and pairs every successful prepare
with one descriptor complete. It does not allocate or invoke IOStorageCompletion.
The future adapter must retain real descriptors, provide their actual
prepare/complete/readBytes/writeBytes methods and translate READ/WRITE to
`kIODirectionIn`/`kIODirectionOut`. The native descriptor pairing/threading
contract is documented in `iokit/IOKit/IOMemoryDescriptor.h`.

The helper rechecks cancellation and current write admission before each sector,
reports only the completed sector prefix, preserves the first transfer error
while separately recording cleanup failure, and quarantines failed/partial
writes. Read transport failures also quarantine write admission, so a failed
read cannot leave an old writable lease reusable. Attempted-sector counts mean transport function calls, not observed wire
commands. Read-buffer copying can partially modify a destination on failure;
the returned complete prefix is not a whole-request atomicity guarantee.
No completed-byte count implies durability.

Two additional sanitized/native/freestanding host tests cover all 1..32-block
request sizes, snapshot independence, prepare/complete pairing, cancellation,
stale epochs, partial transfer/copy errors, cleanup failures, invalid inputs and
dependencies without allocation. Transport entry points are stubbed explicitly
in this model; it does **not** prove real IOMemoryDescriptor ownership, IOKit
completion/lifetime, controller locking or hardware behavior. Neither this
helper nor either write module is integrated into the current provider/images.

## Real descriptor adapter — compiled, still unlinked

`rpi5_sd_memory.{h,cpp}` now provides the actual IOMemoryDescriptor bridge:
exact READ/In and WRITE/Out direction checks, a call-scoped retain/release,
prepare/complete, readBytes/writeBytes and the caller's cancellation callback.
Private heap scratch is 512 bytes for reads and the whole bounded request for
writes (at most 16 KiB), not a maximum-size kernel-stack array. Invalid inputs
and stale write leases fail before allocation/prepare/MMIO. Allocation failure,
prepare failure, partial copying/transport and cleanup failures preserve the
core's status and complete-byte prefix. It does not invoke IOStorageCompletion.
The future single worker must own controller/policy serialization, retain the
submitted descriptor, release its submission queue lock before calling this
helper, and perform exactly one caller completion afterward outside locks.

The unchanged adapter and execution core pass an ASan/UBSan host harness with
explicit descriptor, allocator, interrupt-context and transport doubles. It
covers all 1..32-sector sizes, source mutation after the first sector (full write
snapshot retained), heap/retain pairing, direction/lease rejection, prepare and
cleanup errors, partial timeout and quarantine. These doubles are not IOKit
runtime or hardware proof.

An independent compile against the real pinned IOKit/kernel headers succeeds
with Cortex-A76, kernel and warnings-as-errors flags, using the original IOKit
working directory and a hash-bound compile database. Evidence:
`build/rpi5/sd-memory-real-headers-v3-20261012/manifest.json`, zero diagnostics,
unchanged inputs, object SHA256
`5b66e4f8524f91d9e9e4c308d489cb423dcaaf142b0aa5d50daf35927d71a747`.
The first two isolated compile attempts failed on harness working-directory/
relative-output resolution; their artifacts remain, and neither touched a
provider/kernel image. The successful object is **not linked** into a provider,
kernel or package, and the current read-only image is unchanged.

## Synchronization is not yet implemented

The existing CMD13-ready helper establishes card programming/transfer state,
not a cache flush. The SD Association explains that an enabled cache can release
busy before data is committed and requires flushing before shutdown
([official A2/cache overview](https://www.sdcard.org/press/thoughtleadership/applications-in-action-introducing-the-newest-application-performance-class/)).
The reviewed upstream Linux SD source separately handles cache enabling and
cache flushing through performance-extension registers
([primary source](https://raw.githubusercontent.com/torvalds/linux/master/drivers/mmc/core/sd.c)).
Only protocol facts were inspected; no Linux implementation is copied.

Consequently the future provider must establish the actual post-handoff cache
state, not infer it from default-speed/1-bit mode or from the current read-only
provider's getWriteCacheState=false. If cache is enabled, synchronization must
perform the supported card flush and verify completion. If cache is proven off,
ordered queue draining plus bounded card-ready validation still does not replace
the independent reboot/remount readback durability test. Unknown cache state,
failed flush/status or failed unmount must not produce a durability marker.
No extension-register command or cache toggle is enabled by this preparation.

## Batched file exercise — prepared, not packaged or executed

`tools/rpi5/user/hfswrite.c` is a separate future utility, absent from the
current dispatcher/build/image. It does not mount, format, unlink or open a raw
device for writing. Before creating any file it requires the actual statfs64
identity `hfs`, `/mnt/hfs`, `/dev/disk0s2`, writable with NOSUID/NODEV, plus
512-byte blocks, exactly 262144 blocks and DKIOCISWRITABLE=1. The device is
opened read-only for those ioctls. This source does not supply the writable
provider or mounting operation; the separately gated mount utility below is
now prepared, while provider/cache integration remains required.

One `hfswrite exercise` batch creates five fixed `xnu-gate4-*.bin` files using
O_EXCL/O_NOFOLLOW and 0600. It tests small (32 bytes), empty, cross-page (33034),
overwrite/truncate (1024 to 257) and append (512 to 4633) cases. Each write
operation fsyncs and closes, then independently reopens/compares every byte and
exact EOF in the same boot. Partial writes are bounded; errors, existing files,
failed sync/close or mismatched readback stop without deleting diagnostic data.
The sole final marker explicitly says `DURABILITY_VERIFIED=0`; it cannot pass
the gate. There is no mount update, journal override or forced unmount.

Five focused tests cover the unchanged utility with explicit in-memory syscall
doubles: exact final file contents, partial progress, invalid arguments,
mount/device guards and all file/open/write/read/fsync/close failure paths.
The real Darwin ARM64 freestanding compile passes its native statfs/disk ABI
screen and has only the eight expected project-runtime dependencies. No actual
filesystem or SD writes occur in these tests.

`hfs_write_results.py` provides the exact five complete-file SHA256 vectors and
a separate read-only regular-file verifier. Two native temporary-file tests
reject changed/truncated/extended/symlink/hardlinked files. The caller must
independently establish physical card/partition identity, an intervening reboot,
the verified read-only mount, filesystem consistency and protected boot files.
The helper itself proves bytes only and cannot establish durability.

The isolated real-header write bundle also compiles/partial-links successfully:
`build/rpi5/sd-write-foundations-real-headers-20261012/manifest.json`, unchanged
inputs, no missing definitions/unresolved SD dependencies, object SHA256
`a666ef49182d0d1a0e06d986f447ed1d5d1c7181b72e1400da7322afa1e95ab0`.
It is an audit object, not linked into the current provider/kernel/package.

## Writable HFS mount utility — host-tested, not packaged or executed

`tools/rpi5/user/hfsrw.{h,c}` implements only `mount`, `status` and non-forced
`unmount` for exactly `/dev/disk0s2` at `/mnt/hfs`. The C implementation is absent
unless `RPI5_HFS_WRITE_TRIAL=1` is explicitly defined, and is not included in
the current dispatcher/build/kernel/package. It never accepts arbitrary paths,
raw writes, formatting, mount updates, journal overrides or automatic rollback.

Mounting requires the covered immutable mockfs root, exact partition geometry
(512-byte blocks, 262144 blocks) and DKIOCISWRITABLE=1, queried through a
read-only device descriptor. Native HFS extended arguments are initialized
without journal changes. The mount uses NOSUID/NODEV without RDONLY/NOEXEC;
actual statfs64 filesystem/source/mountpoint/flags must match before a marker.
Status and unmount recheck writable-device admission. A normal unmount must
succeed and reveal the immutable root again; busy/sync errors, an unchanged
mount or malformed post-statistics produce no success marker and no force/retry.
All markers explicitly state `DURABILITY_VERIFIED=0`. These ioctls/flags do not
establish physical identity, cache state or synchronization; the separately
gated real provider and future package screen must do so before staging.

Seven focused tests pass using explicit syscall doubles under ASan/UBSan,
including failure at each geometry ioctl, revoked write protection, interrupted
mount, wrong mount identity/flags, sync/busy/unmount errors and malformed root
restoration. Real Darwin ARM64 freestanding compilation checks native ABI and
only six expected runtime dependencies. With the compile-time gate absent,
the object contains no utility definition or unresolved dependencies. These
are host/ABI checks only; no HFS mount or SD write was performed by this work.

## Remaining work before enabling the write trial

1. **Read-only prerequisite passed** at 03:12:40 UTC: two full HFS
   mount/read/hash/script-and-binary-exec/non-forced-unmount cycles in one boot.
   Preserve `bl33-probe-a5wng87t`, the complete
   `mac-hfs-stats-corrected-trial-20261012` evidence and clean data backup.
2. Collect fresh CID/CSD/controller observations and both headers in the future
   adapter, then use this admission gate before advertising any writable media.
   Do not infer identity/ownership from FDT or this host fixture.
3. Review/integrate the separate bounded PIO engine only into a distinct future
   write package after read-only acceptance. Keep the proven read-only opcode
   allowlist and package build unchanged. No DMA, erase or multi-block write is
   needed. Host-model success is not physical protocol acceptance.
4. Integrate the compiled but unlinked real IOMemoryDescriptor bridge into the
   separately gated single-worker provider. Retain/prepare each descriptor in the correct direction, copy
   into owned sector buffers, enforce the epoch and range both at enqueue and
   execution, serialize reads/writes/synchronization, and complete once outside
   locks. A failed/ambiguous sector must not be reported as durable success.
5. Integrate/package the prepared, compile-time-gated HFS writable mount and
   fixed-file exercise only in that distinct image. Retain their tested failed
   sync/unmount/no-success-marker paths in the actual linked package screen.
6. Batch create/overwrite/extension/empty/cross-page-file checks in one changed
   boot. Reboot/remount and independently read back file bytes from verified
   Linux/Mac on the same exact disposable HFS partition. Check filesystem
   consistency and preserved boot media. This is the actual durability gate,
   not merely successful CMD24, a completed callback, fsync return or cached read.

No existing Gate 4 requirement is removed by this preparation. Write durability
and applicable write-error/removal behavior remain unproven; read-only HFS
repeatability is now backed by actual board evidence, not these host models.
