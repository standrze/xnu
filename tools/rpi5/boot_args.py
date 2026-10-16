# SPDX-License-Identifier: BSD-2-Clause
"""Serialize the pinned arm64 boot_args ABI. Does not select address spaces."""
import struct

SIZE = 1152
OFFSETS = {"Revision": 0, "Version": 2, "virtBase": 8, "physBase": 16,
           "memSize": 24, "topOfKernelData": 32, "Video": 40,
           "machineType": 88, "deviceTreeP": 96, "deviceTreeLength": 104,
           "CommandLine": 108, "bootFlags": 1136, "memSizeActual": 1144}


def encode_with_physical_tree(*, device_tree_pa, kernel_end_pa, **arguments):
    """Derive the initial KVA tree pointer for the non-fileset startup path.

    The tree must live after the kernel, inside the topOfKernelData reservation.
    This checks the linear handoff relationship, not bootstrap mapping coverage;
    callers must also pass every allocation through bootstrap_layout.validate.
    """
    if "device_tree_pointer" in arguments:
        raise ValueError("supply physical tree allocation, not a second pointer")
    start = arguments["phys_base"]
    size = arguments["mem_size"]
    top = arguments["top_of_kernel_data"]
    length = arguments["device_tree_length"]
    virtual = arguments["virt_base"]
    for value in (device_tree_pa, kernel_end_pa, start, size, top, length, virtual):
        if type(value) is not int or value < 0:
            raise ValueError("invalid placement value")
    if not (size > 0 and length > 0 and
            start <= kernel_end_pa <= device_tree_pa < device_tree_pa + length <= top <= start + size <= 1 << 40):
        raise ValueError("tree must follow kernel and fit reserved physical RAM")
    if top % (1 << 14) or device_tree_pa % 4:
        raise ValueError("unaligned reservation or device tree")
    pointer = virtual + device_tree_pa - start
    if virtual + size > 1 << 64:
        raise ValueError("linear virtual mapping overflows")
    return encode(device_tree_pointer=pointer, **arguments)


def encode(*, virt_base, phys_base, mem_size, top_of_kernel_data,
           device_tree_pointer, device_tree_length, command_line, mem_size_actual):
    """Encode headless revision-2/version-2 arguments with flags/machineType zero.

    The caller owns mapping/placement validation, including the phase-specific
    device-tree pointer, all reservations, and topOfKernelData coverage. This
    routine validates representation and never invents a runtime pointer/seed.
    """
    values = {"virtBase": virt_base, "physBase": phys_base, "memSize": mem_size,
              "topOfKernelData": top_of_kernel_data, "deviceTreeP": device_tree_pointer,
              "memSizeActual": mem_size_actual}
    for name, value in values.items():
        if type(value) is not int or not 0 < value < 1 << 64:
            # Physical base zero is valid RAM on some layouts.
            if not (name == "physBase" and type(value) is int and value == 0):
                raise ValueError(f"{name} must fit its unsigned 64-bit field")
    if type(device_tree_length) is not int or not 0 < device_tree_length < 1 << 32:
        raise ValueError("device tree length must fit a nonzero uint32")
    if not isinstance(command_line, str) or "\0" in command_line:
        raise ValueError("command line must be a string without embedded NUL")
    command = command_line.encode("ascii")
    if len(command) >= 1024:
        raise ValueError("command line must leave room for its terminator")
    data = bytearray(SIZE)
    struct.pack_into("<HH", data, 0, 2, 2)
    for name, value in values.items():
        struct.pack_into("<Q", data, OFFSETS[name], value)
    struct.pack_into("<I", data, OFFSETS["deviceTreeLength"], device_tree_length)
    data[OFFSETS["CommandLine"]:OFFSETS["CommandLine"] + len(command)] = command
    return bytes(data)
