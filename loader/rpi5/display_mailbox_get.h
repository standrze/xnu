/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_DISPLAY_MAILBOX_GET_H
#define RPI5_DISPLAY_MAILBOX_GET_H
#include <stddef.h>
#include <stdint.h>

enum rpi5_display_get_kind {
    RPI5_DISPLAY_GET_COUNT = 1,
    RPI5_DISPLAY_GET_SETTINGS = 2
};
#define RPI5_DISPLAY_GET_MAX_DISPLAYS 2u
#define RPI5_DISPLAY_GET_MAX_BYTES 88u
#define RPI5_DISPLAY_GET_ALIGNMENT 16u

/* Only raw property payload words. In particular words[9..15] are NOT a
 * decoded native-C structure, physical address, allocation extent or format.
 * No reply, even repeated equal replies, establishes scanout or ownership. */
struct rpi5_display_get_reply {
    uint32_t kind, display_index, word_count;
    uint32_t words[16];
};

/* Pure single-tag framing; no MMIO, cache operation, allocation or transport.
 * COUNT requires reported_count=index=0. SETTINGS requires a caller-supplied
 * validated count in [1,2] and index<count. This restricts enumeration to the
 * two permitted indices; a transport must separately enforce at most one
 * COUNT and two SETTINGS transactions, serialization, freshness and deadline.
 * Wire storage must be valid/readable/writable and 16-byte aligned. That is a
 * CPU-buffer condition, NOT proof of the physical mailbox address/alignment,
 * DMA visibility or coherence. Written bytes are exactly 28 or 88; tail bytes
 * are untouched. wire and written must not overlap. Outputs unchanged on
 * every failure. Unknown operations (including ALLOCATE 0x40001) are refused. */
int rpi5_display_get_request(uint32_t kind, uint32_t reported_count,
    uint32_t index, void *wire, size_t capacity, size_t *written);

/* Validate against the exact request identity supplied by the caller, not
 * against a tag chosen by the response. Exact global success, total length,
 * tag id/capacity/response length and end tag are required. COUNT rejects a
 * reply count above 2; SETTINGS preserves exactly 16 raw words and requires
 * its first word to match index. No field is interpreted as framebuffer
 * format/address/size. response length is the exact wire extent, not rounded
 * backing capacity. Aligned response and out must not overlap. Atomically
 * publishes on success. The caller must match the actual channel+buffer reply,
 * retain the original request identity, and reject stale or unsolicited data. */
int rpi5_display_get_response(uint32_t kind, uint32_t reported_count,
    uint32_t index, const void *wire, size_t length,
    struct rpi5_display_get_reply *out);
#endif
