# BCM2712 SerDes transport and 54-MHz setup

2026-10-12. Implemented and host-tested, **not integrated with hardware**.
This advances the Ethernet bring-up path independently of Gate 4. No serial,
Pi, media, firmware, kernel build or VM operation occurred for this checkpoint.
The installed zsh/recovery image is unchanged; no trained link is claimed.

## Reference and implemented scope

The [Raspberry Pi controller reference](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c)
uses MDIO address/write/read registers at offsets `0x1100/0x1104/0x1108`.
Read completion sets bit 31; write completion clears it. Its BCM2712 profile
selects the BCM7712 register layout, including HARD_DEBUG at `0x4304`, and a
fixed block-`0x1600` port-0 sequence for the 54-MHz source. These are controller
SerDes operations, **not the RP1 Ethernet PHY's MDIO interface**.

`loader/rpi5/pcie_mdio.{h,c}` implements port 0, registers 0–31 only. It checks
the exact decoded bridge resource, observes an idle write interface, submits
the command, orders it and reads the address register to flush the write.
That readback is recorded, not treated as an undocumented equality guarantee.
Writes submit only a 16-bit payload. Reads retain the 31-bit interface payload.

Each transaction has a checked monotonic 100-us completion deadline and a
separate finite bound of eleven data reads/ten waits of at least 10 us. Late
completion, clock regression, all-ones observations and callback failures
quarantine immediately; an already-busy interface is not overwritten.
Success permits the next serialized transaction. Failure preserves output,
does not undo issued writes and cannot be retried by reinitializing the session.
Callback fault/latency containment and real ownership remain provider obligations.

`loader/rpi5/pcie_serdes.{h,c}` composes the actual MDIO core, not a success
stub. It requires completed shared-calibration and bridge-reset sessions and
rechecks those dependencies before any I/O. The one-shot sequence is:

1. Clear only SERDES_IDDQ in HARD_DEBUG, order/wait at least 100 us, verify.
2. Write register `1f=1600`, then `16=50b9`, `17=bda1`, `18=0094`, `19=97b4`,
   `1b=5030`, `1c=5030`, `1e=0007` through the bounded MDIO transport.
3. Wait at least 100 us; set PHY_CTL_15 (`0x184c`) low byte to `0x12`, preserving
   other bits, order and verify the target field.

Failure quarantines SerDes and embedded MDIO, preserves the underlying MDIO
error and commits no observation. No automatic cleanup, rollback, rearm,
shared-controller shutdown or SSC operation is introduced.

## Verification and next integration

MDIO sanitized host models cover both completion polarities after each of
1–11 polls and all **616 callback-failure positions** across those paths. They
also cover busy-interface refusal, deadlines, stalled/backwards clocks,
all-ones reads, posted-command flushing, output preservation, reuse and bad
resources/providers. The SerDes test links the real MDIO implementation and
checks the complete fixed profile, preserved unrelated bits, all **82 callback
failure positions**, dependency changes, target-field/readback errors and
quarantine propagation. A separate freestanding Cortex-A76 compile/relocatable
link has no undefined symbols. No electrical behavior is inferred from models.

All **27 focused tests** pass across SerDes/MDIO/calibration/reset, FDT,
observer, resource planner, topology and stat-diagnostic preservation checks.
The declaration-only userland profile now explicitly rejects MDIO/SerDes/
RESCAL object inclusion. The already prepared stat-diagnostic boot package
still passes its 29 checks without rebuilding or changing its bytes.

These components remain absent from BL33/XNU build lists. Before physical
integration, provide actual shared power/clock/lifecycle ownership, accessible
Device MMIO and bounded fault handling. Then compose calibration, bridge reset,
SerDes, RC and UBUS error/timeout/QoS setup, outbound/inbound windows and bounded
PERST/link training. No PERST, config/BAR, bus-master, IRQ or DMA operation is
performed by these new components. A configured SerDes is not a trained link;
window/BAR observations, interrupt delivery, GEM/PHY clocks, DMA coherency and
real wire traffic remain required for Ethernet acceptance. See
[bridge lifecycle](GATE5-BRIDGE-LIFECYCLE.md) and [network worklist](GATE5-NETWORK.md).
