/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_ccrng.h"
#include <corecrypto/cc_error.h>
#include <stdint.h>
#if defined(KERNEL)
#include <sys/random.h>
#else
/* Host harness supplies this service; never a second RNG implementation. */
extern void read_random(void *, unsigned int);
#endif

static int generate(struct ccrng_state *, size_t, void *);
static struct ccrng_state state = { .generate = generate };

static int
generate(struct ccrng_state *rng, size_t length, void *output)
{
    uintptr_t start = (uintptr_t)output;
    uintptr_t token = (uintptr_t)&state;
    if (rng != &state || (length && !output) || length > UINTPTR_MAX - start ||
        (length && start < token + sizeof(state) && token < start + length)) {
        return CCERR_PARAMETER;
    }
    unsigned char *cursor = output;
    while (length) {
        /* Match XNU's provider request ceiling and avoid size_t narrowing.
         * read_random owns readiness checks, refresh and CPU selection.
         * Its fail-closed panic is intentionally not converted to success. */
        unsigned int chunk = length > 256 ? 256 : (unsigned int)length;
        read_random(cursor, chunk);
        cursor += chunk;
        length -= chunk;
    }
    return 0;
}

struct ccrng_state *
rpi5_ccrng(int *error)
{
    if (error) {
        *error = 0;
    }
    return &state;
}
