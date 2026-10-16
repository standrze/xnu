/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pcie_device_handoff.h"
#include "board_tree.h"
#include "../../../osfmk/arm64/rpi5_memory_map.h"

static struct rpi5_memory_types initial(void)
{
    struct rpi5_memory_types value = {0};
    value.normal.count = 1;
    value.normal.extent[0] = (struct rpi5_range){0, 0x200000000};
    value.device.count = 3;
    value.device.extent[0] = (struct rpi5_range){0x107d000000, 0x107d004000};
    value.device.extent[1] = (struct rpi5_range){0x107d200000, 0x107d204000};
    value.device.extent[2] = (struct rpi5_range){0x107fff8000, 0x107fffc000};
    return value;
}
static void rejected(const void *fdt, size_t bytes, const struct rpi5_memory_types *input)
{
    struct rpi5_memory_types output, before;
    memset(&output, 0xa5, sizeof output); before = output;
    assert(rpi5_pcie_device_handoff(fdt, bytes, input, &output) == -1);
    assert(!memcmp(&output, &before, sizeof output));
}
int main(int argc, char **argv)
{
    assert(argc == 3);
    FILE *file = fopen(argv[1], "rb"); assert(file);
    assert(!fseek(file, 0, SEEK_END));
    long length = ftell(file); assert(length > 0 && length < 256 * 1024);
    rewind(file);
    /* Intentionally four-byte but not eight-byte aligned FDT. */
    unsigned char *allocation = malloc((size_t)length + 8); assert(allocation);
    void *fdt = allocation + 4;
    assert(fread(fdt, 1, (size_t)length, file) == (size_t)length); fclose(file);
    struct rpi5_memory_types input = initial(), before = input, output;
    size_t bytes = (size_t)length;
    if (!strcmp(argv[2], "reject")) {
        rejected(fdt, bytes, &input);
        assert(!memcmp(&input, &before, sizeof input));
        free(allocation); puts("PCIE_DEVICE_HANDOFF_REJECT NO_MMIO=1"); return 0;
    }
    assert(!strcmp(argv[2], "accept"));
    assert(!rpi5_pcie_device_handoff(fdt, bytes, &input, &output));
    assert(!memcmp(&input, &before, sizeof input));
    assert(!memcmp(&input.normal, &output.normal, sizeof input.normal));
    assert(output.device.count == 6);
    const struct rpi5_range added[3] = {
        {0x1000118000, 0x100011c000}, {0x1000120000, 0x100012c000}, {0x1001504000, 0x1001508000}};
    for (unsigned i = 0; i < 3; i++) {
        assert(output.device.extent[i].start == added[i].start && output.device.extent[i].end == added[i].end);
        assert(output.device.extent[i + 3].start == input.device.extent[i].start);
        assert(output.device.extent[i + 3].end == input.device.extent[i].end);
    }
    unsigned char encoded[RPI5_MEMORY_MAP_MAX_BYTES]; size_t written = 0;
    assert(!rpi5_memory_types_encode(&output, encoded, sizeof encoded, &written));
    assert(written == 8 + 7 * 24);
    struct rpi5_kernel_memory_map kernel = {0};
    assert(!rpi5_map_decode(encoded, written, &kernel));
    /* Follow the actual loader attachment/Apple serialization path too. */
    struct rpi5_board_tree tree;
    const uint64_t affinities[4] = {0, 0x100, 0x200, 0x300};
    assert(!rpi5_board_tree_init(affinities, 4, 0, 54000000,
        (struct rpi5_range){0x107d001000, 0x107d001200}, 0, 0x200000000, &tree));
    assert(!rpi5_board_tree_memory_map(&tree, &output));
    assert(tree.root.children[0] == &tree.chosen && tree.chosen.property_count == 3);
    assert(!strcmp(tree.chosen.properties[2].name, "rpi5-memory-map"));
    assert(tree.chosen.properties[2].length == written);
    assert(!memcmp(tree.chosen.properties[2].data, encoded, written));
    unsigned char apple[16384]; size_t apple_bytes = 0;
    assert(!rpi5_adt_encode(&tree.root, apple, sizeof apple, &apple_bytes));
    unsigned found = 0;
    for (size_t i = 0; i + written <= apple_bytes; i++) {
        if (memcmp(apple + i, encoded, written)) continue;
        assert(!rpi5_map_decode(apple + i, written, &kernel));
        found++;
    }
    assert(found == 1);
    for (unsigned i = 0; i < 3; i++) {
        assert(rpi5_map_type(&kernel, added[i].start, added[i].end) == 2);
        assert(!rpi5_map_type(&kernel, added[i].start - 1, added[i].start));
        assert(!rpi5_map_type(&kernel, added[i].end, added[i].end + 1));
    }
    assert(rpi5_map_type(&kernel, 0, 0x200000000) == 1);
    assert(!rpi5_map_type(&kernel, 0x1000130000, 0x10001300c0)); /* MIP excluded. */
    assert(!rpi5_map_type(&kernel, 0x1f00000000, 0x1f00400000)); /* RP1 BAR excluded. */
    rejected(fdt, bytes, &output); /* No repeat/duplicate declaration expansion. */
    rejected(NULL, bytes, &input);
    rejected(fdt, bytes - 1, &input);
    assert(rpi5_pcie_device_handoff(fdt, bytes, &input, NULL));
    assert(rpi5_pcie_device_handoff(fdt, bytes, &input, &input));
    assert(!memcmp(&input, &before, sizeof input));
    for (unsigned i = 0; i < 3; i++) {
        struct rpi5_memory_types bad = initial();
        bad.device.extent[0] = added[i]; /* Duplicate one exact added resource. */
        rejected(fdt, bytes, &bad);
        bad = initial();
        bad.normal.count = 2; bad.normal.extent[1] = added[i]; /* Final cross-type overlap. */
        rejected(fdt, bytes, &bad);
    }
    struct rpi5_memory_types partial = initial();
    partial.device.extent[0] = (struct rpi5_range){0x1000124000, 0x1000128000};
    rejected(fdt, bytes, &partial);
    struct rpi5_memory_types full = initial();
    full.device.count = 29;
    for (unsigned i = 0; i < 30; i++)
        full.device.extent[i] = (struct rpi5_range){0x1100000000 + i * 0x8000ull, 0x1100004000 + i * 0x8000ull};
    assert(!rpi5_pcie_device_handoff(fdt, bytes, &full, &output));
    assert(output.device.count == 32);
    full.device.count = 30; rejected(fdt, bytes, &full);
    full = initial(); full.device.extent[0].start++; rejected(fdt, bytes, &full);
    full = initial(); full.device.extent[0] = full.device.extent[1]; rejected(fdt, bytes, &full);
    full = initial(); full.normal.count = 0; rejected(fdt, bytes, &full);
    free(allocation);
    puts("PCIE_DEVICE_HANDOFF_PASS EXACT_PAGES=5 APPLE_TREE=1 KERNEL_DECODE=1 NO_MMIO=1");
    return 0;
}
