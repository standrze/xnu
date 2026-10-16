/* SPDX-License-Identifier: BSD-2-Clause
 * Three additional vector cases complete the original harness's 16-case label.
 * Preserve the first harness and its receipt rather than silently rewriting it.
 */
#define main preserved_adapter_main
#include "pthread_static_host.c"
#undef main

int main(void)
{
    struct rpi5_process_vectors out;
    uintptr_t empty[] = {0,0,0,0};
    if (rpi5_process_vectors_parse(empty,4,&out) || out.argc != 0 ||
        *out.argv || *out.envp || *out.apple) return 31;
    uintptr_t unterminated[] = {0,0,0,1};
    if (!rpi5_process_vectors_parse(unterminated,4,&out)) return 32;
    uintptr_t two[] = {2,1,2,0,0,0};
    if (rpi5_process_vectors_parse(two,6,&out) || out.argc != 2 ||
        out.argv != (char **)(two+1)) return 33;
    return preserved_adapter_main();
}
