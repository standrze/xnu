/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_FIRMWARE_FDT_TREE_H
#define RPI5_FIRMWARE_FDT_TREE_H
#include "board_tree.h"
#include "firmware_fdt_record.h"
struct rpi5_firmware_fdt_tree {
    struct rpi5_adt_property properties[4];
    uint8_t record[RPI5_FIRMWARE_FDT_RECORD_BYTES];
};
/* Initialized stable tree/types/FDT and distinct stable storage. Metadata only;
 * the unchanged handoff planner must retain this exact FDT live allocation.
 * It does not qualify writable ownership, source authenticity or PCIe access.
 * No contents/seeds are copied to the public Apple device tree. */
int rpi5_firmware_fdt_tree_attach(struct rpi5_board_tree *, const void *fdt,
    size_t bytes, uint64_t physical, const struct rpi5_memory_types *,
    struct rpi5_firmware_fdt_tree *);
#endif
