/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_SERIAL_TREE_H
#define RPI5_SERIAL_TREE_H
#include "apple_dt.h"
#include "ranges.h"
struct rpi5_serial_tree {
    struct rpi5_adt_node arm_io, uart, defaults;
    /* The board composer may attach the validated GIC and watchdog. */
    const struct rpi5_adt_node *children[3];
    struct rpi5_adt_property io_props[2], uart_props[3], default_prop;
    uint8_t ranges[24], reg[16], phandle[4];
};
/* Input window must come from validated runtime translation. Narrow UART10
 * profile only. Caller reserves a unique, nonzero Apple phandle in the complete
 * tree and attaches arm_io/defaults to its root. Output unchanged on invalid
 * input, self-referential on success: do not move/copy before serialization.
 * This encodes address/selection semantics, not UART ownership or baud setup. */
int rpi5_serial_tree_init(struct rpi5_range uart, uint32_t phandle,
    struct rpi5_serial_tree *out);
#endif
