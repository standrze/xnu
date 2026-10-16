/* SPDX-License-Identifier: BSD-2-Clause
 * Bounds preflight for the historical Apple DHCP parser. Its original
 * parse_buffer reads a TLV length before checking a one-byte trailing tag.
 * Validate all buffers (including overloaded fields) before calling it.
 */
#include "bootp_guard.h"
#include <stdint.h>
#include <string.h>

static int safe_tlvs(const unsigned char *bytes, size_t size, unsigned int *count,
                     unsigned int *overload)
{
    for (size_t i = 0; i < size;) {
        unsigned int tag = bytes[i++];
        if (tag == 255) return 1;
        if (!tag) continue;
        if (i == size || ++*count > 128) return 0;
        size_t length = bytes[i++];
        if (length > size - i) return 0;
        if (tag == 52) {
            if (!overload || *overload || length != 1 || bytes[i] < 1 || bytes[i] > 3) return 0;
            *overload = bytes[i];
        }
        i += length;
    }
    return 0;
}

int darwin_dhcp_options_safe(const void *packet, size_t size)
{
    const unsigned char *bytes = packet;
    static const unsigned char cookie[] = {99, 130, 83, 99};
    if (!bytes || size < 241 || size > 4096 || memcmp(bytes + 236, cookie, 4)) return 0;
    unsigned int overload = 0, count = 0;
    if (!safe_tlvs(bytes + 240, size - 240, &count, &overload)) return 0;
    if ((overload & 1) && !safe_tlvs(bytes + 108, 128, &count, NULL)) return 0;
    if ((overload & 2) && !safe_tlvs(bytes + 44, 64, &count, NULL)) return 0;
    return 1;
}
