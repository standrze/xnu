# One-shot kernel watchdog ownership for PCIe diagnostics

2026-10-12. A separate opt-in DEVELOPMENT build now provides a real PM watchdog
claim/check implementation over the existing XNU mapping. It is a prerequisite
for the concrete PCIe owner, **not that owner**, a final kernel link, physical
reset-timing proof, safe boot-destination proof or Ethernet acceptance.
No accepted source/image, SD, serial, firmware or Pi power state was changed.

## Why the existing watchdog is insufficient

The current kernel routes its timer/callout servicing through
`pe_rpi5_watchdog_timer_tick` from three sites in `osfmk/arm64/sleh.c`. Another
CPU or the terminal callout can continue feeding while the PCIe owner's CPU
is stuck in a peripheral access. Therefore an armed watchdog alone does not
establish a bounded PCIe diagnostic. None of the accepted images is claimed
to have this new ownership mechanism.

The actual PM countdown/profile follows the reviewed
[Raspberry Pi Linux watchdog reference](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/drivers/watchdog/bcm2835_wdt.c):
WDOG offset `0x24`, reset control `0x1c`, 20-bit countdown at 65,536 ticks per
second, password `0x5a000000`, full-reset mode `0x20` under mask `0x30`.
Linux implementation code is not copied into this new core.

## Executable implementation

`loader/rpi5/pcie_watchdog_lease.{h,c}` implements a one-use diagnostic lease:

1. Require an independently accessible, already-running full-reset PM watchdog,
   with more than two seconds remaining, and a valid system-counter frequency.
2. Set BUSY before any callback. Read counter/route/countdown, write the
   15-second WDOG value **once**, order it, recheck route/countdown and counter.
   Arming must return within one counter second; the readback must be between
   14 and 15 seconds. Begin has eight callbacks.
3. Guard subsequent access with four-callback checks: unexpired start+12-second
   counter deadline, nonregressing counter, full-reset route, more than two
   seconds of hardware margin and a nonincreasing countdown. After one counter
   millisecond the hardware count must have fallen from the armed sample.
4. Permit at most 65,536 checks, even if both modeled clocks stall. Never reload,
   rearm, cancel, release, retry or clean up. Failure quarantines permanently;
   even a failed returned write may already have changed the hardware.

The provider must serialize this core and suppress **every other WDOG writer**
before begin. A finite callback/check count does not bound a hung PM access,
CPU abort or barrier. Real PM accessibility, functioning autonomous hardware,
reset routing and destination still need independent admission/evidence.
The lease is not a steady-state watchdog or an indefinite networking runtime.

`loader/rpi5/pcie_watchdog_gate.h` implements that servicing exclusion as a
monotonic owner identity plus nonblocking atomic gate. All normal servicing and
diagnostic entry use the same gate. A claimant refuses an in-flight service
instead of spinning behind it; a successful claim linearizes after earlier
servicing and before PM callbacks. Later normal callers refuse the owner.
Same-thread IRQ preemption/recursion and other-CPU contention cannot deadlock
on a spin wait. The owner is never cleared, including after failed begin.
Wrong-owner guard calls cannot steal the lease or issue a PM access.

`pexpert/arm/rpi5_pcie_watchdog_owner.inc` supplies actual kernel callbacks:
existing validated `rpi5_pm_base`, real ordered volatile PM reads/write,
`DSB SY`, `CNTVCT_EL0` and `CNTFRQ_EL0`. No callback invents a returned error
for a CPU abort/hang. The public claim/check API requires a stable non-null
owner identity and thread context. It rejects interrupt-context activation.

`tools/rpi5/patches/pcie-watchdog-lease.patch` changes a **distinct copy** of
`pe_fiq.c`: its original timer body becomes private, and the shared-gate
wrapper retains the original public servicing symbol. No exported unguarded
service path exists. The new include requires `RPI5_PCI_WDOG_LEASE=1`, BCM2712
and DEVELOPMENT. With the macro disabled, preprocessed code, including panic
line numbers, matches preserved `pe_fiq.c`. Comparison fixes only volatile
`__TIME__`/`__DATE__` macros in the test, never actual build flags.

The claim does not rewrite the legacy watchdog deadline, which existing
terminal code reads outside the new gate. An already-queued callout may
reschedule; its servicing call still refuses the permanent owner. Neither
normal mode enable nor metadata changes can reopen this wrapper's gate.
The new owner never writes RSTC, RSTS, boot-order or reset-selection registers.

## Local evidence

Five focused tests pass:

- ASan/UBSan lease model: all 12 begin/check callback failure positions,
  unchanged begin output on failure, possible failed-write effects without
  rollback, malformed route/countdown, bad arm readback, counter regression,
  arming/deadline boundaries, foreign reload, reentry/reuse, missing callbacks
  and the 65,536-check stalled-clock limit.
- Actual pthread interleaving holds a normal service in flight, rejects a
  conflicting claim, then admits the claim after release. Four threads make
  120,000 later service/steal/wrong-owner attempts; none can feed or steal.
  These are atomic-gate tests, not real timer interrupts or PM accesses.
- The freestanding A76 core has no undefined symbols.
- Real pexpert/XNU C-template compilation and relocatable linkage have zero
  warnings/new unresolved dependencies; non-DEVELOPMENT compilation rejects.
- Disabled-patch equivalence, pinned-source/template mutation rejection and
  overwrite/unsafe-output refusal preserve the baseline.

The broader regression run initially caught a timestamp-only flake in the
previous PCI-family preprocessing-equivalence test. Both such comparisons
now pin volatile date/time macros locally; no resource implementation, accepted
artifact or actual compiler/build flags changed as part of that test repair.

After that repair, all **189 selected host regressions pass** (55.580 seconds),
including original PCI family/resources, prior bring-up cores, kernel GIC/SGI/
topology models, watchdog/hash budgets, protected installation and physical
zsh/socket capture replay. This is not the full XNU suite or a new Pi run.

Current artifact:
`build/rpi5/pcie-watchdog-owner-20261012-final-v2/bcm2712-pcie-watchdog-owner.o`,
13,240 bytes, SHA256
`33bbe7cf546ffe336597b204533d907728a9d250cbb0efe3b1d7bd02ec59f594`.
Manifest SHA256
`643ce20a2bbda45ea313ae4ba182e69dcb1a1538d04d01a412ede8a037525c86`.
All 230 captured inputs match. All eight undefined names exist in the accepted
reference kernel. Earlier experimental objects remain historical, not current
source-stability receipts.

This object contains the adapted original pe_fiq functions: a future final
kernel build must **replace the original pe_fiq object**, not add this alongside
it or ignore duplicate-symbol errors. The original public wrapper must be the
only resolved servicing implementation. The current build tool does not do
that final relink, install an image, invoke the lease or grant hardware access.

```
python3 -m unittest tools.rpi5.tests.test_pcie_watchdog_owner -v
python3 tools/rpi5/build_pcie_watchdog_owner.py --output-dir NEW_DIRECTORY
```

## Recovery destination and next work

The [last verified SD configuration](PROCESS-TRIAL.md) already includes
`set_reboot_order=0xf6`, but this is historical verification, not a fresh read
or a new recovery receipt. Official
[Pi boot documentation](https://www.raspberrypi.com/documentation/computers/config_txt.html#set_reboot_order)
describes this as a one-time override. The earlier
[recovery observation](RECOVERY-AUTOMATION.md) reached SSD Linux with a capture
gap; it does not establish precise timing or cause for this new lease.
`tryboot` is another documented one-shot configuration mechanism, not something
enabled, staged or needed to be invented as a current guarantee here.

A fresh read-only SSH attempt to `192.168.4.23` timed out. Current OS/root is
unverified; the last physical receipt remains the proven zsh/socket XNU image.
No serial or SD access, reboot, power request, firmware update or soak followed.

Next connect this real diagnostic watchdog API to the concrete Device-mapped
PCIe owner, with genuine power/clock/shared reset/RESCAL ownership, bounded
callback logging, unused-window/interrupt/DMA-quiescence checks and original
enumeration write policy. Qualify a distinct full kernel/family/constructor
registration build, preserve the proven image and all backups, and independently
admit the reset/return destination before any PCIe trial. Physical acceptance
must include uninterrupted serial evidence and the resulting SSD root/boot
identity, not just silence or an elapsed timer. Actual RP1/BAR, IRQ, GEM/PHY,
coherent owned DMA and wire traffic remain required. Gate 4 is unchanged.
