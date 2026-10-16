/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_DISPLAY_ALLOCATE_WIRE_H
#define RPI5_DISPLAY_ALLOCATE_WIRE_H
#include <stddef.h>
#include <stdint.h>
#define RPI5_DISPLAY_ALLOCATE_MAX_BYTES 240u
#define RPI5_DISPLAY_ALLOCATE_MESSAGES 4u
enum rpi5_display_allocate_message {
    RPI5_DISPLAY_ALLOCATE_PREFLIGHT=1, RPI5_DISPLAY_ALLOCATE_SELECT,
    RPI5_DISPLAY_ALLOCATE_SET, RPI5_DISPLAY_ALLOCATE_VERIFY
};
struct rpi5_display_allocate_reply { uint32_t kind,count,words[30]; };
/* Exact one-display 1920x1080,32-bit,BGR,ignored-alpha profile. No generic
 * property interface. PREFLIGHT is COUNT + raw display0 SETTINGS. SELECT is
 * SET_DISPLAY_NUM(0). SET contains fixed geometry/depth/order/alpha/offset/
 * overscan, ALLOCATE(16KiB), GET_PITCH. VERIFY contains GET tags only.
 * RELEASE, arbitrary addresses, palettes, DMA and drawing are absent.
 * All fields are byte-encoded LE, never a native ABI structure. Wire must
 * be16-byte aligned and disjoint from written for its FULL declared capacity.
 * Outputs/tail unchanged on failure; only exact emitted bytes are changed. */
int rpi5_display_allocate_request(uint32_t kind,void *wire,size_t capacity,size_t *written);
/* Framing only: preserve exact raw returned scalar fields, including rejected
 * geometry. No address conversion, mapping, reservation or scanout authority.
 * Exact global success and every tag/response length/end are mandatory. */
int rpi5_display_allocate_response(uint32_t kind,const void *wire,size_t bytes,
    struct rpi5_display_allocate_reply *out);
/* Admission before any stateful TX requires live COUNT=1 and preboot mode
 * already32-bit. Pi5 firmware1904 may lie about runtime SET32; do not use SET
 * to grow a16-bit preboot carveout. Unknown raw SETTINGS tail stays opaque. */
int rpi5_display_allocate_preflight(const struct rpi5_display_allocate_reply *);
/* Compare complete SET acknowledgements and separate GET readback. Does not
 * independently measure scanout or fix firmware1971 alpha behavior. */
int rpi5_display_allocate_consistent(const struct rpi5_display_allocate_reply *,
    const struct rpi5_display_allocate_reply *);
#endif
