# PCIe2 initial reset and bridge lifecycle

## Actual kernel transport continuation — 2026-10-12

The initial reset/shared calibration/SerDes cores now have a real IOKit mapping
and ordered-MMIO caller in a separate **uninstalled** object, connected to the
actual one-shot PM owner. They remain absent from boot source lists; no physical
calibration, power/clock accessibility, link or Ethernet result is claimed.
The historical checkpoints below precede this connection. See
[transport implementation, tests and remaining admission](GATE5-PCIE-PHY-TRANSPORT.md).

## SerDes continuation — 2026-10-12

The port-0 MDIO transport and fixed BCM2712 54-MHz SerDes sequence are now
implemented and host-tested. SerDes composes the real MDIO core, requires
completed calibration/reset dependencies, checks targeted fields and propagates
quarantine without retry/rollback. Neither has a hardware caller or is included
in BL33/XNU. See [SerDes implementation and remaining integration](GATE5-SERDES.md).
All 27 focused tests pass; the separate stat-diagnostic package still passes
29 preflight checks and is unchanged/unstaged. No Pi/serial/media operation.

## Shared calibration implementation — 2026-10-12

`loader/rpi5/pcie_rescal.{h,c}` now implements the initial shared calibration
operation against the exact decoded RESCAL resource. It is **not wired into
BL33/XNU** and has performed no hardware access. The provider must claim
system-wide ownership before any register callback, maintain controller 1's
power/clock accessibility, and retain that ownership through later setup.
One session belongs to the physical shared block, not to each PCIe controller.
There is deliberately no automatic claim release or controller shutdown.

The [Raspberry Pi reference RESCAL driver](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/reset/reset-brcmstb-rescal.c)
uses START bit 0 at offset 0, completion bit 0 at offset 8, and clears START
after completion. The new implementation preserves other START bits, verifies
both writes, and rejects an already-active operation without stealing it.
Polling uses a monotonic clock, a 1000-us completion deadline, up to eleven
status reads and ten 100-us waits. A completion observed after deadline fails;
a broken/nonadvancing clock cannot create an unbounded loop. This is a level
completion check like the reference, not proof of a new completion edge.

Each callback/readback/clock/deadline failure quarantines immediately, leaves
the output unchanged and performs no cleanup, retry or rearm. A failing claim
or write may already have taken effect. Callback latency/fault containment and
actual shared ownership remain provider obligations; this helper cannot make
inaccessible hardware safe.

Two focused tests pass: ASan/UBSan callback models cover completion after each
of 1–11 polls, all 352 callback-failure positions across those paths, all-ones
reads, contradictory START, already-started calibration, timeout, late DONE,
clock regression/stall, bad resources/providers and rejected reentry/reuse;
the second cross-compiles freestanding for Cortex-A76 with no undefined symbols.
These are host tests, not calibration, link, RP1, interrupt, DMA or packet proof.

Next integrate actual power/clock/Device-access ownership with these reset and
calibration components, then BCM2712 SerDes/refclock and bounded link training.
The [controller reference](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c)
also preserves shared calibration accessibility during controller shutdown.
Do not use another controller's reset or power-down as an error workaround.
The zsh diagnostic package remains separate and unstaged; fresh SSH still timed
out after the previous development-watchdog interval, which does not establish
the current OS or authorize an assumed SSD staging operation.

## Earlier bridge reset checkpoint

2026-10-12 15:39 UTC. This is independent networking implementation, not Gate 4
storage admission. No board, serial, media, firmware or kernel operation was
performed for this checkpoint. The last physical result remains the full-FDT
declaration boot; no trained link or Ethernet claim is added.

## Reset binding and implementation

The [BCM2712 binding](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/arch/arm64/boot/dts/broadcom/bcm2712.dtsi)
associates PCIe2 with shared RESCAL and bridge reset 44. The validated runtime
decoder already checks both resources and the reset ID. These are distinct
address spaces, not alternative PCIe register bases:

| Resource | CPU physical half-open extent | Proposed 16-KiB Device mapping |
| --- | --- | --- |
| PCIe2 bridge | `[0x1000120000,0x1000129310)` | `[0x1000120000,0x100012c000)` |
| SW_INIT reset provider | `[0x1001504318,0x1001504348)` | `[0x1001504000,0x1001508000)` |
| Shared RESCAL | `[0x1000119500,0x1000119510)` | `[0x1000118000,0x100011c000)` |

These page spans are mapping proposals, not allocation, accessibility or clock
proof. Provider callbacks receive a logical resource view beginning at the
unaligned reset resource, while a future page mapper must retain its page offset.
Never map these as cached RAM or use the PCI/MSI target as a CPU MMIO resource.

The [SW_INIT reset definition](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/reset/reset-brcmstb.c)
uses 32-line banks with `0x18` stride and separate SET/CLEAR/STATUS registers at
`0/4/8`. Thus reset 44 is bit 12 in bank 1: relative offsets `0x18/0x1c/0x20`.
There is **no read-modify-write** of shared reset bits. The reference waits
100–200 us after release.

`loader/rpi5/pcie_reset.{h,c}` implements only this initial reset pulse:

1. Pure init checks the exact resource, reset ID and complete provider callbacks.
2. Enter BUSY before any callback; observe the initial status bank.
3. Assert only reset 44, order completion, wait at least 100 us, verify assertion.
4. Release only reset 44, order completion, wait at least 100 us, verify release.
5. Publish the three status observations and mark COMPLETE only after success.

The provider has no general register write callback. Any failed callback,
all-ones status or contradictory reset bit quarantines the session immediately;
no retry, rollback, implicit cleanup or further access occurs. A failed write
may already have taken effect. The output stays unchanged on failure, but
hardware side effects are not transactional. A used session cannot be rearmed
through init. Caller-owned stable objects and serialized, bounded, non-reentrant
callbacks remain prerequisites; software cannot make a hung/faulting MMIO safe.

Two focused tests pass: ASan/UBSan callback ordering, every one of nine callback
failure positions (including writes that took effect despite reporting failure),
assertion/release contradictions, invalid resource/provider rejection, reentry
and quarantine; plus a freestanding Cortex-A76 compile with no undefined symbols.
This core is absent from the explicit BL33 build source lists and has no kernel
or hardware caller. No bridge reset was issued.

## Remaining bring-up work, in executable order

The [controller implementation](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c)
selects the BCM7712-style register layout for BCM2712: HARD_DEBUG is `0x4304`,
not the BCM2711 `0x4204`. An external bridge reset provider takes precedence
over the bridge-local SW_INIT register. Its BCM2712 profile also avoids bridge
shutdown and disables SSC. These facts prevent treating this reset helper as
the entire controller initialization.

- Close the actual power/clock and MMIO mapping/fault contract in the selected
  loader or kernel provider. Absence of a `clocks` property in the selected
  binding is not proof that a post-firmware bridge is accessible.
- Establish shared RESCAL ownership before any trigger. The
  [RESCAL provider](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/reset/reset-brcmstb-rescal.c)
  starts calibration, polls completion, then clears the start bit; it is not
  equivalent to observing bridge-reset status. Do not independently reset or
  power down another PCIe controller to make this dependency appear satisfied.
- With RP1/config/DMA independently quiesced, use the initial reset helper;
  then implement the BCM2712-specific SerDes/refclock setup and bounded link
  training. Do not infer training from reset release or an old Linux snapshot.
- Only after actual safe bridge accessibility and RC/link checks may the
  existing fixed RP1 config observer execute. Check/program/read back outbound
  windows and BAR assignment before mapping RP1 peripherals.
- Then close MIP/MSI-X/RP1 interrupt routing, GEM clocks/PHY, DMA translation
  and coherency, and IONetworkingFamily attachment; validate real wire traffic.

Future runtime integration needs a distinct recovery-backed image and bounded
capture. None of these steps requires admitting unknown-cache SD writes, and
none of the existing Gate 4 protection or durability requirements is waived.
