# Reducing manual diagnostic recovery

Pending board trial: `bl33-probe-1baj5v2y` integrates bounded hash-only
watchdog servicing. Linux metadata identifies the power-controller binding as
`brcm,bcm2712-pm`, reg 0x7d200000 size 0x308; TF-A independently uses translated
base 0x107d200000. The runtime FDT validator requires this exact profile and
enabled ancestor chain; host mutation tests reject every changed reg byte.
The hook reloads WDOG only when full-reset mode is already active. It never
writes RSTC/RSTS or boot-selection registers. Servicing requires strictly
increasing progress in one fixed large workload, a 60-second architectural
deadline and at most 128 renewals; it ceases after hashing. A final reload can
delay reset up to another 15 seconds beyond the deadline. A stalled counter is
bounded by the finite renewal count, not by a claimed wall-clock deadline.
Hardware servicing and end-to-end payload completion remain unverified.

Latest investigation: the official Raspberry Pi Linux
[watchdog driver](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/drivers/watchdog/bcm2835_wdt.c)
uses a 20-bit countdown at 65536 ticks/second, clamping programmed intervals.
Linux's observed timeout of 60 seconds is not proof of a 60-second bare-metal
countdown: Linux's watchdog core services shorter hardware intervals.

A new pure `watchdog_budget.h` helper authorizes renewals only for strictly
increasing byte counts within one fixed workload, before an absolute deadline,
with a finite renewal count. Host tests cover unchanged state on rejection,
deadline boundaries, counter reversal, repeated/decreasing progress, workload
changes and a stalled counter. This helper is not yet connected to hardware;
MMIO address/profile validation and actual watchdog servicing remain pending.

User requested more evidence per board pass and fewer manual power cycles.

Implemented: independent embedded-payload, CPU-topology and PSCI-binding
inspections now precede reservation parsing and report separate results.
Common framing/live-range/MMIO prerequisites remain mandatory. All inspection
results and reservations must pass before CPU_ON; failure is not converted
into permission to execute or load a kernel. Exceptions still stop execution.

The strict-alignment build eliminates the observed `be64` 64-bit unaligned
load; target disassembly contains eight byte loads. A regression test checks
this generated code because ordinary host tests cannot reproduce MMU-off
Device-memory alignment behavior.

## Recovery candidate and first hardware trial

Official Raspberry Pi [boot-option documentation](https://github.com/raspberrypi/documentation/blob/master/documentation/asciidoc/computers/config_txt/boot.adoc)
describes `kernel_watchdog_timeout` as arming a watchdog across OS handoff,
and Pi 5 `set_reboot_order` as a one-shot boot-order override across reset.
Investigate using these on the SD diagnostic to reset after capture and choose
NVMe on the next boot. Do not assume a watchdog alone changes SD-first order.

Before deployment, verify the installed firmware supports both options, choose
a supported timeout long enough for diagnostics, and inspect TF-A for watchdog
or reset-register interference. Preserve the SD config backup and leave NVMe
Linux configuration untouched. Test recovery explicitly by observing both the
diagnostic serial output and subsequent Linux SSH/root-device identity. A
successful reset without Linux return is not completion. Manual recovery is
still required until this path is demonstrated on hardware.

Trial: SD config now adds `set_reboot_order=0xf6` and
`kernel_watchdog_timeout=15`; original config preserved on SD as
`config.before-recovery.txt`. New config SHA-256:
`be19da65345d93a2548582ce950bd13d32f1b10ad4c26566fdeb830705e9fb2e`.
Probe `bl33-probe-t9__4z1y` SHA-256:
`69e1cee2890228380ded0b218194f76bcac47727ad11c00571ae07956affcc9f`.
114 host tests and native embedded-image audit passed before deployment.

Capture `serial-capture-8wwmamk3` recorded firmware accepting both settings,
TF-A entry and UART nominal success, then no payload completion before capture
ended. SHA-256 `c2f792d8ffd0d91486d0556cb4ba99631421a049f5031e772c6b3f427ccb92f8`.
Follow-up capture `serial-capture-71tnn3uy` recorded Linux login, SHA-256
`160992a981cc9442147fa10d8643606ca33b40a8c60ff35f40c753809e14ec3c`.
SSH confirmed hostname kamidana, root `/dev/nvme0n1p2`, and SD still inserted.
No further reboot was requested by the agent. Thus return to NVMe Linux was
observed without an agent-requested manual recovery. A capture gap omitted
the actual reset and boot selection, so precise watchdog timing/reset cause
is not yet independently established. Future trials should capture continuously.

The diagnostic still has no payload-validation completion evidence. Add stage
markers/counter timestamps before retrying; do not infer an alignment fix has
passed reservation parsing when execution did not reach it.
