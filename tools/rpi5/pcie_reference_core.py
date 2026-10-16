# SPDX-License-Identifier: BSD-2-Clause
"""Fixed, property-allowlisted Linux PCIe reference, never a hardware driver."""
import datetime
import json
from pathlib import Path
import re
import struct
import subprocess
import uuid

HOST = "sandrzej@192.168.4.23"
ROOT_IDENTITY = "/dev/nvme0n1p2 ext4 04570742-280b-43cb-9564-73d454243b1c"
BRIDGE = "/axi/pcie@1000120000"
RP1 = BRIDGE + "/rp1"
GEM = RP1 + "/ethernet@100000"
SOC = "/soc@107c000000"
COMMON = ("compatible", "status", "phandle", "linux,phandle")
# Missing properties are recorded as None, not invented defaults. In particular
# retain IRQ overrides so the native decoder rejects them rather than filtering
# them into an apparently supported tree. No /chosen, identity or seed reads.
PROPERTIES = {
    "/": COMMON + ("#address-cells", "#size-cells", "interrupt-parent"),
    "/axi": COMMON + ("#address-cells", "#size-cells", "ranges", "dma-ranges", "interrupt-parent"),
    BRIDGE: COMMON + (
        "reg", "device_type", "linux,pci-domain", "num-lanes", "max-link-speed",
        "#address-cells", "#size-cells", "#interrupt-cells", "interrupt-parent",
        "interrupts", "interrupts-extended", "interrupt-names", "interrupt-map-mask",
        "interrupt-map", "msi-controller", "msi-parent", "ranges", "dma-ranges",
        "reset-names", "resets", "clocks", "clock-names",
    ),
    "/axi/msi-controller@1000130000": COMMON + (
        "reg", "msi-controller", "msi-ranges", "brcm,msi-offset", "interrupts-extended",
    ),
    RP1: COMMON + (
        "#address-cells", "#size-cells", "#interrupt-cells", "interrupt-controller",
        "interrupt-parent", "interrupts-extended", "ranges", "dma-ranges",
    ),
    RP1 + "/clocks@18000": COMMON + ("#clock-cells", "reg", "clocks"),
    GEM: COMMON + (
        "reg", "#address-cells", "#size-cells", "interrupt-parent", "interrupts",
        "interrupts-extended", "phy-mode", "phy-handle", "clock-names", "clocks",
    ),
    GEM + "/ethernet-phy@1": COMMON + ("reg",),
    SOC: COMMON + ("#address-cells", "#size-cells", "ranges"),
    SOC + "/interrupt-controller@7fff9000": COMMON + (
        "#address-cells", "#interrupt-cells", "interrupt-controller",
    ),
    SOC + "/reset-controller@119500": COMMON + ("reg", "#reset-cells"),
    SOC + "/reset-controller@1504318": COMMON + ("reg", "#reset-cells"),
}
MAX_PROPERTY = 4096
PCI = Path("/sys/bus/pci/devices/0002:01:00.0")


def collect_properties(read_property):
    properties = {}
    for node, names in PROPERTIES.items():
        properties[node] = {}
        for name in names:
            try:
                data = read_property(node, name)
            except FileNotFoundError:
                data = None
            if data is not None and (not isinstance(data, bytes) or len(data) > MAX_PROPERTY):
                raise ValueError("oversized or invalid OF property")
            properties[node][name] = None if data is None else data.hex()
    return properties


def encode_properties(properties):
    """Reconstruct only this filtered topology; no reservations/other devices.

    This is NOT the original firmware DTB and cannot be used to boot a kernel,
    allocate RAM, establish DMA safety or prove absence of omitted properties.
    """
    if not isinstance(properties, dict) or set(properties) != set(PROPERTIES):
        raise ValueError("incomplete or unallowlisted OF nodes")
    nodes = {}
    for path, names in PROPERTIES.items():
        fields = properties[path]
        if not isinstance(fields, dict) or set(fields) != set(names):
            raise ValueError("incomplete or unallowlisted OF properties")
        decoded = {}
        for name, value in fields.items():
            if value is None:
                continue
            if (not isinstance(value, str) or len(value) > 2 * MAX_PROPERTY or
                    len(value) % 2 or not re.fullmatch(r"[0-9a-f]*", value)):
                raise ValueError("invalid OF property hex")
            decoded[name] = bytes.fromhex(value)
        nodes[path] = {"name": "" if path == "/" else path.rsplit("/", 1)[1],
                       "properties": decoded, "children": []}
    for path in sorted(nodes):
        if path != "/":
            parent = path.rsplit("/", 1)[0] or "/"
            nodes[parent]["children"].append(nodes[path])
    strings, offsets = bytearray(), {}

    def cells(*values):
        return struct.pack(">" + "I" * len(values), *values)

    def padded(data):
        return data + bytes(-len(data) % 4)

    def encode(node):
        body = cells(1) + padded(node["name"].encode("ascii") + b"\0")
        for name, value in sorted(node["properties"].items()):
            if name not in offsets:
                offsets[name] = len(strings)
                strings.extend(name.encode("ascii") + b"\0")
            body += cells(3, len(value), offsets[name]) + padded(value)
        for child in node["children"]:
            body += encode(child)
        return body + cells(2)

    structure = encode(nodes["/"]) + cells(9)
    strings_offset = 56 + len(structure)
    return (cells(0xd00dfeed, strings_offset + len(strings), 56, strings_offset,
                  40, 17, 16, 0, len(strings), len(structure)) +
            bytes(16) + structure + strings)


def read_bounded(path, maximum):
    with path.open("rb") as source:
        data = source.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("read exceeds fixed reference bound")
    return data


def linux_identity():
    root = " ".join(subprocess.check_output([
        "findmnt", "-n", "-o", "SOURCE,FSTYPE,UUID", "/",
    ], text=True, timeout=5).split())
    hostname = read_bounded(Path("/proc/sys/kernel/hostname"), 256).decode().strip()
    boot = read_bounded(Path("/proc/sys/kernel/random/boot_id"), 64).decode().strip()
    kernel = read_bounded(Path("/proc/sys/kernel/osrelease"), 256).decode().strip()
    if root != ROOT_IDENTITY or hostname != "kamidana" or str(uuid.UUID(boot)) != boot:
        raise ValueError("not the exact SSD Linux identity")
    return {"root": root, "hostname": hostname, "boot_id": boot, "kernel": kernel}


def linux_snapshot():
    # Follow the stable Linux OF ABI symlink, not the raw whole /sys/firmware/fdt.
    base = Path("/proc/device-tree").resolve(strict=True)

    def read_property(node, name):
        return read_bounded(base / node.lstrip("/") / name, MAX_PROPERTY)

    with (PCI / "config").open("rb") as source:
        header = source.read(64)  # No extended capability or VPD reads.
    if len(header) != 64:
        raise ValueError("short standard PCI header")
    return {"of_properties_hex": collect_properties(read_property),
            "pci_config_first64_hex": header.hex(),
            "resource": read_bounded(PCI / "resource", 4096).decode().strip()}


def capture_linux():
    before = linux_identity()
    first = linux_snapshot()
    second = linux_snapshot()
    after = linux_identity()
    result = {"schema_version": 1, "identity_before": before, "identity_after": after,
              "first": first, "second": second, "pci_bdf": "0002:01:00.0",
              "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "pci_config_writes": 0, "mmio_accesses": 0, "sd_actions": 0,
              "network_changes": 0, "reboots": 0}
    validate_capture(result)
    return result


def validate_capture(result):
    if result.get("schema_version") != 1 or result.get("pci_bdf") != "0002:01:00.0":
        raise ValueError("unsupported reference schema/device")
    for name in ("pci_config_writes", "mmio_accesses", "sd_actions", "network_changes", "reboots"):
        if type(result.get(name)) is not int or result[name] != 0:
            raise ValueError("reference is not the read-only operation profile")
    identity = result.get("identity_before")
    if (not isinstance(identity, dict) or identity != result.get("identity_after") or
            identity.get("root") != ROOT_IDENTITY or identity.get("hostname") != "kamidana"):
        raise ValueError("changed or wrong Linux root/boot identity")
    boot = identity.get("boot_id")
    if not isinstance(boot, str) or str(uuid.UUID(boot)) != boot:
        raise ValueError("invalid boot ID")
    if not isinstance(identity.get("kernel"), str) or not identity["kernel"]:
        raise ValueError("missing Linux kernel identity")
    if result.get("first") != result.get("second"):
        raise ValueError("reference changed between reads; no implicit retry")
    snapshot = result["first"]
    encode_properties(snapshot["of_properties_hex"])
    raw = bytes.fromhex(snapshot["pci_config_first64_hex"])
    if len(raw) != 64:
        raise ValueError("not a 64-byte PCI header")
    words = struct.unpack("<16I", raw)
    if (words[0] != 0x00011de4 or words[2] >> 8 != 0x020000 or
            ((words[3] >> 16) & 0x7f) or not words[1] & 2 or
            any(words[i] & 15 for i in (4, 5, 6))):
        raise ValueError("not the supported enabled RP1 BAR profile")
    rows = snapshot["resource"].splitlines()
    if len(rows) != 7:
        raise ValueError("incomplete PCI resource list")
    resources = []
    for row in rows:
        parts = row.split()
        if len(parts) != 3 or any(not re.fullmatch(r"0x[0-9a-fA-F]{1,16}", p) for p in parts):
            raise ValueError("invalid PCI resource row")
        resources.append(tuple(int(p, 16) for p in parts))
    start, last, flags = resources[1]
    size = last + 1 - start
    if (not flags & 0x200 or flags & (0x100 | 0x2000 | 0x100000) or
            not 0 < start <= last < 1 << 40 or size & (size - 1) or
            start & 0x3fff):
        raise ValueError("unsupported Linux BAR1 resource")
    return {"pci_base": words[5] & ~15, "size": size, "cpu_base": start}
