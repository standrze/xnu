/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RESERVATION_RECORD_TREE_H
#define RPI5_RESERVATION_RECORD_TREE_H
#include "reservation_record.h"
#include "tree_handoff.h"
#include "board_tree.h"
struct rpi5_reservation_record_tree {
    struct rpi5_adt_property properties[6];
    uint8_t record[RPI5_RESERVATION_RECORD_BYTES];
};
/* Exact display chosen5 predecessor; reserve before ADT measurement. Zero
 * placeholder is invalid and must never be emitted/consumed as a live record. */
int rpi5_reservation_record_tree_reserve(struct rpi5_board_tree *,struct rpi5_reservation_record_tree *);
/* Passed resolved must be the same complete result used by successful actual
 * resolved_tree_handoff. Recompute deterministic planner from fresh FDT plus
 * exact live loader/originalFDT inventory; compare all three resolved views.
 * Only then bind exact successful handoff args/tree/kernel/top and SHA256.
 * No physical writes, allocation or release. Stable disjoint inputs required. */
int rpi5_reservation_record_make(const void *,size_t,uint64_t,struct rpi5_range,
    const struct rpi5_resolved_reservations *,const struct rpi5_handoff_input *,
    const struct rpi5_handoff_plan *,uint64_t,struct rpi5_reservation_record *);
int rpi5_reservation_record_tree_commit(struct rpi5_board_tree *,const struct rpi5_reservation_record *,
    struct rpi5_reservation_record_tree *);
#endif
