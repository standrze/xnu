#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Package the RAM-root dependency trial, without rebuilding any executable."""
import argparse
import hashlib
import json
from pathlib import Path

from prepare_pid1 import inspect_process_literals
from ramroot import build, inspect, PAGE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pid1", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    raw = args.pid1.read_bytes()
    if b"RPI5XNU:RAMROOT:READY" not in raw:
        raise ValueError("RAM-root trial payload required")
    literals = inspect_process_literals(raw, b"/bin/child")
    files = {"/sbin/launchd": (raw, 0o555), "/bin/child": (raw, 0o555),
             "/etc/motd": (b"Experimental Pi 5 XNU RAM root. Not a general shell yet.\n", 0o444),
             "/etc/boundary": (b"x" * (PAGE - 4) + b"BOUNDARY", 0o444),
             "/etc/empty": (b"", 0o444)}
    image, report = build(files)
    assert inspect(image) == report
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as output:
        output.write(image)
    report.update({"pid1": str(args.pid1), "linked_process_literals": literals,
                   "source_sha256": {name: hashlib.sha256(data).hexdigest()
                                     for name, (data, _) in files.items()},
                   "tool_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in (Path(__file__), Path(__file__).with_name("ramroot.py"))},
                   "scope": "host package validation only; physical filesystem trial pending"})
    args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
