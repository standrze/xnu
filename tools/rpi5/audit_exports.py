# SPDX-License-Identifier: BSD-2-Clause
"""Read-only export/provider inventory; never filters or changes KPI exports.

This is a triage aid, not a replacement for Apple's kextsymboltool validation.
Input symbols should be produced by `nm -gj` on the linked kernel, as in
config/Makefile's allsymbols target. Alias right-hand sides identify providers.
"""
import argparse
import fnmatch
import hashlib
import json
import subprocess
from pathlib import Path


def audit(exports, symbols):
    records = []
    for path in exports:
        for line_number, raw in enumerate(path.read_text().splitlines(), 1):
            entry = raw.split("#", 1)[0].strip()
            if not entry:
                continue
            if entry.count(":") > 1:
                raise ValueError(f"Unsupported export syntax: {path}:{line_number}")
            public, separator, target = entry.partition(":")
            public, target = public.strip(), target.strip()
            provider = target if separator else public
            if len(public.split()) != 1 or len(provider.split()) != 1:
                raise ValueError(f"Empty export or provider: {path}:{line_number}")
            wildcard = any(c in provider for c in "*?[")
            present = (any(fnmatch.fnmatchcase(s, provider) for s in symbols)
                       if wildcard else provider in symbols)
            if not present:
                records.append({"file": str(path), "line": line_number,
                                "export": public, "provider": provider,
                                "wildcard": wildcard})
    return records


def absolute_zero_symbols(nm_output):
    """Recognize nm's absolute-zero definitions, not legitimate zero offsets."""
    result = []
    for line in nm_output.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[1] in ("A", "a"):
            if int(fields[0], 16) == 0:
                result.append(fields[2])
    return sorted(set(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", type=Path, required=True)
    parser.add_argument("--kernel", type=Path,
                        help="Also inspect absolute-zero definitions using xcrun nm -g")
    parser.add_argument("exports", nargs="+", type=Path)
    args = parser.parse_args()
    symbols = set(args.symbols.read_text().splitlines())
    if not symbols:
        parser.error("Symbol input is empty")
    missing = audit(args.exports, symbols)
    zero = None
    if args.kernel:
        output = subprocess.run(["xcrun", "nm", "-g", str(args.kernel)],
                                text=True, capture_output=True, check=True).stdout
        zero = absolute_zero_symbols(output)
    print(json.dumps({"purpose": "triage-only; no KPI policy inferred",
                      "symbol_count": len(symbols),
                      "absolute_zero_definitions": zero,
                      "inputs_sha256": {
                          str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in [args.symbols, *args.exports,
                                    *([args.kernel] if args.kernel else [])]},
                      "missing_count": len(missing), "missing": missing}, indent=2))


if __name__ == "__main__":
    main()
