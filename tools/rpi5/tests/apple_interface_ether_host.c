/* SPDX-License-Identifier: BSD-2-Clause */
#include <errno.h>
#include <ifaddrs.h>
#include <limits.h>
#include <net/ethernet.h>
#include <net/if.h>
#include <net/if_dl.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

_Static_assert(sizeof(struct ether_addr) == 6, "Darwin Ethernet octet ABI");
_Static_assert(IF_NAMESIZE == 16, "Darwin interface name bound");
_Static_assert(sizeof(struct ifaddrs) == 56, "Darwin LP64 interface list ABI");
_Static_assert(offsetof(struct ifaddrs, ifa_addr) == 24, "Darwin address pointer ABI");
_Static_assert(offsetof(struct sockaddr, sa_family) == 1, "Darwin family byte ABI");
_Static_assert(offsetof(struct sockaddr_dl, sdl_index) == 2, "Darwin link index ABI");

int main(void)
{
    unsigned cases = 0, interfaces = 0;
    for (unsigned slot = 0; slot < 6; slot++)
        for (unsigned value = 0; value < 256; value++) {
            unsigned char bytes[6] = {0, 1, 0x7f, 0x80, 0xfe, 0xff};
            bytes[slot] = (unsigned char)value;
            char address[32], line[64], hostname[32];
            struct ether_addr parsed;
            snprintf(address, sizeof(address), "%02X:%02X:%02X:%02X:%02X:%02X",
                     bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5]);
            struct ether_addr *ether = fixture_ether_aton(address);
            if (!ether || memcmp(ether->ether_addr_octet, bytes, 6)) return 1;
            char *text = fixture_ether_ntoa(ether);
            if (!text) return 2;
            ether = fixture_ether_aton(text);
            if (!ether || memcmp(ether->ether_addr_octet, bytes, 6)) return 3;
            snprintf(line, sizeof(line), " %s\tfixture-host", address);
            if (fixture_ether_line(line, &parsed, hostname) ||
                memcmp(parsed.ether_addr_octet, bytes, 6) || strcmp(hostname, "fixture-host")) return 4;
            cases++;
        }
    const char *bad[] = {"", "x", "0", "0:1", "0:1:2", "0:1:2:3", "0:1:2:3:4",
                         "0:1:2:3:4:g", "0-1-2-3-4-5", "0:1:2:3::5"};
    for (unsigned i = 0; i < sizeof(bad) / sizeof(bad[0]); i++)
        if (fixture_ether_aton(bad[i])) return 5;
    /* Preserve upstream sscanf semantics: leading space, hex prefix,
       octet narrowing and trailing text are accepted by this original API. */
    struct ether_addr *permissive = fixture_ether_aton(" \t0x100:1ff:2:3:4:5 trailing");
    const unsigned char expected[] = {0, 255, 2, 3, 4, 5};
    if (!permissive || memcmp(permissive->ether_addr_octet, expected, 6)) return 6;
    struct ether_addr parsed; char hostname[32];
    if (!fixture_ether_line("0:1:2:3:4:5", &parsed, hostname)) return 7;

    /* Actual original getifaddrs calls local route sysctl. No DNS, remote
       sockets, service doubles or external network traffic are involved. */
    struct ifaddrs *list = NULL;
    if (fixture_getifaddrs(&list)) return 8;
    for (struct ifaddrs *ifa = list; ifa; ifa = ifa->ifa_next) {
        if (!ifa->ifa_addr || ifa->ifa_addr->sa_family != AF_LINK) continue;
        unsigned index = ((struct sockaddr_dl *)ifa->ifa_addr)->sdl_index;
        char name[IF_NAMESIZE];
        if (fixture_if_nametoindex(ifa->ifa_name) != index) return 9;
        errno = EDOM;
        if (fixture_if_indextoname(index, name) != name || strcmp(name, ifa->ifa_name) || errno) return 10;
        interfaces++;
    }
    fixture_freeifaddrs(list);
    errno = 0;
    if (fixture_if_nametoindex("::invalid::") || errno != ENXIO) return 11;
    errno = 0; char name[IF_NAMESIZE];
    if (fixture_if_indextoname(UINT_MAX, name) || errno != ENXIO) return 12;
    if (cases != 1536 || !interfaces) return 13;
    printf("APPLE_INTERFACES_ETHER PASS MAC_CASES=1536 REJECTED=10 LOCAL_AF_LINK=%u ORIGINAL_GETIFADDRS=1\n", interfaces);
    return 0;
}
