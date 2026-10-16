# Socket trial: mounted-root identity before traffic

2026-10-12. This is a distinct v2 diagnostic/package, not a repair or waiver of
the earlier failed strict mount-log trial. Original Apple zsh/ifconfig/route,
PID 1, recovery and accepted kernel are unchanged. No persistent-storage
acceptance, Ethernet driver or SSH service is implied.

## Phased admission

The guarded installer binds the exact disposable card, previous installed
`b67b8013...` image and full FAT hash. It verifies all 40 prior SSD artifacts,
captures fresh complete FAT/HFS and MBR backups, preserves the prior image on
SSD and SD, changes only `probe.bin`, rechecks protection and unmounts FAT.
It does not change boot configuration, mount HFS, repair, retry or reboot.
The new profile extends the isolated remote install namespace; shared frozen
installer sources and historical profile maps are not changed.

The serial recorder first validates the exact package/installation receipts.
Ordered unique firmware extent, loader, root/kernel copy, topology, transfer,
commit, readiness and recovery prompt admit **only** this fixed read-only query:

```
/usr/local/libexec/xnu/socketprobe identity
```

A readable contradictory mount or duplicate/faulting boot is rejected. A torn
mount log is not mount proof and does not waive any historical strict trial.
The independent runtime query must prove:

- Raw Darwin `statfs64(345)` on `/`: mockfs, root/read-only flags, 16-KiB
  block/I/O size, 32 archive nodes, exact packaged allocated extent and no free
  blocks/nodes. External replay checks the extent, not a self-reported PASS.
- Guarded raw lstat64/fstat64, regular-file type/mode/size, matching opened
  device/inode, bounded nonblocking no-follow reads, EOF and SHA256 for every
  packaged regular file, including the executable performing the query.
- Exact visible archive directory metadata. `/dev` is special: XNU overlays
  devfs there, so another guarded statfs verifies `devfs` mounted at `/dev`.
  The covered empty archive `/dev` node is **not** claimed to have been read.

The helper compares preserved file hashes against its fixed generated catalog.
Its own size/hash are compared externally against the pinned package, avoiding
a circular self-hash. SHA256 reuses the already pinned pristine BearSSL source;
license and source/header hashes are retained. This is integrity/identity
diagnosis, not authentication against a malicious kernel.

Only after exact runtime replay does the recorder run a fresh recovery nonce,
the preserved original zsh script, and the v1 diagnostic's unchanged `unix`
and `inet` modes. Those modes test anonymous Unix stream sockets and literal
127.0.0.1 UDP/TCP payloads/half-close, not Ethernet. No interface setup or route
change is silently added if loopback is unconfigured. The real errno is kept.
Success ends with a live recovery command; failure stops without retries.

Identity has at most 2,048 data/metadata calls, reserving a close slot, 1,024
read steps per file and a 2-MiB per-file cap. Fds close once, including uncertain
close failures. Console writes are outside that bound. A hung kernel syscall
is not contained by finite userland counts or poll timeouts.

## Separate prepared artifacts

- Root: `build/rpi5/socket-identity-root-20261012-devfs/ramdisk.bin`, 1,916,928
  bytes, 32 nodes, SHA256
  `3fa5ed9f501cedd744b0d6d75cc0886837db562f3bd42282284d82e2798d9a27`.
- Helper SHA256
  `45c08337ce9ba453a56f7097af5240bb93a17a48c081d511bd878c659c25d0ca`.
- Root receipt SHA256
  `ea24195e8e816583654006856285812b133464f32e02bc6d2208497336ae4abe`.
- Boot: `build/rpi5/bl33-probe-vszhh6o4/probe.bin`, 19,384,000 bytes, SHA256
  `f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536`.
- Boot receipt SHA256
  `40dd908884cc1b031cbd081149ffc4c7238e991f841070b222ba8803c37b47be`.
- `check_socket_identity_package.py` passes 35 local package checks. Report:
  `build/rpi5/socket-identity-devfs-preflight-20261012.json`.

The earlier v1 root, package, receipts and failed physical trial are preserved.
Storage remains off; the loader logs PCI topology only, with no PCIe MMIO.

## Validation boundary

`test_socket_identity` covers actual native file/metadata/hash reads with
synthetic mockfs/devfs statfs, ASan/UBSan, partial and bounded one-byte reads,
every baseline syscall failure position, buffer damage, malformed filesystem/
metadata/fd returns, externally wrong self hash/extent, package pins, immutable
roots, full 40-artifact installer receipt coverage, isolated profile extension,
and refusal to send sockets before runtime identity or after source drift.
These are host/fixture checks, not Pi SVC/VFS or socket acceptance.

Fresh SSH confirms SSD Linux at `/dev/nvme0n1p2`, boot
`d5c3e702-5caf-4452-8799-7cd29803a06a`, the exact known card CID and unchanged
SD-first `BOOT_ORDER=0xf461`. Installation and physical outcome are recorded
separately below when performed; availability alone is not staging admission.

## Protected installation completed

`build/rpi5/socket-identity-installed-20261012` validates as installed and FAT
unmounted. All 40 prior artifacts were rehashed before and after installation;
fresh complete snapshots and the prior image are retained on SSD at
`/home/sandrzej/xnu-gate6-socket-id-2stact57`. The SD backup is
`probe.apple-network-diagnosed-20261012.bin`.

- Plan SHA256: `c9c519d8a24659ba2c185ab967c8f5c10c2ab8a8c3580b49874b17f7f8294edf`.
- Result SHA256: `4d189669fa7c4604d7b27f3f97c0081ea98a6ac55be233c0bb4eab2545b80282`.
- New whole FAT SHA256: `1ad719c6ab914b4b24c2f478ac31f83e052e750ee9a68b588060d415e562d3ff`.
- MBR and HFS remain exactly their prior hashes. No HFS mount, filesystem repair,
  firmware/config change or PCIe MMIO. Rename/fsync is not a power-loss-atomicity
  claim for FAT.

The exclusive Mac recorder armed before the single SSD-Linux software reboot.
Its bounded trial directory is `build/rpi5/mac-socket-identity-trial-20261012`.
Completion and runtime acceptance must come from that recorder's actual raw
bytes and subsequent independent replay, not this installation receipt.

## Physical result — 21:53 UTC

The trial **passed on the actual Pi** and `audit_socket_identity_trial.py`
independently replayed its exact commands, root catalog/self hash, socket
results, exit statuses, prompts and nonce. Seven checks passed. Capture ended
at `2026-10-12T21:53:46.225598+00:00`, 40,471 raw bytes, 347 transmitted bytes,
nonce `Sf84b43c1e9d97a73`.

- Runtime `/` is read-only mockfs: 32 archive nodes, 1,916,928 allocated bytes;
  all **21 regular-file hashes**, visible directory metadata and devfs overlay
  match. The covered archive `/dev` node remains explicitly unobserved.
- Original zsh 5.9 script/array/arithmetic/external-exec smoke exits zero.
- AF_UNIX: three 32-byte stream transfers, both directions, half-close/EOF and
  continued reverse traffic; 26 operations, helper/zsh status zero.
- IPv4 literal loopback: two 32-byte UDP transfers with peer validation, then
  TCP listener/nonblocking connect/poll/SO_ERROR/accept, three bidirectional
  stream transfers, half-close/EOF and reverse traffic; 62 operations, status
  zero. `CONNECT=-36` is the expected EINPROGRESS; SO_ERROR subsequently is 0.
  No interface or routing configuration was needed or performed.
- A fresh recovery echo returns its prompt. The recorder has exited and
  released serial. Last proven board OS is XNU in recovery, not SSD Linux.

The first paced identity command echo contained two exact shell-readiness
frames and one watchdog kick. Independent replay initially rejected that
interleaving; the bounded first-echo parser now reconstructs only those exact
notifications before the four zsh startup lines, checks the entire original
command, and rejects arbitrary inserted output. No notification stripping is
allowed in identity results or later commands. Raw bytes are unchanged. Tests
cover both permitted notifications and malformed/extra-output rejection; the
real frozen physical capture is also replayed without touching hardware.

Final selected regression run: **157 tests pass in 48.524 seconds**, including
17 identity/package/installation/recorder/replay tests. This is a selected
suite, not all XNU tests or complete service/NIC acceptance.

Evidence in the trial directory:

| File | SHA256 |
| --- | --- |
| `serial.bin` | `c42a84b9cafab48c9a05443477f049fd434a5b8ede99da3abb968ad641088baf` |
| `state.json` | `ff34e71815cdf0bff89a3c9f910a336ee97e51244cd9ce16b2aed9f36c49bde1` |
| `validation.json` | `69428393577d190e3cdad19ecf85c69679df2c5e491fc481aedecb9bf2e6da05` |

This closes the first physical Unix/UDP/TCP loopback diagnostic milestone,
not full socket/TTY compatibility, Ethernet, Wi-Fi, SSH, graphics or Gate 4.
Keep the full goal active. Next advance concrete PCIe/RP1 provider integration
and original SSH runtime dependencies without requiring another immediate
manual reboot or soak.
