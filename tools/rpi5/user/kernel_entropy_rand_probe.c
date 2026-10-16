/* SPDX-License-Identifier: BSD-2-Clause
 * Future API diagnostic only. No live key creation, output, or quality test.
 */
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <openssl/rand.h>

extern int rpi5_packet_pthread_prerequisite(int, char **);

static void erase(void *buffer, size_t size)
{
    volatile unsigned char *cursor = buffer;
    while (size--) *cursor++ = 0;
}

int rpi5_pthread_smoke_main(int argc, char **argv)
{
    int status = rpi5_packet_pthread_prerequisite(argc, argv);
    if (status) return status;
    unsigned char buffer[1024];
    const int lengths[] = {0, 1, 256, 257, 1024};
    arc4random_buf(NULL, 0);
    for (unsigned i = 0; i < sizeof(lengths) / sizeof(lengths[0]); i++) {
        int result = RAND_bytes(buffer, lengths[i]);
        erase(buffer, sizeof(buffer));
        if (result != 1) return 30 + (int)i;
    }
    puts("RPI5XNU:RAND:API_OK REQUESTS=5 KERNEL_GETENTROPY_ADAPTER NO_RANDOM_OUTPUT QUALITY_NOT_PROVEN");
    return 0;
}
