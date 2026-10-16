/* SPDX-License-Identifier: BSD-2-Clause */
#include "firmware_fdt_tree.h"
int rpi5_firmware_fdt_tree_attach(struct rpi5_board_tree *tree, const void *fdt,
    size_t bytes, uint64_t physical, const struct rpi5_memory_types *types,
    struct rpi5_firmware_fdt_tree *storage)
{
    uint8_t record[RPI5_FIRMWARE_FDT_RECORD_BYTES];
    struct rpi5_fdt_layout layout;
    if (!tree || !storage || !fdt || tree->chosen.properties != tree->chosen_props ||
        tree->chosen.property_count != 3 ||
        rpi5_fdt_record_encode(physical, bytes, record) ||
        rpi5_memory_type_for(types, (struct rpi5_range){physical, physical + bytes}) != RPI5_MEMORY_NORMAL ||
        rpi5_fdt_layout(fdt, bytes, &layout) || layout.total != bytes || rpi5_fdt_structure(fdt, bytes)) return -1;
    for (unsigned i = 0; i < sizeof record; i++) storage->record[i] = record[i];
    for (unsigned i = 0; i < 3; i++) storage->properties[i] = tree->chosen_props[i];
    storage->properties[3] = (struct rpi5_adt_property){"rpi5-firmware-fdt", storage->record, sizeof storage->record};
    tree->chosen.properties = storage->properties;
    tree->chosen.property_count = 4;
    return 0;
}
