# Physical raw-file diagnosis — 2026-10-12 18:02 UTC

Historical diagnostic baseline. The separate [19:03 UTC corrective trial](GATE6-METADATA-PHYSICAL.md)
now passes raw metadata, the original script and interactive zsh/recovery.
Its new installed-image/FAT receipts supersede the current-state notes below;
these original diagnosis and failed strict-root trial remain unchanged.

This supersedes the unstaged/current-OS notes in the
[preparation checkpoint](GATE6-STAT-DIAGNOSTIC.md), not the original failed zsh
script or held storage/network acceptance. No kernel/VM source edit or rebuild.

## Installed image and protection

SSD Linux was freshly verified: boot `df67a6f1-d645-4ee5-97e3-d61276d7f2d6`,
`/dev/nvme0n1p2`, UUID `04570742-280b-43cb-9564-73d454243b1c`.
`stage_statprobe_trial.py` verified the exact card/layout and **28 historical
NVMe artifacts**, saved three fresh full snapshots and a separate current-image
copy, then installed only the regular-file diagnostic image. Protected files,
MBR and HFS bytes are unchanged; HFS was never mounted. FAT rename is not claimed
power-loss atomic; no XNU SD write/durability proof.

- Local receipt: `build/rpi5/statprobe-trial-installed-20261012/result.json`,
  SHA256 `c6ed4a222de1232d55eb69462b4918c8a553a328094e54f8007dee80f50c4c3b`.
- SSD run: `/home/sandrzej/xnu-gate6-statprobe-gjy3szzg`.
- Current `probe.bin`: 18,057,920 bytes, SHA256
  `822e52de88303be9edfe20dec51d14fe1476a0604c77040b56d6254f1a953e99`.
- Current complete FAT SHA256:
  `60b6ed08168bce63d5420665f955d56e958754f54e0f30ec861c940933413b52`.
- Previous zsh image `b3db210c...` is preserved on SD as
  `probe.zsh-interactive-passed-20261012.bin`, and in that SSD run as
  `zsh-interactive-passed.bin`. Earlier topology, W3, shell, Gate 3 and firmware
  backups remain protected. Do not rerun this or old installers on the new state.

## Strict trial failed safely; separate same-boot diagnosis completed

The recorder was armed before **one software SD reboot**, 17:56:49 UTC. No cold
power action, persistent firmware edit or soak. The exact new image loaded and
the loader verified its RAM-disk copy/full kernel before transfer into recovery.
Concurrent SMP UART writers tore the one-time kernel root-mount line. The strict
recorder correctly timed out with **zero TX**, zero accepted checks. That trial
remains **failed**; runtime mount count is not promoted from loader-copy evidence.

`mac-statprobe-trial-20261012` raw capture: 34,420 bytes, SHA256
`c82f6fa3e15dc9fe1c27a57db4aa2c2e14d7649604bcf554d46e507a390f3a0d`;
state SHA256 `67a91d9e447ccdc291cfb88b245c65a0d2b2bc262101a470185140c94c68f630`.

To avoid another restart, `serial_statprobe_followup.py` is a **separate bounded
read-only diagnosis**, not a bypass passing the strict root trial. It requires
the recent exact zero-TX timeout, unchanged capture, fresh matching preflight,
installed-image receipt, unique ordered SD/image extent/entry/UART markers,
exact verified RAM-disk copy, full kernel materialization, topology/transfer/
commit and recovery readiness. Explicit wrong roots, repeated boots, changed
extents, storage/fault output and expired evidence reject before input. Queued
output is inspected before the fresh nonce, never flushed away.

Actual follow-up: `mac-statprobe-followup-20261012`,
18:02:41.937634–18:02:47.026132 UTC. Nonce `F0c64a9c6550c9e4a`, 79 TX bytes,
clean diagnostic exit zero and live recovery nonce/prompt. Both recorders are
finished and serial is released. Last proven OS is **XNU**, not SSD Linux;
the existing development watchdog is not a guaranteed SSD-return mechanism.

- Raw: 6,203 bytes, SHA256
  `185f824497e05a0afede6967d0eac5665d80b4d0861f9872729f0829f0a884ed`.
- State SHA256: `ba9f8f2c2dbc9e2500713469761197256af9b7f46264c24898c84ecb39f751d3`.
- Offline validation SHA256:
  `ad6631fdcd6dc2e9789ef81f8b17f6fd5941e5e09b9c3d21d5c2f8c0b43c1faf`.

| Operation | Existing files/directory | Missing-path control |
| --- | --- | --- |
| access F_OK/R_OK | 0 | -2 (ENOENT) |
| stat64/lstat64 | -45 (ENOTSUP), all 144 A5 bytes untouched | -2, untouched |
| fstat64 on both files | -45, buffer untouched | Not attempted |
| plain and O_NOCTTY open | fd 3 | Not attempted |
| F_GETFD/F_GETFL; F_DUPFD(minimum 10) | 0/0; fd 10 | Not attempted |
| duplicate then original read | Exact 16 + 16 preserved bytes, shared offset | Not attempted |
| closes and canaries | Clean, intact | Intact |

No successful stat type was returned. Earlier `[[ -f ]]` failure is not evidence
of a corrupted type field; do not fabricate type bits or patch the frozen zsh.

## Matching omission and next correction

`vn_stat_noauth` requests allocation metadata. `vnode_getattr` refreshes mount
statistics when block size is zero, even if allocation sizes were supplied.
`vfs_update_vfsstat -> vfs_getattr -> VFS_GETATTR` returns ENOTSUP when the
filesystem getter slot is null, before stat copyout.

The **actual linked shell kernel** `d133f3a2...` has `_mockfs_vfsops` at
`0xfffffe00079a6fe8`, getter slot offset 40 equal to zero and no getter symbol.
The preserved corrective kernel
`build/rpi5-xcode27/fresh-435uage7/obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712`,
SHA256 `674e6a763a01a7e4becf0399d03641aa4e43ec1c1d995d67623546b9d64f5aad`,
has a verified actual pointer `0xfffffe000757ec80` in table `0xfffffe0007a3afe8`.
Its source correction is described in [the mount-stat checkpoint](GATE4-MOCKFS-STATFS.md).
The zsh image reused the older shell kernel, so that correction was absent.

`audit_statprobe_metadata.py` ties exact physical errors/buffer contents and
shared-offset file bytes to both hash-pinned kernel tables. Analysis-v2 SHA256:
`8c64fa9435eb665d36f4cbda1e7317303845fe43360132336f7c3e586ebcde2d`.
This is a strongly supported **causal inference**, not a physically verified fix.

Next review/package the preserved corrective kernel with the unchanged
diagnostic root, storage boot arguments absent and hardware operations disabled.
Preserve the current diagnostic image with a fresh **32-artifact** chain before
later installation. Then test raw metadata, the original script and interactive
zsh acceptance. Keep the torn strict-boot failure separate; fix robust identity
reporting rather than falsely passing it. Ethernet development is independent;
no networking, durability or full Gate 6 completion is claimed.
