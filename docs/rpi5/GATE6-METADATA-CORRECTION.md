# Corrective metadata kernel: physical trial passed

2026-10-12 19:03 UTC: the prepared package below is now installed and has passed
strict fresh-boot raw metadata, original script, interactive zsh and recovery
acceptance plus independent byte replay. See [physical result and new baseline](GATE6-METADATA-PHYSICAL.md).
This is not full Gate 6, networking or durable-storage acceptance. Earlier
preparation text below remains historical; do not repeat its installer.

## Preparation history, before 19:03 UTC

2026-10-12. Gate 4 durability is still held on the existing card; this work is
independent. The [physical raw-file diagnosis](GATE6-STAT-PHYSICAL.md) remains
authoritative for the running image and failed script acceptance. No old trial
is reclassified as passing.

## Prepared artifact

`build/rpi5/bl33-probe-wdmzdtem/probe.bin`, 18,908,864 bytes:

```
352603430e44ee28e5543ab5de6bd8dba2d606ea8a406b8a0f32815a6a998faa
```

It pairs the already-built corrective kernel
`build/rpi5-xcode27/fresh-435uage7/obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712`
(`674e6a763a01a7e4becf0399d03641aa4e43ec1c1d995d67623546b9d64f5aad`)
with the unchanged 25-node statprobe RAM root
(`5644490c8969d930ad706101ab0656dcfafac78846aca51933f2eb3ec128cc23`).
Recovery, frozen zsh, script and diagnostic bytes are preserved. No shared
kernel/VM source edit or new kernel build was required.

`tools/rpi5/check_zsh_metadata_package.py` passes all 37 host checks. Report:
`build/rpi5/bl33-probe-wdmzdtem/metadata-preflight.json`, SHA256
`1f4ec54b4519f8db55d416a0946f8872f7286e7629c298b37f736c9618e8e60b`.
The original diagnostic checker's public kernel pin is unchanged; the old and
corrective package profiles deliberately reject each other.

## Actual linked checks, not source assumptions

The corrected kernel has `_mockfs_vfs_getattr` wired into the actual vfsops
getter slot. The physical old kernel lacks that getter. Missing mount geometry
is a supported explanation for the observed ENOTSUP, not yet a physically
verified correction.

This preserved kernel also includes a read-only SD provider. Its actual linked
entry bytes were independently disassembled: absent or non-one
`bcm2712_sd_readonly` returns false before `readBinding`, register mapping or
later calls. The package omits that opt-in and embeds exactly the storage-off
terminal command. The reviewed kernel has no write-provider class/boot opt-in.
The new fixed-signature checker rejects guard, argument, layout, protection,
symbol or writer-profile drift. This proves the reviewed rejection path, not a
runtime observation that no storage access happened.

Seven focused test methods pass, including mutation of every checked guard/
epilogue/argument byte, bad mappings and symbols, package/profile separation,
and invalid build-receipt semantics even with a matching receipt hash.

## Next bounded steps

The distinct installer and finite recorder are now implemented locally, not
executed against the Pi:

- `tools/rpi5/stage_zsh_metadata_trial.py` pins the current diagnostic install
  plan/result and full FAT baseline. It carries forward 32 exact NVMe artifacts,
  then makes fresh full MBR/FAT/HFS snapshots and preserves the current image on
  SSD and SD. Existing zsh/topology/recovery files remain protected. Profile
  `zsh-metadata-trial` uses separate backup/temp names; no automatic retry,
  rollback, HFS mount, firmware change or reboot is included.
- `tools/rpi5/serial_zsh_metadata_trial.py` requires a matching installed receipt,
  the exact new image, fresh firmware/loader/copy/transfer markers and the strict
  25-node mount marker before any TX. A torn mount log still stops with zero TX;
  the prior failure and expired follow-up guard are unchanged. After a fresh
  nonce, raw stat/lstat/fstat must actually return the original file types/sizes,
  successful plain/NOCTTY opens and shared-offset content, intact guards and the
  missing-path ENOENT control. Diagnostic exit zero alone cannot launch zsh.
  It then requires the original script and exit zero, both interactive startup
  traces, actual version/array/arithmetic/external-exec output and live recovery.

Four installer tests cover chain/template/receipt drift and no-retry preservation.
Seven serial tests cover exact fresh admission, zero TX on wrong boot, semantic
metadata/descriptor/content faults, rejection of the actual old ENOTSUP capture,
stopping before zsh on failure, and complete original-script/interactive/recovery
sequencing. These are synthetic/local tests, not additional Pi results.

Remaining before physical correction acceptance:

1. The independent byte-replay audit is implemented in
   `tools/rpi5/audit_zsh_metadata_trial.py`. It rechecks the actual package and
   exact installation receipt hashes, fresh strict copy/mount markers, finite
   command-input extent, raw metadata semantics, original script output/exit,
   two interactive startup traces, correct subsequent prompts and live recovery.
   It rejects broader gate/network/durability claims. Five audit tests include
   rehashed transcript mutations, forged matching metadata observations and a
   rewritten otherwise-equivalent receipt. These are synthetic/offline tests,
   not an actual successful correction capture. Run the audit against the real
   completed recorder output before accepting its result.
2. Verify fresh SSD Linux and the exact card/current raw baseline before invoking
   the new installer with `--execute`; do not reuse an old installer or invent a
   verified boot UUID. The fresh SSH check still times out; no current Linux
   boot identity is known.
3. Arm the distinct recorder before one guarded software boot. Only after
   staging protections and fresh boot admission, run raw metadata,
   then the original zsh script and interactive acceptance, ending in recovery.
   Do not fabricate file types or change frozen zsh to hide a kernel error.

This artifact is **not installed or physically tested**. No networking,
script-file success, full Gate 6 exit or durability acceptance is claimed.
Fresh SSH timed out; no automatic Linux return is assumed. No serial, SD,
power, firmware or EEPROM operation was performed for this preparation.

Independent networking remains active: power/clock/shared ownership and Device
access, then RC/UBUS/windows/PERST/link training, RP1 IRQ/DMA and Ethernet.
Socket/SSH dependency closure and additional RAM-root utilities can proceed
without accepting durable SD writes. Physical networking still needs the Pi;
host tests alone do not establish a trained link or packet transfer.
