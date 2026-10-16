#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preserve bounded trial evidence, excluding VM firmware state and boot seeds."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from check_evidence import audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("loader_manifest", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--incomplete", action="store_true", help="preserve a known failed trial without qualifying it")
    parser.add_argument("--shell", action="store_true", help="legacy shell evidence, not managed protocol")
    parser.add_argument("--expected-cli-status", type=int, required=True)
    args = parser.parse_args()
    result = json.loads((args.source / "result.json").read_text())
    report = None if args.incomplete or args.shell else audit(args.source)
    args.destination.mkdir(exist_ok=False)
    for path in sorted(args.source.iterdir()):
        if path.is_file() and (path.name in ("serial.bin", "serial.txt") or path.suffix == ".json"
                               or path.name.startswith("command-") and path.suffix == ".bin"):
            shutil.copy2(path, args.destination / path.name)
    shutil.copy2(args.loader_manifest, args.destination / "loader-manifest.json")
    if report:
        (args.destination / "audit.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    preservation = {"qualification": "historical failed trial" if args.incomplete else "shell regression" if args.shell else "managed wire audit passed",
                    "expectedCLIStatus": args.expected_cli_status, "sessionID": result["sessionID"],
                    "files": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in sorted(args.destination.iterdir()) if path.is_file()}}
    (args.destination / "preservation.json").write_text(json.dumps(preservation, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"destination": str(args.destination), "qualification": preservation["qualification"]}))


if __name__ == "__main__":
    main()
