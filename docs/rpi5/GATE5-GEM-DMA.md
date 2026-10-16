# Gate 5 Ethernet DMA ownership groundwork

This is an independently written, host-tested transport component, not a
working Ethernet interface or Gate 5 acceptance. No Pi, serial, SD, firmware,
MMIO, or power operation is needed to test it. It is not yet included in the
kernel build or connected to an IOKit networking service. The parallel topology
work in `GATE5-NETWORK.md` remains separate; this component does not infer bus
addresses from that decoder.

A separate [live Linux resource reference](GATE5-LINUX-REFERENCE.md) is now
captured without MMIO or target changes. It distinguishes BAR1's PCI bus base
zero from its CPU mapping at `0x1f00000000`, and its 4-MiB size from the larger
RP1 device-tree aperture. It does not prove usable XNU DMA mappings or coherency.

## Implemented boundary

`iokit/Kernel/rpi5_gem_dma.{h,c}` implements a bounded per-slot TX/RX ownership
protocol for 16-byte, little-endian GEM descriptors with 64-bit DMA addresses.
It preserves the upper address word, uses one aligned word store for ownership
publication, and requires explicit packet synchronization and DMA release/acquire
callbacks. A provider must supply already-mapped bus addresses. CPU virtual,
physical and RP1-visible addresses are not assumed interchangeable.

The caller serializes operations and retains mappings and storage. TX buffers
are exposed only through a reservation lease; submission transfers ownership.
RX completion exposes a buffer only after ownership and synchronization checks.
Slot-bound generation tokens reject stale, duplicate and cross-slot leases.
Invalid descriptor metadata, synchronization failure or generation exhaustion
quarantines the slot. There is no timeout-based reclamation or implicit reset.
Reinitialization requires independently established hardware quiescence and no
outstanding leases; a new lifetime must never reuse outstanding old tokens.

The initial profile uses isolated 2048-byte packet allocations, cache granules
64/128/256, frames 14..1518 bytes excluding FCS, one descriptor per packet, no
timestamp extension, jumbo, checksum offload or scatter/gather. Fragmented,
runt, oversized or nonzero-offset receive completions are dropped and must
still be recycled through a valid lease. TX returns raw completion status: CPU
ownership does not prove successful wire delivery. Variant-specific error
interpretation belongs in the future MAC adapter.

Packed descriptor memory must be provider-proven coherent or uncached. Merely
cleaning a cached 16-byte descriptor can overwrite an adjacent descriptor's DMA
updates in the same cache line. Packet synchronization callbacks are mandatory
even if the provider later proves they can safely be no-ops. The enum naming a
memory mode is a caller contract, not proof that RP1 DMA is coherent.

## Validation

Run `python3 -m unittest tools.rpi5.tests.test_gem_dma -v`.

Both tests pass: a native AddressSanitizer/UBSan model and an isolated
freestanding `aarch64-none-elf`, Cortex-A76 compile with no external symbol
dependencies. The native model checks literal descriptor bytes, addresses above
4 GiB, wrap bits, invalid alignments/overflow/memory modes, callback order,
pending ownership, stale/duplicate leases, bounded RX/drop behavior, descriptor
corruption, synchronization faults and generation exhaustion. This is simulated
descriptor/DMA behavior, not an actual cache-coherency, interrupt or network test.

## Integration prerequisites

Before enabling this component on hardware, establish live PCIe BAR/resource
ownership; RP1 power/clock/reset and interrupt routing; DMA address translation,
address width and mapping lifetime; descriptor memory attributes and appropriate
cache/barrier implementations. Verify the actual GEM descriptor mode and MAC
configuration: ADDR64, standard non-PTP descriptors, zero RX offset, no jumbo or
offloads, RX FCS stripping/bad-FCS rejection, and TX padding/FCS generation.
Add ring allocation/scheduling, hardware quiescence and recovery, MMIO queue
publication, PHY/MDIO link negotiation and the compatible XNU networking adapter.

Then validate bounded hardware TX/RX against an independent peer, including
packet contents, errors, wraparound, exhaustion and recovery. IP/DHCP and SSH
come after the link and actual packet transfer; none are claimed here. Physical
tests must be scheduled separately from the active Gate 4 storage trial.

## Hardware facts and provenance

The [official RP1 peripheral manual](https://datasheets.raspberrypi.com/rp1/rp1-peripherals.pdf),
Chapter 7, identifies the Cadence GEM_GXL 1p09, RGMII, 64-bit DMA addressing and
full store-and-forward configuration. The downloaded manual (2023-11-07 build)
was visually inspected at printed page 81; SHA256:
`87fb7b24e8d9add075b849d095a107827610c0409ea194785af624c1ea986c3d`.
It does not specify the descriptor word layout.

Descriptor layout/bit-position facts were cross-checked against the
[Raspberry Pi Linux Cadence hardware header](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/drivers/net/ethernet/cadence/macb.h),
retrieved 2026-10-12 UTC, SHA256:
`ec4394d8c2daf984517441d079e8ca61af986de007e822f094f5b051b90461e7`.
This branch URL is mutable; the hash identifies the observed version. Linux
driver algorithms and code are not incorporated. The small BSD-2-Clause core
expresses its own ownership state machine. Differences among GEM variants are
not resolved by mixing register/error definitions from unrelated platforms.
