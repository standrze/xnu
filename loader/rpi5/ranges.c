/* SPDX-License-Identifier: BSD-2-Clause */
#include "ranges.h"
static int valid(struct rpi5_range r) { return r.start < r.end && r.end <= (1ull << 40); }
int rpi5_ranges_validate_live(const struct rpi5_range *ram, size_t nr,
    const struct rpi5_range *live, size_t nl)
{
    if (!ram || !nr || nr > 32 || !live || !nl || nl > 64) return -1;
    for (size_t i = 0; i < nr; ++i)
        if (!valid(ram[i]) || (i && ram[i-1].end > ram[i].start)) return -1;
    for (size_t i = 0; i < nl; ++i) {
        if (!valid(live[i])) return -1;
        for (size_t j = 0; j < i; ++j)
            if (live[i].start < live[j].end && live[j].start < live[i].end) return -1;
        uint64_t cursor = live[i].start;
        for (size_t j = 0; j < nr && cursor < live[i].end; ++j) {
            if (ram[j].end <= cursor) continue;
            if (ram[j].start > cursor) return -1;
            cursor = ram[j].end < live[i].end ? ram[j].end : live[i].end;
        }
        if (cursor != live[i].end) return -1;
    }
    return 0;
}
int rpi5_ranges_subtract(const struct rpi5_range *ram, size_t nr,
    const struct rpi5_range *excluded, size_t ne, struct rpi5_ranges *out)
{
    if (!out || !ram || !nr || nr > 32 || ne > 64 || (ne && !excluded)) return -1;
    for (size_t i = 0; i < nr; ++i)
        if (!valid(ram[i]) || (i && ram[i-1].end > ram[i].start)) return -1;
    for (size_t i = 0; i < ne; ++i) if (!valid(excluded[i])) return -1;
    struct rpi5_ranges result = {{{0,0}},0};
    /* Scan exclusion boundaries per RAM extent. This avoids intermediate
     * fragmentation depending on input order; capacity applies to final output. */
    for (size_t i = 0; i < nr; ++i) {
        uint64_t cursor = ram[i].start;
        while (cursor < ram[i].end) {
            uint64_t covered_end = cursor, next = ram[i].end;
            for (size_t j = 0; j < ne; ++j) {
                if (excluded[j].start <= cursor && cursor < excluded[j].end) {
                    if (excluded[j].end > covered_end) covered_end = excluded[j].end;
                } else if (cursor < excluded[j].start && excluded[j].start < next) next = excluded[j].start;
            }
            if (covered_end > cursor) {
                cursor = covered_end < ram[i].end ? covered_end : ram[i].end;
                continue;
            }
            if (result.count == 32) return -1;
            result.extent[result.count++] = (struct rpi5_range){cursor, next};
            cursor = next;
        }
    }
    *out = result;
    return 0;
}

int rpi5_ranges_find(const struct rpi5_ranges *available,
    const struct rpi5_range *windows, size_t nw, uint64_t size,
    uint64_t alignment, struct rpi5_range *out)
{
    if (!available || !out || !windows || !nw || nw > 64 || available->count > 32 ||
        !size || size > (1ull << 40) || !alignment || alignment > (1ull << 40) ||
        (alignment & (alignment - 1))) return -1;
    for (size_t i = 0; i < available->count; ++i)
        if (!valid(available->extent[i]) || (i && available->extent[i-1].end > available->extent[i].start)) return -1;
    for (size_t j = 0; j < nw; ++j) if (!valid(windows[j])) return -1;
    uint64_t best = 1ull << 40;
    for (size_t i = 0; i < available->count; ++i) {
        for (size_t j = 0; j < nw; ++j) {
            uint64_t low = available->extent[i].start > windows[j].start ? available->extent[i].start : windows[j].start;
            uint64_t high = available->extent[i].end < windows[j].end ? available->extent[i].end : windows[j].end;
            if (low >= high) continue;
            /* 40-bit bounds make this addition safe in uint64_t. */
            uint64_t aligned = (low + alignment - 1) & ~(alignment - 1);
            if (aligned < high && size <= high - aligned && aligned < best) best = aligned;
        }
    }
    if (best == (1ull << 40)) return -1;
    *out = (struct rpi5_range){best, best + size};
    return 0;
}
