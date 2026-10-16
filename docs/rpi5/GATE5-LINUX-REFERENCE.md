# Read-only Linux RP1 reference — 2026-10-12

Captured while Gate 4 awaits inspection of its silent UART path. Linux root
was verified as `/dev/nvme0n1p2`, ext4 UUID
`04570742-280b-43cb-9564-73d454243b1c`. No PCI configuration write, MMIO access,
network change, SD operation or reboot was performed. Only the standard 64-byte
PCI header, assigned sysfs resources, selected non-secret network-path OF
properties and existing IRQ/DMA metadata were read. `/chosen` and entropy
properties were not captured.

Evidence is in `build/rpi5/rp1-linux-reference-20261012/reference.json`.
`revalidation.json` independently confirms unchanged PCI header/resources and
selected OF properties, with a stable boot ID around that later check. The
original capture did not record boot ID; the later check is not retroactive
attestation of the first capture's boot.

Observed Linux facts:

| Resource | Observed value |
| --- | --- |
| RP1 PCI identity | `0002:01:00.0`, vendor/device `1de4:0001`, driver `rp1` |
| PCI command register | `0x0406` (memory decode and bus mastering enabled) |
| BAR1 PCI bus base | `0x00000000` (not the CPU physical address) |
| BAR1 CPU span | `[0x1f00000000, 0x1f00400000)`, 4 MiB |
| BAR2 CPU span | `[0x1f00400000, 0x1f00410000)`, 64 KiB |
| RP1 OF child aperture | size `0x410000`; larger than BAR1 alone |
| GEM offset / size | `0x100000` / `0x4000` within BAR1 |
| GEM CPU span | `[0x1f00100000, 0x1f00104000)` |
| Clock offset / size | `0x18000` / `0x10038` within BAR1 |
| Clock CPU span | `[0x1f00018000, 0x1f00028038)` |
| Linux Ethernet | `eth0`, platform driver `macb`, MTU 1500, operstate down |
| GEM IRQ observation | Linux IRQ 112, `rp1_irq_chip` hwirq 6, level |
| PHY declaration | `rgmii-id` |

The [Raspberry Pi Linux RP1 driver](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/drivers/mfd/rp1.c)
uses BAR1 for peripheral MMIO. The live BAR1 assignment at PCI bus address zero
is supported by the separately assigned CPU resource and enabled memory decode;
zero must not be treated as synonymous with unassigned. Conversely, Linux's
translated CPU resource must never be supplied as a raw PCI BAR bus address.

The FDT child aperture spans more than BAR1. A mapper must validate the exact
GEM/clock regions and their enclosing 16 KiB pages inside the independently
observed BAR1, rather than require all `0x410000` bytes to fit a `0x400000` BAR.
This is a concrete live-layout constraint for the separate pure resource mapper,
not permission to map/access registers under XNU.

The RP1 PCI parent's sysfs DMA masks report 32 bits. The GEM platform child's
corresponding sysfs attributes are absent. These are not proof of the NIC's
usable address width, DMA translations, cache coherency or isolation. A missing
IOMMU group is not permission to assume identity DMA. The 61 captured Linux
MSI-X allocations (IRQs 45..105) are metadata, not XNU interrupt-routing validation. Ethernet was
down, so no link or packet-transfer proof is claimed even for this Linux snapshot.

Gate 4 still requires actual XNU sector reads, HFS mount/read/exec cycles and
separately verified durable writes. Gate 5 still requires independently owned
PCIe/RP1 initialization, IRQ/DMA correctness, PHY and real packet transfer.
