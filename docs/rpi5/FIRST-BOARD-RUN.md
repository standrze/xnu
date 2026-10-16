# First standalone BL33 run

Status: preparation only, 2026-09-10. Test SD media is now selected and formatted;
no boot configuration is approved. This procedure collects diagnostic evidence; it does
not claim an XNU boot or completion of Gate 1.

## SD preparation update

The user explicitly authorized erasing the inserted 119.4 GiB SD card.
Before formatting, hardware CID `1b534d474432533530654f68d1a16100`, exact capacity
128177930240 bytes, unmounted state, and root on `/dev/nvme0n1p2` were checked.
Only `/dev/mmcblk0` and its old partitions were changed. Old FAT/ext4 signatures
and the partition table were removed, then a DOS partition table with ID
`0x5ae1f07e` and one FAT32 partition was created: start sector 2048, size
1048576 sectors (512 MiB), label `XNU_PROBE`. Remaining space is unallocated.
This was reformatting, not secure sanitization; no old-data backup was made.

Read-only `fsck.vfat -n /dev/mmcblk0p1` completed successfully afterwards.
The NVMe boot/root filesystems remain mounted and unchanged. No boot files,
EEPROM changes, or reboot have been performed. Boot-path selection is still
pending; the earlier no-SD inventory below is historical.

The newest re-audited probe candidate is `build/rpi5/bl33-probe-k72eatix`, with
full live extent `[0x6000000,0x70b23b0)`. Native validation and host-buffer copy
agree for its embedded kernel. As before, this is not physical-placement proof;
the older candidate below is retained as historical provenance.

## Confirmed live baseline

A read-only SSH query to `sandrzej@192.168.4.23` returned:

- EEPROM release `086b83e3332dfc8927c56762771d082f3077a1ae`, dated
  2026/05/26 16:01:25; timestamp 1779807685, update-time 1786421684.
- `BOOT_UART=1`, `POWER_OFF_ON_HALT=0`, `BOOT_ORDER=0xf146`.
- Installed `/boot/firmware/bcm2712-rpi-5-b.dtb` SHA-256
  `e67017e5d45b97af478ebc93d651a086f2adcb6a650fe453eb9f1cf47e66473f`.
- Only physical disk: 238.5G NVMe, with mounted boot and root partitions.
  No SD or USB storage was listed.

Boot order is read right-to-left: this configuration tries NVMe, USB, SD,
then restarts the sequence. An inserted SD card therefore does not supersede
the bootable NVMe. See the official
[BOOT_ORDER documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#BOOT_ORDER).

Before the experiment, obtain an explicit choice of boot selection: an approved
boot-order change with the old value saved, or physical isolation of the NVMe
while fully powered off. Do not disconnect live PCIe hardware. Do not alter
the working NVMe's boot files to force fallback. Neither option has been
performed or authorized by this document.

## Candidate artifacts, not a boot bundle

TF-A source is pinned by `tools/rpi5/tfa.lock.json` to
`332b62e0443b004287d2cfc032a70bba6fb86f35`; its checkout was clean during
this check. Existing `build/rpi5/tfa-candidate/build/rpi5/debug/bl31.bin` has
SHA-256 `413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46`.
This observation is not a reproducible-build attestation: preserve/recheck the
actual build options, toolchain and source manifest before selecting it.

`build/rpi5/bl33-probe-1m_jzldv` is the current host-audited embedded-kernel
candidate. Its full live extent, including BSS and stacks, is
`[0x6000000,0x70b1a70)`. The build manifest explicitly says placement is not
board-verified. Recompute that extent from the selected ELF after every rebuild.
The probe still terminates with `RPI5XNU:BL33:STOP BEFORE XNU LOADER`.

The installed DTB hash identifies a candidate input, not the eventual runtime
FDT: firmware modifies the tree before BL33 entry. Do not archive the complete
runtime FDT without a reviewed seed-redaction policy. Record only required
non-secret diagnostics. EEPROM identity is observed, not a saved EEPROM image.

## Execution sequence and stop conditions

1. User designates disposable SD/USB media. Resolve its exact device identity,
   capacity and mounted partitions before requesting any destructive write.
   Never select the active NVMe. Back up anything the user wants retained.
2. Review a self-contained FAT boot partition using the pinned TF-A platform
   instructions. Its supported mechanism is `armstub`, an explicitly named
   BL33 kernel file, and explicit kernel/FDT load addresses. Do not copy the
   Linux config wholesale: automatic initrd/overlays and unrelated allocations
   change the ownership problem. No runnable config is supplied yet.
3. Resolve complete firmware exclusions and selected artifact extents before
   accepting placement. The synthetic geometry in RESERVATION-POLICY.md is
   not permission to load there. Rehash every selected artifact and preserve
   config, provenance, ELF, raw binary and build manifest together.
4. Select the approved boot path and recovery procedure. Start receive-only
   capture on `sandrzej@192.168.4.76`, stable probe path
   `/dev/serial/by-id/usb-Raspberry_Pi_Debug_Probe__CMSIS-DAP__E66480454F719939-if01`,
   at 115200 8N1. Wait for `CAPTURE_READY` before the authorized power cycle.
   `tools/rpi5/capture_serial.py` is bounded and does not reboot or transmit.
5. Preserve the complete raw log and capture manifest, even on failure. Check
   firmware identity, actual FDT address/size, RAM/reservations, UART divisors,
   CPU identity/features, normalized EL1 state, PSCI and per-CPU timer IRQs.
   A Linux login prompt means the intended test image did not execute.
6. A fault, rejection, timeout, missing CPU or absent IRQ result is a failed or
   incomplete diagnostic run, even if the terminal stop marker appears. Do not
   infer success from that marker alone. Restore the approved normal boot path
   and verify Linux/SSH recovery; record recovery evidence.

Entropy qualification, final ownership/type provenance, runtime tree/loader
integration and the remaining Gate 0 providers are separate unresolved work.
This diagnostic run does not require pretending those are complete, and it
does not authorize transferring control to XNU before their contracts are met.
