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

/* Reuse the existing static Apple Libc startup, not the zsh implementation. */
int zsh_main(int argc, char **argv)
{
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
