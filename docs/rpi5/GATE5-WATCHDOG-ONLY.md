# Standalone watchdog-only recovery candidate — 2026-10-12

Subsequent [single physical recovery trial and verified zsh restoration](GATE5-WATCHDOG-PHYSICAL.md)
passed. The build acceptance below remains a historical local-build snapshot;
its manifest is preserved without retroactively changing its hardware claims.

A distinct **38,592-byte** BL33 image now compiles and links the actual existing
PM lease with a new primary-only entry/provider. It is ready for guarded trial
preparation, **not installed or physically accepted**. It does not boot XNU,
access PCIe/GIC/reset/calibration/RP1/DMA registers, or alter reset routing.
The physically tested serial zsh/socket package remains unchanged.

## Concrete artifact

- Package: `build/rpi5/pm-recovery-bro7oklj/`.
- `probe.bin` SHA256: `a616420b2c243182aeed6d04b49f0ebab416f88a54303b9805aaa82ab90d8ba2`.
- `manifest.json` SHA256: `9561227bec1811f23ef2c9a1bc245ea0159df085c38a82db17f7f1a2a9d6e30d`.
- Image-bound trial tag: `ccee459ca4bb49e4a45c1cfeffe8aeef`.
- All 16 local package checks pass, including every pinned source/object/raw
  image/tool hash, exact commands, ELF entry/loads/no undefined symbols and
  independently checked emitted fixed-address leaf instructions.
- Conservative sum of all linked static C frames: **12,880 bytes** out of
  16,384, with an additional required 512-byte margin. This overcounts mutually
  exclusive, reviewed nonrecursive paths; it is not measured board high-water.

Preserve this artifact and its pinned source/builder/checker/tests. Changes to
the diagnostic require a distinct source/profile/output rather than mutating
the accepted manifest's inputs. Preserve the earlier read-only PCIe-access
candidate separately; it is not this watchdog-only image.

## Actual code path

`recovery_entry.S` derives the existing placement/FDT-window/BSS/stack/EL2→EL1
entry, but removes secondary entry/CPU_OFF and the special IRQ-handler branch.
Every exception vector is fatal; nested faults park. The original entry remains
unchanged. The C main validates the actual firmware FDT, live RAM/reservations,
UART/PM resources, four-CPU declaration and PSCI affinity queries proving the
other CPUs are off. MMU/cache remain off and DAIF masked. No secondary CPU is
started; the sole SMC wrapper supports queries, with no reset wrapper.

The real `pcie_watchdog_lease.c` is reused unchanged. New fixed-address assembly
leaves read PM_RSTC at `0x107d20001c`, read/write PM_WDOG at `0x107d200024`,
order accesses, and read the architectural counter. They accept no address
argument. Only the existing UART and exactly one PM_WDOG reload are peripheral
writes; no PM_RSTC/RSTS write or generic MMIO interface is added.

The provider/protocol in `recovery_pm.inc`:

1. Requires a valid 1 MHz..1 GHz counter frequency, an already-running full-reset
   route and >2-second actual prior watchdog margin.
2. Makes the real lease's one password-protected 15-second reload. An attempt
   consumes the write allowance before the store, including a faulting store.
   Requires valid route again, 14..15-second readback and <=1-second arming time.
3. Drains tagged `ARMED`, waits at least two architectural milliseconds, checks
   for regression at every boundary (including entry to the wait), then calls
   the real lease's non-servicing check. The hardware countdown must decrease;
   the route/margin/12-second diagnostic deadline must still be valid.
4. Drains `CHECKED`, `RESULT` and `STOP NO_RELOAD WAIT_FOR_RESET` and parks.
   One million counter samples bound even a stopped-counter wait. Reentry,
   retry and additional reloads are rejected. Failure quarantines and leaves
   caller output unchanged; it never reloads, restores, reroutes or retries.

Successful protocol execution reports **12 lease callbacks** (8 begin + 4
check). Additional architectural-counter samples and UART records are outside
that number. `SAMPLED` records the initial arming observation, not a fabricated
post-check timestamp. Neither `CHECKED` nor `STOP` asserts a reset occurred.
A bus abort/hang does not return an invented I/O error; fatal reporting/parking
does not itself guarantee a working physical watchdog or reboot destination.

## Verification and current board state

All **61 focused tests pass in 17.097 seconds**: six new package/protocol tests,
existing actual PM owner/lease and access tests, guarded recovery/lifecycle
reference, protected installer and saved physical socket/zsh replay tests.
The new host executable runs the actual provider and immutable lease under
ASan/UBSan with explicit PM/counter/UART-record doubles. It exercises valid
frequency boundaries, invalid frequencies, route/prior/readback/decrement/
margin faults, arming/wait/deadline counter failures, a stopped counter,
recording failures, single-write gating, reentry/retry and atomic output.
These doubles do **not** emulate a hung bus or prove physical reset.

All accepted 2,435 IRQ-transport and 2,411 IRQ-kernel source/output pins match;
all 35 checks on the unchanged physically tested zsh/socket package pass.
The prior complete 286-test kernel run is separate, not newly rerun here.

Fresh SSH confirms Linux boot `8512e93e-ec70-4715-bb02-d118afe393ed`, root
`/dev/nvme0n1p2`, ext4 UUID `04570742-280b-43cb-9564-73d454243b1c`. Both
`XNU_PROBE` and `XNU_G4_READ` partitions are unmounted. The Mac exposes
`/dev/cu.usbmodem102`; this turn did not open it or establish its identity by
serial I/O. Current file/block/backup contents were not rehashed by this SSH
metadata check; the earlier [read-only reference](GATE5-PCIE-RECOVERY-REFERENCE.md)
remains that evidence. No media write/mount, serial action, firmware/config
change, Pi reboot/power action or new XNU trial occurred.

## Next physical step, not another soak

Implement the baseline-aware guarded installer/rollback and uninterrupted,
image-bound recorder. Reverify the exact SD, current working image and all
**44 inherited NVMe artifacts**, then take complete fresh MBR/FAT/HFS snapshots
and preserve the working image before staging. Old installers must continue
refusing the new baseline. Do not rewrite timeout-60 config to fit this image's
independent 15-second reload.

Arm capture before one software SD boot. Require the exact tag and successful
PM observations, non-servicing stop, a continuous captured reset/boot sequence,
then a different verified SSD Linux boot/root/mode 6. SSH silence, elapsed time,
manual power cycling or a recorder gap is not physical recovery proof. Unknown
outcomes require inspection of the existing run, not a blind second install.
Preserve/restore the tested zsh image through verified rollback tooling.

Then advance the bounded PCIe-access candidate and concrete shared-domain/
IRQ/endpoint/DMA admission, controller/RP1/BAR, interrupt delivery, GEM and
wire packets. Full zsh/TTY, Ethernet, sockets/SSH, Apple CLI tools/Darwin layout
and recovery remain active; Gate 4 durable storage remains a separate hold.
