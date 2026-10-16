/* SPDX-License-Identifier: BSD-2-Clause */
/* Limited allocator-only adapter, 2026-10-12. NOT an IOKit implementation.
 * Compile the unmodified Apple IOPCIRange.cpp and ORIGINAL range declarations,
 * excluding unrelated kernel object classes. Heap/log paths trap if reached.
 * Original Apple files/notices and APPLE_LICENSE remain in the pinned checkout.
 */
#ifndef RPI5_APPLE_RANGE_PRIVATE_ADAPTER_H
#define RPI5_APPLE_RANGE_PRIVATE_ADAPTER_H
#include <stddef.h>
#include <stdint.h>
#ifndef KERNEL
#error This adapter only supports the isolated KERNEL allocator profile
#endif
#undef KERNEL
#include <IOKit/pci/IOPCIConfigurator.h>
#define KERNEL 1

static_assert(sizeof(IOPCIScalar)==8 && sizeof(IOPCIRange)==128, "Pinned LP64 range ABI");
static_assert(offsetof(IOPCIRange,end)==40 && offsetof(IOPCIRange,zero)==48,
              "Pinned range-list sentinel ABI");

extern "C" void rpi5_apple_range_zero(void *, size_t);
extern "C" [[noreturn]] void *rpi5_apple_range_unsupported(void);
extern "C" void rpi5_apple_range_log(const char *, ...);
#define bzero(p,n) rpi5_apple_range_zero((p),(n))
#define IOMallocType(T) static_cast<T *>(rpi5_apple_range_unsupported())
#define IOFreeType(p,T) ((void)(p), (void)rpi5_apple_range_unsupported())
#define panic(s) ((void)(s), (void)rpi5_apple_range_unsupported())
#define assert(condition) ((condition)?(void)0:(void)rpi5_apple_range_unsupported())
#define kprintf(...) rpi5_apple_range_log(__VA_ARGS__)
#endif
