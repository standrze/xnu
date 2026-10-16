# Gate 5 wired Ethernet: next authority review — 2026-10-14

This review starts from the immutable physical CPU-ring result, not from the
older software manifests.  The board report
`build/rpi5/gem-cpu-ring-physmap-board-evidence-20261014-v1.json` passes and has
SHA-256 `050d50a2efd723ddd3bf37ad3b0f7753b4242396ee41d6271b5a5729e5d5b96f`.
Its raw serial stream has SHA-256
`adb0cdd8d16da53fcf8951b0bf3004c6a4371cc9729cb965cadb3e31da64bd70`.
The Pi performed 640 CPU descriptor writes and 640 matching readbacks across
the two retained Normal-NC pages, with 64 TX and 64 RX slots and the expected
prefetch tails.  It then restored the endpoint command, BARs, maps and normal
boot image and returned automatically to NVMe Linux.

That result deliberately has zero packet spans, zero queue publication, zero
bus mastering, zero DMA execution, zero interrupt delivery and zero packets.
The printed RP1 addresses are qualified geometry while the preferred RAM
viewport is owned; they are not device-DMA completion evidence.  Ethernet and
SSH therefore remain unproved.

## Decision

The next real hardware authority should be **queue-0 base-register
publication/readback/restoration while PCI BME, GEM receive/transmit enable and
all GEM interrupts remain off**.

Do not make BME the next write.  BME authorizes the whole RP1 PCI endpoint, not
only the GEM block.  GEM `RE=0` and `TE=0` alone do not prove every other RP1
bus master quiescent.  Do not make IRQ delivery next either: an interrupt path
without an accepted DMA completion source adds no packet evidence and expands
the failure surface.  Do not repeat the PHY reset/identity test; GPIO32 reset
and Clause-22 ID/BMCR/BMSR reads have already passed physically.  Link
configuration is a later, separate authority.

The immediate software prerequisite is one default-off full-buffer successor.
The just-passed package intentionally allocates only two descriptor pages
(`0x8000`) and no packet buffers.  Reintroduce the existing full retained
provider's `0x48000` allocation and its 128 isolated 2048-byte packet spans,
then prove every span's retained/static mapping, Normal-NC attributes, complete
preferred-RAM translation, non-overlap and ownership while all device authority
is still disabled.  This is a CPU-only prerequisite, not another mapping soak.

## Smallest queue-publication trial

Use the already accepted same-boot controller, assignment, MEM-only decode,
clock/MID/capability, preferred-RAM viewport, allocation and owner chain.  Add a
new narrow GEM-MMIO write core with an exact allowlist:

- queue 0 RX lower `RBQP` at `0x0018`;
- queue 0 TX lower `TBQP` at `0x001c`;
- RX upper `RBQPH` at `0x04d4`;
- TX upper `TBQPH` at `0x04c8`.

The offsets and high-before-low initialization order come from the already
hash-pinned Raspberry Pi Cadence source at commit
`80d4218cb877ccb07d09a9f21f0678e78d8b36f5`.  The trial must not copy Linux
runtime code.

Before the first write, require fresh checks that:

1. the endpoint PCI command has MEM set and BME clear;
2. GEM NCR has `RE=0`, `TE=0`, no command/strobe bits and no unknown set bits;
3. every GEM interrupt enable is off and no interrupt acknowledgement/clear is
   performed;
4. the exact one-queue capability remains stable, ADDR64 is supported, the
   two retained ring mappings remain Normal-NC, and the preferred RAM viewport
   has fresh complete readback;
5. all 640 ring words still equal the CPU-owned image and no packet descriptor
   has been released to the device.

Write upper halves first and lower halves last, with the existing outer-shareable
ordering primitive between publication and readback.  For the observed board
geometry the values are RX `0x00000010:0x0b0ec000` and TX
`0x00000010:0x0b0f0000`; these values must come from the live retained provider,
not constants in the driver.  Read all four registers back exactly, recheck BME,
NCR and interrupt masks, then restore all four original queue values in reverse
order and verify them.  Finally compare all 640 descriptor words again and run
the existing exact automatic restoration/SSD-return path.

Acceptance is only: **the exact retained CPU-owned rings can be published to
and removed from queue 0 without granting DMA ownership**.  It is not DMA,
completion, wire traffic, `en0`, IP or SSH.

Required negative tests include every read/write/owner/time failure; changed
source/capability/mapping objects; high/low halves from different generations;
swapped RX/TX values; truncation above 32 bits; nonzero BME/RE/TE/IER; descriptor
mutation; restoration/readback failure; reentry; and deadline expiry.  Any
failure after a write is terminal quarantine until reset, not an in-place retry.

## Ordered authorities after that gate

1. **Full packet mappings, CPU-only.** Qualify the full `0x48000` provider and
   all 128 packet spans.  Connect the existing `rpi5_gem_dma` lease/sync model,
   but keep descriptors CPU-owned.
2. **Queue publication, BME off.** Run the bounded four-register trial above.
3. **PHY configuration/link, still no BME.** Add a separate bounded Clause-22
   write state machine for advertisement/autonegotiation and require stable
   link/speed/duplex plus exact rollback or reset containment.  Reuse the passed
   GPIO32 reset, MDIO clock and PHY1 identity path; do not repeat its identity
   gate as a substitute for link.
4. **RP1-wide quiescence and BME-only cycle.** Establish that no non-GEM RP1
   master can issue traffic.  Then set endpoint COMMAND from MEM to MEM|BME,
   read it back, perform no queue/NCR/descriptor write, clear BME first and
   restore exactly.  This proves configuration authority only.
5. **One polling packet-DMA trial, IRQ masked.** Configure the narrow supported
   DMACFG/NCFGR profile, publish one valid buffer/ring lifetime, enable BME,
   release exactly one descriptor and poll bounded completion.  TX and RX are
   separately accountable; a TX descriptor completion is not wire delivery.
   Quiesce GEM, clear BME, unpublish queues and only then release mappings.
6. **One interrupt-delivery trial.** After polling completion works, bind the
   existing RP1 hwirq 6/MIP/GIC path, enable only the required GEM queue-0 bit,
   prove one source/ack/EOI/completion sequence and mask it before teardown.
   Polling remains a diagnostic, not final driver operation.
7. **Apple family composition.** Link the exact pinned Apple networking family,
   then the thin `IOEthernetController` wrapper.  First acceptance is `en0`
   registered and valid-but-link-down; next is stable link, then one verified
   local frame in each direction, ARP/IPv4, sockets and finally `sshd`.

This sequence intentionally delays BME until packet memory, queue programming,
PHY link and RP1-wide quiescence are independently understood.  It also delays
interrupt activation until a bounded polling completion gives the interrupt a
known source.

## Existing reusable implementation

- `iokit/Kernel/BCM2712GEMDMARings*.inc`,
  `BCM2712GEMDMABatchTransport.inc`, `rpi5_gem_ring_stage.*` and
  `rpi5_gem_ring_batch.*` already provide retained Apple allocation, mapping,
  immutable-source checks and CPU-owned descriptor construction.
- `iokit/Kernel/rpi5_gem_ram_window.*` selects only the preferred RAM inbound
  viewport.  `rpi5_gem_dma_route.*` retains CPU/PCI/RP1 address distinctions.
- `iokit/Kernel/rpi5_gem_dma.*` already implements per-slot TX/RX leases,
  explicit packet synchronization and descriptor ownership transitions.  It is
  host/A76 tested but has not performed board DMA.
- `loader/rpi5/rp1_gem_mdio.*` and the reset transport already implement the
  bounded MDIO read/reset path.  They do not implement autonegotiation writes.
- `pexpert/arm/rpi5_pcie_irq_owner.inc`, `rpi5_pcie_irq_api.h` and the existing
  PCIe IRQ packages provide selective mask/ownership groundwork, not RP1 hwirq
  6 delivery or GEM completion proof.
- `iokit/Kernel/rpi5_gem_network_adapter.*` already encodes the default-off
  family admission/packet-ownership boundary.  Its eight acceptance bits
  correctly prevent registration before RAM route, rings, TX/RX DMA, IRQ,
  completion/ownership and Apple-family composition all exist.
- Original Apple `IOBufferMemoryDescriptor`/`IODMACommand` are already used by
  the provider.  Apple IOPCIFamily `726.100.6` has a partial, separately
  audited build and BCM2712 config/resource adapters in the workspace.
- Apple `IONetworkingFamily-186` is pinned by eight exact source hashes in
  `tools/rpi5/ionetworkingfamily_186_sources.json`.  The intended conventions
  are `IOEthernetController`, `attachInterface(..., false)`, valid-but-down
  `setLinkStatus`, serialized work-loop/event sources, `IOOutputQueue` stall
  semantics, exact mbuf ownership, queued RX plus `flushInputQueue`, and
  synchronous disable/detach.  The whole family is not yet linked into this
  `xnu-12377.121.6` workspace.
- Apple's BSD/DLIL core is already in the kernel, and the RAM root already has
  Apple `network_cmds-396.6` `ifconfig` and `route`.  These become useful only
  after a real interface exists.

The current physical ring package is
`build/rpi5/gem-cpu-ring-physmap-trial-20261014-v2`, manifest SHA-256
`9cc31e53c773af491806b2cee60a794679034da042df4fd4a6c50ab1522b6b80`,
kernel `6afdabf0ca98b0e854f7ee27e29e9868ee31b60cf955899867eb39572a14d128`
and image `fbfca7c3e40893ddd383b5183b5f5f3db9a52fbbfb3b87c749523c2d6a3fcbae`.
Its manifest predates the physical run and correctly remains a build-time
claim; the immutable board report above is the runtime authority.

## Blocking gaps

- no board-qualified packet-buffer mapping or synchronization path;
- no GEM queue-register write/restore core or typed evidence parser;
- no RP1-wide bus-master quiescence proof, so BME is not yet safe;
- no accepted DMACFG/NCFGR write profile, buffer publication or completion;
- no RP1 MIP/MSI/GIC hwirq 6 delivery and acknowledgement evidence;
- PHY autonegotiation/link remains down and no bounded PHY write policy exists;
- no verified live unicast MAC-address source for `getHardwareAddress()`;
- IONetworkingFamily-186 has not been compiled/linked against the exact target
  kernel, and no `IOEthernetController` service is in the board catalogue;
- no wire peer capture, ARP/IPv4 configuration, daemon composition or SSH.

## Review checks

The review reran 14 software tests: the four GEM/Apple adapter tests and ten DMA
core, preferred-RAM and ring-batch tests.  All passed.  They are software
evidence only and do not change the hardware acceptance boundary above.
