#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Bounded read-only RAM root; retains a static launchd Mach-O at byte zero.

Manifest: {"files": {"/sbin/launchd": {"source": "pid1", "mode": 365},
                     "/etc/motd": {"source": "motd", "mode": 292}}}
Modes are decimal 365 (0555 executable) and 292 (0444 data). Sources are
relative to the manifest. Directories are derived, with an empty /dev.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct

try:
    from .prepare_pid1 import inspect as inspect_macho
except ImportError:
    from prepare_pid1 import inspect as inspect_macho

PAGE = 16384
MAX_SIZE = 64 * 1024 * 1024
MAX_NODES = 32
MAGIC = b"RPI5RFS1"
RECORD = struct.Struct("<IIQQII64s32s")


def build(files):
    """files maps absolute paths to (bytes, POSIX mode); canonical layout."""
    directories = {"/", "/dev"}
    if "/sbin/launchd" not in files or files["/sbin/launchd"][1] != 0o555:
        raise ValueError("executable /sbin/launchd required")
    for name, (data, mode) in files.items():
        path = PurePosixPath(name)
        if (not name.startswith("/") or str(path) != name or name == "/" or
                any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,63}", p) or p in (".", "..")
                    for p in name.split("/")[1:]) or
                name == "/dev" or name.startswith("/dev/")):
            raise ValueError("invalid or reserved path")
        if mode not in (0o444, 0o555) or len(data) > MAX_SIZE:
            raise ValueError("unsupported mode or file size")
        if mode == 0o555:
            inspect_macho(data)
        directories.update(str(p) for p in path.parents)
    if directories.intersection(files) or len(directories) + len(files) > MAX_NODES:
        raise ValueError("file/directory collision or node limit")
    names = sorted(directories | files.keys(), key=lambda s: (s.count("/"), s != "/", s))
    # Root must precede top-level children; parents precede descendants.
    names.remove("/")
    names.insert(0, "/")
    data_image = bytearray()
    extents = {}
    order = ["/sbin/launchd"] + sorted(set(files) - {"/sbin/launchd"})
    for name in order:
        data, mode = files[name]
        extents[name] = (len(data_image), len(data))
        if len(data_image) + len(data) + PAGE > MAX_SIZE:
            raise ValueError("image exceeds 64 MiB")
        data_image.extend(data)
        data_image.extend(bytes(-len(data_image) % PAGE))
    size = len(data_image) + PAGE
    if size > MAX_SIZE:
        raise ValueError("image exceeds 64 MiB")
    table = bytearray(PAGE)
    struct.pack_into("<8sIIQQ", table, 0, MAGIC, 1, len(names), size, 0)
    entries = []
    for index, name in enumerate(names):
        directory = name in directories
        parent = names.index(str(PurePosixPath(name).parent)) if index else 0
        offset, length = (0, 0) if directory else extents[name]
        mode = 0o555 if directory else files[name][1]
        component = b"" if not index else PurePosixPath(name).name.encode("ascii")
        RECORD.pack_into(table, 32 + index * 128, parent, 1 if directory else 2,
                         offset, length, mode, 0, component, bytes(32))
        entries.append({"path": name, "offset": offset, "size": length, "mode": mode,
                        "type": "directory" if directory else "file"})
    image = bytes(data_image + table)
    return image, {"format": "RPI5RFS1", "size": size, "entries": entries,
                   "sha256": hashlib.sha256(image).hexdigest()}


def inspect(image):
    """Strict canonical host validation; kernel also validates independently."""
    if not 2 * PAGE <= len(image) <= MAX_SIZE or len(image) % PAGE:
        raise ValueError("invalid RAM-root size")
    table = image[-PAGE:]
    magic, version, count, total, reserved = struct.unpack_from("<8sIIQQ", table)
    if magic != MAGIC or version != 1 or not 4 <= count <= MAX_NODES or total != len(image) or reserved:
        raise ValueError("invalid RAM-root header")
    names, files = [], {}
    for i in range(count):
        parent, kind, offset, size, mode, flags, name, padding = RECORD.unpack_from(table, 32 + i * 128)
        if (i and parent >= i) or flags or any(padding) or kind not in (1, 2):
            raise ValueError("invalid RAM-root entry")
        try:
            component = name.split(b"\0", 1)[0].decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError("non-ASCII component") from exc
        path = "/" if i == 0 else names[parent].rstrip("/") + "/" + component
        if path in names or offset > len(image) - PAGE or size > len(image) - PAGE - offset:
            raise ValueError("duplicate path or extent outside data")
        names.append(path)
        if kind == 2:
            files[path] = (image[offset:offset + size], mode)
    canonical, report = build(files)
    if canonical != image:
        raise ValueError("noncanonical or malformed RAM-root metadata/padding")
    return report


def inspect_init(image):
    if len(image) >= PAGE and image[-PAGE:-PAGE + 8] == MAGIC:
        return inspect(image)
    return inspect_macho(image)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    files = {name: ((args.manifest.parent / record["source"]).read_bytes(), record["mode"])
             for name, record in manifest["files"].items()}
    image, report = build(files)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as output:
        output.write(image)
    report["source_manifest"] = str(args.manifest)
    report["source_sha256"] = {name: hashlib.sha256(data).hexdigest()
                                for name, (data, _) in files.items()}
    report["builder_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
