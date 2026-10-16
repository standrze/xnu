/* SPDX-License-Identifier: BSD-2-Clause
 * Project shared-compute API, not Apple's Metal ABI. All vectors are copied.
 */
#ifndef DARWIN_GPU_CLIENT_H
#define DARWIN_GPU_CLIENT_H
#include <stddef.h>
#include <stdint.h>
#define GPU_VECTOR_MAX 16
#define GPU_SOCKET_PATH "/data/.darwin-gpu.sock"
/* Status: 0 success; 1 unsupported; 2 invalid; 3 unavailable; 4 quota;
 * 5 execution failure. Negative values are local transport -errno/errors.
 * On failure the caller's output is unchanged. No CPU fallback. */
int gpu_client_add(const float *a, const float *b, size_t count, float *result);
int gpu_main(int argc, char **argv);
static inline uint32_t gpu_word(const unsigned char *p)
{ return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3]; }
static inline void gpu_set_word(unsigned char *p, uint32_t n)
{ p[0]=(unsigned char)(n>>24); p[1]=(unsigned char)(n>>16); p[2]=(unsigned char)(n>>8); p[3]=(unsigned char)n; }
#endif
