#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Link only source-built guest archives, checking a static no-import Mach-O."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from prepare_pid1 import inspect

HERE = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--archive", type=Path, action="append", required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
    binary = out / "zsh"
    command = ["xcrun", "ld", "-arch", "arm64", "-platform_version", "macos", "26.0", "27.0",
               "-static", "-e", "_start", "-dead_strip", "-no_adhoc_codesign", "-no_uuid",
               "-alias", "_fopen", "_fopen$DARWIN_EXTSN",
               "-map", str(out / "link.map"), "-o", str(binary)]
    command.extend(str(p.resolve()) for p in args.archive)
    result = subprocess.run(command, text=True, capture_output=True, timeout=120)
    (out / "link.log").write_text(result.stdout + result.stderr)
    report = {"command": command, "exit": result.returncode,
              "archives": {str(p.resolve()): sha(p) for p in args.archive},
              "host_runtime_linked": False, "guest_executed": False}
    report["symbol_adaptations"] = {"fopen$DARWIN_EXTSN": "Apple Libc-167 fopen; basic guest modes only, not all modern extensions"}
    if result.returncode == 0:
        report["executable"] = inspect(binary.read_bytes())
        report["sha256"] = sha(binary)
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report if result.returncode == 0 else {"exit": result.returncode, "log": str(out / "link.log")}))
    return result.returncode

if __name__ == "__main__":
    raise SystemExit(main())
