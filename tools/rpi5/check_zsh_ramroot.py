#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only Pi-format preflight of a pinned VM zsh root; not Pi execution."""
import argparse
import hashlib
import json
from pathlib import Path
import re

try:
    from .prepare_pid1 import inspect as inspect_macho
    from .ramroot import inspect as inspect_root, MAX_SIZE
except ImportError:
    from prepare_pid1 import inspect as inspect_macho
    from ramroot import inspect as inspect_root, MAX_SIZE


def checked_hash(data, expected, label):
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError(f"invalid {label} SHA256 pin")
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError(f"{label} SHA256 differs from pin")
    return actual


def check(root, zsh, root_sha256, zsh_sha256):
    root_hash = checked_hash(root, root_sha256, "RAM root")
    zsh_hash = checked_hash(zsh, zsh_sha256, "zsh")
    root_report = inspect_root(root)
    executable = inspect_macho(zsh)
    entries = {entry["path"]: entry for entry in root_report["entries"]}
    shell = entries.get("/bin/zsh")
    if not shell or shell["type"] != "file" or shell["mode"] != 0o555:
        raise ValueError("RAM root needs executable /bin/zsh")
    offset, size = shell["offset"], shell["size"]
    if root[offset:offset + size] != zsh:
        raise ValueError("RAM-root /bin/zsh differs from pinned executable")
    return {
        "schema_version": 1,
        "scope": "Pi RAM-root/static Mach-O structural preflight only",
        "root_sha256": root_hash,
        "zsh_sha256": zsh_hash,
        "root_bytes": len(root),
        "root_nodes": len(entries),
        "format": root_report["format"],
        "zsh_executable": executable,
        "passed": True,
        "pi_executed": False,
        "source_provenance_audited": False,
        "isa_and_syscall_compatibility_proven": False,
        "sd_actions": 0,
        "serial_actions": 0,
        "reboots": 0,
        "remaining": [
            "Audit Pi-specific syscall, startup, signal/VM and console contracts",
            "Audit executable ISA selection for Cortex-A76",
            "Preserve recovery shell and package a distinct opt-in Pi image",
            "Run marker-guarded Pi version/builtin/external-exec/prompt trial",
        ],
    }


def read_bounded(path):
    with path.open("rb") as source:
        data = source.read(MAX_SIZE + 1)
    if len(data) > MAX_SIZE:
        raise ValueError("input exceeds 64 MiB")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--zsh", required=True, type=Path)
    parser.add_argument("--root-sha256", required=True)
    parser.add_argument("--zsh-sha256", required=True)
    parser.add_argument("--report", type=Path, help="Optional NEW local report; never overwritten")
    args = parser.parse_args()
    report = check(read_bounded(args.root), read_bounded(args.zsh),
                   args.root_sha256, args.zsh_sha256)
    report["inputs"] = {"root": str(args.root.resolve()), "zsh": str(args.zsh.resolve())}
    report["checker_source_sha256"] = {
        name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in ("check_zsh_ramroot.py", "prepare_pid1.py", "ramroot.py")
    }
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        with args.report.open("x") as output:
            output.write(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
