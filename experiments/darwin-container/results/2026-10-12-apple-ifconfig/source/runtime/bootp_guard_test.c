/* SPDX-License-Identifier: BSD-2-Clause
 * Focused native bounds checks only; not DHCP or guest execution evidence.
 */
#include "bootp_guard.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void check(const unsigned char *packet, size_t size, int expected)
{
    /* Exact allocation makes ASan detect reads past truncated packets. */
    unsigned char *copy = malloc(size ? size : 1);
    assert(copy);
    memcpy(copy, packet, size);
    assert(darwin_dhcp_options_safe(copy, size) == expected);
    free(copy);
}

int main(void)
{
    unsigned char packet[640] = {0};
    const unsigned char cookie[] = {99, 130, 83, 99};
    memcpy(packet + 236, cookie, 4);
    packet[240] = 53; packet[241] = 1; packet[242] = 2; packet[243] = 255;
    assert(!darwin_dhcp_options_safe(NULL, 244));
    for (size_t size = 0; size < 244; size++) check(packet, size, 0);
    check(packet, 244, 1);
    packet[243] = 1; check(packet, 244, 0); /* dangling tag */
    packet[244] = 4; check(packet, 245, 0); /* truncated payload */
    packet[240] = 52; packet[241] = 1; packet[242] = 3; packet[243] = 255;
    packet[108] = packet[44] = 255;
    check(packet, 244, 1);
    packet[107] = 1; packet[44] = 0;
    check(packet, 244, 0); /* sname has no end; last byte is a tag */
    packet[44] = 255; packet[108] = 52; packet[109] = 1; packet[110] = 1; packet[111] = 255;
    check(packet, 244, 0); /* nested overload is rejected */
    packet[108] = 255; packet[242] = 4;
    check(packet, 244, 0); /* invalid overload flags */
    packet[242] = 1; packet[243] = 52; packet[244] = 1; packet[245] = 1; packet[246] = 255;
    check(packet, 247, 0); /* duplicate overload */
    for (size_t i = 240; i < 627; i += 3) {
        packet[i] = 1; packet[i + 1] = 1; packet[i + 2] = 0;
    }
    packet[627] = 255;
    check(packet, 628, 0); /* 129 options exceeds the combined bound */
    packet[624] = 255; check(packet, 625, 1); /* exactly 128 options */
    puts("DHCP_TLV_GUARD_OK truncation overload option-bound (ASan host check)");
    return 0;
}
