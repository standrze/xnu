/* SPDX-License-Identifier: BSD-2-Clause
 * Project command adapter. Query construction, socket transport, retries,
 * reply validation and wire parsing are original pinned Apple libresolv.
 */
#include <arpa/inet.h>
#include <arpa/nameser.h>
#include <errno.h>
#include <netdb.h>
#include <resolv.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef DARWIN_APPLE_LIBINFO
#include <net/if.h>
#include <ifaddrs.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

extern void darwin_network_nameserver_port(unsigned short);

static int libinfo_trial(int argc, char **argv)
{
    if (argc != 6 || !*argv[3] || strlen(argv[3]) > 253 ||
        !*argv[5] || strlen(argv[5]) > 64) return 2;
    char *end;
    long dns_port = strtol(argv[2], &end, 10);
    if (*end || dns_port < 1 || dns_port > 65535) return 2;
    long tcp_port = strtol(argv[4], &end, 10);
    if (*end || tcp_port < 1 || tcp_port > 65535) return 2;
    darwin_network_nameserver_port((unsigned short)dns_port);
    struct addrinfo hints = {.ai_family = AF_INET, .ai_socktype = SOCK_STREAM,
                            .ai_flags = AI_NUMERICHOST | AI_NUMERICSERV};
    struct addrinfo *entry = NULL;
    /* Original numeric validation and IPv6 packaging, with no DNS query. */
    if (getaddrinfo("192.0.2.1", "80", &hints, &entry) || !entry ||
        entry->ai_family != AF_INET || entry->ai_socktype != SOCK_STREAM ||
        ((struct sockaddr_in *)entry->ai_addr)->sin_port != htons(80)) return 1;
    freeaddrinfo(entry);
    entry = NULL;
    hints.ai_family = AF_INET6;
    if (getaddrinfo("::1", "80", &hints, &entry) || !entry ||
        entry->ai_family != AF_INET6 ||
        !IN6_IS_ADDR_LOOPBACK(&((struct sockaddr_in6 *)entry->ai_addr)->sin6_addr)) return 1;
    freeaddrinfo(entry);
    entry = NULL;
    if (!getaddrinfo("not-a-numeric-address", "80", &hints, &entry) || entry) return 1;
    hints.ai_family = AF_UNIX;
    if (getaddrinfo("127.0.0.1", "80", &hints, &entry) != EAI_FAMILY || entry) return 1;
    unsigned int index = if_nametoindex("en0");
    char name[IF_NAMESIZE];
    if (!index || !if_indextoname(index, name) || strcmp(name, "en0")) {
        fprintf(stderr, "Apple interface lookup failed: %d\n", errno);
        return 1;
    }
    printf("DARWIN:NET:APPLE_LIBINFO_NUMERIC IPv4 IPv6 errors en0=%u\n", index);
    hints.ai_family = AF_INET;
    hints.ai_flags = AI_NUMERICSERV | AI_CANONNAME;
    int error = getaddrinfo(argv[3], argv[4], &hints, &entry);
    if (error || !entry || !entry->ai_canonname || strcmp(entry->ai_canonname, argv[3])) {
        fprintf(stderr, "Apple getaddrinfo failed: error=%d errno=%d\n", error, errno);
        freeaddrinfo(entry);
        return 1;
    }
    char text[INET_ADDRSTRLEN];
    if (!inet_ntop(AF_INET, &((struct sockaddr_in *)entry->ai_addr)->sin_addr, text, sizeof(text))) {
        freeaddrinfo(entry); return 1;
    }
    int fd = socket(entry->ai_family, entry->ai_socktype, entry->ai_protocol);
    struct timeval timeout = {3, 0};
    size_t length = strlen(argv[5]), sent = 0, received = 0;
    char echo[65];
    int ok = fd >= 0 && setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) == 0 &&
        setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout)) == 0 &&
        connect(fd, entry->ai_addr, entry->ai_addrlen) == 0;
    freeaddrinfo(entry);
    while (ok && sent < length) {
        ssize_t count = send(fd, argv[5] + sent, length - sent, 0);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) { ok = 0; break; }
        sent += (size_t)count;
    }
    while (ok && received < length) {
        ssize_t count = recv(fd, echo + received, length - received, 0);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) { ok = 0; break; }
        received += (size_t)count;
    }
    if (fd >= 0) close(fd);
    if (!ok || received != length || memcmp(echo, argv[5], length)) return 1;
    printf("DARWIN:NET:APPLE_GETADDRINFO %s %s Libinfo-542.40.3\n", argv[3], text);
    printf("DARWIN:NET:APPLE_GAI_TCP ECHO=%s\n", argv[5]);
    return 0;
}
#endif

/* Reuse the existing static Apple Libc startup, not the zsh implementation. */
int zsh_main(int argc, char **argv)
{
#ifdef DARWIN_APPLE_LIBINFO
    if (argc > 1 && !strcmp(argv[1], "gai")) return libinfo_trial(argc, argv);
#endif
    if (argc != 4 || (strcmp(argv[1], "udp") && strcmp(argv[1], "tcp"))) {
        fprintf(stderr, "usage: resolverctl udp|tcp PORT NAME\n");
        return 2;
    }
    char *end;
    long port = strtol(argv[2], &end, 10);
    if (*end || port < 1 || port > 65535 || strlen(argv[3]) > 253) return 2;
    struct __res_state state = {0};
    if (res_ninit(&state) != 0 || state.nscount != 1) {
        fprintf(stderr, "resolver init failed: errno=%d servers=%d\n", errno, state.nscount);
        res_ndestroy(&state);
        return 1;
    }
    state.nsaddr_list[0].sin_port = htons((unsigned short)port);
    state.retrans = 2;
    state.retry = 1;
    if (!strcmp(argv[1], "tcp")) state.options |= RES_USEVC;
    unsigned char answer[2048];
    int size = res_nquery(&state, argv[3], ns_c_in, ns_t_a, answer, sizeof(answer));
    if (size < 0) {
        fprintf(stderr, "Apple query failed: errno=%d h_errno=%d\n", errno, state.res_h_errno);
        res_ndestroy(&state);
        return 1;
    }
    ns_msg message;
    ns_rr record;
    char text[INET_ADDRSTRLEN];
    int ok = ns_initparse(answer, size, &message) == 0 && ns_msg_count(message, ns_s_an) == 1 &&
        ns_parserr(&message, ns_s_an, 0, &record) == 0 && ns_rr_type(record) == ns_t_a &&
        ns_rr_class(record) == ns_c_in && ns_rr_rdlen(record) == 4 &&
        inet_ntop(AF_INET, ns_rr_rdata(record), text, sizeof(text)) != NULL;
    if (ok) printf("DARWIN:NET:APPLE_QUERY %s %s %s libresolv-96\n", argv[1], argv[3], text);
    else fprintf(stderr, "Apple answer parse failed\n");
    res_ndestroy(&state);
    return ok ? 0 : 1;
}
