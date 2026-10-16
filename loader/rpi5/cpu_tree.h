/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_CPU_TREE_H
#define RPI5_CPU_TREE_H
#include "apple_dt.h"
struct rpi5_cpu_tree {
    struct rpi5_adt_node root, cpu[4];
    const struct rpi5_adt_node *children[4];
    struct rpi5_adt_property properties[4][4];
    uint8_t reg[4][4], frequency[4];
};
/* Construct only /cpus, not a complete board tree. Affinities must be validated
 * Pi profile IDs (0,0x100,0x200,0x300); boot ID occurs exactly once. Frequency
 * is supplied from the architectural counter, not a CPU/core clock guess.
 * Output unchanged on validation failure. On success pointers refer into out;
 * retain its address until serialization and do not copy the structure. */
int rpi5_cpu_tree_init(const uint64_t *affinity, size_t count,
    uint64_t boot_affinity, uint32_t counter_hz, struct rpi5_cpu_tree *out);
#endif
