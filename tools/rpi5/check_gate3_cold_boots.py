#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Check a Gate 3 cold-boot ledger; physical power evidence still needs review."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re


SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SELECTION = Path(__file__).with_name("gate3_selected_cases.txt")
REQUIRED_CASES = [line.strip() for line in SELECTION.read_text().splitlines()
                  if line.strip() and not line.lstrip().startswith("#")]
SKIP_EXCEPTIONS = {"xnu.vm_tests":
                   ["System not designed to support this test, skipping..."]}
QUALIFICATION_PATH = Path(__file__).with_name("check_gate3_qualification.py")
QUALIFICATION_SPEC = importlib.util.spec_from_file_location(
    "check_gate3_qualification", QUALIFICATION_PATH)
QUALIFICATION = importlib.util.module_from_spec(QUALIFICATION_SPEC)
QUALIFICATION_SPEC.loader.exec_module(QUALIFICATION)
FOUR_CORES = b"RPI5XNU:CPU_ON:ONLINE_MASK=0xf"
PID1_TICK = b"XNU-RPI5 USERSPACE PID1 TICK"
BOOT_BANNER = b"RPi: BOOTSYS"
QUALIFICATION_MARKERS = (
    ("xnupost", re.compile(rb"RPI5XNU:XNUPOST:PASS SELECTED=(\d+) PASSED=(\d+)")),
    ("concurrency_start", b"RPI5XNU:QUALIFICATION:START STAGE=SMP_CONCURRENCY"),
    ("concurrency_pass", b"RPI5XNU:SMP_CONCURRENCY:PASS"),
    ("kernel_tlb_start", b"RPI5XNU:QUALIFICATION:START STAGE=TLB"),
    ("kernel_tlb_pass", b"RPI5XNU:TLB:PASS"),
    ("user_tlb_start", b"RPI5XNU:QUALIFICATION:START STAGE=USER_TLB"),
    ("user_tlb_pass", b"RPI5XNU:USER_TLB:PASS"),
    ("invalidation_pass", b"RPI5XNU:CROSS_CORE_INVALIDATION:PASS"),
    ("soak_arm", re.compile(rb"RPI5XNU:SOAK:ARM SECONDS=[^0-9]?28800")),
    ("pre_soak_pass", b"RPI5XNU:QUALIFICATION:PRE_SOAK_PASS"),
)


def utc(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("UTC timestamp needs an offset")
    return parsed.astimezone(timezone.utc)


def inspect_capture(directory: Path):
    metadata_path = directory / "manifest.json"
    if not metadata_path.exists():
        metadata_path = directory / "state.json"
    metadata = json.loads(metadata_path.read_text())
    digest = hashlib.sha256()
    size = 0
    four_cores = False
    pid1 = False
    boot_stage = 0
    boots = 0
    ordered_boot_chain = False
    failure = False
    qualification = {name: [] for name, _ in QUALIFICATION_MARKERS}
    xnupost_counts = []
    with (directory / "serial.bin").open("rb") as stream:
        for number, line in enumerate(stream, 1):
            size += len(line)
            digest.update(line)
            stripped = line.rstrip(b"\r\n")
            if BOOT_BANNER in line:
                boots += 1
                boot_stage = 1 if boots == 1 else 0
            elif boots == 1 and boot_stage == 1 and FOUR_CORES in line:
                boot_stage = 2
            elif boots == 1 and boot_stage == 2 and PID1_TICK in line:
                boot_stage = 3
                ordered_boot_chain = True
            if boots == 1:
                four_cores |= FOUR_CORES in line
                pid1 |= PID1_TICK in line
                for name, marker in QUALIFICATION_MARKERS:
                    match = (marker.fullmatch(stripped) if isinstance(marker, re.Pattern)
                             else stripped == marker)
                    if match:
                        qualification[name].append(number)
                        if name == "xnupost":
                            xnupost_counts.append(tuple(int(value)
                                                       for value in match.groups()))
            failure |= ((b"RPI5XNU:" in line and b":FAIL" in line) or
                        b"Kernel panic" in line or b"panic(cpu" in line)
    positions = [qualification[name][0] for name, _ in QUALIFICATION_MARKERS
                 if len(qualification[name]) == 1]
    qualified_pre_soak = (len(positions) == len(QUALIFICATION_MARKERS) and
                          all(left < right for left, right in zip(positions, positions[1:])) and
                          len(xnupost_counts) == 1 and xnupost_counts[0][0] > 0 and
                          xnupost_counts[0][0] == xnupost_counts[0][1])
    named_qualification = QUALIFICATION.inspect(
        directory, REQUIRED_CASES, 28800, SKIP_EXCEPTIONS,
        pre_soak_only=True)
    return {
        "metadata": str(metadata_path),
        "finished": metadata.get("status") == "finished",
        "size_matches": metadata.get("bytes") == size,
        "hash_matches": metadata.get("sha256") == digest.hexdigest(),
        "four_cores": four_cores,
        "pid1_tick": pid1,
        "ordered_boot_chain": ordered_boot_chain,
        "qualified_pre_soak": qualified_pre_soak,
        "qualified_named_pre_soak": named_qualification["qualification_check_pass"],
        "boot_banners": boots,
        "no_failure": not failure,
        "sha256": digest.hexdigest(),
        "started": utc(metadata["started_utc"]),
        "ended": utc(metadata["ended_utc"]),
    }


def evaluate(path: Path):
    ledger = json.loads(path.read_text())
    expected_image = ledger["candidate_image_sha256"]
    expected_kernel = ledger["kernel_sha256"]
    if not SHA256.fullmatch(expected_image) or not SHA256.fullmatch(expected_kernel):
        raise ValueError("candidate hashes must be lowercase SHA-256")
    sd_image_hashes_match = (ledger.get("sd_image_sha256_before") == expected_image and
                             ledger.get("sd_image_sha256_after") == expected_image)
    attempts = ledger["attempts"]
    results = []
    streak = 0
    previous_restored = None
    seen_captures = set()
    seen_serial_hashes = set()
    for number, attempt in enumerate(attempts, 1):
        reasons = []
        if attempt.get("number") != number:
            reasons.append("attempt numbers are not consecutive")
        if (attempt.get("image_sha256") != expected_image or
                attempt.get("kernel_sha256") != expected_kernel):
            reasons.append("candidate image or kernel changed")
        if not attempt.get("power_method") or not attempt.get("power_off_evidence"):
            reasons.append("power-control method or independent evidence missing")
        removed = utc(attempt["power_removed_utc"])
        restored = utc(attempt["power_restored_utc"])
        if restored - removed < timedelta(seconds=10):
            reasons.append("power-off interval shorter than 10 seconds")
        if previous_restored is not None and removed <= previous_restored:
            reasons.append("power-cycle timestamps overlap or regress")
        previous_restored = restored
        directory = (path.parent / attempt["capture_dir"]).resolve()
        if directory in seen_captures:
            reasons.append("capture reused by another attempt")
        seen_captures.add(directory)
        try:
            capture = inspect_capture(directory)
            if not all(capture[key] for key in (
                    "finished", "size_matches", "hash_matches", "four_cores",
                    "pid1_tick", "ordered_boot_chain", "qualified_pre_soak",
                    "qualified_named_pre_soak",
                    "no_failure")):
                reasons.append("capture incomplete, corrupt, or lacks runtime evidence")
            if capture["sha256"] != attempt.get("serial_sha256"):
                reasons.append("ledger serial hash differs from raw capture")
            if capture["sha256"] in seen_serial_hashes:
                reasons.append("raw serial capture reused by another attempt")
            seen_serial_hashes.add(capture["sha256"])
            if capture["started"] > removed or capture["ended"] <= restored:
                reasons.append("serial capture does not span the power cycle")
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            reasons.append(f"capture unreadable: {error}")
        if attempt.get("result") != "PASS":
            reasons.append("attempt not recorded as PASS")
        if reasons:
            streak = 0
        else:
            streak += 1
        results.append({"number": number, "pass": not reasons,
                        "reasons": reasons, "ending_streak": streak})
    return {
        "ledger": str(path),
        "attempt_count": len(attempts),
        "ending_streak": streak,
        "sd_image_hashes_match": sd_image_hashes_match,
        "checks_pass": streak >= 20 and sd_image_hashes_match,
        "physical_power_evidence_requires_human_review": True,
        "attempts": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    args = parser.parse_args()
    report = evaluate(args.ledger)
    print(json.dumps(report, indent=2))
    if not report["checks_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
