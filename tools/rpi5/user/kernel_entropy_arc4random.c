/* SPDX-License-Identifier: BSD-2-Clause
 * Project-owned Darwin API adapter, NOT Apple/corecrypto or a new RNG.
 * Every byte comes from the existing kernel getentropy service. This adapter
 * makes no claim about the kernel's seed quality or readiness for live keys.
 *
 * No user-space generator, mutable global, lock, allocation, TLS cache, or fork
 * hook exists. A fork therefore inherits no adapter RNG state or held lock.
 * Zero length is a no-op (including NULL). For nonzero length, NULL or a
 * wrapping half-open address range is fatal. Other invalid pointers are left
 * to the real syscall's copyout validation. Any syscall failure is fatal, even
 * after earlier chunks succeeded: the void API must never return partial data
 * as success. The caller's buffer is not logged or hashed on either path.
 */
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/random.h>
#include <unistd.h>

static __attribute__((noreturn)) void random_request_failed(void)
{
    /* Keep a real trap if an invalid environment ever returns from syscall 1;
     * a direct call's SDK noreturn annotation would delete that fallback. */
    void (*volatile exit_process)(int) = _exit;
    exit_process(127);
    __builtin_trap();
}

void arc4random_buf(void *buffer, size_t size)
{
    if (size == 0) return;
    if (buffer == NULL || size > UINTPTR_MAX - (uintptr_t)buffer)
        random_request_failed();

    unsigned char *cursor = buffer;
    while (size != 0) {
        size_t chunk = size > 256 ? 256 : size;
        if (getentropy(cursor, chunk) != 0) random_request_failed();
        size -= chunk;
        if (size != 0) cursor += chunk;
    }
}
