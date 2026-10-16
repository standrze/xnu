# Diagnostic non-secure PCIe SPI mask lease — 2026-10-12

A separate complete XNU kernel now contains actual selective GIC masking and
fresh read-only mask/active checks, using the existing validated GIC Device
mapping and the actual one-shot PM watchdog lease. It is **uninstalled and
unbooted**. This is a concrete diagnostic interrupt-ownership component, not
the full firmware/power/shared-domain/controller-source/endpoint/DMA provider,
an interrupt-delivery driver, RP1 MSI handler, Ethernet or SSH acceptance.

## Build and immutable artifact

```
python3 tools/rpi5/build_pcie_irq_kernel.py \
  --output-dir build/rpi5/pcie-irq-kernel-NEW
PYTHONPATH=tools/rpi5/tests:tools/rpi5 python3 -m unittest \
  tools.rpi5.tests.test_pcie_irq_mask -v
python3 tools/rpi5/compare_native_macho.py \
  build/rpi5/pcie-irq-kernel-20261012-final/kernel.pcie-irq
```

Kernel: `build/rpi5/pcie-irq-kernel-20261012-final/kernel.pcie-irq`,
**17,972,568 bytes**, SHA256
`59623dcb5b0b63574540d8fc0d80e7ba03ddbc0668bbedc6d6d25de25eaa988e`.
Manifest SHA256:
`3078ff46d3cc69dc9e0d45480eee81fe71d1f4b2485d3e33f2fec63d018256b8`.
All **2,411 unique pins** revalidate (2,393 input and 19 generated entries,
with the copied source present in both lists).

The builder verifies the accepted controller receipt and every prior pin,
copies the accepted watchdog-patched `pe_fiq.c`, then applies a zero-fuzz IRQ
include patch to that copy. Both actual pexpert C and the new core compile
warning-free with real XNU headers. The complete link replaces the old composed
watchdog object with the new actual pexpert object, its original receipt-pinned
watchdog-lease constituent and the new IRQ core. No fake symbols, duplicated
watchdog implementation, shared source/object edits or activation personality.
The existing C aggregate copies use ordinary XNU memory helpers; the final
kernel resolves every symbol, with the same ten original linker warnings and
no added warnings. Its five new implementations and all twelve existing
controller implementations are executable. Seven added original initializers
still occur exactly once with their real pointer rebases.

Actual native-loader host-buffer validation agrees: 18 segments, 105,826 local
relocations, 19,021,824 materialized bytes and a 17,972,696-byte container.
The entry at `0xfffffe0007513488` branches directly to `start_first_cpu` at
`0xfffffe000751505c`. This proves neither physical loading, constructors nor
PCIe access. No combined loader/kernel/root package is created.

## Actual behavior

`loader/rpi5/pcie_irq_mask.{h,c}` requires the fixed original-FDT PCIe2 routing:
direct INTIDs 265/266, INTx 261–264, MIP0 160–223, bridge reset 44 and exact
bridge span. Initialization performs no I/O. The actual PE API is in
`pexpert/arm/rpi5_pcie_irq_owner.inc`, separately exposed by
`rpi5_pcie_irq_api.h` only in the opt-in BCM2712 DEVELOPMENT/watchdog build.

Claim requires a stable owner identity that **already owns** the PM diagnostic
lease, a non-null current thread, initialized GIC mapping and masked local
DAIF.I/F. It takes a nonblocking, monotonic gate and retains the actual thread
until reset, including on failure. A later recycled thread address must not
gain the old lease. Every real callback checks that thread, gate identity,
mapping and (during claim) local interrupt masking. Watchdog checks bracket
each complete API operation, not each individual GIC read, so the core does
not multiply the finite lease budget unnecessarily. A hung load/barrier remains
subject to the already-owned watchdog; it never returns a made-up error.

Claim reads GICD_TYPER and three enable/pending/active banks, refusing selected
active interrupts before any writes. It issues **at most three** exact
write-one-to-clear ICENABLER values:

| GIC bank | Register offset | Value | Selected INTIDs |
| --- | --- | --- | --- |
| 5 | `0x194` | `0xffffffff` | 160–191 |
| 6 | `0x198` | `0xffffffff` | 192–223 |
| 8 | `0x1a0` | `0x000007e0` | 261–266 |

The private callbacks reject any other write offset/value. There is no word
read-modify-write. NVMe INTIDs 255/256 and 279–286 are excluded, including the
bits in shared bank 8. No bank 0/7, group, priority, target, pending-clear,
active-clear, interrupt-enable, GICC acknowledge/EOI, PCIe/MIP or DMA writes.
Actual volatile word-load/store callback bodies contain `DSB SY` ordering,
checked in the emitted assembly, not just by searching source comments.
Register semantics follow the
[Arm GICv2 architecture specification](https://documentation-service.arm.com/static/5f8ff21df86e16515cdbfafe),
sections 4.3.5–4.3.9, and the reviewed
[Linux GIC register definitions](https://github.com/torvalds/linux/blob/master/include/linux/irqchip/arm-gic.h).
New board code is independently authored BSD code; Linux implementation code
is not copied.

After masking, two fresh snapshots must show selected enable and active bits
clear, with unchanged TYPER. Pending bits are retained, not cleared or required
zero; they may change. **MASKED is not source/DMA quiescence.** A fresh check
repeats those read-only snapshots and can run with local IRQs enabled. Unrelated
NVMe active/pending/enable bits may change without being masked or mistaken for
PCIe2 failure. Claim has at most 106 core callbacks, check 61, with no poll,
delay, retry, release, restore or cleanup. Every returned failure leaves the
caller output unchanged; a post-write/post-watchdog failure permanently
quarantines rather than pretending writes did not happen. The PM gate remains
owned and ordinary watchdog servicing stays suppressed until reset.

## Security and integration boundaries

The non-secure GIC view can read secure or unimplemented interrupt bits as
zero and ignore writes. The APIs do not infer secure ownership from that zero,
read or modify security groups, or enable an interrupt to test ownership.
Firmware cooperation/implementation and accessible inherited domains remain
independent prerequisites, as do MIP/controller-source masking, endpoint/DMA
quiescence, whole-controller ownership and autonomous reset/SSD return.

No new boot caller or controller call was added: the accepted controller
composition is retained unchanged. In particular, this **is not a drop-in
PRECLAIM callback**. Its PM lease must already be armed, whereas the existing
transport claims that lease inside `runInitialPHY`. The next distinct transport
integration must place IRQ claim immediately **after that existing single PM
claim and before the first reset/calibration/register operation**, with safely
masked local IRQ/FIQ and explicit restoration only on successful admission.
It must wire fresh IRQ checks into the guard on the same owner identity and
revise the concrete admission sequencing without claiming the watchdog twice
or pretending a preclaim ownership flag already masked hardware. Missing
firmware/domain/endpoint prerequisites must still refuse physical activation.

GIC pages are reused; no loader Device-page expansion is made. Any later
controller1/MIP access needs its own memory-type and lifetime integration.
Keep the bounded access/recovery prerequisites in [GATE5-ACCESS.md](GATE5-ACCESS.md)
and the [fresh Linux lifecycle reference](GATE5-PCIE-LIFECYCLE-REFERENCE.md).

## Validation scope

Four focused tests cover:

- ASan/UBSan model: all 106 claim and 61 check callback failures, partial
  physical-write effects, active-before-mask refusal, ignored writes, changed
  TYPER, pending changes, live unrelated NVMe bits, exact offsets/values,
  output atomicity, alias/reentry/reuse refusal and malformed bindings.
- The **actual production PE include body**, executed with explicit host
  thread/GIC/watchdog doubles: masked local entry, null/foreign thread, retained
  thread, wrong owner, nonblocking gate reentry, two watchdog guards, post-claim
  writes refused, mapping loss and final-watchdog failure/output preservation.
- Freestanding A76 compilation plus actual complete XNU compile/link, source/
  generated pins, opt-in/non-DEVELOPMENT rejection and disabled-patch
  preprocessing equivalence to the accepted watchdog owner.
- Changed accepted receipt, unsafe output and overwrite refusal.

All **282 selected regressions pass** in 150.979 seconds, including the new
IRQ/lifecycle tests, prior actual controller/clock/profile/unused/FDT kernel
builds, original PCI infrastructure, zsh replay and localhost socket checks.
These are local model/compile/link/host-buffer tests, not real interrupt or
watchdog timing. No Pi, serial, SD, power, firmware or reboot action, new soak,
known-good image/root modification or Gate 4 durability waiver occurred.
