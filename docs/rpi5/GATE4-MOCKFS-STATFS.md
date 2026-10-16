# Gate 4 HFS pre-mount failure and corrective build

## Physical correction accepted — 03:12:40 UTC

After exact SSD Linux returned with boot ID
`eab1bae1-ee62-4ee7-a437-17e39fc11bcc`, a new complete two-pass Linux HFS
reference (`hfs-linux-reference-fdlatk62`) matched the fixture. All 29 package
checks were rerun unchanged. The actual corrective installer result is
`hfs-stats-correction-installed-20261012/result.json`; it preserved the failed
image under distinct SD/NVMe names and left HFS/protected boot bytes unchanged.

Fresh recorder arming preceded the one-shot software reboot. The corrected
`9defaf57...` package passed both complete HFS mount/full-file-hash/script and
binary exec/non-forced-unmount cycles in one boot. All ten file reconstructions
(134590 bytes) and ordered mount/status/unmount markers were independently
rechecked from `mac-hfs-stats-corrected-trial-20261012/serial.bin`, SHA256
`9c276399b75fa03d4d3058cd3dada12e73ff82787ee264ff215929e41f4aa315`.
Final shell nonce returned; HFS is unmounted. This is actual corrected VFS/HFS
dispatch acceptance, not write durability, cold boots or full Gate 4 completion.

The rest of this document retains the earlier failure/build/execution history.
Do not repeat the already executed correction installer. Preserve the passed
package/capture and continue the distinct write-path trial preparation.

2026-10-12 UTC. The first installed HFS read-only candidate is
`bl33-probe-qxmk1ban/probe.bin`, SHA256
`38c4f0e1bf927f4960a85493429a24be1119b9c00e94b29e2a2974b0e3c8d832`.
The guarded fixture and boot installers actually succeeded; actual complete
Linux partition reads matched fixture SHA256
`168c89cb97645ba07b353b3584087e5770d9c2793c6e86b7a8bc3471cbb477e1`.

## Observed failure, not acceptance

`mac-hfs-read-continuation-20261012/state.json` ended failed at 02:14:15 UTC:
zero completed mount cycles/file reads, 56 transmitted bytes, zero SD data-write
commands. Raw capture SHA256 is
`5ea552dae20a3aa9f362c1ab8269beb4db2533fa4a5d34d5a0606cfa5ff8cd39`.
It contains the distinct HFS loader, intact HFS REGISTERED, exact SD capacity,
fresh shell nonce, real second BSD partition and this completed response:

```text
xnu:/# hfsro mount /dev/disk0s2
hfsro statfs64: errno 45
xnu:/#
```

The utility's first statfs64 call inspects the covered `/mnt/hfs` directory on
mockfs before opening the partition or calling mount. XNU's statfs64 refreshes
mount statistics through `vfs_update_vfsstat -> vfs_getattr -> VFS_GETATTR`.
The original mockfs vfsops table has no getter. Returning ENOTSUP here is not
a failed HFS mount or evidence of HFS corruption. Do not suppress the utility's
covered-root identity check or treat its error as successful registration.

## Narrow correction

`mockfs_mount` now retains the validated archive extent size before publishing
mount data. An archive-profile-only VFS_GETATTR handler returns fixed read-only
geometry: 16-KiB blocks/I/O size, total/used blocks including padding/table,
zero free/available blocks, actual archive node count and no free file slots.
It rejects malformed counts, root or extent bounds; the legacy raw-executable
path remains ENOTSUP. It does not invent a filesystem identity, mount HFS,
change mount flags, add writable RAM-root operations or enable disk writes.

The native host harness executes the actual changed getter with the pinned
VFSATTR macros and bounded mount doubles. It tests every allowed page-aligned
archive extent/count and invalid state, plus profile wiring/publication order.
All 167 expanded focused host tests pass. This is not actual statfs64/VFS
dispatch proof; a fresh kernel and physical HFS trial are still required.

## Completed corrective build and screen

By 02:40 UTC, fresh kernel build `rpi5-xcode27/run-obi6gw3d` succeeded with
`source_unchanged_during_build=true` and `fresh_kernel_outputs=true`.
`fresh-435uage7/obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712`
has SHA256 `674e6a763a01a7e4becf0399d03641aa4e43ec1c1d995d67623546b9d64f5aad`.
The separate package `bl33-probe-a5wng87t/probe.bin` has SHA256
`9defaf57a932aca9dfca06ad928eca4fe3e9bbd07fb5c7562b1b80c4df28222a`;
the read-only HFS userland remains unchanged.

`check_hfs_stats_package.py` retains the original 28 HFS checks and verifies
the actual linked `_mockfs_vfsops` getter slot against `_mockfs_vfs_getattr`.
It validates the pinned header layout (including five reserved pointers,
excluding the commented statfs declaration), file-backed extents and executable
handler protection. All 29 checks pass in the package's
`hfs-stats-preflight.json`: table `0xfffffe0007a3afe8`, slot offset 40,
target/handler `0xfffffe000757ec80`. The actual failed kernel is rejected for
its missing handler. This is pointer-wiring evidence, not runtime dispatch.

`stage_hfs_stats_correction.py` is a separate fixed-name corrective profile,
not a bypass of the initial stager. It validates the actual initial installation,
unchanged fixture, prior SD proof, complete failed capture and preserved original
zero-input prefix. Only the exact completed pre-mount errno-45 response with no
HFS success/file marker or data writes is accepted. The original torn boot
bytes remain untouched; only the intact command response is normalized.
The failed image receives distinct SD/NVMe backups; original passed SD-only,
shell, Gate 3, full FAT/MBR, configuration, BL31 and DTB backups are retained.
The shared remote workflow verifies full HFS bytes before and after, unmounts
the FAT partition and does not reboot. Existing partial files or an unknown
outcome require inspection, never retry/rollback. Host tests use temporary
regular files and mocked mount/reference operations, not FAT/hardware proof.
The actual evidence chain also passed a local historical-reference replay;
the real current-time guard rejects the now-stale reference. No corrected
image has been staged or booted yet.

The expanded focused regression passes all 177 tests in one run (22.684 s).
The receive-only capture (`mac-hfs-statfs-to-linux-20261012`, process handle
91049) and exact-root SSH wait (`wait-nvme-after-hfs-statfs-20261012`, handle
68904) remain live. These are observation handles, not proof that Linux is up.

## Historical correction sequence — now executed; do not rerun

1. Require hostname `kamidana`, the exact NVMe root/UUID, and a boot ID different
   from `75595c3b-a621-42ec-bf24-5a73e7ead187`. Do not open/mount SD while XNU
   is active. Existing watchdog fallback is expected near 03:05 UTC, not a soak.
2. Run `capture_hfs_reference.py` for `sandrzej@192.168.4.23`, with the original
   `hfs-read-fixture-h9wpku5p/reference.json` and
   `sd-linux-reference-99_23_zu/reference.json`; retain its fresh output path.
3. Run the distinct correction installer using that new reference and
   `bl33-probe-a5wng87t/hfs-stats-preflight.json`. Other required inputs are
   `mac-sd-read-link-restored-continuation-20261012/state.json`,
   `hfs-stage-executed-20261012/{plan,result}.json`,
   `hfs-boot-installed-20261012/{plan,result}.json`, the original
   `hfs-linux-reference-lzloo4fh/reference.json` and
   `bl33-probe-qxmk1ban/preflight.json`, plus
   `mac-hfs-read-continuation-20261012/state.json`. Default is local plan only;
   actual execution needs `--execute` and a fresh output directory. Inspect any
   unknown/failed execution in its exact remote run; never blindly retry.
4. Only after successful installation and verified Linux, stop the exclusive
   receive-only capture, preserving its bytes and explicitly recording the
   deliberate stop. Arm a **fresh** `serial_hfs_read_trial.py` with the new
   package preflight and fresh reference. Do not use the historical resume flag.
5. Only after the recorder reports ARMED, perform the existing one-shot SD boot
   (`vcmailbox 0x0003808b 4 4 0xf61`, sync, software reboot). Leave configuration,
   firmware, partition table and HFS bytes unchanged.
6. Collect the unchanged two full mount/read/hash/script-and-binary-exec/nonforced
   unmount cycles. Do not claim success from package/host tests. Preserve any
   actual failure and address its cause before another changed trial.

## Corrective staging requirements

Leave the failed capture, installed candidate and all existing backups intact.
The original initial stager requires one partition and the passed SD-only image;
the card now has **two** partitions and a failed HFS-read candidate. Do not rerun
it, replace its old-image expectation ad hoc, or overwrite its fixed backups.

After the existing one-hour watchdog returns SSD Linux, verify fresh exact root,
card/two-partition identity and two complete HFS reads. The new package must be
distinct, retain every read-only guard, include the actual getter, and pass
linked-binary checks. A separate corrective installer must bind the prior
installed result and raw pre-mount failure, preserve the failed candidate under
a new explicit name, retain all prior backups, and verify protected boot files
and full HFS bytes before/after. Arm before one software reboot. Repeat all two
mount/full-file-hash/script-and-binary-exec/nonforced-unmount cycles; no weakened
or synthetic substitute. Separate write/durability acceptance remains afterward.

The old receive-only fallback recorder was deliberately stopped after verified
Linux return, not a failed soak. The current receive-only recorder and exact-root
SSH waiter are observation handles for the existing fallback, not qualification
or permission to touch media while XNU is active.
