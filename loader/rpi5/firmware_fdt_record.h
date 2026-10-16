/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_FIRMWARE_FDT_RECORD_H
#define RPI5_FIRMWARE_FDT_RECORD_H
#include <stddef.h>
#include <stdint.h>

#define RPI5_FIRMWARE_FDT_RECORD_BYTES 32
#define RPI5_FIRMWARE_FDT_MAX_BYTES (16u * 1024 * 1024)
struct rpi5_firmware_fdt_span { uint64_t physical, bytes; };
/* XNU returns pre-kernel/boot segments to VM later. Only the retained tail
 * AFTER the complete kernelcache is valid for this long-lived view. */
static inline int rpi5_fdt_retained_tail(const struct rpi5_firmware_fdt_span *span,
    uint64_t kernel_end, uint64_t retained_end)
{
    return !span || !kernel_end || ((kernel_end | retained_end) & UINT64_C(0x3fff)) ||
        kernel_end >= retained_end || retained_end > (UINT64_C(1) << 40) ||
        span->physical < kernel_end || span->physical >= retained_end ||
        span->bytes < 40 || span->bytes > RPI5_FIRMWARE_FDT_MAX_BYTES ||
        span->bytes > retained_end - span->physical;
}
static inline uint64_t rpi5_fdt_record_le64(const uint8_t *p)
{
    uint64_t value = 0;
    for (unsigned i = 0; i < 8; i++) value |= (uint64_t)p[i] << (8 * i);
    return value;
}
static inline int rpi5_fdt_record_encode(uint64_t physical, uint64_t bytes,
    uint8_t out[RPI5_FIRMWARE_FDT_RECORD_BYTES])
{
    static const uint8_t magic[8] = {'R','5','F','D','T','0','1',0};
    if (!out || !physical || (physical & 7) || physical >= (UINT64_C(1) << 40) ||
        bytes < 40 || bytes > RPI5_FIRMWARE_FDT_MAX_BYTES ||
        bytes > (UINT64_C(1) << 40) - physical) return -1;
    for (unsigned i = 0; i < 8; i++) {
        out[i] = magic[i];
        out[8 + i] = (uint8_t)(physical >> (8 * i));
        out[16 + i] = (uint8_t)(bytes >> (8 * i));
        out[24 + i] = 0; /* Reserved flags, not permission/ownership evidence. */
    }
    return 0;
}
/* Geometry only. Caller independently verifies Normal RAM, all live-range
 * exclusions and retention. Unaligned serialized input is permitted. */
static inline int rpi5_fdt_record_decode(const void *record, size_t length,
    uint64_t managed_start, uint64_t managed_bytes, uint64_t retained_end,
    struct rpi5_firmware_fdt_span *out)
{
    static const uint8_t magic[8] = {'R','5','F','D','T','0','1',0};
    if (!record || !out || length != RPI5_FIRMWARE_FDT_RECORD_BYTES ||
        !managed_bytes || managed_start >= (UINT64_C(1) << 40) ||
        managed_bytes > (UINT64_C(1) << 40) - managed_start ||
        ((managed_start | managed_bytes | retained_end) & UINT64_C(0x3fff)) ||
        retained_end <= managed_start || retained_end > managed_start + managed_bytes) return -1;
    const uint8_t *p = (const uint8_t *)record;
    for (unsigned i = 0; i < 8; i++) if (p[i] != magic[i] || p[24 + i]) return -1;
    struct rpi5_firmware_fdt_span result = {rpi5_fdt_record_le64(p + 8), rpi5_fdt_record_le64(p + 16)};
    if (!result.physical || (result.physical & 7) || result.physical < managed_start ||
        result.physical >= retained_end || result.bytes < 40 ||
        result.bytes > RPI5_FIRMWARE_FDT_MAX_BYTES || result.bytes > retained_end - result.physical) return -1;
    *out = result;
    return 0;
}
#endif
