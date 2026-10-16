#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Check named XNUPOST cases in a raw Pi serial capture."""

import argparse
import hashlib
import json
from pathlib import Path
import re


SUMMARY = re.compile(rb"^RPI5XNU:XNUPOST:(PASS|FAIL) SELECTED=(\d+) PASSED=(\d+)$")
TIMING = re.compile(rb"^RPI5XNU:XNUPOST:TIMING TICKS=(\d+) FREQ=(\d+)$")


def inspect(path: Path, required: list[str], require_summary: bool = False,
            require_timing: bool = False,
            allowed_skips: dict[str, list[str]] | None = None) -> dict:
    allowed_skips = allowed_skips or {}
    cases = {}
    current = None
    failures = []
    starts = finishes = 0
    summaries = []
    timings = []
    boots = 0
    first_boot_records = True
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for number, raw in enumerate(stream, 1):
            digest.update(raw)
            line = raw.rstrip(b"\r\n")
            boots += b"RPi: BOOTSYS" in line
            summary_match = SUMMARY.fullmatch(line)
            if summary_match:
                summaries.append((summary_match.group(1).decode(),
                                  int(summary_match.group(2)),
                                  int(summary_match.group(3))))
            timing_match = TIMING.fullmatch(line)
            if timing_match:
                timings.append((int(timing_match.group(1)),
                                int(timing_match.group(2))))
            if ((b"RPI5XNU:" in line and b":FAIL" in line) or
                    b"Kernel panic" in line or b"panic(cpu" in line):
                failures.append(f"runtime failure at line {number}")
            if not line.startswith(b"[KTEST]\t"):
                if (summary_match or timing_match) and boots != 1:
                    first_boot_records = False
                continue
            if boots != 1:
                first_boot_records = False
            fields = line.split(b"\t")
            if len(fields) < 2:
                continue
            event = fields[1]
            if event == b"START":
                starts += 1
            elif event == b"FINISH":
                finishes += 1
            elif event == b"TESTBEGIN":
                if current is not None and not cases[current]["ended"]:
                    cases[current]["incomplete"] = True
                if len(fields) < 7:
                    failures.append(f"malformed TESTBEGIN at line {number}")
                    current = None
                    continue
                current = fields[-1].decode("utf-8", "replace")
                entry = cases.setdefault(current, {"begun": 0, "ended": 0,
                                                   "pass_assertions": 0,
                                                   "fail_assertions": 0,
                                                   "skips": 0, "skip_messages": [],
                                                   "incomplete": False})
                entry["begun"] += 1
            elif event == b"TESTEND":
                name = fields[-1].decode("utf-8", "replace") if len(fields) >= 7 else ""
                if current != name or name not in cases:
                    failures.append(f"unmatched TESTEND at line {number}")
                else:
                    cases[name]["ended"] += 1
                current = None
            elif event in (b"PASS", b"FAIL", b"TESTSKIP"):
                if event == b"FAIL":
                    failures.append(f"KTEST FAIL at line {number}")
                if current is not None:
                    key = {b"PASS": "pass_assertions", b"FAIL": "fail_assertions",
                           b"TESTSKIP": "skips"}[event]
                    cases[current][key] += 1
                    if event == b"TESTSKIP":
                        cases[current]["skip_messages"].append(
                            fields[-1].decode("utf-8", "replace"))
    if current is not None and cases[current]["ended"] < cases[current]["begun"]:
        cases[current]["incomplete"] = True
    required_checks = {
        name: (name in cases and cases[name]["begun"] == 1 and
               cases[name]["ended"] == 1 and cases[name]["pass_assertions"] > 0 and
               cases[name]["fail_assertions"] == 0 and
               sorted(cases[name]["skip_messages"]) ==
               sorted(allowed_skips.get(name, [])) and
               not cases[name]["incomplete"])
        for name in required
    }
    summary_check = (len(summaries) == 1 and summaries[0] ==
                     ("PASS", len(required), len(required)))
    timing_check = len(timings) == 1 and timings[0][1] > 0
    return {"capture": str(path), "sha256": digest.hexdigest(),
            "starts": starts, "finishes": finishes,
            "boot_banners": boots, "first_boot_records": first_boot_records,
            "summaries": summaries, "summary_check": summary_check,
            "timings": timings, "timing_check": timing_check,
            "duration_seconds": timings[0][0] / timings[0][1] if timing_check else None,
            "required": required_checks, "allowed_skips": allowed_skips,
            "cases": cases, "failures": failures,
            "suite_check_pass": bool(required) and all(required_checks.values()) and
            all(name in required for name in allowed_skips) and
            starts > 0 and starts == finishes and not failures and
            (not (require_summary or require_timing) or
             (boots >= 1 and first_boot_records)) and
            (not require_summary or summary_check) and
            (not require_timing or timing_check)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("serial", type=Path)
    parser.add_argument("--require", action="append", default=[], metavar="NAME")
    parser.add_argument("--require-summary", action="store_true")
    parser.add_argument("--require-timing", action="store_true")
    parser.add_argument("--allow-skip", action="append", default=[],
                        metavar="CASE=MESSAGE",
                        help="Allow one exact TESTSKIP message in a required case")
    args = parser.parse_args()
    allowed_skips = {}
    for item in args.allow_skip:
        name, separator, message = item.partition("=")
        if not separator or not name or not message or name not in args.require:
            parser.error("--allow-skip needs required CASE=exact skip message")
        allowed_skips.setdefault(name, []).append(message)
    report = inspect(args.serial, args.require, args.require_summary,
                     args.require_timing, allowed_skips)
    print(json.dumps(report, indent=2))
    if not report["suite_check_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
