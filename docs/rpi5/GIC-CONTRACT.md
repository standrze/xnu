# Pi 5 GIC probe contract — 2026-09-05

Runtime follow-up: the native probe now validates the translated GIC/UART
profile and supported timer interrupt tuples before PSCI/GIC operations. The
[Linux v6.12 architected-timer binding](https://github.com/torvalds/linux/blob/v6.12/Documentation/devicetree/bindings/timer/arm%2Carch_timer.yaml)
orders unnamed interrupts as secure, nonsecure, virtual, hypervisor. The pinned
third tuple is `<1 11 0xf08>`. Native code requires the exact supported four-tuple
profile and checks its GIC parent; alternate named/extended forms remain
unsupported. This validates declared routing only, not observed IRQ delivery.

Per-CPU identity follow-up: secondary records now include the banked target mask.
Primary requires each accepted CPU to have a unique nonzero one-hot mask,
including comparison against the primary's mask. These masks are observations,
not inferred from MPIDR or list position. The host dispatch model permutes mask
assignment to test that distinction. Physical register values remain unverified.

The pinned firmware DTB's
`/soc@107c000000/interrupt-controller@7fff9000` is compatible with arm,gic-400.
The existing host reg/ranges translator resolves its four register extents to:

| Interface | Physical half-open extent |
| --- | --- |
| Distributor | 0x107fff9000–0x107fffa000 |
| CPU interface | 0x107fffa000–0x107fffc000 |
| Hypervisor interface | 0x107fffc000–0x107fffe000 |
| Virtual CPU interface | 0x107fffe000–0x1080000000 |

DTB provenance is recorded in DEVICE-TREE-CONTRACT.md. These are static source
addresses, not runtime FDT validation. Register offsets follow the pinned TF-A
include/drivers/arm/gic_common.h and gicv2.h.

The native probe reads GICD_TYPER (+4), GICD_IIDR (+8), GICC_IIDR (+0xfc),
and the banked GICD_ITARGETSR bytes for INTIDs 0–31 (+0x800 through +0x81f).
Their folded mask must be nonzero and one-hot for a usable CPU target identity.
It never derives the target bit from MPIDR.Aff0. This inventory makes no claim
about controller access permissions or interrupt delivery. It does not read
GICC_IAR (which acknowledges an interrupt), change Group configuration, or
enable/disable any controller interrupt.

Still required before the IRQ gate: runtime discovery and identity checks;
review of non-secure Group 1 ownership/access under TF-A; virtual timer PPI 27
configuration; an IRQ vector with register preservation and exception return;
acknowledge/source-quiesce/EOI ordering; bounded timeout and cleanup; then actual
serial evidence on each CPU. A single-primary inventory and masked timer
condition observation cannot establish these properties.

## IRQ entry implementation checkpoint

Pinned TF-A rpi4_bl31_setup.c supplies no secure interrupt properties;
gicv2_secure_ppi_sgi_setup_props therefore writes IGROUPR0 with all ones.
The native EL1 vector table now routes only EL1h IRQ slot 5 to irq_entry.S.
It saves x0–x30, ELR and SPSR on a 16-byte-aligned frame before calling C,
restores them, and forces SPSR.I on return: this is a one-shot probe, not a
general kernel interrupt handler. All native probe code is general-register-only.
EL2 and all other vectors retain fatal diagnostics.

The handler records the full IAR value, disables CNTV for INTID 27, uses a DSB
before EOIR, and writes DIR only if non-secure GICC_CTLR bit 9 requests split
completion. Special IDs 1020–1023 receive no EOI. Unexpected ordinary IDs are
completed and returned with IRQs masked; their source is not serviced.
There is no UART logging inside the handler and no nested IRQ support.

Non-secure EOImodeNS is bit 9, unlike its secure alias at bit 10; see
[Arm GICv2 specification, table 4-30](https://documentation-service.arm.com/static/5f8ff196f86e16515cdbf969).
The entry has only build/disassembly evidence, not actual interrupt execution.

## Single-primary enablement checkpoint

timer_irq_probe now requires a GICv2 CPU-interface ID, security extensions,
masked IRQ entry, valid CNTFRQ, no enabled PPIs/SPIs, no pending/active interrupts,
and level configuration for PPI 27. It assumes sole ownership and the pinned
firmware's Group 1 assignment. It does not rewrite security-group registers.
SGI enable bits may be read-as-one; pending/active SGIs still stop the test.

The test saves distributor/CPU control, PMR and timer priority; sets non-secure
priority 0x80, PMR 0xff, combined EOI mode and Group 1 enables; enables only
timer 27 and checks enable readback. It programs CNTV roughly 1 ms ahead and
unmasks IRQs for at most one million polling iterations. It then masks IRQs,
disables CNTV/PPI 27, clears its pending bit, and restores saved controller state.
Readback checks the timer is inactive/disabled/not pending and saved values match.

Serial output distinguishes configuration, cleanup and actual handler state.
SINGLE_CPU_IRQ_OBSERVED requires exactly one timer-27 acknowledgment with active,
unmasked timer status and successful cleanup. This marker has not been observed
on hardware and cannot establish secondary-CPU behavior. Iteration timeout is
not a calibrated duration. MMIO exceptions take the fatal path; normal cleanup
cannot be promised after a bus fault. Runtime discovery and behavioral testing
remain required before claiming the hardware gate.

Host control-flow evidence: tests/test_irq_model.py extracts timer_irq_probe
from production source and compiles it with explicit register/assembly
substitutes under AddressSanitizer and UndefinedBehaviorSanitizer. Eleven
scenarios exercise success, timeout, unexpected IRQ, refused enablement,
cleanup failure, arithmetic wrap and precondition rejection. The model injects
the handler outcome; it does not execute irq_entry.S or probe_irq_handler and
does not model bus barriers, security views or asynchronous delivery. It checks
that failed cleanup cannot produce the observed-success marker.

A second harness now extracts probe_irq_handler itself and checks its register
access/event order with explicit system-register substitutes: timer quiescence
precedes EOI; split mode adds DIR; bit 10 alone does not select split mode in
the non-secure view; full acknowledgment source bits survive; special IDs cause
no completion write. These tests run with address/undefined-behavior sanitizers.
They validate C decisions and requested operation order, not actual barrier
semantics or the assembly exception frame/return.
