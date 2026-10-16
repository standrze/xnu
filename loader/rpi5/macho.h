/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_MACHO_H
#define RPI5_MACHO_H
#include <stddef.h>
#include <stdint.h>
struct rpi5_macho_commands { uint32_t count, bytes, flags; };
/* Framing only: thin little-endian ARM64/ALL MH_EXECUTE and supported command
 * shapes. Does NOT validate segments, relocations, symbols or load permission.
 * Entire buffer must be readable and stable. Atomic output on failure. */
int rpi5_macho_commands(const void *image, size_t size, struct rpi5_macho_commands *out);
struct rpi5_macho_segment {
    uint64_t vmaddr, vmsize, fileoff, filesize;
    uint32_t maxprot, initprot;
    uint8_t name[16];
};
struct rpi5_macho_segments {
    struct rpi5_macho_segment segment[32];
    uint64_t entry;
    uint32_t count;
};
/* Segment/section bounds and file-backed executable entry only. Symbols and
 * relocations still require validation before loading. Atomic output. */
int rpi5_macho_segments(const void *image, size_t size, struct rpi5_macho_segments *out);
/* Validate required symbol tables, bounded strings and no unresolved symbols.
 * Does not validate local relocation records or grant permission to load. */
int rpi5_macho_symbols(const void *image, size_t size);
/* Validate local unsigned 64-bit absolute relocation sites for zero virtual
 * slide. No pointer adjustment or load writes. Scratch is caller-owned uint32
 * storage, power-of-two capacity >= twice relocation count; may be overwritten
 * on failure. Scratch must not overlap the image. Output count is atomic. */
int rpi5_macho_relocations(const void *image, size_t size, uint32_t *scratch,
    size_t capacity, uint32_t *out_count);
struct rpi5_macho_placement {
    uint64_t destination[32];
    uint64_t header, end, entry;
    uint32_t count;
};
/* Plan zero-slide destinations inside ONE caller-proven free RAM extent.
 * Does not discover ownership, copy bytes, validate relocations or establish
 * bootstrap mapping coverage/table capacity. Output atomic. */
int rpi5_macho_placement(const void *image, size_t size, uint64_t header_pa,
    uint64_t free_start, uint64_t free_end, struct rpi5_macho_placement *out);
/* Materialize into caller-owned writable memory corresponding to header_pa.
 * Caller must prove exclusive ownership and reserve physical placement plus
 * image/scratch/output separately. All buffers must be disjoint and stable.
 * Validates before destination writes; does not map, synchronize instruction
 * caches, build boot data or transfer control. Zero virtual slide only. */
int rpi5_macho_materialize(const void *image, size_t size, void *destination,
    size_t destination_size, uint64_t header_pa, uint32_t *scratch,
    size_t capacity, struct rpi5_macho_placement *out);
/* Read back the full materialized envelope, including zero-fill, gaps and
 * rounded tail. Stable disjoint readable buffers required. No writes, fixups,
 * ownership discovery or cache synchronization; zero virtual slide only. */
int rpi5_macho_verify_materialized(const void *image, size_t size,
    const volatile void *destination, size_t destination_size, uint64_t header_pa);
#endif
