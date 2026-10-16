/* SPDX-License-Identifier: BSD-2-Clause */
/* Execute only pure helpers, using ORIGINAL Apple types and actual XNU headers. */
#include "../../../iokit/Kernel/BCM2712PCIResourceAddress.h"
#include "../../../iokit/Kernel/BCM2712PCIAssignedRange.h"

extern "C" int main(void);

static IOPCIPhysicalAddress row(unsigned bar, uint64_t base, uint64_t size, bool wide = false)
{
    IOPCIPhysicalAddress r = {};
    r.physHi.s.busNum = 1;
    r.physHi.s.registerNum = kIOPCIConfigBaseAddress0 + bar * 4;
    r.physHi.s.space = wide ? kIOPCI64BitMemorySpace : kIOPCI32BitMemorySpace;
    r.physHi.s.reloc = 1;
    r.physHi.s.prefetch = wide;
    r.physLo = (UInt32)base;
    r.physMid = (UInt32)(base >> 32);
    r.lengthLo = (UInt32)size;
    r.lengthHi = (UInt32)(size >> 32);
    return r;
}

static bool rejected(const struct rpi5_pcie_window windows[2], const void *data, size_t size,
    IOPCIAddressSpace device)
{
    struct bcm2712_pci_resource_address out[6], before[6];
    for (unsigned i = 0; i < 6; i++) {
        out[i].tag = 0x12345678; out[i].pci_base = UINT64_MAX;
        out[i].size = 0x87654321; out[i].cpu_base = 0xabcdef;
        before[i] = out[i];
    }
    uint32_t count = 0x87654321;
    if (bcm2712_pci_resource_addresses(windows, 2, data, size, device, out, &count)) return false;
    if (count != 0x87654321) return false;
    for (unsigned i = 0; i < 6; i++) {
        if (out[i].tag != before[i].tag || out[i].pci_base != before[i].pci_base ||
            out[i].size != before[i].size || out[i].cpu_base != before[i].cpu_base) return false;
    }
    return true;
}

#define CHECK(expression) do { if (!(expression)) return __LINE__; } while (0)
extern "C" int main(void)
{
    static_assert(sizeof(IOPCIPhysicalAddress) == 20, "Actual property record width");
    IOPCIRange allocated = {}, sentinel = {};
    CHECK(!bcm2712_pci_range_assigned(nullptr));
    CHECK(!bcm2712_pci_range_assigned(&allocated));
    allocated.start = 0x1000; allocated.size = 0x1000; allocated.end = 0x2000;
    CHECK(!bcm2712_pci_range_assigned(&allocated)); /* Nonzero alone is not assignment. */
    allocated.start = 0; allocated.size = 0x400000; allocated.end = 0x400000;
    allocated.nextSubRange = &sentinel;
    CHECK(bcm2712_pci_range_assigned(&allocated)); /* Zero with actual list membership is. */
    allocated.end--; CHECK(!bcm2712_pci_range_assigned(&allocated)); allocated.end++;
    allocated.start = UINT64_MAX; CHECK(!bcm2712_pci_range_assigned(&allocated)); allocated.start = 0;
    allocated.size = 0; CHECK(!bcm2712_pci_range_assigned(&allocated)); allocated.size = 0x400000;
    auto tagged = row(1, 0, 0x400000).physHi;
    allocated.type = kIOPCIResourceTypePrefetchMemory;
    allocated.flags = kIOPCIRangeFlagBar64;
    auto wide_tag = bcm2712_pci_range_space(tagged, &allocated);
    CHECK(wide_tag.s.space == kIOPCI64BitMemorySpace &&
        (wide_tag.bits & ~UINT32_C(0x03000000)) == (tagged.bits & ~UINT32_C(0x03000000)));
    allocated.flags = 0; CHECK(bcm2712_pci_range_space(tagged, &allocated).bits == tagged.bits);
    allocated.flags = kIOPCIRangeFlagBar64; allocated.type = kIOPCIResourceTypeIO;
    CHECK(bcm2712_pci_range_space(tagged, &allocated).bits == tagged.bits);
    struct rpi5_pcie_window windows[2] = {
        {0x02000000, 0, 0x1f00000000ull, 0xfffffffc},
        {0x43000000, 0x400000000ull, 0x1c00000000ull, 0x300000000ull}
    };
    IOPCIAddressSpace device = {};
    device.s.busNum = 1;
    IOPCIPhysicalAddress records[7] = {
        row(0, 0x410000, 0x4000), row(1, 0, 0x400000), row(2, 0x400000, 0x10000)
    };
    struct bcm2712_pci_resource_address out[6] = {};
    uint32_t count = 99;
    CHECK(bcm2712_pci_resource_addresses(windows, 2, records, 3*sizeof(records[0]), device, out, &count));
    CHECK(count == 3 && out[1].pci_base == 0 && out[1].cpu_base == 0x1f00000000ull);
    CHECK(out[0].cpu_base == 0x1f00410000ull && out[2].cpu_base == 0x1f00400000ull);
    CHECK(out[1].tag == records[1].physHi.bits && out[1].size == 0x400000);
    /* An unaligned OSData payload is copied, not dereferenced as an aligned struct. */
    unsigned char unaligned[1 + 3*sizeof(IOPCIPhysicalAddress)] = {};
    for (size_t i = 0; i < 3*sizeof(IOPCIPhysicalAddress); i++)
        unaligned[1+i] = reinterpret_cast<const unsigned char *>(records)[i];
    CHECK(bcm2712_pci_resource_addresses(windows, 2, unaligned+1, sizeof(unaligned)-1, device, out, &count));
    IOPCIPhysicalAddress r = row(3, 0x600000000ull, 0x100000000ull, true);
    CHECK(bcm2712_pci_resource_addresses(windows, 2, &r, sizeof(r), device, out, &count));
    CHECK(count == 1 && out[0].cpu_base == 0x1e00000000ull && out[0].size == 0x100000000ull);
    CHECK(rejected(windows, records, sizeof(records), device));
    CHECK(rejected(windows, records, 1, device));
    CHECK(rejected(windows, nullptr, sizeof(r), device));
    CHECK(!bcm2712_pci_resource_addresses(windows, 1, &r, sizeof(r), device, out, &count));
    CHECK(!bcm2712_pci_resource_addresses(windows, 2, &r, sizeof(r), device, nullptr, &count));
    CHECK(!bcm2712_pci_resource_addresses(windows, 2, &r, sizeof(r), device, out, nullptr));
    CHECK(bcm2712_pci_resource_addresses(windows, 2, nullptr, 0, device, out, &count) && !count);
    for (unsigned bit = 26; bit <= 29; bit++) {
        r = row(1, 0, 0x400000); r.physHi.bits |= 1u << bit;
        CHECK(rejected(windows, &r, sizeof(r), device));
    }
    r = row(1, 0, 0x400000); r.physHi.s.reloc = 0; CHECK(rejected(windows, &r, sizeof(r), device));
    r = row(1, 0, 0x400000); r.physHi.s.prefetch = 1; CHECK(rejected(windows, &r, sizeof(r), device));
    r = row(1, 0, 0x400000); r.physHi.s.space = kIOPCIIOSpace; CHECK(rejected(windows, &r, sizeof(r), device));
    r = row(1, 0, 0x400000); r.physHi.s.space = kIOPCI64BitMemorySpace; CHECK(rejected(windows, &r, sizeof(r), device));
    for (unsigned reg = 0; reg < 256; reg++) {
        r = row(1, 0, 0x400000); r.physHi.s.registerNum = reg;
        if (reg < 0x10 || reg > 0x24 || (reg & 3)) CHECK(rejected(windows, &r, sizeof(r), device));
    }
    for (unsigned bus = 0; bus < 256; bus++) {
        r = row(1, 0, 0x400000); r.physHi.s.busNum = bus;
        if (bus != 1) CHECK(rejected(windows, &r, sizeof(r), device));
    }
    r = row(1, 0, 0x400000); r.physHi.s.deviceNum = 1; CHECK(rejected(windows, &r, sizeof(r), device));
    r = row(1, 0, 0x400000); r.physHi.s.functionNum = 1; CHECK(rejected(windows, &r, sizeof(r), device));
    IOPCIAddressSpace invalid = device; invalid.s.busNum = 2;
    CHECK(rejected(windows, &r, sizeof(r), invalid));
    invalid = device; invalid.es.registerNumExtended = 1; CHECK(rejected(windows, &r, sizeof(r), invalid));
    invalid = device; invalid.s.registerNum = 1; CHECK(rejected(windows, &r, sizeof(r), invalid));
    uint64_t bad_sizes[] = {0, 1, 8, 17, 0x600000, UINT64_MAX};
    for (auto size : bad_sizes) { r = row(1, 0, size); CHECK(rejected(windows, &r, sizeof(r), device)); }
    r = row(1, 1, 0x400000); CHECK(rejected(windows, &r, sizeof(r), device));
    r = row(1, UINT64_MAX, 16); CHECK(rejected(windows, &r, sizeof(r), device));
    r = row(1, 0x100000000ull, 16); CHECK(rejected(windows, &r, sizeof(r), device));
    r = row(1, 0xfffffff0, 16); CHECK(rejected(windows, &r, sizeof(r), device)); /* Four-byte excess. */
    r = row(1, 0xffffffe0, 16);
    CHECK(bcm2712_pci_resource_addresses(windows, 2, &r, sizeof(r), device, out, &count));
    r = row(1, 0x300000000ull, 16, true); CHECK(rejected(windows, &r, sizeof(r), device));
    r = row(1, 0x700000000ull, 16, true); CHECK(rejected(windows, &r, sizeof(r), device));
    r = row(5, 0x400000000ull, 16, true); CHECK(rejected(windows, &r, sizeof(r), device));
    IOPCIPhysicalAddress pair[2] = {row(3, 0x400000000ull, 16, true), row(4, 0x1000, 16)};
    CHECK(rejected(windows, pair, sizeof(pair), device)); /* MEM64 high slot. */
    pair[0] = row(1, 0, 0x400000); pair[1] = row(2, 0x1000, 16);
    CHECK(rejected(windows, pair, sizeof(pair), device)); /* Overlapping apertures. */
    pair[1] = row(1, 0x400000, 0x10000); CHECK(rejected(windows, pair, sizeof(pair), device)); /* Duplicate BAR. */
    struct rpi5_pcie_window bad[2] = {windows[0], windows[1]};
    r = row(1, 0, 0x400000);
    bad[1].space = 0x03000000; CHECK(rejected(bad, &r, sizeof(r), device));
    bad[1] = windows[1]; bad[1].cpu_base = windows[0].cpu_base; CHECK(rejected(bad, &r, sizeof(r), device));
    bad[1] = windows[1]; bad[1].pci_base = 0; CHECK(rejected(bad, &r, sizeof(r), device));
    bad[1] = windows[1]; bad[0].size = 0; CHECK(rejected(bad, &r, sizeof(r), device));
    bad[0] = windows[0]; bad[0].cpu_base = (UINT64_C(1)<<40)-0x1000;
    CHECK(rejected(bad, &r, sizeof(r), device));
    /* 16384 aligned sizes/positions: translation must preserve exact offset and
     * full containment, never substitute the host's already translated base. */
    for (unsigned exponent = 4; exponent < 20; exponent++) for (unsigned n = 0; n < 512; n++) {
        uint64_t size = UINT64_C(1) << exponent;
        uint64_t base = (uint64_t)n * size;
        r = row(1, base, size);
        CHECK(bcm2712_pci_resource_addresses(windows, 2, &r, sizeof(r), device, out, &count));
        CHECK(count == 1 && out[0].cpu_base == windows[0].cpu_base + base && out[0].size == size);
        r = row(1, windows[0].cpu_base + base, size);
        CHECK(rejected(windows, &r, sizeof(r), device));
        r = row(3, windows[1].pci_base + base, size, true);
        CHECK(bcm2712_pci_resource_addresses(windows, 2, &r, sizeof(r), device, out, &count));
        CHECK(count == 1 && out[0].cpu_base == windows[1].cpu_base + base && out[0].size == size);
    }
    return 0;
}
