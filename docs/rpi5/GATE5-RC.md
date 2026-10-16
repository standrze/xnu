# PCIe2 root-complex setup and composed local test

2026-10-12. `loader/rpi5/pcie_rc.{h,c}` implements the previously missing
BCM2712 root-complex configuration step. It invokes the **actual** window
programmer and is now a required dependency of the link core. It is not in a
boot image, installed, or physically executed. Ethernet/SSH remain unproven.

The independent implementation uses register facts from the
[Raspberry Pi controller reference](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c)
and [PCI register definitions](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/include/uapi/linux/pci_regs.h).
It sets the BCM2712 burst/SCB/UR/RCB fields, programs the declared windows,
sets bridge class and little-endian inbound mode, and disables root ASPM and
clock power management with a **16-bit** link-control transaction. Native x4
is required; width override and SCB RAM-size programming are not invented.
Disable/retrain requests reject rather than being replayed by an RMW.

Unrelated configuration bits are preserved, writes ordered and read back,
with an independent final verification pass and repeated RC/link-down/PERST#
guards. There are 34 direct RC callbacks plus at most 112 window callbacks.
No polls, PERST# release, endpoint config/BAR, IRQ/MSI enable or DMA occurs in
this component. Callback bounds do not contain a real CPU abort/hung access.

Init requires an unconsumed window session and completed shared calibration/
bridge reset. The actual provider must still establish Device accessibility,
power/clocks/shared ownership, IDDQ release/settling, masked interrupt delivery,
safe unused windows, and quiescent endpoint bus mastering/DMA. Original FDT
options must be reviewed for the fixed diagnostic policy; a reduced decoder
does not prove absent options. Failure quarantines RC/windows, preserves caller
output, and stops without retry, cleanup, reset, rollback or shared shutdown.
Already-issued writes may remain. The link core now checks the same RC/window/
halfword-callback/reset/calibration owners and quarantines RC on link failure.
Its hardware checks reject ASPM/clock-PM drift before release and at completion.

`python3 -m unittest tools.rpi5.tests.test_pcie_rc tools.rpi5.tests.test_pcie_link -v`
checks all 146 RC/window callback-failure positions, invalid reads, dropped
writes, late drift, rejected profiles/dependencies, output preservation and
reentry. The composed test calls real RC/window/UBUS/link cores for both UBUS
profiles; reset/calibration/SerDes and MMIO responses remain synthetic. The
freestanding A76 combined object links without undefined symbols. Existing
21-path/1,701-position link fault tests still pass. This is not a trained link.

The proven zsh package remains unchanged and passes all 37 checks; the separate
read-only access candidate still passes its 15 checks without install admission.
Fresh SSH to `192.168.4.23` timed out. No serial, media, firmware, power, reboot
or soak operation occurred. Hardware access/recovery admission and unused-window
safety still precede physical integration. Prefer compatible original Apple
IOPCIFamily/IONetworkingFamily for enumeration/resource/network infrastructure;
this early board-specific controller setup is not a replacement for them.
See [Apple-source reuse](GATE6-APPLE-TOOLS.md). Gate 4 durability stays separate.
