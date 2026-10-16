# SPDX-License-Identifier: BSD-2-Clause
"""Host model of the current 16K start.s bootstrap mappings, not a loader."""
PAGE = 1 << 14
BLOCK = 1 << 25
L1_SPAN = 1 << 36
LINK_BASE = 0xfffffe0007004000


def validate(*, phys_base, virt_base, mem_size, header_pa, ram, reserved, required):
    """Ranges are half-open (start,end). required includes all early boot data.

    ram must describe one explicitly selected contiguous usable extent; reserved
    describes firmware/MMIO holes, not the kernel's own allocations. No defaults
    for these inputs: callers must supply actual board-derived information.
    """
    def check(ok, reason):
        if not ok:
            raise ValueError(reason)

    def interval(pair, limit):
        check(len(pair) == 2, "range must contain start and end")
        a, b = pair
        check(type(a) is int and type(b) is int and 0 <= a < b <= limit,
              "invalid range")
        return a, b

    for value in (phys_base, virt_base, mem_size, header_pa):
        check(type(value) is int and value >= 0, "invalid boot argument")
    check(mem_size > 0 and phys_base + mem_size <= 1 << 40, "physical extent exceeds 40 bits")
    check(virt_base < 1 << 64 and virt_base + mem_size <= 1 << 64, "virtual extent overflow")
    check(phys_base % PAGE == virt_base % PAGE == header_pa % PAGE == 0,
          "unaligned boot base")
    check(phys_base <= header_pa < phys_base + mem_size, "header outside advertised memory")
    delta = header_pa - phys_base
    kva = virt_base + delta
    check(kva == LINK_BASE, "initial contract requires zero virtual slide")
    check(kva % BLOCK == header_pa % BLOCK, "L2 physical/virtual incongruence")
    count = (mem_size - delta) // BLOCK
    check(count > 0, "zero-entry assembly mapping")
    physical_start = header_pa // BLOCK * BLOCK
    physical_end = physical_start + count * BLOCK
    virtual_start = kva // BLOCK * BLOCK
    virtual_end = virtual_start + count * BLOCK
    # One root each and one L2 page for every intersected 64GiB L1 region.
    def tables(start, end):
        return (end - 1) // L1_SPAN - start // L1_SPAN + 1
    pages = 2 + tables(physical_start, physical_end) + tables(virtual_start, virtual_end)
    check(pages <= 4, "mapping exceeds four explicitly cleared bootstrap pages")
    r0, r1 = interval(ram, 1 << 40)
    check(r0 <= phys_base and phys_base + mem_size <= r1, "advertised extent outside usable RAM")
    check(r0 <= physical_start and physical_end <= r1, "rounded mapping outside usable RAM")
    for pair in reserved:
        a, b = interval(pair, 1 << 40)
        check(not (a < phys_base + mem_size and phys_base < b), "reservation in advertised RAM")
        check(not (a < physical_end and physical_start < b), "reservation in rounded mapping")
    check(bool(required), "required boot ranges must be supplied")
    for pair in required:
        a, b = interval(pair, 1 << 40)
        check(phys_base <= a and b <= phys_base + mem_size, "required range outside advertised RAM")
        check(physical_start <= a and b <= physical_end, "required range outside bootstrap mapping")
    return {"physical_mapping": [physical_start, physical_end],
            "virtual_mapping": [virtual_start, virtual_end], "table_pages": pages,
            "l2_entries_per_mapping": count, "adjusted_mem_size": mem_size - delta,
            "unmapped_advertised_tail": [physical_end, phys_base + mem_size],
            "scope": "host arithmetic only; no actual RAM discovery or boot execution"}
