/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef DARWIN_GPU_RELAY_H
#define DARWIN_GPU_RELAY_H
#include "gpu_client.h"
#include <sys/socket.h>
#include <sys/un.h>
struct gpu_relay {
    int fd, owned, pending;
    uint32_t sequence;
    int64_t deadline;
    struct sockaddr_un peer;
    socklen_t peer_size;
};
int gpu_relay_open(struct gpu_relay *relay);
void gpu_relay_close(struct gpu_relay *relay);
/* One datagram in flight, independent of PTY input/output backpressure. */
int gpu_relay_request(struct gpu_relay *relay, unsigned char payload[256], size_t *size);
int gpu_relay_reply(struct gpu_relay *relay, const unsigned char *payload, size_t size);
int gpu_relay_expired(struct gpu_relay *relay);
#endif
