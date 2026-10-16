# Actual early PCIe-access diagnostic

## Latest physical result — 2026-10-12

The exact 53,376-byte candidate below now **physically passes all 30 ordered
register reads** on the Pi, including real halfword reads, in **578,620 us**.
Actual result is RC 0 / 184 callbacks, followed by the explicit no-write/
no-config/no-DMA/NIC_READY=0 observation and non-servicing stop. All 15 values
match between the two snapshots; this is not a lifetime-stability claim.

The single 45,200-byte, uninterrupted, zero-TX Mac capture spans fresh SD boot,
all exact READ_BEGIN/READ_END pairs and subsequent autonomous reset/BOOTSYS/
bootloader, actual `0xf6` override and NVMe selection. Independent SSH confirms
new SSD Linux boot **`3977a538-fae5-434d-a94f-50c9422fea84`**, root
`/dev/nvme0n1p2`, ext4 UUID `04570742-280b-43cb-9564-73d454243b1c`, mode 6,
partition 1, tryboot 0. This is one software trial, no manual power cycle,
repeated install/boot or soak. Firmware/config/HFS data remain unchanged.

Some important raw observations (identical in both passes):

| Address | Value | Limited conclusion under existing project predicates |
| --- | --- | --- |
| `0x1000124068`, status | `0x0001e080` | `(status & 0xf0) == 0x80`, the project's RC-down predicate; not live-link `0xb0` |
| `0x1000124064`, control | `0x00000000` | Project PERST-release bit 2 is clear; does not establish global shared-domain ownership |
| `0x10001200be`, halfword link status | `0x9011` | Retained raw; must not infer negotiated live speed/width while link-up predicate is absent |

Full exact 30-value data and independent replay are retained at
`build/rpi5/mac-pcie-access-trial-20261012/access-replay.json`.

The new installer/recorder use separate fixed profiles, private remote profile
maps and actual immutable guarded publication/copy/hash helpers. The historical
publisher and validators are not modified. Initial staging verifies **52**
inherited NVMe artifacts plus fresh complete MBR/FAT/HFS snapshots and working
image backup. Explicit restoration after recovery verifies **56** artifacts,
takes a new snapshot set, preserves this tested access image and restores
working zsh image SHA256
**`f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536`**.
Final independent SSH confirms the same new Linux boot and both SD partitions
unmounted. New FAT SHA256 is
**`fd2d20729dca2025df35310eb1165a64692d0bed3e604bb8f77355ff28ec8033`**;
MBR/HFS hashes and every protected config/firmware/image remain unchanged.
The next installer must use this restored receipt and **60 inherited artifacts**,
not an earlier same-image/different-FAT baseline.

Evidence:

- `build/rpi5/pcie-access-installed-20261012/`: plan SHA256
  `a9f0221690bf6f86ea513cbd76bc90dba598dd855a3cb60e6004f7245fa3f075`,
  result `c7f3291048eb640d888e39c55020b88ab2f78beb0c7f63b721be75945bf18cf5`.
- `build/rpi5/mac-pcie-access-trial-20261012/`: serial SHA256
  `9e3cc38c061a26f9d7ea0f45d70564a4779e3afb44dce5a058b3ae014d0e2b1b`,
  byte-offset/monotonic journal, source/installation binding and fresh Linux
  return receipt. The image is bound by its exact verified installation and
  fresh SD-boot sequence; this historical candidate has no unique UART tag.
- `build/rpi5/pcie-access-restored-20261012/`: plan SHA256
  `b61c5f43270dd15f9195939dca5eaaa5de5ecf26a845adb8e561bf8e80e5c546`,
  result `0dd7f83b3b63906ca03128d90a71befa00b4afa90ae2aaef3c0b769593f04f80`.

```
python3 tools/rpi5/check_pcie_access_evidence.py
python3 -m unittest tools.rpi5.tests.test_pcie_access_install \
  tools.rpi5.tests.test_pcie_access_serial \
  tools.rpi5.tests.test_pcie_access_evidence -v
```

The parser requires every exact pair/address/width/pass/index, valid register
value, 184-callback result and <=5-second measured duration. Tests reject all
30 invalid-value/missing-pair positions, duplicate/reordered/wrong image/width/
address/fault/success-flag mutations. Native publisher tests run the actual
copy/guard/rename path with isolated names; accepted maps stay unchanged.
Aggregate replay additionally checks uninterrupted journal/source/installation
binding, later reset/boot sequence, fresh SSD identity and verified restoration.
The source/build manifest's original no-hardware claims are preserved as build
snapshots, not retroactively rewritten.

All **88 focused regressions pass in 20.872 seconds**, including independent
saved physical access/recovery/restore replay and the earlier saved watchdog/
zsh/socket results. The accepted 2,435 IRQ-transport and 2,411 IRQ-kernel source/
output pins still match; all 35 unchanged zsh/socket package checks pass. The
earlier complete 286-test kernel result remains separate, not newly rerun.

**Next:** close concrete power/shared reset/firmware/source/endpoint/DMA and
interrupt ownership for the already implemented controller composition, then
add its actual boot caller and make a distinct watchdog-contained controller
trial. Follow with RP1 config/BAR discovery, IRQ delivery, coherent DMA/GEM and
wire packets. This successful read-only experiment does not admit those writes
or claim Ethernet, SSH, new XNU userland execution or Gate 4 durability.

## Historical source/build acceptance (superseded by the physical result above)

Continuation 2026-10-12: a separate
[real kernel watchdog ownership layer](GATE5-PCIE-WATCHDOG-OWNER.md) now compiles
and tests without changing this standalone candidate or any accepted image.
It prevents other kernel timer/callout writers from feeding after a diagnostic
claim, but physical reset timing/return and the concrete PCIe owner remain
unproved. Later historical SD configuration records `set_reboot_order=0xf6`;
the old `0xf461` interpretation below is not a fresh current-config reading.

2026-10-12. A **distinct standalone ARM image** now contains real register loads,
not just host callbacks: `build/rpi5/pcie-access-vo0exx93/probe.bin`, 53,376 bytes,
SHA256 `f276e0be0d6c9d670189f425c623a86de70e5defce413315d03ab458dd02b10d`.
Manifest SHA256 `e28aed3208f013a05872907cfa202695822d5ac1cdf06e132668261457012c45`.
It is **not installed or Pi-executed**. Passing local checks explicitly leaves
`installation_admitted=false` and `hardware_recovery_proven=false`.

The image is a prerequisite accessibility/recovery experiment, not the finished
PCIe controller provider, link training, RP1 enumeration, Ethernet or SSH.
Gate 4 durability remains independently held. No current boot image, serial
session, SD partition, firmware, kernel, frozen zsh or VM work was changed.

## Executable implementation

- `loader/rpi5/pcie_access.{h,c}`: exact private read allowlist, one-shot state,
  guard/timestamp/log sequencing, two passes, 184-callback bound, 5-second
  returned-callback deadline, unchanged output and quarantine on failure.
- `loader/rpi5/access_mmio.S`: actual `LDR W0` / `LDRH W0` leaves bracketed by
  `DSB SY`, with **no exception fixup or invented IO-error return**.
- `loader/rpi5/probe_access_main.c`: actual EL2 preflight, existing unmodified
  EL2-to-EL1 entry, masked primary-only EL1 execution, PM-watchdog provider,
  UART stage logging and fatal exception reporting/parking.
- `tools/rpi5/build_pcie_access_probe.py`: separate local build/source-output
  manifest. It has no installation, SSH, serial, media or reboot path.
- `tools/rpi5/check_pcie_access_package.py`: independent hash/ELF/profile/
  source-list/stack checks plus exact emitted word/halfword leaf-byte checks.
  It never treats a passing build as admission to install.

Early entry checks MMU/cache-off, little-endian data accesses and masked DAIF.
Unchanged `probe_entry.S` establishes HCR.RW-only (no stage 2, DC override or
VHE) before EL1. No EL1 attempt to read privileged HCR_EL2 is made. The
[Arm memory-model guide, section 3.2](https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/Learn%20the%20Architecture/Armv8-A%20memory%20model%20guide.pdf?revision=58b1dd0a-3800-4218-b21a-f95a0332034c)
describes Device-nGnRnE data accesses with stage 1 disabled and unmodified
stage-1 attributes when stage 2 is disabled. The compiler uses strict alignment
and general registers only. This is an early flat-address diagnostic, not a
new kernel Device-page mapping or a recoverable memory probe.

Before any PCIe/reset/calibration register access, the image validates runtime
FDT structure, phandles, exact PCIe/RP1/PM/UART bindings, advertised RAM, fixed
firmware exclusions, the complete live loader/FDT extents and SMC PSCI binding.
The current affinity must match CPU 0 and AFFINITY_INFO must report the other
three CPUs OFF. No CPU_ON is issued. Dynamic pool declarations are not allocated;
no kernel or allocator is started. Trusted firmware must still provide the
readable FDT window and initial loader/RAM ownership: parsing cannot discover
whether arbitrary physical memory is safe to read.

## Exactly what is read

Each of two passes performs the following fixed reads, with a drained UART
READ_BEGIN marker before issuing each table access and READ_END afterward:

| Resource | CPU physical address or offsets from its base | Access width |
| --- | --- | --- |
| Reset-44 status bank | `0x1001504338` | 32 bits |
| Shared RESCAL | `0x1000119500`, `0x1000119508` | 32 bits |
| PCIe2, base `0x1000120000` | `4068`, `4064`, `406c`, `4008`, `043c`, `0188`, `04dc`, `4304`, `184c` | 32 bits |
| PCIe2 root link fields | `00dc`, `00be`, `00bc` | 16 bits |

These named registers are not clear-on-read status sources in the reviewed
[controller](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c),
[reset](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/reset/reset-brcmstb.c)
and [RESCAL](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/reset/reset-brcmstb-rescal.c)
references. There are no config-selector/endpoint/BAR/RP1/IRQ/DMA accesses,
PCIe writes, reset pulse or calibration trigger. Different values between
passes are retained as observations, not asserted stable hardware. All-ones
reads and invalid halfword results refuse publication. The successful marker
says OBSERVED and NIC_READY=0, not controller/link ready.

## Actual fault/watchdog behavior and the admission gap

The PM resource is exactly `0x107d200000`. Before table reads the provider
requires full-reset routing plus a nonzero prior countdown, reloads **only**
PM_WDOG once for 15 seconds and verifies the 14..15-second readback range.
Subsequent guards check routing, positive margin above eight seconds,
nonincreasing countdown and actual decrement from the armed sample. They
never reload it. The image does not write PM_RSTC, PM_RSTS or PCIe resources.
UART setup/transmission is the other intentional peripheral writer.
Register facts follow the
[Raspberry Pi watchdog reference](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/watchdog/bcm2835_wdt.c).

A synchronous abort or hung read/barrier does **not** return a callback error.
Existing fatal vectors report stage/ESR/ELR/FAR/SPSR when possible and park
without watchdog servicing; a nested report fault also parks. Guards clear
the table-stage tag before PM/UART operations so those faults are not attributed
to the preceding PCIe load. Autonomous full reset is the intended whole-image
recovery mechanism, but it has not been physically observed for this candidate.
Early failure before successful watchdog admission can leave the CPU parked.
The firmware boot watchdog is not assumed to remain enabled after Arm handoff.

**A watchdog reset is not image rollback or proof of SSD Linux return.** The
last recorded EEPROM value is `BOOT_ORDER=0xf461`. The
[official boot-order definition](https://raw.githubusercontent.com/raspberrypi/documentation/master/documentation/asciidoc/computers/raspberry-pi/eeprom-bootloader.adoc)
reads nibbles right-to-left: that value tries SD, then NVMe, then USB, then
repeats. A bootable SD diagnostic can therefore be selected again. This is
source-backed interpretation of the earlier recorded configuration, not a
fresh hardware observation. No EEPROM, boot-order, partition or image change
was made to work around it. Neither an expired observation timer nor missing
SSH establishes reset, a safe next destination or board power state.

Before installation, independently establish a bounded reset and one-shot
return/recovery destination. Preserve and verify the exact current zsh image,
36-artifact NVMe preservation chain and fresh MBR/FAT/HFS snapshots under a
new baseline-aware installer; old installers must continue rejecting the current
baseline. Arm an image-bound recorder before the single software boot. Require
all 30 ordered read pairs, strict result/completion markers and actual subsequent
recovery evidence; partial reads or a reset alone are not acceptance. Stop after
one outcome, without another soak or a loop of unattended retries.

## Local evidence and remaining scope

The candidate passes all **15** package checks. Its conservative bound sums
all emitted linked nonrecursive C frames, even mutually exclusive alternatives:
14,608 of 16,384 bytes, with a required 512-byte assembly/alignment reserve.
This is not a measured hardware stack high-water result. Actual linked ELF
contains no undefined symbols; the checker verifies exact emitted halfword/
word loads and barriers rather than source strings alone. Every selected source,
object, ELF/raw output and stack file is hashed; source stability is rechecked
after compilation. Earlier intermediate local candidates remain historical and
may fail current source-drift checks; only the named final candidate is current.

ASan/UBSan models cover all 184 callback failures, all 30 invalid register
observations, halfword overflow, every post-start timestamp regression/deadline
failure, stalled time, exact address/width/order, missing callbacks/resources,
output preservation and reentry/reuse. Actual A76 build/leaf-byte checks also
mutation-test profile, source-list, source-hash, stack and extent rejection.
All **92 selected regressions** pass (13.017 seconds), including saved physical
zsh replay. The unchanged proven zsh package still passes all 37 checks.

A fresh SSH check of `192.168.4.23` returned **No route to host**. Current OS/root
and connectivity are unverified; the last physical result remains XNU recovery.
No serial, media, power, firmware or reboot operation occurred.

After actual access/recovery admission, implement real power/clock/shared
ownership, unused-window safety and RC misc/class/endian setup; compose reset,
calibration, windows, SerDes/UBUS and [bounded link setup](GATE5-LINK.md) in the
reference order. Then RP1/BAR ownership, IRQ/MSI, GEM/PHY clocks, DMA coherency,
Ethernet packets and sockets/SSH remain required. Broader zsh/TTY compatibility,
RAM-root utilities and recovery tooling remain active alongside networking;
the replacement-card durability hold has not become a global development hold.
