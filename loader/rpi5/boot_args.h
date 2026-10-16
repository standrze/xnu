/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_BOOT_ARGS_H
#define RPI5_BOOT_ARGS_H
#include <stddef.h>
#include <stdint.h>
#define RPI5_BOOT_ARGS_SIZE 1152
struct rpi5_boot_args_input {
    uint64_t virt_base, phys_base, mem_size, top, tree_pa, kernel_end, mem_actual;
    uint32_t tree_length;
};
/* Headless revision/version 2 ABI. Derives initial tree KVA from physical
 * allocation, requiring tree after kernel and within top reservation. Command
 * is counted ASCII without NUL, max 1023 bytes. Caller separately validates
 * bootstrap coverage and ownership of arguments/tree/all boot allocations.
 * Output untouched on failure, written only after all inputs are consumed. */
int rpi5_boot_args_encode(const struct rpi5_boot_args_input *input,
    const char *command, size_t length, void *output, size_t capacity);
#endif
