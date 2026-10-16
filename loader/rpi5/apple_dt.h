/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_APPLE_DT_H
#define RPI5_APPLE_DT_H
#include <stddef.h>
#include <stdint.h>
#define RPI5_ADT_MAX_DEPTH 64
struct rpi5_adt_property { const char *name; const void *data; uint32_t length; };
struct rpi5_adt_node {
    const char *name;
    const struct rpi5_adt_property *properties;
    const struct rpi5_adt_node *const *children;
    uint32_t property_count, child_count;
};
/* Stable readable input graph; output/written must not alias any input or each
 * other. Property bytes are explicit, never implicitly endian-converted.
 * Bounded to 256 nodes, depth 64, 128 properties/children per node, 16 MiB.
 * Validates entire graph/capacity before output writes; no board semantics. */
int rpi5_adt_encode(const struct rpi5_adt_node *root, void *output,
    size_t capacity, size_t *written);
/* Same graph validation without encoding; output length unchanged on failure. */
int rpi5_adt_measure(const struct rpi5_adt_node *root, size_t capacity, size_t *written);
#endif
