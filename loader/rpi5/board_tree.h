/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_BOARD_TREE_H
#define RPI5_BOARD_TREE_H
#include "cpu_tree.h"
#include "serial_tree.h"
#include "memory_type.h"
#include "fdt.h"
struct rpi5_board_tree {
    struct rpi5_cpu_tree cpus;
    struct rpi5_serial_tree serial;
    struct rpi5_adt_node root, chosen, image_memory_map, gic, watchdog, sdhci;
    const struct rpi5_adt_node *chosen_children[1];
    const struct rpi5_adt_node *children[5];
    struct rpi5_adt_property root_props[1];
    struct rpi5_adt_property gic_props[2];
    uint8_t gic_reg[32];
    struct rpi5_adt_property watchdog_props[2];
    uint8_t watchdog_reg[16];
    struct rpi5_adt_property sdhci_props[7];
    uint8_t sdhci_reg[32], sdhci_clock[4], sdhci_irq[4];
    uint8_t sd_power_reg[48], sd_pad_variant[4], sd_settling_us[4];
    struct rpi5_adt_property ramdisk_prop;
    uint8_t ramdisk_record[16];
    struct rpi5_adt_property chosen_props[3];
    uint8_t dram_base[8], dram_size[8];
    uint8_t memory_map[RPI5_MEMORY_MAP_MAX_BYTES];
};
/* Compose the reviewed early-consumer properties, without a seed. Call the
 * seed-tree encoder after ownership/provider validation. Actual DRAM envelope
 * is distinct from managed memory and is NOT inferred from RAM minus reserves.
 * Inputs must not alias out. Validation failure preserves out. On success out
 * contains internal pointers and must stay at a stable address. No evidence of
 * firmware ownership, entropy, clock accuracy, IOKit matching or a boot. */
int rpi5_board_tree_init(const uint64_t *affinity, size_t count,
    uint64_t boot_affinity, uint32_t counter_hz, struct rpi5_range uart,
    uint64_t dram_base, uint64_t dram_size, struct rpi5_board_tree *out);
/* Attach one validated 16 KiB-aligned static Mach-O image under
 * /chosen/memory-map/RAMDisk. Caller must independently prove destination
 * ownership, copy/readback, and retention through XNU's early mount. */
int rpi5_board_tree_ramdisk(struct rpi5_board_tree *tree,
    uint64_t physical_address, uint64_t length);
/* Attach or replace explicit types on an initialized, stable board tree.
 * Types must not alias tree. Invalid input leaves the tree unchanged. */
int rpi5_board_tree_memory_map(struct rpi5_board_tree *tree,
    const struct rpi5_memory_types *types);
/* Attach only the exact PM range already validated against the runtime FDT. */
int rpi5_board_tree_watchdog(struct rpi5_board_tree *tree,
    struct rpi5_range watchdog);
/* Root-level physical reg tuple: the SD host is outside arm-io's real range.
 * Input must have passed rpi5_fdt_sdhci. No host/card initialization or voltage
 * proof is implied by publishing this node. Atomic on invalid geometry.
 */
int rpi5_board_tree_sdhci(struct rpi5_board_tree *, const struct rpi5_fdt_sdhci *);
/* Append exact physical GPIO/pad ranges plus explicit variant/timing to an
 * already attached SD node. Input must pass rpi5_fdt_sd_power. Describes wiring,
 * never rail state or exclusive ownership. Invalid/duplicate input is atomic.
 */
int rpi5_board_tree_sd_power(struct rpi5_board_tree *, const struct rpi5_fdt_sd_power *);
#endif
