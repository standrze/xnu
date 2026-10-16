# BCM2712 PCIe2 UBUS/AXI post-SerDes setup

2026-10-12. Implemented and host-tested, **not wired to hardware**. This is
another component of the Ethernet bring-up path, not a trained link or NIC.
No Pi/serial/media/power/firmware or shared kernel/VM operation occurred.

## Reference and scope

Reviewed the live [Raspberry Pi Linux controller reference](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c),
specifically `brcm_pcie_post_setup_bcm2712` and its register definitions.
The UBUS error controls are at `0x40a4`, error-response data at `0x4170`,
UBUS timeout at `0x40a8`, and configuration-retry timeout at `0x405c`.
AXI fixes at `0x416c` clear bit 7 and set bits 13/12/11. If bit 12 reads back
Reserved-0, the reference limits outstanding requests to 15 in the low six bits.
The default disables VDM QoS reception through bit 5 at `0x40a0`.

`loader/rpi5/pcie_ubus.{h,c}` implements these fixed defaults after a completed
SerDes session. It requires the exact bridge mapping resource and retained
SerDes/MDIO/calibration/reset dependencies, rechecking their states before I/O.
There is no actual Device-access provider yet; model COMPLETE states do not
establish mapping accessibility, clocks, exclusive ownership or fault handling.

The core orders writes, verifies the target fields and programmed timeouts,
and supports both the retained timing-fix and Reserved-0/fallback paths. The
intentional all-ones error-data write is not read back: all-ones observations
cannot safely prove accessibility. Every actual register read rejects all ones.
Unrelated bits are preserved on read-modify-write submissions.

Success commits observations only after all 20 callbacks (normal) or 23
callbacks (fallback) complete. Failure preserves the caller's observations and
quarantines this session, SerDes and its MDIO transport. It does not undo issued
writes, retry, rearm, or reset/shut down shared providers. The provider remains
responsible for independently bounded callbacks and contained MMIO faults.

## Verification and remaining hardware integration

Sanitized host models cover both paths, all 43 callback-failure positions,
all-ones reads, wrong field/timeout readbacks, changed dependencies, invalid
resources/callbacks, reentry, output preservation and non-rearmable quarantine.
Failed writes are modeled as potentially effective. A separate freestanding
Cortex-A76 compile has no undefined symbols; explicit observation-field stores
avoid an implicit `memcpy` dependency found during the first target check.

The existing declaration-only zsh package now explicitly excludes UBUS objects;
its bytes are unchanged and all 37 corrective-package checks still pass.
The new unit is absent from actual BL33/XNU build lists. This checkpoint does
not satisfy any hardware, packet-transfer or Gate 4 durability requirement.

Next close the real Device/power/clock/shared-provider lifecycle, compose RC
mode/class/misc setup and FDT-derived inbound/outbound windows, apply optional
FIFO/VDM QoS maps when declared, and implement bounded PERST/link training.
Endpoint config/BAR observations, RP1 interrupt delivery, GEM/PHY clocks, DMA
coherency and real Ethernet traffic remain necessary. This helper does not
touch PERST, config selectors, endpoint BARs, windows, bus-master enable,
interrupt routing or DMA.
