# Live PCIe lifecycle reference — 2026-10-12

Fresh SSH verified `kamidana` running Linux `6.18.34+rpt-rpi-2712`, root
`/dev/nvme0n1p2`, ext4 UUID `04570742-280b-43cb-9564-73d454243b1c`, boot ID
`8512e93e-ec70-4715-bb02-d118afe393ed`. Two metadata snapshots and the final
root/boot check agree. This supersedes older unreachable/current-OS-unknown
observations, not their historical results. No Pi reboot, serial open/input,
driver/power change, mount, SD block access/write, firmware change or soak.
Separate sysfs-only card metadata matches the recorded CID and capacity;
that does **not** verify current FAT/image bytes or admit an installer.

## New reproducible tool and evidence

```
python3 tools/rpi5/capture_pcie_lifecycle_reference.py \
  --output-dir build/rpi5/pcie-lifecycle-reference-NEW
python3 tools/rpi5/capture_pcie_lifecycle_reference.py \
  --output-dir build/rpi5/pcie-lifecycle-reference-OTHER-NEW --execute
PYTHONPATH=tools/rpi5/tests:tools/rpi5 python3 -m unittest \
  tools.rpi5.tests.test_pcie_lifecycle_reference -v
```

Default is a local plan only. Execution embeds the existing unchanged PCIe
reference module in its own namespace and the new lifecycle reader in memory
over strict-host-key SSH. It installs no remote helper. Only fixed properties
are read, filtered **before** property contents; no `/chosen`, seed or MAC/
serial-number property capture. The original standard 64-byte RP1 PCI header
is read twice; there are no raw MMIO/config-selector/PCI writes. Runtime power,
link speed/width, existing MSI allocations, selected clock rows and IRQ routes
are read from existing Linux interfaces; debugfs is not mounted by the tool.

Snapshots must agree except interrupt counters, which are preserved separately
and may increase on a busy Linux system. Unknown clock-table format is refused;
an absent file is explicitly unavailable, not an enabled clock. Changed root,
boot, bindings, power, link, routing, allocations or selected clocks fail with
no implicit retry. Source hashes are checked before and after SSH. Existing
output directories cannot be overwritten. Timeouts retain partial output and
an unknown outcome rather than asserting the remote process stopped.

Final evidence: `build/rpi5/pcie-lifecycle-reference-20261012-final/`:

- `result.json` SHA256:
  `588a020573f73b94cf047749e08717d1e2e22a7e1c06c553943214431ab2a71c`.
- `remote.stdout` SHA256:
  `9357193846e4908d199355a04ab56154f5b937c831ae022f83031b558b924c45`.
- The independent existing collector also passed actual native topology/BAR
  reconciliation in `build/rpi5/pcie-reference-fresh-20261012/`, on the same
  verified Linux boot. BAR1/GEM/clock physical spans match the earlier reference.

The first lifecycle attempt failed in the local-authored remote wrapper with
`NameError: json`, before evaluating `capture_lifecycle`; it is preserved at
`pcie-lifecycle-reference-20261012/`. The corrected v2 succeeded; final adds
explicit decoding and exclusion of the NVMe MIP range. No failed trial was
overwritten or represented as a board failure.

## Concrete results that constrain the provider

Linux PCIe1/NVMe and PCIe2/RP1 PCI devices all report runtime power `active`.
The **platform host controllers** report `unsupported`, not `active`. Those
are different interfaces; neither is an XNU power/clock ownership lease.
NVMe is currently Gen2 x1, RP1 Gen2 x4. Both controller nodes omit `clocks`,
`clock-names` and `power-domains`; the existing 63-row clock framework table
contains no selected PCIe/RESCAL-named clock. This is a declaration/framework
observation, **not proof** that inaccessible or gated hardware is safe to read.

Both controllers reference the same zero-cell RESCAL provider, phandle 35,
with distinct bridge-reset IDs 43 and 44. The
[Raspberry Pi controller reference](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c)
documents RESCAL's dependence on controller 1 staying accessible. Its optional
`sw_pcie` clock lookup does not turn an absent clock property into a hardware
accessibility guarantee. Do not reset, unbind, suspend or mask the live Linux
SSD to experiment with controller 2.

Live declared interrupt destinations (GIC INTID, not Linux IRQ numbers):

| Path | GIC INTIDs | Future PCIe2-only bank selection |
| --- | --- | --- |
| PCIe2 MIP0 MSI | 160–223 | banks 5 and 6: `0xffffffff` each |
| PCIe2 INTx | 261–264 | bank 8 bits 5–8 |
| PCIe2 direct controller/MSI outputs | 265–266 | bank 8 bits 9–10 |
| PCIe1 direct outputs, excluded | 255–256 | preserve bank 7 bit 31 and bank 8 bit 0 |
| PCIe1 MIP1 MSI, excluded | 279–286 | preserve bank 8 bits 23–30 |

Combined PCIe2 bank-8 selection is **`0x000007e0`**, not all ones. A blanket
bank-8 mask would also touch SSD routing. The decoder rejects overlaps with
the separately decoded PCIe1 direct/MIP destinations. No GIC enable, pending,
active or controller IRQ mask register was actually read/written here. These
are **future selection masks**, not observed hardware mask state. A missing
`/proc/interrupts` row does not prove an interrupt disabled. The live Linux
MSI allocations are five for NVMe and 61 for RP1, not XNU MSI enablement.

The RP1 fixed oscillator is 50 MHz. Live GEM clock declarations resolve to
the RP1 provider IDs and the selected Linux clock table reports:

| GEM clock | Provider ID | Linux clock | Observed rate |
| --- | --- | --- | --- |
| `pclk` | 12 | `clk_sys` | 200 MHz |
| `hclk` | 12 | `clk_sys` | 200 MHz |
| `tsu_clk` | 29 | `clk_eth_tsu` | 50 MHz |
| `tx_clk` | 16 | `clk_eth` | 125 MHz |

Each selected output reports hardware enable `Y`. Assigned-clock declarations
are retained as raw cells, not substituted for the actual Linux rates or
implemented as XNU clock programming. Source binding reference:
[BCM2712 device tree](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/arch/arm64/boot/dts/broadcom/bcm2712.dtsi).

## Validation and next implementation boundary

All **26 selected tests pass** in 4.089 seconds: ten new lifecycle tests plus
the existing PCIe reference, FDT, full-profile, resource-plan and topology
tests. New coverage includes property filtering, missing/unsupported clocks,
changed boot/power/routes, increasing IRQ counters, precise bank selection,
NVMe overlap refusal, source drift, no-network default, overwrite refusal,
remote namespace/output execution and timeout/no-retry behavior.

All prior accepted pin sets revalidate: controller 2,380; clock 2,343;
profile/QoS 2,312; unused-window 2,272; complete PCI/FDT 2,241. The unchanged
physically tested zsh/socket package still passes all 35 checks. This turn
did not rebuild, replace, package, install or boot a kernel/image/root.

Next implement actual inherited-domain/shared-controller and interrupt
ownership over the verified bindings, rather than a cached Linux-state flag.
The current kernel GIC initialization only checks its local PPI bank; it
does **not** establish the PCIe SPI banks above are masked/quiescent. A future
provider must observe/control those exact bits without touching NVMe, retain
endpoint/DMA quiescence across PERST release and verify unused windows in each
appropriate phase. Any newly required controller1/MIP mapped pages need their
own loader memory-type/ownership integration; do not silently widen the existing
five-page Device handoff.

Before the first physical access/controller experiment, independently close
the [one-shot watchdog reset and boot-destination prerequisites](GATE5-ACCESS.md),
preserve/verify the current installed socket/zsh image through a new baseline-
aware installer, then arm an image-bound recorder before one bounded boot.
The fresh EEPROM read remains `BOOT_ORDER=0xf461`; the unmounted SD's current
configuration/image bytes were **not** read, so no current one-shot SSD-return
claim is made. Existing physical zsh/socket evidence stays accepted, Gate 4's
durability hold stays separate, and Ethernet/SSH/full TTY remain incomplete.
