/* SPDX-License-Identifier: BSD-2-Clause
 * Build compatibility for Libinfo-542 against the modern public SDK.
 * These address ranges are specified in si_getaddrinfo.c's original comments.
 * No address classification is replaced with a constant result.
 */
#ifndef DARWIN_LIBINFO_BUILD_H
#define DARWIN_LIBINFO_BUILD_H
#define __APPLE_USE_RFC_3542 1
#include <sys/socket.h>
#include <netinet/in.h>
#include <net/if_dl.h>
#include <fcntl.h>
#include <unistd.h>
#ifndef IN_DS_LITE
#define IN_DS_LITE(a) (((uint32_t)(a) & 0xfffffff8U) == 0xc0000000U)
#endif
#ifndef IN_6TO4_RELAY_ANYCAST
#define IN_6TO4_RELAY_ANYCAST(a) (((uint32_t)(a) & 0xffffff00U) == 0xc0586300U)
#endif
/* Layout from XNU bsd/sys/socket.h and bsd/netinet/in_private.h. */
union sockaddr_in_4_6 {
    struct sockaddr sa;
    struct __sockaddr_header sah;
    struct sockaddr_in sin;
    struct sockaddr_in6 sin6;
};
#endif
