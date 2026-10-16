# UART clock mismatch investigation

The fourth board capture (`build/rpi5/serial-capture-7921oqcz`) reports
IBRD=23 and FBRD=55, while its FDT declares UART clock 44,236,800 Hz.
The current exact nominal-baud validator rejects that combination.

The pinned TF-A source explains the programmed divisors:

- `plat/rpi/rpi5/include/rpi_hw.h` defines the UART clock as 44,000,000 Hz.
- `plat/rpi/rpi5/include/platform_def.h` selects that clock and 115200 baud.
- `drivers/arm/pl011/aarch64/pl011_console.S` computes the integer quotient
  `(clock * 4) / baud`, then splits it into IBRD and FBRD.
- `floor(176000000 / 115200) = 1527 = 64 * 23 + 55`, exactly matching hardware.

Using the FDT-declared clock, these divisors imply approximately 115879 baud,
0.5894% above 115200. This is a source-backed explanation of the mismatch,
not a measurement of the actual UART clock or proof of acceptable timing.
Neither firmware nor loader UART configuration has been changed here.

Before the next board trial, choose and test an explicit policy for preserving
bounded nominal error or reprogramming the UART from the validated clock.
Do not simply treat this observed mismatch as exact 115200 baud, and retain
the existing line-format, enable-state and forbidden-flow-control checks.

The subsequent SSH check to 192.168.4.23 timed out. This alone does not prove
the board's power or boot state; Linux recovery or a corrected address is
needed before an SD deployment can be verified.

## Implemented correction (hardware verification pending)

The probe now requests an exactly representable rate from the validated FDT
clock before its existing strict readback check. The helper drains transmission
with a bounded poll, disables UARTEN, writes IBRD/FBRD then LCR_H to latch them,
and restores CR. It rejects active interrupts/DMA and unsupported line format.
This follows the programming sequence in the
[Arm PL011 reference manual](https://documentation-service.arm.com/static/5e8e36c2fd977155116a90b5).
The call runs on the primary before secondary startup, with a receive-only
capture peer. It does not change clock sources or assert measured wire timing.

The native register-model test covers the observed 23/55 to 24/0 correction,
fractional exact rates, invalid arithmetic/input/format, disabled UART,
interrupts/DMA, bounded drain timeout, and preservation of unrelated registers.
All 113 host tests passed before probe integration. These tests do not emulate
peripheral latching or electrical behavior. Linux SSH subsequently recovered;
no new probe has yet been deployed at the time of this note.
