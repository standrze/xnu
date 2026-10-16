#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Check the ordered combined Gate 3 run; cold boots remain a separate gate."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re


def sibling(name):
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TRIALS = sibling("check_gate3_trials")
XNUPOST = sibling("check_gate3_xnupost")
SOAK = sibling("check_gate3_soak")
SUMMARY = re.compile(rb"RPI5XNU:XNUPOST:PASS SELECTED=(\d+) PASSED=(\d+)")


def inspect(directory: Path, required_cases: list[str], seconds: int = 28800,
            allowed_skips: dict[str, list[str]] | None = None,
            pre_soak_only: bool = False) -> dict:
    allowed_skips = allowed_skips or {}
    serial = directory / "serial.bin"
    markers = [
        ("xnupost", SUMMARY),
        ("concurrency_start", b"RPI5XNU:QUALIFICATION:START STAGE=SMP_CONCURRENCY"),
        ("concurrency_pass", b"RPI5XNU:SMP_CONCURRENCY:PASS"),
        ("kernel_tlb_start", b"RPI5XNU:QUALIFICATION:START STAGE=TLB"),
        ("kernel_tlb_pass", b"RPI5XNU:TLB:PASS"),
        ("user_tlb_start", b"RPI5XNU:QUALIFICATION:START STAGE=USER_TLB"),
        ("user_tlb_pass", b"RPI5XNU:USER_TLB:PASS"),
        ("invalidation_pass", b"RPI5XNU:CROSS_CORE_INVALIDATION:PASS"),
        ("soak_arm", re.compile(rb"RPI5XNU:SOAK:ARM SECONDS=[^0-9]?" +
                                 str(seconds).encode())),
        ("pre_soak_pass", b"RPI5XNU:QUALIFICATION:PRE_SOAK_PASS"),
        ("soak_pass", b"RPI5XNU:SOAK:PASS SECONDS=" + str(seconds).encode()),
    ]
    found = {name: [] for name, _ in markers}
    records = {name: [] for name in ("ktest", "xnupost_timing",
                                   "concurrency_detail", "concurrency_timing",
                                   "kernel_tlb_detail", "kernel_tlb_timing",
                                   "user_tlb_detail", "user_tlb_timing")}
    record_prefixes = {
        "xnupost_timing": b"RPI5XNU:XNUPOST:TIMING ",
        "concurrency_detail": b"RPI5XNU:SMP_CONCURRENCY:DETAIL ",
        "concurrency_timing": b"RPI5XNU:SMP_CONCURRENCY:TIMING ",
        "kernel_tlb_detail": b"RPI5XNU:TLB:DETAIL ",
        "kernel_tlb_timing": b"RPI5XNU:TLB:TIMING ",
        "user_tlb_detail": b"RPI5XNU:USER_TLB:DETAIL ",
        "user_tlb_timing": b"RPI5XNU:USER_TLB:TIMING ",
    }
    digest = hashlib.sha256()
    boots = 0
    with serial.open("rb") as stream:
        for number, raw in enumerate(stream, 1):
            digest.update(raw)
            line = raw.rstrip(b"\r\n")
            boots += b"RPi: BOOTSYS" in line
            if line.startswith(b"[KTEST]\t"):
                records["ktest"].append((boots, number))
            for name, prefix in record_prefixes.items():
                if line.startswith(prefix):
                    records[name].append((boots, number))
            for name, pattern in markers:
                matched = (pattern.fullmatch(line) if isinstance(pattern, re.Pattern)
                           else line == pattern)
                if matched:
                    found[name].append((boots, number))
    required_markers = markers[:-1] if pre_soak_only else markers
    sequence = [found[name][0][1] for name, _ in required_markers
                if len(found[name]) == 1]
    ordering = (len(sequence) == len(required_markers) and
                all(found[name][0][0] == 1 for name, _ in required_markers) and
                all(left < right for left, right in zip(sequence, sequence[1:])))
    def within(record, start, end):
        return (len(records[record]) == 1 and len(found[start]) == 1 and
                len(found[end]) == 1 and records[record][0][0] == 1 and
                found[start][0][1] < records[record][0][1] < found[end][0][1])

    records_ordered = (bool(records["ktest"]) and len(found["xnupost"]) == 1 and
                       all(boot == 1 and number < found["xnupost"][0][1]
                           for boot, number in records["ktest"]) and
                       len(records["xnupost_timing"]) == 1 and
                       records["xnupost_timing"][0][0] == 1 and
                       records["ktest"][-1][1] < found["xnupost"][0][1] <
                       records["xnupost_timing"][0][1] and
                       len(found["concurrency_start"]) == 1 and
                       records["xnupost_timing"][0][1] <
                       found["concurrency_start"][0][1] and
                       all(within(record, start, end) for record, start, end in (
                           ("concurrency_detail", "concurrency_start", "concurrency_pass"),
                           ("concurrency_timing", "concurrency_start", "concurrency_pass"),
                           ("kernel_tlb_detail", "kernel_tlb_start", "kernel_tlb_pass"),
                           ("kernel_tlb_timing", "kernel_tlb_start", "kernel_tlb_pass"),
                           ("user_tlb_detail", "user_tlb_start", "user_tlb_pass"),
                           ("user_tlb_timing", "user_tlb_start", "user_tlb_pass"))))
    xnupost = XNUPOST.inspect(serial, required_cases, True, True, allowed_skips)
    trials = {stage: TRIALS.inspect(serial, stage) for stage in
              ("SMP_CONCURRENCY", "TLB", "USER_TLB")}
    soak = None if pre_soak_only else SOAK.inspect(directory, seconds)
    checks = {
        "one_ordered_first_boot_sequence": ordering,
        "stage_records_ordered": records_ordered,
        "xnupost_suite": xnupost["suite_check_pass"],
        "four_core_concurrency": trials["SMP_CONCURRENCY"]["trial_check_pass"],
        "kernel_tlb": trials["TLB"]["trial_check_pass"],
        "user_tlb": trials["USER_TLB"]["trial_check_pass"],
    }
    if pre_soak_only:
        checks["no_premature_soak_pass"] = not found["soak_pass"]
    else:
        checks["eight_hour_soak"] = soak["marker_check_pass"]
    return {
        "capture": str(directory), "sha256": digest.hexdigest(),
        "required_cases": required_cases, "allowed_skips": allowed_skips,
        "markers": found, "records": records,
        "trial_duration_seconds": {stage: result["duration_seconds"]
                                   for stage, result in trials.items()},
        "xnupost_duration_seconds": xnupost["duration_seconds"],
        "checks": checks, "qualification_check_pass": all(checks.values()),
        "scope": ("first-boot pre-soak serial evidence only; physical power-off and "
                  "image identity need independent review" if pre_soak_only else
                  "combined image and serial evidence only; does not credit 20 cold boots"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("--require-case", action="append", default=[], metavar="NAME")
    parser.add_argument("--require-case-file", type=Path, metavar="PATH",
                        help="One exact selected XNUPOST case per line; # comments allowed")
    parser.add_argument("--allow-skip", action="append", default=[],
                        metavar="CASE=MESSAGE")
    parser.add_argument("--seconds", type=int, default=28800)
    parser.add_argument("--pre-soak-only", action="store_true",
                        help="Check ordered first-boot qualification before the timed soak")
    args = parser.parse_args()
    required_cases = list(args.require_case)
    if args.require_case_file is not None:
        required_cases.extend(line.strip() for line in
                              args.require_case_file.read_text().splitlines()
                              if line.strip() and not line.lstrip().startswith("#"))
    if not required_cases or len(required_cases) != len(set(required_cases)) or args.seconds < 60:
        parser.error("unique required cases and seconds >= 60 are required")
    allowed_skips = {}
    for item in args.allow_skip:
        name, separator, message = item.partition("=")
        if not separator or not name or not message or name not in required_cases:
            parser.error("--allow-skip needs required CASE=exact skip message")
        allowed_skips.setdefault(name, []).append(message)
    report = inspect(args.capture_dir, required_cases, args.seconds,
                     allowed_skips, args.pre_soak_only)
    print(json.dumps(report, indent=2))
    if not report["qualification_check_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
