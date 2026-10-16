/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual Apple-tree/seed transaction, retained handoff and strict PCI decoder.
 * All pointers/registers/seed bytes are synthetic, no physical access. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "firmware_fdt_tree.h"
#include "firmware_seed_tree.h"
#include "fdt_sanitize.h"
#include "pcie_fdt.h"
#include "tree_handoff.h"

static unsigned consume_calls;
static int consume(uint8_t *source, size_t size, uint8_t *out, size_t bytes, uint8_t *used)
{
    assert(size == 64 && bytes == 256 && !*used);
    consume_calls++;
    *used = 1;
    memset(source, 0, size);
    memset(out, 0x5a, bytes);
    return 0;
}
static void *load(const char *path, size_t *bytes)
{
    FILE *f = fopen(path, "rb"); assert(f);
    assert(!fseek(f, 0, SEEK_END)); long size = ftell(f);
    assert(size > 0 && size < 256 * 1024); rewind(f);
    /* Intentionally four-byte but not eight-byte aligned input. */
    unsigned char *allocation = malloc((size_t)size + 8); assert(allocation);
    void *p = allocation + 4;
    assert(fread(p, 1, (size_t)size, f) == (size_t)size); fclose(f);
    *bytes = (size_t)size;
    return p;
}
static void record_tests(void)
{
    uint8_t unaligned[34], before[32];
    uint8_t *r = unaligned + 1;
    struct rpi5_firmware_fdt_span span, original = {123, 456};
    assert(!rpi5_fdt_record_encode(0xb000000, 4096, r));
    assert(!rpi5_fdt_record_decode(r, 32, 0x6000000, 0xa000000, 0xb004000, &span));
    assert(span.physical == 0xb000000 && span.bytes == 4096);
    assert(!rpi5_fdt_retained_tail(&span, 0x8000000, 0xb004000));
    assert(rpi5_fdt_retained_tail(&span, 0xb004000, 0xb008000));
    assert(rpi5_fdt_retained_tail(&span, 0x8000001, 0xb004000));
    assert(rpi5_fdt_retained_tail(&span, 0x8000000, 0xb000000));
    memcpy(before, r, 32);
    for (unsigned i = 0; i < 32; i++) {
        if (i >= 8 && i < 24) continue;
        r[i] ^= 1; span = original;
        assert(rpi5_fdt_record_decode(r, 32, 0x6000000, 0xa000000, 0xb004000, &span));
        assert(!memcmp(&span, &original, sizeof span)); r[i] ^= 1;
    }
    assert(rpi5_fdt_record_decode(NULL, 32, 0x6000000, 0xa000000, 0xb004000, &span));
    assert(rpi5_fdt_record_decode(r, 31, 0x6000000, 0xa000000, 0xb004000, &span));
    assert(rpi5_fdt_record_decode(r, 32, 0x6000001, 0xa000000, 0xb004000, &span));
    assert(rpi5_fdt_record_decode(r, 32, 0x6000000, 0, 0xb004000, &span));
    assert(rpi5_fdt_record_decode(r, 32, 0x6000000, 0xa000000, 0xb000000, &span));
    assert(rpi5_fdt_record_decode(r, 32, 0x6000000, 0xa000000, 0x100004000, &span));
    assert(rpi5_fdt_record_decode(r, 32, UINT64_MAX - 0x3fff, 0x4000, 0, &span));
    const uint64_t addresses[] = {0, 1, 0xb000001, UINT64_C(1) << 40, UINT64_MAX};
    for (unsigned i = 0; i < sizeof addresses / sizeof addresses[0]; i++) {
        assert(rpi5_fdt_record_encode(addresses[i], 4096, r));
        assert(!memcmp(r, before, 32));
    }
    const uint64_t lengths[] = {0, 39, RPI5_FIRMWARE_FDT_MAX_BYTES + 1, UINT64_MAX};
    for (unsigned i = 0; i < sizeof lengths / sizeof lengths[0]; i++) {
        assert(rpi5_fdt_record_encode(0xb000000, lengths[i], r)); assert(!memcmp(r, before, 32));
    }
}
int main(int argc, char **argv)
{
    assert(argc == 4); record_tests();
    size_t bytes, image_bytes;
    void *source = load(argv[1], &bytes), *image = load(argv[2], &image_bytes);
    unsigned char *copy = malloc(bytes), *original = malloc(bytes); assert(copy && original);
    memcpy(copy, source, bytes); memcpy(original, source, bytes);
    if (!strcmp(argv[3], "reject")) {
        assert(rpi5_fdt_sanitize_boot_seeds(copy, bytes));
        assert(!memcmp(copy, original, bytes));
        puts("FIRMWARE_FDT_REJECT ATOMIC=1 NO_MMIO=1");
    } else {
        assert(!strcmp(argv[3], "accept"));
        struct rpi5_pcie_fdt before, after;
        assert(!rpi5_fdt_pcie_rp1(source, bytes, &before));
        assert(!rpi5_fdt_sanitize_boot_seeds(copy, bytes));
        assert(!memcmp(source, original, bytes));
        assert(!rpi5_fdt_pcie_rp1(copy, bytes, &after));
        assert(!memcmp(&before, &after, sizeof before));
        const char *names[] = {"rng-seed", "kaslr-seed", "random-seed"};
        unsigned redacted = 0;
        for (unsigned i = 0; i < 3; i++) {
            struct rpi5_fdt_property p;
            int status = rpi5_fdt_property(copy, bytes, "/chosen", names[i], &p);
            if (status == -2) { assert(i); continue; }
            assert(!status); redacted++;
            for (unsigned j = 0; j < p.length; j++) assert(!copy[p.offset + j]);
            /* Only known seed values change, not any other byte or padding. */
            memset(original + p.offset, 0, p.length);
        }
        assert(!memcmp(copy, original, bytes));
        assert(!rpi5_fdt_sanitize_boot_seeds(copy, bytes)); /* Idempotent copy sanitization. */
        struct rpi5_board_tree tree;
        struct rpi5_firmware_fdt_tree storage;
        struct rpi5_memory_types types = {0};
        const uint64_t affinities[4] = {0, 0x100, 0x200, 0x300};
        types.normal.count = 1; types.normal.extent[0] = (struct rpi5_range){0, 0x200000000};
        assert(!rpi5_board_tree_init(affinities, 4, 0, 54000000,
            (struct rpi5_range){0x107d001000, 0x107d001200}, 0, 0x200000000, &tree));
        assert(!rpi5_board_tree_memory_map(&tree, &types));
        assert(!rpi5_firmware_fdt_tree_attach(&tree, source, bytes, 0xb000000, &types, &storage));
        assert(tree.chosen.property_count == 4 && tree.chosen.properties == storage.properties);
        assert(!strcmp(storage.properties[3].name, "rpi5-firmware-fdt") && storage.properties[3].length == 32);
        assert(rpi5_firmware_fdt_tree_attach(&tree, source, bytes, 0xb000000, &types, &storage));
        struct rpi5_range live[] = {{0x9000000, 0x9004000}, {0xb000000, 0xb000000 + bytes}};
        struct rpi5_fdt_memory ram = {.start = {0}, .end = {0x200000000}, .count = 1};
        struct rpi5_reservation_plan reservations = {0};
        struct rpi5_resolved_reservations resolved;
        assert(!rpi5_resolve_reservations(&ram, &reservations, live, 2, &resolved));
        struct rpi5_handoff_input input = {.header_pa = 0x7004000, .phys_base = 0x6000000,
            .mem_size = 0xa000000, .mem_actual = 0x200000000, .args_pa = 0x8000000, .tree_pa = 0x8004000};
        struct rpi5_handoff_plan handoff;
        assert(!rpi5_resolved_tree_handoff(image, image_bytes, &input, &resolved, &types,
            &tree.root, 16384, live, 2, "serial=3", 8, &handoff));
        assert(handoff.top == ((0xb000000 + bytes + 0x3fff) & ~UINT64_C(0x3fff)));
        struct rpi5_firmware_fdt_span span;
        assert(!rpi5_fdt_record_decode(storage.record, 32, input.phys_base, input.mem_size, handoff.top, &span));
        assert(span.physical == live[1].start && span.bytes == bytes);
        uint8_t seed[64], used = 0, apple[16384]; size_t written = 0;
        memset(seed, 0x42, sizeof seed);
        assert(!rpi5_firmware_seed_tree(&tree, seed, &used, apple, sizeof apple, &written, consume));
        assert(used == 1 && consume_calls == 1 && written && tree.chosen.properties == storage.properties);
        assert(tree.chosen.property_count == 4);
        unsigned found = 0;
        for (size_t i = 0; i + 32 <= written; i++) if (!memcmp(apple + i, storage.record, 32)) found++;
        assert(found == 1);
        /* The full raw FDT is not a property in the public Apple tree. */
        for (size_t i = 0; i + 40 <= written; i++) assert(memcmp(apple + i, source, 40));
        for (unsigned i = 0; i < sizeof seed; i++) assert(!seed[i]);
        printf("FIRMWARE_FDT_PASS SEEDS=%u RETAINED=1 APPLE_TREE=1 PCIE_DECODE=1 NO_MMIO=1\n", redacted);
    }
    free((unsigned char *)source - 4); free((unsigned char *)image - 4);
    free(copy); free(original);
    return 0;
}
