/* SPDX-License-Identifier: BSD-2-Clause
 * Real candidate/parser; explicit host-only SMC/EL doubles. NO target execution.
 */
#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "psci_restart_candidate.h"

static const void *tree;
static size_t bytes;
static uint64_t el = 4, version = 0x10001, feature, reset_result;
static unsigned queries, features, resets, recurse;
static struct rpi5_restart_once once;
uint64_t rpi5_restart_current_el(void) { return el; }
uint64_t rpi5_restart_psci_version(void) {
    __atomic_add_fetch(&queries, 1, __ATOMIC_RELAXED);
    if (recurse) assert(rpi5_restart_attempt(&once, tree, bytes) == RPI5_RESTART_BUSY);
    return version;
}
uint64_t rpi5_restart_psci_feature(void) { features++; return feature; }
uint64_t rpi5_restart_psci_reset(void) { resets++; return reset_result; }
static void clear(void) {
    once.entered = queries = features = resets = recurse = 0;
    el = 4; version = 0x10001; feature = reset_result = 0;
}
static void *concurrent(void *unused) {
    (void)unused;
    int result = rpi5_restart_attempt(&once, tree, bytes);
    assert(result == RPI5_RESTART_RETURNED || result == RPI5_RESTART_BUSY);
    return NULL;
}
int main(int argc, char **argv) {
    assert(argc == 3);
    FILE *input = fopen(argv[1], "rb"); assert(input);
    assert(!fseek(input, 0, SEEK_END)); long size = ftell(input); assert(size > 0);
    assert(!fseek(input, 0, SEEK_SET)); void *memory = malloc((size_t)size); assert(memory);
    assert(fread(memory, 1, (size_t)size, input) == (size_t)size); assert(!fclose(input));
    tree = memory; bytes = (size_t)size;
    if (!strcmp(argv[2], "reject")) {
        assert(rpi5_restart_attempt(&once, tree, bytes) == RPI5_RESTART_REFUSED);
        assert(!once.entered && !queries && !features && !resets);
        free(memory); puts("RESTART_BINDING_REJECT NO_SMC=1"); return 0;
    }
    assert(!strcmp(argv[2], "accept"));
    for (unsigned i = 0; i < 4; i++) {
        clear(); el = i * 4;
        if (el == 4) continue;
        assert(rpi5_restart_attempt(&once, tree, bytes) == RPI5_RESTART_REFUSED);
        assert(!once.entered && !queries && !features && !resets);
    }
    const uint64_t versions[] = {0, 1, 0x10000, 0x10002, 0x20000, UINT64_MAX};
    for (unsigned i = 0; i < sizeof(versions)/sizeof(*versions); i++) {
        clear(); version = versions[i];
        assert(rpi5_restart_attempt(&once, tree, bytes) == RPI5_RESTART_VERSION);
        assert(once.entered == 1 && queries == 1 && !features && !resets);
        version = 0x10001;
        assert(rpi5_restart_attempt(&once, tree, bytes) == RPI5_RESTART_BUSY);
        assert(queries == 1);
    }
    const uint64_t errors[] = {1, UINT32_MAX, UINT64_MAX, UINT64_MAX-1, UINT64_MAX-2};
    for (unsigned i = 0; i < sizeof(errors)/sizeof(*errors); i++) {
        clear(); feature = errors[i];
        assert(rpi5_restart_attempt(&once, tree, bytes) == RPI5_RESTART_UNSUPPORTED);
        assert(queries == 1 && features == 1 && !resets);
        feature = 0;
        assert(rpi5_restart_attempt(&once, tree, bytes) == RPI5_RESTART_BUSY);
    }
    for (unsigned i = 0; i < 3; i++) {
        clear(); recurse = 1; reset_result = i == 0 ? 0 : i == 1 ? UINT64_MAX : 1;
        assert(rpi5_restart_attempt(&once, tree, bytes) == RPI5_RESTART_RETURNED);
        assert(queries == 1 && features == 1 && resets == 1);
        assert(rpi5_restart_attempt(&once, tree, bytes) == RPI5_RESTART_BUSY);
        assert(resets == 1);
    }
    clear(); pthread_t threads[16];
    for (unsigned i = 0; i < 16; i++) assert(!pthread_create(&threads[i], NULL, concurrent, NULL));
    for (unsigned i = 0; i < 16; i++) assert(!pthread_join(threads[i], NULL));
    assert(queries == 1 && features == 1 && resets == 1 && once.entered == 1);
    clear();
    assert(rpi5_restart_attempt(NULL, tree, bytes) == RPI5_RESTART_REFUSED);
    assert(rpi5_restart_attempt(&once, NULL, bytes) == RPI5_RESTART_REFUSED);
    assert(rpi5_restart_attempt(&once, tree, SIZE_MAX) == RPI5_RESTART_REFUSED);
    assert(rpi5_restart_attempt((struct rpi5_restart_once *)memory, tree, bytes) == RPI5_RESTART_REFUSED);
    assert(rpi5_restart_attempt(&once, (void *)(UINTPTR_MAX-15), 40) == RPI5_RESTART_REFUSED);
    assert(!queries && !features && !resets && !once.entered);
    free(memory);
    puts("RESTART_POLICY PASS EL_BINDING VERSION FEATURES RETURNED_REJECT ONCE16 REENTRY NO_HARDWARE");
    return 0;
}
