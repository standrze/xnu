#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Inventory Gate 3 PASS/FAIL markers in unmodified serial captures."""

import argparse
import hashlib
import json
from pathlib import Path
import re


MARKER = re.compile(rb"^RPI5XNU:([A-Z][A-Z0-9_]*):(PASS|FAIL)$")


def inspect(path):
    digest = hashlib.sha256()
    size = 0
    markers = []
    # Eight-hour raw UART captures can be large; hash and inspect them in
    # one streaming pass without copying the complete capture into RAM.
    with path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, 1):
            size += len(raw_line)
            digest.update(raw_line)
            match = MARKER.fullmatch(raw_line.rstrip(b"\r\n"))
            if match:
                markers.append({"line": line_number,
                                "stage": match.group(1).decode("ascii"),
                                "result": match.group(2).decode("ascii")})
    return {"path": str(path), "bytes": size,
            "sha256": digest.hexdigest(), "markers": markers}


def evaluate(captures, required):
    by_stage = {}
    for capture in captures:
        for marker in capture["markers"]:
            by_stage.setdefault(marker["stage"], set()).add(marker["result"])
    failed = sorted(stage for stage, results in by_stage.items() if "FAIL" in results)
    missing = sorted(set(required) - {stage for stage, results in by_stage.items()
                                      if results == {"PASS"}})
    return {"captures": captures, "failed_stages": failed,
            "missing_required_stages": missing,
            "marker_check_pass": not failed and not missing}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("serial", nargs="+", type=Path, help="raw serial.bin files")
    parser.add_argument("--require", action="append", default=[], metavar="STAGE",
                        help="stage that must have an uncontradicted PASS marker")
    args = parser.parse_args()
    if any(not re.fullmatch(r"[A-Z][A-Z0-9_]*", stage) for stage in args.require):
        parser.error("--require values must be uppercase stage names")
    report = evaluate([inspect(path) for path in args.serial], args.require)
    print(json.dumps(report, indent=2))
    if not report["marker_check_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
