# BCM2712 PCIe2 bounded link setup

2026-10-12. `loader/rpi5/pcie_link.{h,c}` now implements the fixed PCIe2
Gen2/x4 diagnostic link-start path. It is **not connected to actual MMIO or
included in the BL33/XNU builds**. No trained link, RP1 enumeration, Ethernet,
SSH, storage or new physical boot is claimed by this checkpoint.

## Implemented operation

The independent implementation follows register/timing facts in the
[Raspberry Pi Linux controller reference](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c):
`brcm_pcie_set_gen`, `brcm_pcie_start_link`, RC setup and BCM2712 offsets.
Target speed uses a true 16-bit transaction at `0xdc`; a 32-bit RMW could
affect neighboring fields. PERST# release is bit 2 (`0x4`) at `0x4064`.
The code disables the CLKREQ override/L1SS bits at BCM2712 `0x4304`, verifies
reset release, waits at least 100 ms, and polls PHY/data-link state in 5-ms
intervals for at most another 100 ms. Statistics capture, optional SSC and
post-link power management are not imported from the reference.

Before release it requires:

- COMPLETE window, UBUS, SerDes, MDIO, reset and calibration dependencies,
  with the same exact bridge mapping, context and register callbacks;
- exclusive lifecycle admission, safe unused windows and quiescent endpoint
  bus mastering/DMA, asserted PERST#, RC role, no link or L23 request;
- actual misc burst/SCB/UR/RCB fields, bridge class, little-endian inbound
  mode, x4 capability, fixed SerDes period and disabled root ASPM;
- no forced PERST or IDDQ state, no SSC or optional Tperst_clk extension.

The actual provider must inspect original FDT options. The existing resource
decoder does not retain every optional link property; omitted decoder fields
are not evidence that those properties are absent. This is a deliberately
explicit initial diagnostic profile, not general PCIe policy or the completed
network port. RC misc/class/endian configuration still needs implementation;
the new code verifies those prerequisites rather than fabricating them.

Writes preserve unrelated capability/control/debug bits and are ordered and
read back. Reset settling has a 110-ms upper observation limit; undersleep,
clock stall/regression/wrap and oversleep reject. Link polling has at most
21 status reads. Successful paths have 41..121 callbacks. Callback/setup/final
verification latency is a separate provider obligation, not included in the
100-ms poll deadline. These bounds cannot contain a hung MMIO or CPU abort.

After link-up, negotiated Gen1/2 x1/x2/x4 is recorded, including downtraining;
training-in-progress and invalid negotiated values reject. A final pass checks
capability, target speed, debug, ASPM and PERST state. Lifecycle admission is
rechecked, and the last hardware read must still show RC/PHY/data-link up and
not L23. This is a momentary observation, not guaranteed future link stability
or permission to access config space. Configuration probing still needs its
own link/lifecycle/fault guards.

## Failure and preservation

Every failure leaves caller output unchanged. Link, window, UBUS, SerDes and
MDIO sessions are quarantined against reuse. No cleanup, reset, retraining,
additional delay, retry or rollback callback follows a detected failure;
issued writes and released PERST# can persist. Shared reset/calibration
providers are not shut down. Reentrant calls and reuse reject without I/O.

The component is excluded from declaration-only zsh package profiles. Existing
hash-bound loader files, kernel, frozen zsh/root and current installed image
were not edited or rebuilt. The current known-good package remains SHA256
`352603430e44ee28e5543ab5de6bd8dba2d606ea8a406b8a0f32815a6a998faa`
and still passes all 37 checks. Its earlier physical zsh acceptance is recorded
separately in [the physical metadata trial](GATE6-METADATA-PHYSICAL.md).

## Verification

`python3 -m unittest tools.rpi5.tests.test_pcie_link -v` passes:

- ASan/UBSan callback model: all 21 link-arrival positions and **1,701 callback
  failure positions**, all-ones reads, dropped writes, timing faults, bad RC/
  SerDes/ASPM/negotiation profiles, degraded links, final-state drift/link loss,
  dependency/owner/mapping errors, output preservation and reentry/reuse;
- freestanding Cortex-A76 compilation with no undefined symbols.

The expanded PCIe, metadata, zsh, staging/recorder and independent saved-physical
replay group passes **90 tests**. These are local regressions, not new board
execution. A fresh read-only SSH check of `192.168.4.23` timed out; SSD Linux
return is not assumed. Serial, SD, Pi power and firmware were untouched.

## Next integration boundary

Implement actual accessible Device/power/clock/shared ownership and fault/
watchdog recovery, disable or independently audit unused windows, and provide
RC misc/class/endian setup. Compose those with reset, calibration, windows,
SerDes/UBUS and this link path in the reference order, in a distinct hashed
hardware-trial build that preserves the proven zsh/recovery package. Only then
run a guarded physical link/RP1 trial. IRQ/MSI, endpoint BAR ownership, GEM/PHY
clocks, DMA coherency and packets remain subsequent requirements. Gate 4's
replacement-card durability hold remains separate; userland, sockets/SSH
dependencies, RAM-root utilities and bounded recovery remain in scope.
