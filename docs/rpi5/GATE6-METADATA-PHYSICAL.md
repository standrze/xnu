# Physical Pi zsh metadata/script correction — 2026-10-12 19:03 UTC

The corrected image passed one strict fresh-boot trial on the physical 8-GB Pi 5.
Raw file metadata now succeeds; the **original** zsh script executes and exits
zero; interactive zsh 5.9 computes builtin output, runs an external command,
returns prompts and exits to live recovery. Independent offline byte replay
passed against the actual package and exact installed receipts.

This is a new successful trial, not a reclassification of the original failed
script or the earlier torn-mount diagnostic. Those captures remain unchanged.
It does not complete Gate 6's full distribution/ABI/TTY scope, prove an isolated
kernel root cause, provide Ethernet/SSH, or admit Gate 4 durable writes.

## Installation and protection

Fresh SSD Linux boot: `7eaed962-0050-4e4d-a6b0-106f1fd46bd6`, hostname `kamidana`,
root `/dev/nvme0n1p2`, ext4 UUID `04570742-280b-43cb-9564-73d454243b1c`.
The exact existing disposable card was rechecked, including CID
`1b534d474432533530654f68d1a16100`, capacity 128,177,930,240 bytes, MBR layout,
FAT `XNU_PROBE` UUID `4FA7-3725`/PARTUUID `5ae1f07e-01`, and unmounted HFS.

`stage_zsh_metadata_trial.py` verified all **32 historical NVMe artifacts**,
saved and readback-verified fresh full MBR/FAT/HFS snapshots, preserved the old
diagnostic image on SSD and SD, installed only the new FAT regular file, then
reverified protected files/raw extents and unmounted FAT. No HFS mount/write,
partition, configuration, persistent firmware/EEPROM edit, retry or rollback.
FAT rename is not claimed power-loss atomic. The spare-card durability hold
remains independent.

| Artifact | SHA256 |
| --- | --- |
| Current `probe.bin`, 18,908,864 bytes | `352603430e44ee28e5543ab5de6bd8dba2d606ea8a406b8a0f32815a6a998faa` |
| Corrective kernel | `674e6a763a01a7e4becf0399d03641aa4e43ec1c1d995d67623546b9d64f5aad` |
| Unchanged 25-node RAM root | `5644490c8969d930ad706101ab0656dcfafac78846aca51933f2eb3ec128cc23` |
| Complete post-install FAT | `18b6fdf87a5438df040c1266189ea6cb1f4420a44448b5c8d4d7c8eaf6f89e09` |
| Protected MBR, unchanged | `c5e2c9b892f23d51d496e09363f872882a18e55fb1530080e38a511b93324b4a` |
| Protected HFS, unchanged | `168c89cb97645ba07b353b3584087e5770d9c2793c6e86b7a8bc3471cbb477e1` |

Receipt directory: `build/rpi5/zsh-metadata-installed-20261012`.
Plan SHA256 `a3351305fb88c445b0979098b4ce25c043c1f6af3ad766d99376a5129997e433`;
result SHA256 `c93c515375365984715585a849c383ffee1894588d4735202d1d93f56f32a7dc`.
SSD run: `/home/sandrzej/xnu-gate6-metadata-4nivsj7n`.
Old diagnostic `822e52de...` remains in SSD `statprobe-diagnosed.bin` and SD
`probe.statprobe-diagnosed-20261012.bin`. Earlier interactive zsh, topology,
W3, recovery shell and Gate 3 backups remain protected. A future installer
must derive the new current baseline and preservation chain from these receipts;
do not rerun an old installer or merely substitute hashes to force acceptance.

## One armed boot and physical results

The verified Mac Debug Probe `E66480454F719939`, `/dev/cu.usbmodem102`, was free
before exclusive capture. The recorder armed at **19:02:04.159030 UTC** before
the guarded software reboot at **19:02:25 UTC**. The existing transient
`vcmailbox 0x0003808b 4 4 0xf61` request selected SD; recorded EEPROM remained
`BOOT_ORDER=0xf461`. No physical power cycle or soak was requested.

Before TX, the recorder required the exact 18,908,864-byte firmware read,
unique ordered corrective RAM-disk/full-kernel copy markers, declarations-only
PCIe profile, transfer/commit, strict intact 25-node mount line and recovery
readiness. It did not reuse the expired same-boot waiver. Nine acceptance checks
passed; 330 bytes were transmitted with fresh nonce `Z4c69ae90bcd1bf6d`.

- `/etc/zsh-smoke.zsh` and `/etc/motd`: access/stat/lstat/fstat all succeed,
  mode `0100444`, sizes 211 and 63 bytes, intact 144-byte raw-buffer canaries.
  Plain/O_NOCTTY opens, descriptor flags, duplication and exact shared-offset
  16+16-byte reads pass; all closes succeed.
- `/etc`: stat/lstat succeed, directory mode `040555`, size zero. The missing
  path returns ENOENT with untouched A5 buffers and intact guards.
- `zsh -f /etc/zsh-smoke.zsh`: actual version, arithmetic/array and external-exec
  outputs, `SMOKE_DONE`, returned recovery prompt and exit status zero.
- Interactive launcher: both expected startup traces, actual `pi-zsh# ` prompt,
  `PI_ZSH:5.9`, `PI_BUILTINS:xnu:42`, external nonce output and returned prompts.
- `exit` returns to recovery, which executes a fresh recovery nonce command.

Capture ended at **19:03:28.500490 UTC**, 40,922 bytes. Recorder is finished,
the serial descriptor is closed/released, and the last proven OS is **XNU**
in recovery, not SSH Linux. No automatic SSD return is assumed from its
existing development watchdog. No kernel/VM source change or new build was
needed; the frozen zsh/root content was not altered to hide a metadata error.

## Independent replay and limits

Evidence directory: `build/rpi5/mac-zsh-metadata-trial-20261012`.

| Evidence | SHA256 |
| --- | --- |
| `serial.bin` | `5ad1778eb5d1c062df0c1eef60d5f68e62f0d06cc56df881b7fe1ad5e0ff4ecd` |
| `state.json` | `91d99dd462df04118df2999702a4608449b78e421374857e43a7feea64453e5a` |
| `validation.json` | `26ef9cadd6c871239db0592581a3fcf14f9a66c7cd9443cc81106a227cbd2cc1` |

`audit_zsh_metadata_trial.py` replays actual raw bytes and rebinds the exact
package/receipt hashes, strict boot markers, input extent, raw metadata,
original script, interactive outputs/prompts and final recovery. It does not
trust the recorder's pass flag alone. An optional hash-pinned saved-physical
regression now repeats this audit; it does not contact the Pi or serial port.

All **88 selected host regressions** pass (11.862 seconds), including the saved
physical replay, PCIe component tests, package/staging/recorder and synthetic
failure checks. All 24 metadata-specific tests pass separately. Those counts
are regression coverage, not additional physical boots or broader ABI proof.

The full objective remains open: broader signals/job control/TTY and runtime
compatibility, PCIe provider/link/RP1 interrupts/DMA/GEM, socket diagnostics,
SSH dependencies/services, more RAM-root utilities and durable storage.
No additional cold boot or soak is required for this fixed-path script milestone.
