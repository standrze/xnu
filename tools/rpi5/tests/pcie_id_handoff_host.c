/* SPDX-License-Identifier: BSD-2-Clause */
/* Exercise the real no-init emitted Apple tree, then the kernel decoders.
 * All addresses and FDT content are fixtures, never hardware access. */
#define main retained_original_main
#include "firmware_fdt_host.c"
#undef main
#include "pcie_device_handoff.h"
#include "../../../osfmk/arm64/rpi5_memory_map.h"

struct observed { const uint8_t *record, *map; uint32_t record_bytes, map_bytes; };
static void walk(const uint8_t *p, size_t size, size_t *cursor,
    unsigned depth, struct observed *out)
{
    assert(depth < 64 && *cursor + 8 <= size);
    uint32_t props = (uint32_t)rpi5_map_le(p + *cursor, 4);
    uint32_t children = (uint32_t)rpi5_map_le(p + *cursor + 4, 4);
    *cursor += 8;
    int chosen = 0;
    for (uint32_t i = 0; i < props; i++) {
        assert(*cursor + 36 <= size);
        const uint8_t *name = p + *cursor;
        uint32_t length = (uint32_t)rpi5_map_le(name + 32, 4);
        assert(memchr(name, 0, 32) && length <= size - *cursor - 36);
        const uint8_t *value = name + 36;
        if (!strcmp((const char *)name, "name")) {
            assert(!i && length && !value[length - 1]);
            chosen = depth == 1 && !strcmp((const char *)value, "chosen");
        }
        if (chosen && !strcmp((const char *)name, "rpi5-firmware-fdt")) {
            assert(!out->record); out->record = value; out->record_bytes = length;
        }
        if (chosen && !strcmp((const char *)name, "rpi5-memory-map")) {
            assert(!out->map); out->map = value; out->map_bytes = length;
        }
        *cursor += 36 + ((length + 3u) & ~3u);
        assert(*cursor <= size);
    }
    for (uint32_t i = 0; i < children; i++) walk(p, size, cursor, depth + 1, out);
}
static void emitted_contract(const void *fdt, size_t bytes, int attach)
{
    struct rpi5_board_tree tree;
    struct rpi5_memory_types before = {0}, types;
    struct rpi5_firmware_fdt_tree storage;
    struct rpi5_pcie_fdt binding;
    const uint64_t affinities[4] = {0, 0x100, 0x200, 0x300};
    before.normal.count = 1;
    before.normal.extent[0] = (struct rpi5_range){0, 0x200000000};
    before.device.count = 3;
    before.device.extent[0] = (struct rpi5_range){0x107d000000, 0x107d004000};
    before.device.extent[1] = (struct rpi5_range){0x107d200000, 0x107d204000};
    before.device.extent[2] = (struct rpi5_range){0x107fff8000, 0x107fffc000};
    assert(!rpi5_pcie_device_handoff(fdt, bytes, &before, &types));
    assert(types.device.count == 6);
    assert(!rpi5_fdt_pcie_rp1(fdt, bytes, &binding));
    assert(!rpi5_board_tree_init(affinities, 4, 0, 54000000,
        (struct rpi5_range){0x107d001000, 0x107d001200}, 0, 0x200000000, &tree));
    assert(!rpi5_board_tree_memory_map(&tree, &types));
    if (attach) assert(!rpi5_firmware_fdt_tree_attach(&tree, fdt, bytes, 0xb000000, &types, &storage));
    assert(!tree.image_memory_map.property_count); /* Real no-init path. */
    uint8_t seed[64], used = 0, apple[16384]; size_t written = 0, cursor = 0;
    memset(seed, 0x42, sizeof seed);
    assert(!rpi5_firmware_seed_tree(&tree, seed, &used, apple, sizeof apple, &written, consume));
    struct observed out = {0};
    walk(apple, written, &cursor, 0, &out);
    assert(cursor == written && out.map);
    struct rpi5_kernel_memory_map map;
    assert(!rpi5_map_decode(out.map, out.map_bytes, &map));
    struct rpi5_firmware_fdt_span span;
    if (!attach) { assert(!out.record); return; } /* Kernel must reject missing property. */
    assert(out.record && out.record_bytes == 32);
    assert(!rpi5_fdt_record_decode(out.record, out.record_bytes, 0x6000000,
        0xa000000, (0xb000000 + bytes + 0x3fff) & ~UINT64_C(0x3fff), &span));
    assert(span.physical == 0xb000000 && span.bytes == bytes);
    assert(rpi5_map_type(&map, span.physical, span.physical + span.bytes) == 1);
    assert(!rpi5_fdt_retained_tail(&span, 0xa000000,
        (0xb000000 + bytes + 0x3fff) & ~UINT64_C(0x3fff)));
    const struct rpi5_range resources[] = {binding.bridge_regs, binding.rescal_regs, binding.bridge_reset_regs};
    for (unsigned i = 0; i < 3; i++)
        assert(rpi5_map_type(&map, resources[i].start, resources[i].end) == 2);
    /* Descriptor may not name Device memory or overlap the loaded kernel. */
    assert(rpi5_map_type(&map, resources[0].start, resources[0].end) != 1);
    assert(rpi5_fdt_retained_tail(&span, 0xb004000, 0xb008000));
}
int main(int argc, char **argv)
{
    assert(argc == 4 && !strcmp(argv[3], "accept"));
    assert(!retained_original_main(argc, argv));
    size_t bytes; void *fdt = load(argv[1], &bytes);
    emitted_contract(fdt, bytes, 0);
    emitted_contract(fdt, bytes, 1);
    free((uint8_t *)fdt - 4);
    puts("PCIE_ID_HANDOFF NO_INIT=1 SERIALIZED_CHOSEN=1 KERNEL_DECODE=1 NORMAL_RETAINED=1 DEVICE_RESOURCES=3 MISSING_REJECT=1 NO_MMIO=1");
    return 0;
}
