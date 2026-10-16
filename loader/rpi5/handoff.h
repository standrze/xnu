/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_HANDOFF_H
#define RPI5_HANDOFF_H
#include "macho.h"
#include "bootstrap.h"
#include "boot_args.h"
struct rpi5_handoff_input {
    uint64_t header_pa, phys_base, mem_size, mem_actual, args_pa, tree_pa;
    struct rpi5_range usable;
    uint32_t tree_length;
};
struct rpi5_handoff_plan {
    struct rpi5_macho_placement kernel;
    struct rpi5_bootstrap_mapping mapping;
    uint64_t top, args_pa;
    uint8_t args[RPI5_BOOT_ARGS_SIZE];
};
/* Pure plan. Caller must provide complete live allocations and one genuinely
 * reservation-free usable extent. Tree bytes/semantics/entropy and relocation
 * validation remain separate requirements. Does not copy or transfer control.
 * Inputs/output must be stable, readable/writable as appropriate. */
int rpi5_handoff_plan(const void *image, size_t size, const struct rpi5_handoff_input *input,
    const struct rpi5_range *live, size_t live_count, const char *command,
    size_t command_length, struct rpi5_handoff_plan *out);
#endif
