/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_BOOT_DATA_H
#define RPI5_BOOT_DATA_H
#include "boot_args.h"
/* Caller proves writable ownership and exact plan/ABI correspondence. Four
 * ranges must be disjoint. Copy then volatile readback; failure after writes
 * clears both destinations. Does not discover RAM or transfer control. */
int rpi5_boot_data_publish(const uint8_t args[RPI5_BOOT_ARGS_SIZE],
    const uint8_t *tree,size_t tree_length,volatile uint8_t *args_destination,
    volatile uint8_t *tree_destination);
/* Handoff preparation: retain verified destinations, then erase the entire
 * caller-owned encoded-tree scratch capacity. Preflight rejection mutates
 * nothing. After valid preflight, scratch is consumed even if publish fails.
 * This does not transfer control or erase the retained tree's seed. */
int rpi5_boot_data_commit(const uint8_t args[RPI5_BOOT_ARGS_SIZE],
    uint8_t *tree,size_t tree_length,size_t scratch_capacity,
    volatile uint8_t *args_destination,volatile uint8_t *tree_destination);
#endif
