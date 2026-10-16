# SPDX-License-Identifier: BSD-2-Clause
"""Compose an in-memory, zero-slide handoff plan. Never writes a boot medium."""
from audit_macho import inspect
from boot_args import SIZE, encode_with_physical_tree
from bootstrap_layout import LINK_BASE, PAGE, validate
from apple_dt import encode as encode_tree


def prepare_with_tree(kernel, *, device_tree, **placement):
    """Compose an encoded tree and handoff, deriving length from exact bytes.

    This enforces encoding/allocation consistency, not hardware properties.
    """
    if "device_tree_length" in placement:
        raise ValueError("tree length is derived from encoded bytes")
    tree = encode_tree(device_tree)
    plan = prepare(kernel, device_tree_length=len(tree), **placement)
    plan["device_tree"] = tree
    plan["boot_data_writes"] = [
        {"physical_address": placement["device_tree_pa"], "data": tree},
        {"physical_address": placement["boot_args_pa"], "data": plan["boot_args"]},
    ]
    return plan


def prepare(kernel, *, header_pa, phys_base, mem_size, mem_size_actual,
            ram, reserved, boot_args_pa, device_tree_pa, device_tree_length,
            live_allocations, command_line):
    """Return copy/zero operations and serialized boot arguments, without executing.

    live_allocations maps names to physical half-open ranges (loader code,
    stacks, init image, etc.). Caller must supply all still-live allocations.
    The device tree bytes, firmware provenance and runtime entropy are outside
    this host planner and remain mandatory before a real handoff.
    """
    image = inspect(kernel)
    if image["virtual_base"] != LINK_BASE or image["segments"][0]["fileoff"] != 0:
        raise ValueError("kernel does not match initial linked-header contract")
    if image["flags"] & (1 << 31):
        raise ValueError("kernel collection flag unsupported")
    if any(s["size"] for segment in image["segments"] for s in segment["sections"]
           if s["name"] == "__thread_starts"):
        raise ValueError("threaded fixups require separate loader contract")
    for value in (header_pa, phys_base, mem_size, mem_size_actual, boot_args_pa,
                  device_tree_pa, device_tree_length):
        if type(value) is not int or value < 0:
            raise ValueError("invalid physical placement")
    if not 0 < mem_size <= mem_size_actual <= 1 << 40:
        raise ValueError("invalid actual memory size")
    if boot_args_pa % 8 or device_tree_length == 0:
        raise ValueError("unaligned boot arguments or empty tree")
    if not isinstance(live_allocations, dict) or not live_allocations:
        raise ValueError("explicit live loader allocations required")
    allocations = []
    copies, zeros = [], []
    for segment in image["segments"]:
        if not segment["vmsize"]:
            continue
        pa = header_pa + segment["vmaddr"] - LINK_BASE
        allocations.append((pa, pa + segment["vmsize"], "kernel:" + segment["name"]))
        if segment["filesize"]:
            copies.append({"file_offset": segment["fileoff"], "physical_address": pa,
                           "length": segment["filesize"]})
        if segment["zero_fill"]:
            zeros.append({"physical_address": pa + segment["filesize"], "length": segment["zero_fill"]})
    kernel_end = max(end for _, end, _ in allocations)
    allocations.extend([(boot_args_pa, boot_args_pa + SIZE, "boot_args"),
                        (device_tree_pa, device_tree_pa + device_tree_length, "device_tree")])
    for name, pair in live_allocations.items():
        if not isinstance(name, str) or not name or len(pair) != 2:
            raise ValueError("invalid live allocation")
        start, end = pair
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= 1 << 40:
            raise ValueError("invalid live allocation extent")
        allocations.append((start, end, "loader:" + name))
    allocations.sort()
    for previous, following in zip(allocations, allocations[1:]):
        if previous[1] > following[0]:
            raise ValueError(f"allocation overlap: {previous[2]} and {following[2]}")
    if boot_args_pa < kernel_end or device_tree_pa < kernel_end:
        raise ValueError("boot data must follow kernel extent")
    top = (max(end for _, end, _ in allocations) + PAGE - 1) // PAGE * PAGE
    virt_base = LINK_BASE - (header_pa - phys_base)
    mapping = validate(phys_base=phys_base, virt_base=virt_base, mem_size=mem_size,
                       header_pa=header_pa, ram=ram, reserved=reserved,
                       required=[(start, end) for start, end, _ in allocations] + [(top - 1, top)])
    args = encode_with_physical_tree(device_tree_pa=device_tree_pa, kernel_end_pa=kernel_end,
                virt_base=virt_base, phys_base=phys_base, mem_size=mem_size,
                top_of_kernel_data=top, device_tree_length=device_tree_length,
                command_line=command_line, mem_size_actual=mem_size_actual)
    return {"kernel_sha256": image["sha256"], "copy_operations": copies,
            "zero_operations": zeros, "allocations": allocations,
            "entry_pa": header_pa + image["entry"] - LINK_BASE,
            "entry_x0_pa": boot_args_pa, "boot_args": args,
            "top_of_kernel_data": top, "mapping": mapping,
            "scope": "host plan only; source-buffer lifetime, device-tree contents, firmware, CPU state and entropy unverified"}
