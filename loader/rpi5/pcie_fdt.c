/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_fdt.h"
#include "fdt.h"

#define PHYS_LIMIT (1ull << 40)
#define PCI_MEM32 0x02000000u
#define PCI_MEM64 0x03000000u
#define PCI_PREFETCH64 0x43000000u

static const char root_path[] = "/";
static const char axi_path[] = "/axi";
static const char bridge_path[] = "/axi/pcie@1000120000";
static const char mip_path[] = "/axi/msi-controller@1000130000";
static const char rp1_path[] = "/axi/pcie@1000120000/rp1";
static const char clock_path[] = "/axi/pcie@1000120000/rp1/clocks@18000";
static const char gem_path[] = "/axi/pcie@1000120000/rp1/ethernet@100000";
static const char phy_path[] = "/axi/pcie@1000120000/rp1/ethernet@100000/ethernet-phy@1";
static const char soc_path[] = "/soc@107c000000";
static const char gic_path[] = "/soc@107c000000/interrupt-controller@7fff9000";
static const char rescal_path[] = "/soc@107c000000/reset-controller@119500";
static const char reset_path[] = "/soc@107c000000/reset-controller@1504318";

static uint32_t be32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
        ((uint32_t)p[2] << 8) | p[3];
}

static uint64_t be64(const uint8_t *p)
{
    return ((uint64_t)be32(p) << 32) | be32(p + 4);
}

static int property(const void *fdt, size_t size, const char *path,
    const char *name, const uint8_t **data, uint32_t *length)
{
    struct rpi5_fdt_property p;
    if (rpi5_fdt_property(fdt, size, path, name, &p)) return -1;
    *data = (const uint8_t *)fdt + p.offset;
    *length = p.length;
    return 0;
}

static int equal(const uint8_t *a, const char *b, size_t n)
{
    for (size_t i = 0; i < n; i++) if (a[i] != (uint8_t)b[i]) return 0;
    return 1;
}

static int exact(const void *fdt, size_t size, const char *path,
    const char *name, const char *wanted, size_t wanted_size)
{
    const uint8_t *p;
    uint32_t length;
    return !property(fdt, size, path, name, &p, &length) &&
        length == wanted_size && equal(p, wanted, wanted_size);
}

static int compatible(const void *fdt, size_t size, const char *path,
    const char *wanted)
{
    const uint8_t *p;
    uint32_t length;
    if (property(fdt, size, path, "compatible", &p, &length) || !length) return 0;
    size_t wanted_size = 0;
    while (wanted[wanted_size]) wanted_size++;
    int found = 0;
    for (uint32_t i = 0; i < length;) {
        uint32_t start = i;
        while (i < length && p[i]) i++;
        if (i == length || i == start) return 0;
        if (i - start == wanted_size && equal(p + start, wanted, wanted_size)) found = 1;
        i++;
    }
    return found;
}

static int enabled(const void *fdt, size_t size, const char *path)
{
    struct rpi5_fdt_property prop;
    int rc = rpi5_fdt_property(fdt, size, path, "status", &prop);
    if (rc == -2) return 1;
    if (rc) return 0;
    const uint8_t *p = (const uint8_t *)fdt + prop.offset;
    return (prop.length == sizeof "okay" && equal(p, "okay", sizeof "okay")) ||
        (prop.length == sizeof "ok" && equal(p, "ok", sizeof "ok"));
}

static int u32(const void *fdt, size_t size, const char *path,
    const char *name, uint32_t *out)
{
    const uint8_t *p;
    uint32_t length;
    if (property(fdt, size, path, name, &p, &length) || length != 4) return -1;
    *out = be32(p);
    return 0;
}

static int u32_is(const void *fdt, size_t size, const char *path,
    const char *name, uint32_t value)
{
    uint32_t result;
    return !u32(fdt, size, path, name, &result) && result == value;
}

static int absent(const void *fdt, size_t size, const char *path,
    const char *name)
{
    struct rpi5_fdt_property prop;
    return rpi5_fdt_property(fdt, size, path, name, &prop) == -2;
}

static int empty(const void *fdt, size_t size, const char *path,
    const char *name)
{
    const uint8_t *p;
    uint32_t length;
    return !property(fdt, size, path, name, &p, &length) && length == 0;
}

static int span(uint64_t base, uint64_t length, uint64_t limit)
{
    return length && base < limit && length <= limit - base;
}

static int overlaps(uint64_t a, uint64_t asize, uint64_t b, uint64_t bsize)
{
    return a < b + bsize && b < a + asize;
}

static int one_reg(const void *fdt, size_t size, const char *path,
    struct rpi5_range *out)
{
    struct rpi5_ranges regs;
    if (rpi5_fdt_reg(fdt, size, path, &regs) || regs.count != 1) return -1;
    *out = regs.extent[0];
    return 0;
}

/* The first supported profile has identity translation at /axi for both
 * register and DMA addresses. Require it before reporting parent PCI ranges
 * as CPU physical addresses. Non-identity maps need an explicit adapter. */
static int axi_identity(const void *fdt, size_t size)
{
    const uint8_t *ranges, *dma;
    uint32_t length, dma_length;
    if (property(fdt, size, axi_path, "ranges", &ranges, &length) ||
        property(fdt, size, axi_path, "dma-ranges", &dma, &dma_length) ||
        !length || length != dma_length || length % 24u ||
        length / 24u > 32u) return -1;
    for (uint32_t pos = 0; pos < length; pos += 24u) {
        uint64_t child = be64(ranges + pos);
        uint64_t parent = be64(ranges + pos + 8);
        uint64_t bytes = be64(ranges + pos + 16);
        if (child != parent || !span(child, bytes, PHYS_LIMIT)) return -1;
        for (uint32_t j = 0; j < 24u; j++)
            if (ranges[pos + j] != dma[pos + j]) return -1;
        for (uint32_t old = 0; old < pos; old += 24u) {
            uint64_t start = be64(ranges + old);
            uint64_t size_old = be64(ranges + old + 16);
            if (overlaps(child, bytes, start, size_old)) return -1;
        }
    }
    return 0;
}

/* The MIP node has a second reg tuple at the PCI MSI target address. That
 * tuple is deliberately outside /axi/ranges, so rpi5_fdt_reg must not be used
 * for the whole MIP node. Translate only its first (control) tuple here. */
static int axi_lookup(const void *fdt, size_t size, uint64_t address,
    uint64_t bytes, uint64_t *translated)
{
    const uint8_t *p;
    uint32_t length;
    if (property(fdt, size, axi_path, "ranges", &p, &length) ||
        !length || length % 24u || length / 24u > 32u) return -1;
    uint32_t matches = 0;
    uint64_t result = 0;
    for (uint32_t pos = 0; pos < length; pos += 24u) {
        uint64_t child = be64(p + pos), host = be64(p + pos + 8);
        uint64_t extent = be64(p + pos + 16);
        if (!span(child, extent, PHYS_LIMIT) ||
            !span(host, extent, PHYS_LIMIT)) return -1;
        if (address >= child && address - child < extent &&
            bytes <= extent - (address - child)) {
            result = host + (address - child);
            matches++;
        }
    }
    if (matches > 1) return -1;
    if (!matches) return 1;
    *translated = result;
    return 0;
}

static int windows(const void *fdt, size_t size, const char *name,
    struct rpi5_pcie_window *out, uint32_t count, const uint32_t *spaces)
{
    const uint8_t *p;
    uint32_t length;
    if (property(fdt, size, bridge_path, name, &p, &length) ||
        length != count * 28u) return -1;
    for (uint32_t i = 0; i < count; i++) {
        const uint8_t *row = p + i * 28u;
        struct rpi5_pcie_window w = {
            .space = be32(row), .pci_base = be64(row + 4),
            .cpu_base = be64(row + 12), .size = be64(row + 20),
        };
        uint64_t translated = 0;
        if (w.space != spaces[i] || !span(w.pci_base, w.size, PHYS_LIMIT) ||
            !span(w.cpu_base, w.size, PHYS_LIMIT) ||
            axi_lookup(fdt, size, w.cpu_base, w.size, &translated) ||
            translated != w.cpu_base) return -1;
        for (uint32_t j = 0; j < i; j++) {
            if (overlaps(w.cpu_base, w.size, out[j].cpu_base, out[j].size) ||
                (w.space == out[j].space && overlaps(w.pci_base, w.size,
                    out[j].pci_base, out[j].size))) return -1;
        }
        out[i] = w;
    }
    return 0;
}

static int rp1_dma_windows(const void *fdt, size_t size,
    struct rpi5_rp1_dma_window *out)
{
    const uint8_t *p;
    uint32_t length;
    static const uint32_t spaces[3] = {PCI_PREFETCH64, PCI_MEM32, PCI_MEM32};
    if (property(fdt, size, rp1_path, "dma-ranges", &p, &length) ||
        length != 3u * 28u) return -1;
    for (uint32_t i = 0; i < 3; i++) {
        const uint8_t *row = p + i * 28u;
        struct rpi5_rp1_dma_window w = {
            .rp1_base = be64(row), .space = be32(row + 8),
            .pci_base = be64(row + 12), .size = be64(row + 20),
        };
        if (w.space != spaces[i] || !span(w.rp1_base, w.size, PHYS_LIMIT) ||
            !span(w.pci_base, w.size, PHYS_LIMIT)) return -1;
        for (uint32_t j = 0; j < i; j++) {
            if (overlaps(w.rp1_base, w.size, out[j].rp1_base, out[j].size) ||
                (w.space == out[j].space && overlaps(w.pci_base, w.size,
                    out[j].pci_base, out[j].size))) return -1;
        }
        out[i] = w;
    }
    return 0;
}

static int spi(const uint8_t *p, uint32_t flags, uint32_t *intid)
{
    uint32_t number = be32(p + 4);
    if (be32(p) != 0 || number >= 988 || be32(p + 8) != flags) return -1;
    *intid = number + 32;
    return 0;
}

int rpi5_fdt_pcie_rp1(const void *fdt, size_t size, struct rpi5_pcie_fdt *out)
{
    if (!fdt || !out || rpi5_fdt_structure(fdt, size) ||
        rpi5_fdt_phandles(fdt, size)) return -1;
    struct rpi5_pcie_fdt result = {0};
    const uint8_t *p;
    uint32_t length, value;
    const char *paths[] = {root_path, axi_path, bridge_path, mip_path,
        rp1_path, clock_path, gem_path, phy_path, soc_path, gic_path,
        rescal_path, reset_path};
    for (size_t i = 0; i < sizeof paths / sizeof paths[0]; i++)
        if (!enabled(fdt, size, paths[i])) return -1;
    if (!compatible(fdt, size, root_path, "raspberrypi,5-model-b") ||
        !compatible(fdt, size, root_path, "brcm,bcm2712") ||
        !compatible(fdt, size, axi_path, "simple-bus") ||
        !compatible(fdt, size, bridge_path, "brcm,bcm2712-pcie") ||
        !compatible(fdt, size, mip_path, "brcm,bcm2712-mip") ||
        !compatible(fdt, size, rp1_path, "simple-bus") ||
        !compatible(fdt, size, clock_path, "raspberrypi,rp1-clocks") ||
        !compatible(fdt, size, gem_path, "raspberrypi,rp1-gem") ||
        !compatible(fdt, size, gem_path, "cdns,macb") ||
        !compatible(fdt, size, soc_path, "simple-bus") ||
        !compatible(fdt, size, gic_path, "arm,gic-400") ||
        !compatible(fdt, size, rescal_path, "brcm,bcm7216-pcie-sata-rescal") ||
        !compatible(fdt, size, reset_path, "brcm,brcmstb-reset")) return -1;
    if (!u32_is(fdt, size, root_path, "#address-cells", 2) ||
        !u32_is(fdt, size, root_path, "#size-cells", 2) ||
        !u32_is(fdt, size, axi_path, "#address-cells", 2) ||
        !u32_is(fdt, size, axi_path, "#size-cells", 2) ||
        !u32_is(fdt, size, bridge_path, "linux,pci-domain", 2) ||
        !u32_is(fdt, size, bridge_path, "num-lanes", 4) ||
        !u32_is(fdt, size, bridge_path, "max-link-speed", 2) ||
        !u32_is(fdt, size, bridge_path, "#address-cells", 3) ||
        !u32_is(fdt, size, bridge_path, "#size-cells", 2) ||
        !u32_is(fdt, size, bridge_path, "#interrupt-cells", 1) ||
        !u32_is(fdt, size, rp1_path, "#address-cells", 2) ||
        !u32_is(fdt, size, rp1_path, "#size-cells", 2) ||
        !u32_is(fdt, size, rp1_path, "#interrupt-cells", 2) ||
        !u32_is(fdt, size, gem_path, "#address-cells", 1) ||
        !u32_is(fdt, size, gem_path, "#size-cells", 0) ||
        !u32_is(fdt, size, gic_path, "#address-cells", 0) ||
        !u32_is(fdt, size, gic_path, "#interrupt-cells", 3) ||
        !u32_is(fdt, size, clock_path, "#clock-cells", 1) ||
        !exact(fdt, size, bridge_path, "device_type", "pci", sizeof "pci") ||
        !empty(fdt, size, gic_path, "interrupt-controller") ||
        !empty(fdt, size, mip_path, "msi-controller") ||
        !empty(fdt, size, bridge_path, "msi-controller") ||
        !empty(fdt, size, rp1_path, "interrupt-controller")) return -1;
    if (u32(fdt, size, gic_path, "phandle", &result.gic_phandle) ||
        u32(fdt, size, mip_path, "phandle", &result.mip_phandle) ||
        u32(fdt, size, rp1_path, "phandle", &result.rp1_phandle) ||
        u32(fdt, size, clock_path, "phandle", &result.clock_phandle) ||
        !result.gic_phandle || !result.mip_phandle || !result.rp1_phandle ||
        !result.clock_phandle ||
        !u32_is(fdt, size, root_path, "interrupt-parent", result.gic_phandle) ||
        !u32_is(fdt, size, bridge_path, "interrupt-parent", result.gic_phandle) ||
        !u32_is(fdt, size, bridge_path, "msi-parent", result.mip_phandle) ||
        !u32_is(fdt, size, rp1_path, "interrupt-parent", result.rp1_phandle))
        return -1;
    if (!absent(fdt, size, axi_path, "interrupt-parent") ||
        !absent(fdt, size, gem_path, "interrupt-parent") ||
        !absent(fdt, size, bridge_path, "interrupts-extended") ||
        !absent(fdt, size, mip_path, "interrupts-extended") ||
        !absent(fdt, size, rp1_path, "interrupts-extended") ||
        !absent(fdt, size, gem_path, "interrupts-extended")) return -1;

    if (axi_identity(fdt, size) ||
        one_reg(fdt, size, bridge_path, &result.bridge_regs) ||
        one_reg(fdt, size, rescal_path, &result.rescal_regs) ||
        one_reg(fdt, size, reset_path, &result.bridge_reset_regs)) return -1;
    if (property(fdt, size, mip_path, "reg", &p, &length) || length != 32)
        return -1;
    uint64_t mip_control = be64(p), mip_control_size = be64(p + 8);
    uint64_t mip_target = be64(p + 16), mip_target_size = be64(p + 24);
    uint64_t translated = 0;
    if (!span(mip_control, mip_control_size, PHYS_LIMIT) ||
        !span(mip_target, mip_target_size, PHYS_LIMIT) ||
        axi_lookup(fdt, size, mip_control, mip_control_size, &translated) ||
        axi_lookup(fdt, size, mip_target, mip_target_size, &translated) != 1)
        return -1;
    result.mip_regs = (struct rpi5_range){translated, translated + mip_control_size};
    result.mip_target = (struct rpi5_range){mip_target, mip_target + mip_target_size};
    if (result.bridge_regs.start != 0x1000120000ull ||
        result.bridge_regs.end != 0x1000129310ull ||
        result.mip_regs.start != 0x1000130000ull ||
        result.mip_regs.end != 0x10001300c0ull ||
        result.mip_target.start != 0xfffffff000ull ||
        result.mip_target.end != PHYS_LIMIT ||
        result.rescal_regs.start != 0x1000119500ull ||
        result.rescal_regs.end != 0x1000119510ull ||
        result.bridge_reset_regs.start != 0x1001504318ull ||
        result.bridge_reset_regs.end != 0x1001504348ull) return -1;

    if (!exact(fdt, size, bridge_path, "interrupt-names",
            "pcie\0msi", sizeof "pcie\0msi") ||
        property(fdt, size, bridge_path, "interrupts", &p, &length) ||
        length != 24 || spi(p, 4, &result.bridge_intid[0]) ||
        spi(p + 12, 4, &result.bridge_intid[1]) ||
        result.bridge_intid[0] == result.bridge_intid[1] ||
        !exact(fdt, size, bridge_path, "interrupt-map-mask",
            "\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\7", 16)) return -1;
    if (property(fdt, size, bridge_path, "interrupt-map", &p, &length) ||
        length != 4u * 32u) return -1;
    for (uint32_t i = 0; i < 4; i++) {
        const uint8_t *row = p + i * 32u;
        if (be32(row) || be32(row + 4) || be32(row + 8) ||
            be32(row + 12) != i + 1 ||
            be32(row + 16) != result.gic_phandle ||
            spi(row + 20, 4, &result.intx_intid[i])) return -1;
        for (uint32_t j = 0; j < i; j++)
            if (result.intx_intid[i] == result.intx_intid[j]) return -1;
        if (result.intx_intid[i] == result.bridge_intid[0] ||
            result.intx_intid[i] == result.bridge_intid[1]) return -1;
    }
    if (property(fdt, size, mip_path, "msi-ranges", &p, &length) ||
        length != 20 || be32(p) != result.gic_phandle ||
        spi(p + 4, 1, &result.mip_intid_base)) return -1;
    result.mip_intid_count = be32(p + 16);
    if (!result.mip_intid_count || result.mip_intid_count > 1020u -
        result.mip_intid_base || !u32_is(fdt, size, mip_path,
        "brcm,msi-offset", 0)) return -1;
    for (uint32_t i = 0; i < 2; i++)
        if (result.bridge_intid[i] >= result.mip_intid_base &&
            result.bridge_intid[i] - result.mip_intid_base <
                result.mip_intid_count) return -1;
    for (uint32_t i = 0; i < 4; i++)
        if (result.intx_intid[i] >= result.mip_intid_base &&
            result.intx_intid[i] - result.mip_intid_base <
                result.mip_intid_count) return -1;

    static const uint32_t outbound_spaces[2] = {PCI_MEM32, PCI_PREFETCH64};
    static const uint32_t dma_spaces[3] = {PCI_MEM32, PCI_PREFETCH64, PCI_MEM64};
    if (windows(fdt, size, "ranges", result.outbound, 2, outbound_spaces) ||
        windows(fdt, size, "dma-ranges", result.dma, 3, dma_spaces)) return -1;
    result.outbound_count = 2;
    result.dma_count = 3;
    /* The final inbound alias addresses MIP's physical MSI target through its
     * control register window. It is not general-purpose DMA memory. */
    if (result.dma[2].pci_base != result.mip_target.start ||
        result.dma[2].size != result.mip_target.end - result.mip_target.start ||
        result.dma[2].cpu_base != result.mip_regs.start) return -1;

    if (!exact(fdt, size, bridge_path, "reset-names",
            "rescal\0bridge", sizeof "rescal\0bridge") ||
        !u32_is(fdt, size, rescal_path, "#reset-cells", 0) ||
        !u32_is(fdt, size, reset_path, "#reset-cells", 1) ||
        property(fdt, size, bridge_path, "resets", &p, &length) ||
        length != 12 ||
        u32(fdt, size, rescal_path, "phandle", &value) || !value ||
        be32(p) != value ||
        u32(fdt, size, reset_path, "phandle", &value) || !value ||
        be32(p + 4) != value) return -1;
    result.bridge_reset_id = be32(p + 8);
    if (result.bridge_reset_id != 44) return -1;

    if (property(fdt, size, rp1_path, "ranges", &p, &length) || length != 28)
        return -1;
    result.rp1_local_base = be64(p);
    if (be32(p + 8) != PCI_MEM32) return -1;
    result.rp1_pci_base = be64(p + 12);
    result.rp1_aperture_size = be64(p + 20);
    if (!span(result.rp1_local_base, result.rp1_aperture_size, PHYS_LIMIT) ||
        !span(result.rp1_pci_base, result.rp1_aperture_size, PHYS_LIMIT))
        return -1;
    if (rp1_dma_windows(fdt, size, result.rp1_dma)) return -1;
    result.rp1_dma_count = 3;
    if (result.rp1_dma[1].rp1_base != result.rp1_local_base ||
        result.rp1_dma[1].pci_base != result.rp1_pci_base ||
        result.rp1_dma[1].size != result.rp1_aperture_size) return -1;

    if (property(fdt, size, clock_path, "reg", &p, &length) || length != 16)
        return -1;
    uint64_t clock_local = be64(p);
    result.clock_size = be64(p + 8);
    if (!span(clock_local, result.clock_size, PHYS_LIMIT) ||
        clock_local < result.rp1_local_base ||
        clock_local - result.rp1_local_base >= result.rp1_aperture_size ||
        result.clock_size > result.rp1_aperture_size -
            (clock_local - result.rp1_local_base)) return -1;
    result.clock_bar_offset = clock_local - result.rp1_local_base;
    if (result.clock_bar_offset != 0x18000ull ||
        result.clock_size != 0x10038ull) return -1;

    if (property(fdt, size, gem_path, "reg", &p, &length) || length != 16)
        return -1;
    uint64_t gem_local = be64(p);
    result.gem_size = be64(p + 8);
    if (!span(gem_local, result.gem_size, PHYS_LIMIT) ||
        gem_local < result.rp1_local_base ||
        gem_local - result.rp1_local_base >= result.rp1_aperture_size ||
        result.gem_size > result.rp1_aperture_size -
            (gem_local - result.rp1_local_base)) return -1;
    result.gem_bar_offset = gem_local - result.rp1_local_base;
    if (result.gem_bar_offset != 0x100000ull || result.gem_size != 0x4000ull)
        return -1;
    uint64_t gem_pci = result.rp1_pci_base + result.gem_bar_offset;
    if (gem_pci < result.rp1_pci_base) return -1;
    int mapped = 0;
    for (uint32_t i = 0; i < result.outbound_count; i++) {
        const struct rpi5_pcie_window *w = &result.outbound[i];
        if (w->space == PCI_MEM32 && gem_pci >= w->pci_base &&
            gem_pci - w->pci_base < w->size &&
            result.gem_size <= w->size - (gem_pci - w->pci_base)) mapped++;
    }
    if (mapped != 1) return -1;
    if (property(fdt, size, gem_path, "interrupts", &p, &length) ||
        length != 8) return -1;
    result.rp1_irq = be32(p);
    result.rp1_irq_flags = be32(p + 4);
    if (result.rp1_irq != 6 || result.rp1_irq_flags != 4 ||
        !exact(fdt, size, gem_path, "clock-names",
            "pclk\0hclk\0tsu_clk\0tx_clk", sizeof "pclk\0hclk\0tsu_clk\0tx_clk") ||
        property(fdt, size, gem_path, "clocks", &p, &length) ||
        length != 32) return -1;
    static const uint32_t clock_ids[4] = {12, 12, 29, 16};
    for (uint32_t i = 0; i < 4; i++) {
        if (be32(p + i * 8u) != result.clock_phandle ||
            be32(p + i * 8u + 4) != clock_ids[i]) return -1;
        result.gem_clock_id[i] = clock_ids[i];
    }
    if (!exact(fdt, size, gem_path, "phy-mode", "rgmii-id", sizeof "rgmii-id"))
        return -1;
    if (u32(fdt, size, phy_path, "phandle", &result.phy_phandle) ||
        !result.phy_phandle ||
        !u32_is(fdt, size, gem_path, "phy-handle", result.phy_phandle) ||
        u32(fdt, size, phy_path, "reg", &result.phy_address) ||
        result.phy_address != 1) return -1;
    *out = result;
    return 0;
}
