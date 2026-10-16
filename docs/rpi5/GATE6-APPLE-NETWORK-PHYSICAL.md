# Original Apple networking tools: physical same-boot diagnosis

2026-10-12 UTC. Original `network_cmds-396.6` ifconfig/route executed on Pi XNU
at their upstream `/sbin` paths. This is **not a passed strict fresh-mount trial,
working Ethernet, packet traffic, SSH or Gate 4 durability**.

## Image and protected installation

`build/rpi5/bl33-probe-i3d1ah4e/probe.bin`, 19,334,848 bytes, SHA256
`b67b8013361b94b1874d7f0bbe6013d1c8efc99ca37b0debf7bc0012915f9ce8`.
Loader manifest SHA256
`47bf3fc69041d731fded0a9528bc8302c01889fd1d2768b7a9321f77fa6e93f5`.
Uses unchanged accepted kernel `674e6a76...` and additive 27-node root
`0fdb9540...`; existing recovery/zsh/statprobe bytes/modes are preserved.
All 28 local package checks pass.

The kernel audit maps the two utilities' 36 distinct BSD syscall numbers
through actual `_sysent` slots to file-backed handlers, including socket,
sysctl and ioctl. It checks `_nsysent`, the 24-byte entry layout and a nosys
negative control. Symbol presence alone is insufficient. This is not complete
Mach/platform trap, ISA, call-path or syscall-semantics qualification.

Fresh SSH verified `kamidana`, SSD Linux boot UUID
`23738cc3-f560-4de2-bd06-a7b5c5b86426`, root `/dev/nvme0n1p2`, ext4 UUID
`04570742-280b-43cb-9564-73d454243b1c`. The installer reverified exact authorized
128,177,930,240-byte SD CID `1b534d474432533530654f68d1a16100` and partitions.
All 36 prior SSD backups verified. Three fresh complete MBR/FAT/HFS snapshots
and the old image were preserved in `/home/sandrzej/xnu-gate6-apple-net-op2sjbnc`.
Known-good zsh is also retained as SD `probe.zsh-metadata-passed-20261012.bin`.

Receipts: `build/rpi5/apple-network-installed-20261012`:

- Plan SHA256: `4eef009e31488479d8a8d34f6548ad5b22c1e76c57a63a06700769fe33b11e2a`.
- Result SHA256: `1dadcc9be3a8513bdff363a62e74cdc5bd4999a52160eff9b133cf12a836a49e`.
- Installed FAT SHA256: `ed51edc3c7209a5bb1efb72d8dfd17d4824db9314fd968075b8915f45134b205`.
- Protected MBR remains `c5e2c9b8...`; HFS remains `168c89cb...`.

Mac Debug Probe serial `E66480454F719939` and free `/dev/cu.usbmodem102` were
freshly verified. Exclusive capture armed before a guarded software reboot;
SSD root/boot ID/card CID/unmounted SD/full installed FAT and persisted
`BOOT_ORDER=0xf461` were rechecked first. No EEPROM/transient boot-order change,
physical power cycle, HFS mount, repair, partition change or soak occurred.

## Failed strict trial; successful separate diagnosis

`build/rpi5/mac-apple-network-trial-20261012` ran 20:15:08–20:18:08 UTC and
timed out with **zero TX**: SMP startup output corrupted the mount line.
Exact image read, verified root/kernel copies, topology-only profile,
transfer/commit and recovery readiness are intact. No same-boot waiver was
added to that strict trial.

The separate follow-up uses the existing statprobe diagnostic pattern. It
requires a recent hash-bound zero-TX timeout, exact unique ordered loader/copy/
transfer evidence and current installed receipt. Wrong roots, duplicate boots,
payload rejection and faults reject. Queued serial bytes are retained and
inspected, not flushed. It does not convert the missing mount line into proof.

`build/rpi5/mac-apple-network-followup-20261012`, 20:20:18–20:20:27 UTC:

- Original `zsh -f /etc/zsh-smoke.zsh`: version 5.9, array/arithmetic, external
  exec, SMOKE_DONE and exit zero.
- `/sbin/ifconfig -l`: actual `lo0`, exit zero. This is software loopback,
  **not an Ethernet NIC**. No packet test occurred.
- `/sbin/route -n`: actual usage, expected exit 64. Reviewed original source
  opens `socket(PF_ROUTE, SOCK_RAW, 0)` before usage and exits fatally on socket
  failure. Reaching usage supports that limited socket-open path. There is
  no route operand, message send or route alteration.
- Fresh final recovery nonce and returned recovery prompt.

216 TX bytes; 856 captured bytes. The idle banner split the first command echo;
queued initial bytes include unclassified noise. Replay requires the unique
actual nonce response, then exact subsequent command echoes, ordered output,
statuses and prompts. This is not clean startup/full TTY or socket qualification.

- Serial SHA256: `a26d7bb78c13af1b58eb4a3048a1f05018ac628f560a3994933957e1c2d7209a`.
- State SHA256: `a8eab6c2d818e6643925dcce74536ef1ab351a28069daa83b64e13e9c90cfe01`.
- Independent validation SHA256: `c67de6d90d8ba8212f639e1b35caa4ca4dc29d2dc55e028c40969020ce43a422`.

`audit_apple_network_followup.py` reopens the package, installation and failed
capture, binds hashes, enforces time/TX bounds and replays actual output.
Mutated commands/results/claims reject. It retains false strict-mount and
mounted-node-count claims. Serial is released; last proven state XNU recovery,
not SSD Linux. Do not rerun old installers: the next chain has 40 SSD artifacts.

## Next work

Continue PCIe access/recovery admission and RP1 NIC integration independently;
loopback enumeration cannot substitute for Ethernet. Prepare bounded socket
data-path diagnostics and compatible Apple tools next. Fix reliable post-mount
identity/framing before strict fresh-root acceptance; do not repeat cycles to
get lucky with concurrent logging. Preserve zsh and all current evidence.
[Darwin filesystem conventions](FILESYSTEM-CONVENTIONS.md) remain in force.
