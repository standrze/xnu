# Actual controller composition — 2026-10-12

One real IOKit entry now composes the actual initial PHY/UBUS/unused-window/
QoS/pre-link clock chain, RC and translation windows, bounded link training
and post-link CLKREQ. It uses the same owned sessions, mapped pages, retained
provider and single watchdog claim. The separate complete kernel is
**uninstalled and unbooted**. No trained physical link, RP1 discovery, packets
or Ethernet/SSH claim follows from the local tests.

## Artifact and reproduction

```
python3 tools/rpi5/build_pcie_controller_kernel.py \
  --output-dir build/rpi5/pcie-controller-kernel-NEW
PYTHONPATH=tools/rpi5/tests:tools/rpi5 python3 -m unittest \
  tools.rpi5.tests.test_pcie_controller \
  tools.rpi5.tests.test_pcie_controller_kernel -v
python3 tools/rpi5/compare_native_macho.py \
  build/rpi5/pcie-controller-kernel-20261012-final/kernel.pcie-controller
```

- Kernel: `build/rpi5/pcie-controller-kernel-20261012-final/kernel.pcie-controller`.
- Size: **17,954,968 bytes**.
- Kernel SHA256: `03a3f4c7febd07dd9fa485077d4b2759c6c5ba718438b7b6e3a3d2ed627076d6`.
- Manifest SHA256: `d35e4a56930c857a4e2c77143e5e672f12a9da46b916cf0aa8ea0511acfd4846`.
- **2,358 input + 24 generated entries = 2,380 unique files**, revalidated.

The builder verifies all prior receipts, copies the accepted clock-policy
transport and applies an explicit zero-fuzz patch. It compiles that real
IOKit C++ owner plus the existing unchanged C RC/link cores with actual XNU
headers. The existing original-family window implementation is reused, not
duplicated or replaced by a stub. Only the preceding transport is replaced
at complete linkage; original Apple PCI and source-built kernel providers stay.
All three new units compile warning-free. Complete linkage has zero undefined
symbols and the same ten original linker warnings, none added. Twelve required
core/method definitions are executable; seven existing added initializers retain
unique real targets and local rebases in the read-only runtime table.

Actual-loader parsing/materialization agrees in host buffers: 18 segments,
105,821 local relocations, 19,005,440 materialized bytes and 17,955,096 container
bytes. Entry still branches from `0xfffffe000750f488` to unchanged
`start_first_cpu` at `0xfffffe000751105c`. This is not a physical load,
constructor execution or a combined loader/kernel/root package.

## Executable order and transport changes

`runController` requires a non-null independent provider callback and an open
retained owner. Before the irreversible watchdog claim it calls that provider,
then rechecks open ownership. Preparation/claim failure does not publish output.
The actual initial chain runs once; no COMPLETE prerequisite is fabricated.

1. Actual reset/RESCAL/SerDes/UBUS, unused-window inspection, QoS and pre-link
   `aspm-no-l0s` handling on the existing sessions.
2. Real window init and RC configure, which invokes the existing actual window
   programmer once. Native x4 is required; no invented width or 8-GB SCB size.
   The known MEM32 four-byte hardware-decode excess is explicitly acknowledged,
   not allocated or authorized as usable memory.
3. Real link init/train using those same RC/windows/UBUS/reset/halfword callbacks.
   Program Gen2, clear clock overrides, release PERST, wait at least 100 ms,
   poll at 5-ms intervals up to 100 ms, record negotiated speed/width and verify.
4. Actual post-link clock finish for absent/default/safe/no-l1ss modes, with
   root ASPM/clock-PM still disabled; final owner/provider/watchdog guard, then
   atomic publication of the whole composite observation.

Real LE16 callbacks now issue `LDRH`/`STRH` with `DMB OSH`/`DSB SY` and guards
before/after. Their emitted function bodies are checked, not merely source
strings. No word RMW touches adjacent link-status/W1C fields. Long link waits
use at most 100 one-ms `IODelay` chunks per call, each guarded before/after.
The actual monotonic clock still enforces settling and deadlines; added check
latency is not hidden or subtracted. Older phases keep their 1–100-us limit.

Every RC/window/pre-release lifecycle check performs a **fresh actual**
two-snapshot unused-window inspection, using a new local one-shot inspector,
not the old COMPLETE observation. The modeled successful path has twelve such
checks, in addition to the earlier chain's inspection. After release, the
independent provider must retain/verify unused-window and IRQ/endpoint/DMA
safety without incorrectly requiring link down or asserted PERST.

New exact phase permissions (read/write address-width pairs): RC **50/26**,
link **31/4**, post-link clock **7/2**. Every old phase retains its previous
policy. No config selector, endpoint, BAR, MIP, IRQ-mask or DMA register is
made writable by this transport. Outbound/inbound translations alone are not
endpoint bus-master permission or a DMA allocation.

Hardware sequence/register references:
[Raspberry Pi PCIe controller](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c),
[BCM2712 firmware resources](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/arch/arm64/boot/dts/broadcom/bcm2712.dtsi).
This independently written BSD board backend reuses original Apple PCI
infrastructure; it is not a claim that Apple's driver supports RP1 unchanged.

## What the provider contract does — and does not — establish

The callback's only context is the already retained IOService provider. Its
code/context must remain valid until reset. The implementation must independently
verify current inherited power/clocks and shared RESCAL accessibility,
exclusive controller/mapping lifecycle, interrupt masking, endpoint/DMA
quiescence, fault containment and autonomous recovery. It may not return a
cached registry permission or delegate back to the transport's owner guard.
No concrete implementation is supplied by this composition. A non-null function
pointer or zero callback return cannot itself prove those physical conditions.

The callback runs in these explicit phases, including around every real
transport operation and each link delay chunk:

| Phase | Additional contract |
| --- | --- |
| PRECLAIM | Independently establish admission before any destructive claim; callback must terminate safely without assuming this trial's watchdog is armed |
| INITIALIZING | Retain admission while the actual initial reset/RESCAL/SerDes chain runs |
| HELD_RESET | Verify asserted PERST/link down and disabled/safe unused windows |
| RELEASED | Allow the reset transition and a training/active link; retain unused-window/IRQ/DMA safety without requiring link down |

RELEASED is set immediately before the release write and is **not** proof of
physical posted completion. The real link core checks that completion. Missing
callbacks refuse before claiming. Callback reentry is guarded; the original
initial entry also refuses reentry from a controller admission callback before
retaining/claiming. A post-callback watchdog check retains the existing deadline.
The finite check count does not contain an aborting or hung MMIO/barrier or
establish hardware reset timing/SSD return. This short diagnostic watchdog
lease is not a production NIC lifetime policy.

Failure quarantines all actual owner sessions, preserves caller output and
stops without cleanup MMIO, retraining, reset, rollback or lease release.
Already-issued translations/clock writes and a released PERST may persist.
After a claim, the existing self-retain keeps provider/maps pinned until reset.
Foreign callers cannot mutate owner state. No second claim or new mapped page
is added. No provider personality or boot caller activates the composition.

## Validation and remaining work

Five focused tests pass. A native callback model executes the **production
run/lifecycle method bodies** with real UBUS/unused/QoS/clock/RC/window/link C
cores. Initial reset/SerDes admission, owner, registers, delays and provider
checks are modeled; this is not IOKit lifetime execution or board evidence.
All four clock modes pass. Every one of **12,806 modeled owner-guard failure
positions and 12,810 provider-failure positions** stops without later callbacks,
preserves output and rejects reuse. Fresh unused-window activation before
release, full link timeout, prior-chain failure, closed provider, missing
callback and foreign-thread refusal are covered. Halfword neighbor preservation
and complete chained observations are checked. Exhaustive phase tests use
independent register tables. Real-kernel tests cover warning-free compilation,
complete linkage/fixups, emitted halfword instructions/barriers, call order,
opt-in enforcement, all pins and receipt/protected-output rejection.

All **268 selected regressions pass in 137.465 seconds**, using localhost
access for native UDP/TCP cases. Prior complete/unused/profile/clock pin sets
(2,241/2,272/2,312/2,343 unique files) and all 35 checks on the unchanged
physically tested zsh/socket package also revalidate. This is not a whole-
repository, physical reset/link or packet-driver run.

Next supply the concrete lifecycle provider and physical access/recovery
evidence, then combine loader/kernel/root and preflight before a bounded board
trial. Actual link/RP1 config/BAR discovery, interrupt routing, DMA/coherency,
GEM clocks/PHY and wire traffic remain required. Full serial zsh/TTY, Ethernet,
SSH/sockets, original Apple CLI tools/Darwin layout and recovery stay active;
Gate 4 durability remains separate. No accepted source/image/root changed;
no Pi, serial, SD, power, firmware, reboot or soak action or fresh OS/root
observation occurred.
