/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_FIRMWARE_FDT_API_H
#define RPI5_FIRMWARE_FDT_API_H
#include <stddef.h>
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Built-in private ABI. Valid only after arm_vm_init; source is retained Normal
 * boot memory. No registry/userland export or physical-access permission.
 * Failure leaves both independent output locations unchanged. */
bool rpi5_firmware_fdt_view(const void **data, size_t *bytes);
#ifdef __cplusplus
}
#endif
#endif
