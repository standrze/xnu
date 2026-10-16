/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_FREESTANDING_STRING_H
#define RPI5_FREESTANDING_STRING_H
#include <stddef.h>
void *memcpy(void *restrict dst, const void *restrict src, size_t size);
void *memmove(void *dst, const void *src, size_t size);
void *memset(void *dst, int value, size_t size);
int memcmp(const void *a, const void *b, size_t size);
size_t strlen(const char *s);
#endif
