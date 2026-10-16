# Pi 5 display mailbox FDT contract

Status: offline pure decoder; no mailbox transaction or hardware acceptance.
The helper is `loader/rpi5/display_mailbox_fdt.c`. It uses the existing real
FDT structure/property/phandle/register-translation parsers without modifying
them. The companion GET message planner remains separate and unchanged.

## Admitted graph

A caller supplies stable, readable bytes from the current boot's original FDT.
The pure helper cannot establish freshness or firmware ownership by itself.
It requires the Pi 5 Model B/BCM2712 root, explicit root 2/2 cell widths, and
exactly one declaration of each binding, including disabled declarations:

`brcm,bcm2708-fb` → `firmware` phandle →
`raspberrypi,bcm2835-firmware` → single `mboxes` phandle →
`brcm,bcm2835-mbox` with `#mbox-cells = 0`.

All three must be enabled direct children of the same supported `/soc` or
`/soc@107c000000` simple bus. Node names and phandle numbers are not guessed;
the actual compatible declarations and links are resolved. Global duplicate
phandles, multiple compatible declarations, ambiguous consumed properties,
unsupported nesting and alternative leaf resources fail closed. Firmware's
normal clock/reset child nodes do not become mailbox-controller ancestors.

The exact primary Pi 5 tree declares bus 1/1 cell widths, one `ranges` tuple
`<0 0x10 0 0x80000000>`, and mailbox `reg = <0x7c013880 0x40>`.
The real translation parser must independently yield
`[0x107c013880, 0x107c0138c0)`. This is an MMIO extent only, not the address of
a request buffer. [BCM2712 source](https://github.com/raspberrypi/linux/blob/80d4218cb877ccb07d09a9f21f0678e78d8b36f5/arch/arm64/boot/dts/broadcom/bcm2712.dtsi#L189),
[Pi firmware/FB links](https://github.com/raspberrypi/linux/blob/80d4218cb877ccb07d09a9f21f0678e78d8b36f5/arch/arm64/boot/dts/broadcom/bcm2712-rpi.dtsi#L7).

## Explicit conditional DMA profile

`RPI5_MAILBOX_DMA_PI5_NO_RANGES_DIRECT` names one selected platform profile,
not a general Device Tree rule that absent `dma-ranges` means identity DMA.
The helper requires absence of `dma-ranges` on the mailbox controller, SoC,
root and FB reference, and an explicitly empty property on the firmware
sibling. It rejects DMA, IOMMU, coherency, alternate DMA-parent/interconnect,
restricted-memory and secure-status overrides on participating nodes and
ancestors. It does not reject unrelated devices' DMA descriptions.

The source-backed chain is:

- Raspberry Pi's firmware driver allocates its coherent request buffer against
  **the mailbox controller device**, not the firmware sibling, and performs
  barriers around the transaction. Firmware's empty `dma-ranges` therefore
  cannot authorize a buffer translation for this controller.
  [Firmware driver](https://github.com/raspberrypi/linux/blob/80d4218cb877ccb07d09a9f21f0678e78d8b36f5/drivers/firmware/raspberrypi.c#L103).
- The platform bus sets an initial 32-bit DMA mask and requests DMA setup even
  when the property is absent. `of_dma_get_range` returns `-ENODEV` without an
  applicable range; in this path the device's range map remains unset.
  [Platform defaults](https://github.com/raspberrypi/linux/blob/80d4218cb877ccb07d09a9f21f0678e78d8b36f5/drivers/base/platform.c#L530),
  [OF setup](https://github.com/raspberrypi/linux/blob/80d4218cb877ccb07d09a9f21f0678e78d8b36f5/drivers/of/device.c#L84),
  [DMA-parent/range traversal](https://github.com/raspberrypi/linux/blob/80d4218cb877ccb07d09a9f21f0678e78d8b36f5/drivers/of/address.c#L904).
- The selected ARM64 direct-DMA path, without a range map or IOMMU and without
  an architecture-specific address transform, leaves the physical address
  unchanged. Neither the SoC's MMIO offset nor a legacy VPU alias is applied.
  This is conditional source evidence, not a tested transaction on this boot.
  [Direct mapping](https://github.com/raspberrypi/linux/blob/80d4218cb877ccb07d09a9f21f0678e78d8b36f5/include/linux/dma-direct.h#L75),
  [ARM64 configuration](https://github.com/raspberrypi/linux/blob/80d4218cb877ccb07d09a9f21f0678e78d8b36f5/arch/arm64/Kconfig).

The result records raw property absence/emptiness and this profile identifier;
there is deliberately no API converting a caller's buffer address. The
`linux_default_dma_mask_bits` field describes the reference's initial default,
not proof that an arbitrary 32-bit address is accessible by current firmware.

## Remaining transaction prerequisites

Address identity does not imply coherence. Linux uses coherent allocation,
including cache preparation and uncached/remapped memory for noncoherent
devices; the bare loader must establish its own exact cache/barrier contract.
[ARM64 maintenance](https://github.com/raspberrypi/linux/blob/80d4218cb877ccb07d09a9f21f0678e78d8b36f5/arch/arm64/mm/dma-mapping.c),
[Direct allocator](https://github.com/raspberrypi/linux/blob/80d4218cb877ccb07d09a9f21f0678e78d8b36f5/kernel/dma/direct.c#L202).

A future transport must prove same-boot FDT provenance, original controller
ownership, no active competing mailbox consumer, CPU/EL/cache state, and an
exact aligned retained request-buffer symbol below its admitted address limit.
The image base alone is not that symbol. RAM coverage, reservations, all live
image/stack/FDT ranges and cache-line sharing must be checked separately.
Timeout must quarantine firmware-visible storage until reset; no implicit
retry or draining another owner's reply. No successful GET response alone
establishes framebuffer allocation, scanout ownership, pixel layout or mapping
attributes. None of those operations are implemented here.

## Reproducible offline evidence

Eleven exact primary source files are preserved under
`build/rpi5/display-mailbox-dma-primary-80d4218-20261013`, with byte lengths and
SHA256 values in `tools/rpi5/display_mailbox_fdt_sources.json`. They are reference
material, not compiled imports. Tests do not refetch sources.

Run `python3 -m unittest tools.rpi5.tests.test_display_mailbox_fdt -v`.
Five groups exercise the real C under ASan/UBSan, malformed/duplicate/status/
phandle/cell/translation/topology controls, every truncation of accepted
fixtures, whole-input/output alias rejection, unchanged output on failure,
the preserved source bytes, and Cortex-A76 freestanding compilation.
Fixtures are synthetic and do not claim a live mailbox or framebuffer.
