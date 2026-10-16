/* SPDX-License-Identifier: BSD-2-Clause */
#include "Block_private.h"
#include <pthread.h>
#include <stdio.h>
#include <string.h>

static int (^global_block)(int) = ^(int n) { return n + 7; };

static int (^make_counter(int initial))(int)
{
    __block int count = initial;
    int (^stack)(int) = ^(int n) { count += n; return count; };
    return Block_copy(stack);
}

static void *retain_worker(void *context)
{
    int (^block)(int) = context;
    for (unsigned i = 0; i < 1024; i++) {
        int (^copy)(int) = Block_copy(block);
        if (copy != block || copy(3) != 14) return (void *)1;
        Block_release(copy);
    }
    return NULL;
}

int main(void)
{
    if (_Block_copy(NULL) != NULL) return 1;
    _Block_release(NULL);
    int (^global_copy)(int) = Block_copy(global_block);
    if (global_copy != global_block || global_copy(3) != 10) return 2;
    Block_release(global_copy);
    int captured = 11;
    int (^stack)(int) = ^(int n) { return captured + n; };
    int (^heap)(int) = Block_copy(stack);
    if (heap == stack || heap(3) != 14 ||
        ((struct Block_layout *)heap)->isa != _NSConcreteMallocBlock ||
        Block_size(heap) != ((struct Block_layout *)stack)->descriptor->size) return 3;
    int (^second)(int) = Block_copy(heap);
    if (second != heap) return 4;
    Block_release(second);
    int (^counter)(int) = make_counter(10);
    if (counter(1) != 11 || counter(2) != 13) return 5;
    int (^counter_copy)(int) = Block_copy(counter);
    Block_release(counter);
    if (counter_copy(3) != 16) return 6;
    Block_release(counter_copy);
    int (^inner)(int) = Block_copy(stack);
    int (^outer)(int) = Block_copy(^(int n) { return inner(n) + 1; });
    Block_release(inner);
    if (outer(2) != 14) return 7;
    Block_release(outer);
    pthread_t threads[4];
    for (unsigned i = 0; i < 4; i++)
        if (pthread_create(&threads[i], NULL, retain_worker, heap)) return 8;
    for (unsigned i = 0; i < 4; i++) {
        void *result;
        if (pthread_join(threads[i], &result) || result) return 9;
    }
    Block_release(heap);
    puts("APPLE_BLOCKS_RUNTIME PASS GLOBAL=1 STACK_HEAP=1 BYREF_ESCAPE=1 NESTED=1 NULL=2 RETAIN_THREADS=4 RETAINS=4096");
    return 0;
}
