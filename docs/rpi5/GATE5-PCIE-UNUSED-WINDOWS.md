# Read-only unused-window prerequisite — 2026-10-12

The real IOKit reset/RESCAL/SerDes/UBUS owner now has a separate continuation
that inspects unused translation windows on its existing Device mapping.
It compiles and links into a distinct complete kernel. This is implementation
and local build evidence, **not physical PCIe or Ethernet acceptance**.

## Artifact and reproduction

```
python3 tools/rpi5/build_pcie_unused_kernel.py \
  --output-dir build/rpi5/pcie-unused-kernel-NEW
PYTHONPATH=tools/rpi5/tests:tools/rpi5 python3 -m unittest \
  tools.rpi5.tests.test_pcie_unused \
  tools.rpi5.tests.test_pcie_unused_kernel -v
python3 tools/rpi5/compare_native_macho.py \
  build/rpi5/pcie-unused-kernel-20261012-final/kernel.pcie-unused
```

- Kernel: `build/rpi5/pcie-unused-kernel-20261012-final/kernel.pcie-unused`.
- Size: **17,936,648 bytes**.
- SHA256: `6460a16b8c315a6534311c918923fc36bd61b2ccedb11f9fc9d52cec55eaec2b`.
- Manifest SHA256: `9b6e032b51ce407fe31c54f3b458eb39629d2022f120c5513f475a4b8102500a`.
- **2,254 input + 20 generated entries = 2,272 unique files**, all revalidated.

The builder verifies the accepted complete-kernel receipt and every protected
dependency, including its UUID-only original replay evidence. It copies the
accepted retained-FDT transport, applies the explicit continuation patch with
zero fuzz, compiles that copy and the new C core against the actual XNU headers,
and replaces exactly the prior transport object at final linkage. The original
arm_init/pe_fiq replacements and other real PCI/FDT constituent objects remain
in place. It cannot overwrite outputs or write into source/accepted directories.

Both new translation units compile without warnings. The complete kernel has
zero undefined symbols and the same ten original linker warnings, none added.
The seven existing added initializers remain uniquely executable and correctly
rebased in the genuine read-only table. The new entry, ownership callback and
both C operations have executable final definitions; the C observation copy
resolves to XNU's existing `memcpy`, not an invented freestanding shim.

Native actual-loader parsing/materialization agrees in host buffers:
18 segments, 105,819 local relocations, 18,989,056 materialized bytes;
17,936,776 container bytes. The entry branch still reaches the actual
`start_first_cpu`. This does not load the physical Pi.

## What the inspection actually does

The reference hardware layout is Raspberry Pi's primary
[BCM2712 controller source](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c).
It specifies ten inbound slots for this controller and four outbound windows.
Our independently written BSD-licensed helper checks the slots not touched by
the existing active-window programmer: inbound **4–10**, outbound **2–3**.

Two snapshots each read 23 registers: RC/link/L23 status, PERST/L23 control,
SerDes IDDQ status, seven BAR-low/remap-low pairs and two outbound
base-limit/base-high/limit-high tuples. Owner checks run before/after every
read and before publishing the result: at most **139 core callbacks**, no
polls or delays. All-ones reads reject. Both snapshots must show RC role,
link down, PERST asserted, no L23 request/state and IDDQ released. Every
window tuple must match across snapshots; unrelated live status bits may vary.

Inbound BAR **SIZE=0** is the disabled condition. Remap `ACCESS_EN` is recorded
but not incorrectly treated as an enabled BAR: the reference sets this bit
even when programming a zero-sized inbound BAR. Outbound windows have no
separate enable bit here; the decoded 40-bit inclusive base must exceed the
decoded limit. All-zero registers decode an active 1-MiB window and reject.
High bytes participate in the comparison; low-only checks would be wrong.

The new phase allows exactly those **23 read32 addresses and no writes**,
other widths, banks, config selectors, MSI or DMA registers. Old phases retain
their prior policy exactly. The C++ continuation runs the actual prior
`runPHYAndUBUS` first, using its real sessions and single watchdog claim, then
enters this new inspection phase. **The initial reset/PHY/UBUS sequence still
performs its documented writes; only the added inspection is read-only.**
No new mapping, watchdog claim, registry permission boolean or synthetic
COMPLETE prerequisite is added. Caller output commits only after all stages
and the final actual owner/watchdog guard pass. Failure quarantines the owner
and its sessions without cleanup MMIO, retry, power-off or lease release.

## Validation and remaining work

Six focused tests pass, including address/undefined-behavior sanitizers,
139 callback-failure positions, 46 all-ones read positions, dependency loss
at all 139 callback positions, drift in all 20 window tuple words, every
nonzero inbound SIZE encoding, outbound high-byte/zero/inclusive-boundary
cases, reentry/reuse rejection and unchanged output on failure. An exhaustive
phase/address/bank/width/direction model admits exactly 23 new reads, zero
new writes, and preserves every prior phase. Actual kernel compilation,
complete linkage, all pins, opt-in build guards, receipt drift and unsafe
output rejection are also checked. Models are not live IOKit execution.

Accepted Device (190), PHY (716), UBUS (747), retained-FDT (1,294), complete
kernel (2,241) and new kernel (2,272) unique-file pin sets all revalidate.
The physically tested, unchanged zsh/socket package passes its 35 host checks.
All **252 selected regressions pass in 97.751 seconds** with local-loopback
access. The initial restricted run failed only the two native IPv4 socket
cases at UDP bind; rerunning the same full selection with loopback permission
passes. This is local socket regression evidence, not a new Pi/network trial.

This does **not** implement the active-window programmer's whole
`check_quiescent` provider. A COMPLETE snapshot is momentary, not permission
to program windows later without rechecking. Genuine inherited power/clocks,
shared-controller ownership, masked interrupt delivery, endpoint bus mastering/
DMA quiescence and bounded autonomous recovery remain required. Finite callback
counts do not contain hung/aborting MMIO. No concrete provider/personality or
boot caller activates this code; no physical register was observed this turn.

Next: finish the concrete provider's lifecycle/admission and full original-FDT
option checks, retain current quiescence/unused-window checks while wiring
RC/windows/link, then config/BAR discovery, interrupts, DMA and GEM Ethernet.
A fresh combined loader/kernel/root package and its preflight must precede
physical installation. Preserve serial zsh/TTY, SSH/socket, original Apple
utilities/Darwin layout and recovery scope. Gate 4 durability stays separate.
No accepted source/image/root was modified, and no Pi, serial, SD, power,
firmware, reboot or soak action occurred. Current Pi OS/root was not inspected.
