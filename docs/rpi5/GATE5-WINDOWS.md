# BCM2712 PCIe2 address-window programming

2026-10-12. `loader/rpi5/pcie_windows.{h,c}` is implemented and host-tested,
**not hardware-integrated**. Gate 4 durability remains held independently.
No serial, media, power, firmware, kernel or VM operation was performed.

## Encoding and scope

Reviewed the [Raspberry Pi Linux controller reference](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c),
specifically its inbound-size encoder, BCM7712 inbound setup, outbound setup,
BCM2712 configuration and 7278-style PERST handling. BCM2712 uses ten inbound
slots, not the generic maximum of sixteen. PERST# is bit **2** (`0x4`) at
`0x4064`, with asserted value zero; link/role status is at `0x4068`.

The pure planner validates the decoded PCIe2 binding's two outbound and three
inbound rows, including 40-bit spans, MEM32 bounds, alignments, powers of two,
the distinct MIP alias, and overlaps even when PCI memory flags differ.
It preserves CPU physical and PCI bus addresses separately. It neither
allocates DMA memory nor treats the 64-GiB inbound reachability range as the
8-GB board's installed RAM.

Outbound hardware granularity is 1 MiB. The actual pinned first FDT window
declares size `0xfffffffc` at CPU `0x1f00000000`, PCI zero. Encoding it decodes
four extra bytes: declared CPU end `0x1ffffffffc`, hardware end `0x2000000000`.
The default exact policy rejects that excess. A separate explicit policy
acknowledges **only this exact four-byte case**. Plans retain both ends and
the padding count; the extra bytes are not authorized resources, RAM or DMA.
Arbitrary padding and ambiguous/overflowing decodes are rejected atomically.

## One-shot operation and provider requirements

The programmer operates only inbound slots 1..3 and outbound slots 0..1.
It orders each write, verifies programmed fields, preserves unrelated outbound
RMW bits, and performs another complete target-field pass before publication.
It rechecks exclusive/quiescent provider ownership, RC role, link down,
asserted PERST# and absence of an L23 request before each window and at exit.
There are 22 writes and 112 callbacks on success, without polling.
Bad status stops before another register access. Failure quarantines the
session, preserves caller output and never retries, cleans up or rolls back;
already-issued writes can remain effective.

An actual provider must still establish accessible Device mappings,
power/clocks/reset/shared calibration ownership, independent callback latency
and fault containment, endpoint/DMA quiescence, and safe/disabled unused
inbound slots 4..10 and outbound slots 2..3. Those unused slots are deliberately
not modified or independently audited by this component. A modeled provider's
zero return is not physical evidence. COMPLETE denotes only the named window
subset, not a fully admitted controller, trained link, endpoint BAR assignment,
MSI/IRQ delivery, bus mastering or DMA authorization.

The source audit also found that ARM64 `ml_probe_read` and `ml_probe_read_64`
in `osfmk/arm64/loose_ends.c` panic as unimplemented. The existing BL33
`probe_exception_entry` records the exception and stops; it is not a resumable
MMIO accessor. Neither can be passed off as the missing recoverable provider.
An actual early-access trial needs explicit fault/watchdog/recovery handling
and measured board evidence before these helpers are connected to hardware.

## Checks and next steps

`python3 -m unittest tools.rpi5.tests.test_pcie_windows -v` passes three tests:

- ASan/UBSan model: all 112 callback-failure positions, all-ones reads, wrong
  target readbacks, final-pass drift, reentry/reuse rejection, output
  preservation, exact encodings across size boundaries and malformed inputs.
- Actual FDT-decoder composition on mandatory synthetic and hash-verified
  saved firmware DTBs; this is host execution of saved declarations, not a
  new physical boot or proof of programmed windows.
- Freestanding Cortex-A76 compilation with no undefined symbols.

All **87** selected PCIe, stat/metadata, staging, zsh, recorder and offline-audit
regression tests pass (11.486 seconds). The declaration-only zsh package checker
now rejects window-programmer objects. The new module is absent from actual
BL33/XNU build source lists. Prepared corrective package `bl33-probe-wdmzdtem`
remains byte-identical (`352603430e44ee28e5543ab5de6bd8dba2d606ea8a406b8a0f32815a6a998faa`)
and passes all 37 checks; it is still not installed or physically accepted.
Fresh SSH to `192.168.4.23` timed out, so current Pi OS/root is unverified.

Next close the real access/provider lifecycle, including unused-window policy,
compose controller misc/class/RC setup with reset/calibration/windows/SerDes/
UBUS in the reference order, then implement bounded PERST release/link training.
Only after that can RP1 enumeration, interrupt routing, GEM/PHY clocks, DMA
coherency and actual Ethernet packets be accepted. None is blocked on claiming
durable SD writes, and none is established by these host models.
