/* SPDX-License-Identifier: BSD-2-Clause
 * Bounded project DHCP orchestration using original Apple bootp wire, BPF,
 * checksum, packet-match and IPv4 interface routines. Not Apple's daemon:
 * no configd, CF run loop, lease renewal or mDNS service is impersonated.
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <ifaddrs.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <net/if.h>
#include <net/if_dl.h>
#include <net/if_arp.h>
#include <net/route.h>
#include <netinet/in.h>
#include <netinet/bootp.h>
#include <arpa/inet.h>
#include <dhcp.h>
#include <dhcplib.h>
#include <dhcp_options.h>
#include <bootp_transmit.h>
#include <ifutil.h>
#include "../runtime/bootp_guard.h"

struct lease {
    struct in_addr ip, mask, router, dns, server;
    uint32_t seconds;
};

static int identity(unsigned char mac[6], unsigned int *index)
{
    struct ifaddrs *list;
    if (getifaddrs(&list)) return -1;
    int found = 0;
    for (struct ifaddrs *i = list; i; i = i->ifa_next) {
        if (!i->ifa_addr || strcmp(i->ifa_name, "en0") || i->ifa_addr->sa_family != AF_LINK) continue;
        struct sockaddr_dl *dl = (struct sockaddr_dl *)i->ifa_addr;
        if (dl->sdl_alen != 6 || dl->sdl_len < 8 + dl->sdl_nlen + 6 || !dl->sdl_index) continue;
        memcpy(mac, LLADDR(dl), 6);
        *index = dl->sdl_index;
        found = 1;
        break;
    }
    freeifaddrs(list);
    return found ? 0 : -1;
}

static int option(dhcpol_t *options, unsigned int tag, void *value, int width, int list)
{
    int size = 0;
    void *bytes = dhcpol_find(options, tag, &size, NULL);
    if (!bytes || size < width || (!list && size != width) || (list && size % width)) return -1;
    memcpy(value, bytes, width);
    return 0;
}

static int accept_reply(unsigned char *bytes, size_t size, uint32_t xid,
                        const unsigned char mac[6], unsigned int type, struct lease *lease)
{
    if (!darwin_dhcp_options_safe(bytes, size) ||
        !dhcp_packet_match((struct bootp *)bytes, xid, ARPHRD_ETHER, (void *)mac, 6)) return 0;
    dhcpol_t options;
    if (!dhcpol_parse_packet(&options, (struct dhcp *)bytes, (int)size, NULL)) return 0;
    unsigned char message_type = 0;
    struct lease candidate = {.ip = ((struct dhcp *)bytes)->dp_yiaddr};
    int valid = !option(&options, 53, &message_type, 1, 0) && message_type == type &&
        !option(&options, 54, &candidate.server, 4, 0) && candidate.ip.s_addr && candidate.server.s_addr;
    if (valid && type == DHCPACK) {
        valid = candidate.ip.s_addr == lease->ip.s_addr && candidate.server.s_addr == lease->server.s_addr &&
            !option(&options, 1, &candidate.mask, 4, 0) && !option(&options, 3, &candidate.router, 4, 1) &&
            !option(&options, 6, &candidate.dns, 4, 1) && !option(&options, 51, &candidate.seconds, 4, 0);
        candidate.seconds = ntohl(candidate.seconds);
        uint32_t mask = ntohl(candidate.mask.s_addr);
        valid = valid && mask && !(~mask & (~mask + 1)) && candidate.seconds &&
            candidate.router.s_addr && candidate.dns.s_addr &&
            (candidate.router.s_addr & candidate.mask.s_addr) == (candidate.ip.s_addr & candidate.mask.s_addr);
    }
    dhcpol_free(&options);
    if (valid) *lease = candidate;
    return valid;
}

/* Explicit project routing adapter; Apple route(8) is a separate import. */
static int default_route(struct in_addr gateway)
{
    struct { struct rt_msghdr header; struct sockaddr_in dst, gateway, mask; } request = {0};
    request.header.rtm_msglen = sizeof(request);
    request.header.rtm_version = RTM_VERSION;
    request.header.rtm_type = RTM_ADD;
    request.header.rtm_flags = RTF_UP | RTF_GATEWAY | RTF_STATIC;
    request.header.rtm_addrs = RTA_DST | RTA_GATEWAY | RTA_NETMASK;
    request.header.rtm_pid = getpid();
    request.header.rtm_seq = (int)(arc4random() & 0x7fffffff);
    request.dst.sin_len = request.gateway.sin_len = request.mask.sin_len = sizeof(struct sockaddr_in);
    request.dst.sin_family = request.gateway.sin_family = request.mask.sin_family = AF_INET;
    request.gateway.sin_addr = gateway;
    int fd = socket(PF_ROUTE, SOCK_RAW, 0);
    if (fd < 0) return -1;
    struct timeval timeout = {2, 0};
    int result = -1;
    if (setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) ||
        write(fd, &request, sizeof(request)) != sizeof(request)) goto done;
    for (int i = 0; i < 8; i++) {
        unsigned char reply[4096];
        ssize_t size = read(fd, reply, sizeof(reply));
        if (size < (ssize_t)sizeof(struct rt_msghdr)) break;
        struct rt_msghdr header;
        memcpy(&header, reply, sizeof(header));
        if (header.rtm_version == RTM_VERSION && header.rtm_pid == request.header.rtm_pid &&
            header.rtm_seq == request.header.rtm_seq && header.rtm_type == RTM_ADD) {
            result = header.rtm_errno ? -1 : 0;
            if (header.rtm_errno) errno = header.rtm_errno;
            break;
        }
    }
done:
    close(fd);
    return result;
}

int zsh_main(int argc, char **argv)
{
    (void)argv;
    if (argc != 1) { fprintf(stderr, "usage: dhcpctl (bounded en0 bootstrap, not ipconfigd)\n"); return 2; }
    unsigned char mac[6];
    unsigned int index;
    if (identity(mac, &index)) { fprintf(stderr, "Apple getifaddrs: en0 missing\n"); return 1; }
    int attached = inet_attach_interface("en0");
    if ((attached && attached != EEXIST) || inet_set_autoaddr("en0", 1)) return 1;
    int fd = inet_dgram_socket(), result = 1, autoaddr = 1;
    if (fd < 0) goto done;
    struct timeval timeout = {2, 0};
    int yes = 1;
    struct sockaddr_in local = {.sin_len = sizeof(local), .sin_family = AF_INET, .sin_port = htons(68)};
    if (setsockopt(fd, SOL_SOCKET, SO_BROADCAST, &yes, sizeof(yes)) ||
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) ||
        setsockopt(fd, IPPROTO_IP, IP_BOUND_IF, &index, sizeof(index)) ||
        bind(fd, (struct sockaddr *)&local, sizeof(local))) goto done;
    _Alignas(16) unsigned char packet[576] = {0}, response[4096], frame[1024];
    struct dhcp *request = (struct dhcp *)packet;
    request->dp_op = BOOTREQUEST; request->dp_htype = ARPHRD_ETHER; request->dp_hlen = 6;
    uint32_t xid = arc4random();
    request->dp_xid = htonl(xid);
    request->dp_flags = htons(0x8000);
    memcpy(request->dp_chaddr, mac, 6);
    static const unsigned char cookie[] = {99, 130, 83, 99};
    memcpy(packet + sizeof(*request), cookie, sizeof(cookie));
    struct lease lease = {0};
    for (unsigned int stage = 0; stage < 2; stage++) {
        dhcpoa_t options;
        unsigned char client[7] = {ARPHRD_ETHER}, wanted[] = {1, 3, 6, 51};
        memcpy(client + 1, mac, 6);
        dhcpoa_init(&options, packet + 240, sizeof(packet) - 240);
        if (dhcpoa_add_dhcpmsg(&options, stage ? DHCPREQUEST : DHCPDISCOVER) != dhcpoa_success_e ||
            dhcpoa_add(&options, 61, sizeof(client), client) != dhcpoa_success_e ||
            (stage && (dhcpoa_add(&options, 50, 4, &lease.ip) != dhcpoa_success_e ||
                       dhcpoa_add(&options, 54, 4, &lease.server) != dhcpoa_success_e)) ||
            dhcpoa_add(&options, 55, sizeof(wanted), wanted) != dhcpoa_success_e ||
            dhcpoa_add(&options, 255, 0, NULL) != dhcpoa_success_e) goto done;
        int length = 240 + dhcpoa_used(&options), accepted = 0;
        if (length < 300) length = 300;
        for (int attempt = 0; attempt < 3 && !accepted; attempt++) {
            struct in_addr broadcast = {.s_addr = INADDR_BROADCAST}, zero = {0};
            if (bootp_transmit(fd, frame, "en0", ARPHRD_ETHER, NULL, 6, broadcast, zero,
                               67, 68, packet, length) < 0) goto done;
            for (int receive = 0; receive < 4; receive++) {
                struct sockaddr_in from;
                socklen_t from_size = sizeof(from);
                ssize_t size = recvfrom(fd, response, sizeof(response), 0, (struct sockaddr *)&from, &from_size);
                if (size < 0) break;
                if (from.sin_family != AF_INET || from.sin_port != htons(67)) continue;
                if (accept_reply(response, (size_t)size, xid, mac, stage ? DHCPACK : DHCPOFFER, &lease)) {
                    accepted = 1; break;
                }
            }
        }
        if (!accepted) { fprintf(stderr, "Apple wire DHCP: %s timeout\n", stage ? "ACK" : "OFFER"); goto done; }
    }
    struct in_addr broadcast = {.s_addr = lease.ip.s_addr | ~lease.mask.s_addr};
    if (inet_aifaddr(fd, "en0", lease.ip, &lease.mask, &broadcast) || default_route(lease.router) ||
        inet_set_autoaddr("en0", 0)) goto done;
    autoaddr = 0;
    char ip[INET_ADDRSTRLEN], mask[INET_ADDRSTRLEN], router[INET_ADDRSTRLEN], dns[INET_ADDRSTRLEN];
    if (!inet_ntop(AF_INET, &lease.ip, ip, sizeof(ip)) || !inet_ntop(AF_INET, &lease.mask, mask, sizeof(mask)) ||
        !inet_ntop(AF_INET, &lease.router, router, sizeof(router)) || !inet_ntop(AF_INET, &lease.dns, dns, sizeof(dns))) goto done;
    FILE *configuration = fopen("/data/resolv.conf", "w");
    if (!configuration) goto done;
    int written = fprintf(configuration, "nameserver %s\n", dns);
    int closed = fclose(configuration);
    if (written < 0 || closed) goto done;
    printf("DARWIN:NET:APPLE_BOOTP bootp-268.1 options match BPF checksum IPv4\n");
    printf("DARWIN:NET:DHCP IP=%s MASK=%s ROUTER=%s DNS=%s LEASE=%u\n", ip, mask, router, dns, lease.seconds);
    result = 0;
done:
    if (autoaddr) (void)inet_set_autoaddr("en0", 0);
    if (fd >= 0) close(fd);
    if (result) fprintf(stderr, "dhcpctl: failed errno=%d\n", errno);
    return result;
}
