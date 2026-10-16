/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_CONTAINER_H
#define RPI5_CONTAINER_H
#include <stddef.h>
#include <stdint.h>
struct rpi5_payload { uint64_t offset, length; };
struct rpi5_container { struct rpi5_payload kernel, init; uint32_t count; };
/* Version 1 integrity container, not a signed/authenticated boot format.
 * Complete stable readable buffer required. Atomic output; no copying/boot. */
int rpi5_container_parse(const void *buffer, size_t size, struct rpi5_container *out);
#endif
