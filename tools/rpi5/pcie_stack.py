# SPDX-License-Identifier: BSD-2-Clause
"""Conservative reviewed nonrecursive C-frame bound for the opt-in FDT log."""


def check(frames, stack_bytes=0x4000):
    sizes = {}
    for row in frames:
        unit = row["location"].split(":")[0]
        function = row["location"].split(":")[-1]
        key = (unit, function)
        if key in sizes or type(row["bytes"]) is not int or row["bytes"] < 0:
            raise ValueError("ambiguous/invalid PCIe stack evidence")
        sizes[key] = row["bytes"]
    required = {
        ("loader/rpi5/probe_main.c", "probe_el1_main"),
        ("loader/rpi5/pcie_topology.c", "rpi5_pcie_topology_log"),
        ("loader/rpi5/pcie_fdt.c", "rpi5_fdt_pcie_rp1"),
        *[("loader/rpi5/fdt.c", name) for name in
          ("rpi5_fdt_structure", "rpi5_fdt_layout", "rpi5_fdt_property", "rpi5_fdt_phandles")],
        ("loader/rpi5/fdt_reg.c", "rpi5_fdt_reg"),
    }
    if not required.issubset(sizes):
        raise ValueError("missing PCIe diagnostic stack frames")
    selected = {}
    for (unit, name), size in sizes.items():
        include = (unit in ("loader/rpi5/pcie_topology.c", "loader/rpi5/pcie_fdt.c", "loader/rpi5/uart.c") or
                   unit == "loader/rpi5/probe_main.c" and name in ("probe_el1_main", "text", "hex") or
                   unit == "loader/rpi5/fdt.c" and name in (
                       "be32", "be64", "overlap", "equal", "value_equal", "rpi5_fdt_structure",
                       "rpi5_fdt_layout", "rpi5_fdt_property", "rpi5_fdt_phandles") or
                   unit == "loader/rpi5/fdt_reg.c" and name in (
                       "cells", "compatible", "width", "fits", "enabled", "parent", "rpi5_fdt_reg"))
        if include:
            selected[unit + ":" + name] = size
    # Every emitted reachable/helper alternative is counted together, including
    # UART alternatives, instead of assuming mutually exclusive calls overlap.
    # runtime_cpus has returned before the hook: its large frame is not live.
    total = sum(selected.values())
    if total + 512 >= stack_bytes:
        raise ValueError("PCIe topology diagnostic exhausts early stack headroom")
    return {"conservative_bytes": total, "stack_bytes": stack_bytes,
            "required_margin": 512, "minimum_remaining_bytes": stack_bytes - total,
            "frames_bytes": selected,
            "scope": "Reviewed nonrecursive FDT/console C frames; not whole-program or hardware proof"}
