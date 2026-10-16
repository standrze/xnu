/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_HASH_H
#define RPI5_HASH_H
#include <stddef.h>
#include <stdint.h>
/* Unkeyed payload integrity only, not authenticity or entropy generation.
 * Readable stable input; writable 32-byte output. Empty input may be NULL. */
int rpi5_sha256(const void *data, size_t length, uint8_t output[32]);
/* Optional diagnostic observer; default is a no-op. Receives counts only,
 * never bytes or digest. Must not mutate input/output or re-enter hashing. */
void rpi5_hash_progress(size_t completed, size_t total);
#endif
