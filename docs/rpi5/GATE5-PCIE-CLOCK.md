# PCIe clock and ASPM-advertisement continuation — 2026-10-12

The actual IOKit transport now honors original-FDT `aspm-no-l0s` after its
real PHY/UBUS/unused-window/QoS sequence, before any link training. The same
new core implements post-link CLKREQ handling for all declared modes. That
post-link function is compiled and linked, **not connected to a hardware
caller**: genuine RC/windows/link and lifecycle admission remain required.
This is a separate uninstalled complete kernel, not physical Ethernet proof.

## Artifact and reproduction

```
python3 tools/rpi5/build_pcie_clock_kernel.py \
  --output-dir build/rpi5/pcie-clock-kernel-NEW
PYTHONPATH=tools/rpi5/tests:tools/rpi5 python3 -m unittest \
  tools.rpi5.tests.test_pcie_clock \
  tools.rpi5.tests.test_pcie_clock_kernel -v
python3 tools/rpi5/compare_native_macho.py \
  build/rpi5/pcie-clock-kernel-20261012-final/kernel.pcie-clock
```

- Kernel: `build/rpi5/pcie-clock-kernel-20261012-final/kernel.pcie-clock`.
- Size: **17,937,752 bytes**.
- SHA256: `f479a21cf52d75dde84230540d7ac91a350eee1c79795a03ac08f8d5ab7eaafa`.
- Manifest SHA256: `03edd498d0cd7cc008fbb6a6f2b3a5ec6ad54d6411b9bec6b6b08814a66a9807`.
- **2,325 input + 20 generated entries = 2,343 unique files**, revalidated.

The builder checks all accepted prior receipts, copies the accepted transport,
applies its explicit zero-fuzz patch and compiles actual IOKit C++ plus the new
C core against the real XNU headers. Only the previous transport is replaced
at complete linkage; original Apple PCI and other source-built providers remain.
Both new units compile warning-free. The complete kernel has zero undefined
symbols and the same ten original linker warnings, none added. Seven existing
added initializers retain unique executable targets and real local rebases in
the read-only constructor table. Four new entry/core definitions are executable.

Native real-loader parsing/materialization agrees in host buffers: 18 segments,
105,819 local relocations, 18,989,056 materialized bytes and 17,937,880 container
bytes. Entry remains `0xfffffe000750f488`, branching directly to unchanged
`start_first_cpu` at `0xfffffe000751105c`. This does not prove a physical load,
constructor execution or loader/kernel/root package integration.

## Controller semantics

Primary references are the
[Raspberry Pi controller](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c)
and [firmware binding](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/Documentation/devicetree/bindings/pci/brcm%2Cstb-pcie.yaml).
The new BSD-licensed helper is independently written board-specific code;
original Apple IOPCIFamily remains unchanged in the protected baseline.

The two phases have intentionally different link/reset predicates:

| Phase | Hardware predicate | Operation |
| --- | --- | --- |
| Before link | RC role, link down, PERST asserted, no L23/IDDQ/forced reset, existing AXI fixes | Clear link-capability L0s bit `0x400` only if requested; preserve every other field and require native x4 |
| After link | Actual same-owner completed RC/windows/link, PHY/DL active, PERST released, no L23/IDDQ/forced reset, AXI fixes, root ASPM/clock-PM/retrain/link-disable bits clear | Apply declared CLKREQ mode and verify stable capability, root advertisement, debug and active link |

Absent `aspm-no-l0s` causes no pre-link write; it never enables L0s. Immediate
and independent final checks verify the full preserved capability word. The
new transport phase permits exactly five aligned bridge reads and one write
address (`0x04dc`), retaining all old phases' permissions. It does not permit
PERST/debug/AXI/root-capability/window/config/IRQ/DMA writes.

Post-link modes remain faithful and distinct:

| Declaration | Effective mode | Debug clock bits (`0x4304`) | Root L1SS advertisement (`0x04f8`) |
| --- | --- | --- | --- |
| absent | default, explicitly recorded | `0x200000` | Preserve inherited word |
| default | default | `0x200000` | Preserve inherited word |
| safe | safe | `0x110000` | Replace only mask `0xf8` with mode 2 (`0x10`) |
| no-l1ss | no-l1ss | `0x2` | Replace only mask `0xf8` with mode 2 (`0x10`) |

The actual preceding link trainer must have cleared all clock override bits.
Safe/no-l1ss remove L1SS advertisement **before** the debug-mode write. The
controller's default L1SS-support bit is not root/endpoint ASPM enablement:
root ASPM and clock-PM remain disabled throughout, checked via a true 16-bit
link-control read. There is no adjacent W1C/status word RMW. BCM2712 uses the
BCM7712 register family, which has **no RGR1 timeout timer**; neither `0x9208`
nor the unrelated UBUS timeout is written by this core. SSC/Tperst requests
remain subject to the existing strict original-FDT decoder.

## Ownership, failures and actual integration limit

Init is pure, from the actual COMPLETE QoS/UBUS/SerDes/reset/RESCAL chain and
private full-FDT profile. Every callback is surrounded by ownership/dependency
guards. Pre-link currently uses 33 callbacks without the option or 54 with it;
post-link uses 84 for absent/default or 110 for safe/no-l1ss. No polls, delays,
new mappings or second watchdog claim are added. Bounds count terminating
callbacks, not hung/aborting MMIO or electrical CLKREQ timing.

Post-link init/binding checks require the same mapping, owner context, actual
read/write/order callbacks, reset/calibration, windows, RC and true halfword
operations as the completed link. Bad unbound link arguments/dependencies
reject without callbacks, output changes or quarantining another session.
Once an operation begins, failure preserves caller output and quarantines
clock/QoS/UBUS/SerDes/MDIO and any bound link/windows/RC. No cleanup, retry,
retraining, shared reset, rollback or lease release occurs. Issued writes may
persist. Actual owner failure also quarantines its existing reset/calibration
sessions. Object/maps remain pinned after the irreversible watchdog claim.

The real `runPHYUBUSQoSAndClock` calls the real preceding chain, then the new
init/prepare on its private QoS session. It does **not** manufacture COMPLETE
RC/windows/link flags or turn the ownership guard into `check_lifecycle`.
`rpi5_pcie_clock_finish` has no transport/boot caller yet. No personality is
registered and no board code activates either path. Independently accessible
Device/power/clocks/shared-domain ownership, IRQ/endpoint/DMA quiescence and
autonomous recovery remain mandatory before physical activation.

## Validation and next work

Five focused tests pass: sanitized native pre/post-link modes with and without
the option; **1,124 callback failures + 1,124 dependency-loss positions**;
280 all-ones read failures; immediate/final target readback corruption; invalid
link/reset/IDDQ/AXI and root ASPM/clock-PM/retrain state; same-owner dependency
mismatches; atomic outputs, quarantine and reentry/reuse rejection; exhaustive
old/new phase permissions; actual warning-free compilation, complete linkage,
real constructor fixups, all pins, opt-in enforcement and protected-output/
receipt-drift rejection. Models do not establish IOKit runtime lifetime or
physical access. Prior complete/unused/profile pin sets and the tested unchanged
zsh/socket package's 35 checks also revalidate.

All **263 selected regressions pass in 116.236 seconds**, using localhost
access for the native UDP/TCP cases. This includes earlier profile/QoS,
unused-window, RC/windows/link, Apple PCI, firmware-FDT, loader, zsh/socket,
watchdog and GIC checks; it is not a whole-repository or physical-network run.

Next implement the concrete inherited-domain/shared-ownership and IRQ/endpoint/
DMA-quiescence provider with independent recovery; wire actual RC/windows/link
and post-link CLKREQ on those sessions, then config/BAR discovery, interrupts,
DMA and GEM. A combined loader/kernel/root package and preflight still precede
a board trial. Full serial zsh/TTY, Ethernet, SSH/sockets, original Apple CLI
tools/Darwin layout and recovery stay in scope; Gate 4 remains separate.
No accepted source/image/root changed, and no Pi, serial, SD, power, firmware,
reboot or soak action or fresh OS/root observation occurred.
