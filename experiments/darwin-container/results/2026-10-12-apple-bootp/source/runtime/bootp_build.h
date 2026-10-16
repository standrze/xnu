/* SPDX-License-Identifier: BSD-2-Clause
 * Explicit static IPv4 build boundary. Selected routines need no CF runtime.
 * Redirect only their C-format diagnostic messages to the guest's real stdio;
 * discarded CF property-list, printing and service functions remain unlinked.
 */
#ifndef DARWIN_BOOTP_BUILD_H
#define DARWIN_BOOTP_BUILD_H
#include <stdio.h>
#include <syslog.h>
#include <sys/ioctl.h>
#include <net/if.h>
#define _S_IPCONFIGURATIONLOG_H
#define IPConfigLog(level, format, ...) ((void)(level), (void)fprintf(stderr, format "\n", ##__VA_ARGS__))
#define IPConfigLogFL(level, format, ...) IPConfigLog(level, format, ##__VA_ARGS__)
/* Exact ioctl numbers/types from this XNU's bsd/sys/sockio_private.h. */
#ifndef SIOCPROTOATTACH
#define SIOCPROTOATTACH _IOWR('i', 80, struct ifreq)
#define SIOCPROTODETACH _IOWR('i', 81, struct ifreq)
#endif
#endif
