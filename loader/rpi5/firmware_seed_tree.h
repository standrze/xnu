/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_FIRMWARE_SEED_TREE_H
#define RPI5_FIRMWARE_SEED_TREE_H
#include "board_tree.h"
/* Preflight exact seeded length before consuming. Caller supplies validated,
 * writable firmware source and disjoint stable board tree/output/state. The
 * callback is the isolated consume-once implementation (mocked in host tests).
 * No firmware/version/ownership discovery. No transfer. */
int rpi5_firmware_seed_tree(struct rpi5_board_tree *tree, uint8_t seed[64],
    uint8_t *consumed, void *output, size_t capacity, size_t *written,
    int (*consume)(uint8_t *,size_t,uint8_t *,size_t,uint8_t *));
#endif
