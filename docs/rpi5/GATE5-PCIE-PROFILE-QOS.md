# Original firmware options and actual QoS continuation — 2026-10-12

The real IOKit controller preparation now checks the full original firmware
tree before opening its provider or creating mappings. A new continuation
applies the decoded FIFO/VDM priority map after the existing real
reset/RESCAL/SerDes/UBUS and unused-window stages. This is a distinct,
**uninstalled complete kernel**, not physical PCIe or Ethernet acceptance.

## Artifact and reproduction

```
python3 tools/rpi5/build_pcie_profile_kernel.py \
  --output-dir build/rpi5/pcie-profile-kernel-NEW
PYTHONPATH=tools/rpi5/tests:tools/rpi5 python3 -m unittest \
  tools.rpi5.tests.test_pcie_profile \
  tools.rpi5.tests.test_pcie_qos \
  tools.rpi5.tests.test_pcie_profile_kernel -v
python3 tools/rpi5/compare_native_macho.py \
  build/rpi5/pcie-profile-kernel-20261012-final/kernel.pcie-profile
```

- Kernel: `build/rpi5/pcie-profile-kernel-20261012-final/kernel.pcie-profile`.
- Size: **17,937,328 bytes**.
- Kernel SHA256: `c08a6823efe95303244038ea7f1f35fa5fb2f94768d936bf46450ec33b350c90`.
- Manifest SHA256: `c07780ae59eafde944b0e946ef40a0b934309470a68172737224329efa87fe4c`.
- **2,290 input + 24 generated entries = 2,312 unique files**, all revalidated.

The builder verifies all accepted dependencies, copies the previous transport,
applies an explicit zero-fuzz patch, and compiles the copied C++ owner and two
new C cores using actual XNU headers. Only the previous transport object is
replaced at final linkage; earlier real PCI/FDT/watchdog/core constituents and
the original source-built kernel providers remain. Sources and prior outputs
are not overwritten. Only fresh direct build children/temporary outputs work.

All three new units compile warning-free. Complete linkage has zero undefined
symbols and the same ten original linker warnings, none added. Seven existing
added initializers retain unique executable targets and real local loader
fixups. The profile decoder, QoS operations and actual IOKit entry have
executable final definitions, not callback stubs or fabricated prerequisites.

Native actual-loader parsing/materialization agrees in host buffers: 18
segments, 105,819 local relocations, 18,989,056 materialized bytes,
17,937,456 container bytes; unchanged direct entry to `start_first_cpu`.
This is not a physical load, constructor execution or a combined boot package.

## Original FDT, not a reduced binding

The profile decoder first calls the existing strict PCIe/RP1 binding decoder,
then reads original options at `/axi/pcie@1000120000`. Both binding and profile
outputs remain unchanged on any failure; the input tree is never modified.
`prepareBoot` supplies the existing retained, sanitized private Apple OSData
copy. The actual `prepare` checks options before singleton/provider/map claims.

Gen2/x4 remains required. SSC requests, nonzero Tperst extensions, explicit
SCB sizing and controller clock/power-domain/IOMMU declarations unsupported by
this fixed backend reject. Their absence does **not** prove physical ownership.
CLKREQ strings are validated and retained as distinct absent/safe/default/
no-l1ss values; absence is not inferred to mean a safe clock state. The empty
`aspm-no-l0s` boolean is retained. **CLKREQ and ASPM are not programmed by this
stage**; RC/link policy must explicitly consume them before activation.

QoS maps are mutually exclusive, exactly four/eight **bytes**, with each
priority 0–15; wrong lengths, cell-encoded arrays, duplicate properties and
invalid high bits reject. Nothing silently truncates a priority. No map is a
distinct no-write path, not proof that inherited priority registers are defaults.

The pinned stock firmware DTB passes unchanged: Gen2/x4, absent CLKREQ,
`aspm-no-l0s`, VDM map `[8,8,8,9,10,10,11,11]` packed as `0xbbaa9888`.
Its SHA256 is independently pinned:
`399caff4dcf03c55e20b6a4a7907dd8bd1c0cc42a9fc79e0b3b2ad4f7511585a`.
This is the existing downloaded reference, **not a fresh live Pi FDT**.

Primary binding/controller references:
[Raspberry Pi binding](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/Documentation/devicetree/bindings/pci/brcm%2Cstb-pcie.yaml),
[Raspberry Pi controller](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c).
The new board helper is independently written BSD-licensed code; original
Apple IOPCIFamily remains reused unchanged in the protected baseline.

## QoS operation and failure behavior

FIFO mode programs eight per-TC low-16-bit maps while preserving upper fields.
VDM mode programs normal/panic priority words, vendor matching and forwarding;
the final reception-enable write occurs **after** map/control readbacks.
Every write has an ownership guard and ordering callback. Before each target
and final publication, require RC role, link down, PERST asserted, no L23,
IDDQ released, actual UBUS AXI fix bits and the expected reception state.
An independent final pass rechecks all target fields. Complete all-15 VDM
priority words and old all-ones vendor IDs are legal data; independent
status/control/debug/AXI reads still reject all ones. This is not MMIO
accessibility or QoS-performance proof.

The new phase allows 17 read addresses and 13 write addresses, all aligned
32-bit bridge accesses. Old phases retain their prior policy. It does not
allow config selection, active translation windows, PERST/debug/AXI writes,
interrupt registers, endpoint bus mastering or DMA. Actual operations use
0/8/5 writes and 16/248/161 core callbacks for no-map/FIFO/VDM respectively.
No polls, delays, new mapped pages or second watchdog claim are added.

The C++ wrapper calls the actual preceding stages with their real sessions,
then applies the parsed private profile and commits caller output only after
the final owner/watchdog guard. Failure quarantines all owner sessions,
preserves caller output and stops without cleanup MMIO, retry, reset or
rollback. Already-issued writes persist. The finite callback bound does not
contain a hung/aborting MMIO instruction; independent recovery remains required.

## Validation and next work

Six focused tests pass: sanitized parser/priority models, the pinned DTB,
malformed/unsupported/duplicate options, all **425 callback-failure and 425
dependency-loss positions**, every immediate/final target readback failure,
VDM enable ordering, no-map zero writes, legal all-15 VDM priorities, output
atomicity, quarantine/reuse rejection, exact phase permissions and actual
kernel compilation/linkage. The preparation-order test checks the real copied
source; it does not execute IOKit/provider lifetime code on the host.
Profile opt-in, receipt/firmware drift and unsafe output rejection also pass.
All **258 selected regressions pass in 108.009 seconds** with local-loopback
access for the native socket cases. No Pi or external-network test is implied.

Accepted complete (2,241), unused-window (2,272) and new profile (2,312)
unique-file pin sets revalidate. All 35 checks on the unchanged physically
tested serial-zsh/socket package pass. No accepted source/image/root changed.

Next close concrete inherited power/clock/shared-controller ownership,
IRQ/endpoint/DMA quiescence and autonomous recovery admission. Then consume
the retained CLKREQ/ASPM declarations while wiring RC/windows/link, preserving
current unused-window verification; proceed to config/BAR discovery,
interrupts, DMA and GEM Ethernet. A combined loader/kernel/root package and
preflight still precede any board trial. No provider personality/boot caller
activates this code. No Pi, serial, SD, power, firmware, reboot or soak action,
fresh OS/root observation, Ethernet/SSH acceptance or Gate 4 waiver occurred.
Keep full serial zsh/TTY, SSH/sockets, original Apple utilities/Darwin layout
and recovery requirements active.
