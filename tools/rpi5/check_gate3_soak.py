#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Check raw Gate 3 soak evidence without replacing the board audit."""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re


HEARTBEAT = re.compile(rb"^RPI5XNU:SOAK:HEARTBEAT ACKS=(\d+),(\d+),(\d+)$")
SOAK_ARM = re.compile(rb"^RPI5XNU:SOAK:ARM SECONDS=[^0-9]?(\d+)$")
SOAK_PASS = re.compile(rb"^RPI5XNU:SOAK:PASS SECONDS=(\d+)$")
IPI_PASS = re.compile(rb"^RPI5XNU:IPI_STRESS:PASS CPUS=1-3 ACKS=(\d+),(\d+),(\d+)$")
CACHE_PASS = b"RPI5XNU:CACHE_VIS:PASS ROUNDS=64 ERRORS=0"


def inspect(directory: Path, seconds: int) -> dict:
    manifest_path = directory / "state.json"
    if not manifest_path.exists():
        manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    started = datetime.fromisoformat(manifest["started_utc"].replace("Z", "+00:00"))
    ended = datetime.fromisoformat(manifest["ended_utc"].replace("Z", "+00:00"))
    if started.tzinfo is None or ended.tzinfo is None:
        raise ValueError("capture timestamps require UTC offsets")
    actual_seconds = (ended - started).total_seconds()
    digest = hashlib.sha256()
    size = 0
    heartbeats = []
    soak_arm = False
    soak_pass = False
    ipi_pass = False
    cache_pass = False
    failure = False
    linux_after_pass = False
    boots = 0
    with (directory / "serial.bin").open("rb") as stream:
        for raw_line in stream:
            size += len(raw_line)
            digest.update(raw_line)
            line = raw_line.rstrip(b"\r\n")
            boots += b"RPi: BOOTSYS" in line
            match = HEARTBEAT.fullmatch(line)
            if match and boots == 1 and soak_arm and not soak_pass:
                heartbeats.append(tuple(int(value) for value in match.groups()))
            match = SOAK_ARM.fullmatch(line)
            if match and boots == 1 and int(match.group(1)) == seconds and not soak_pass:
                soak_arm = True
            match = SOAK_PASS.fullmatch(line)
            if match and boots == 1 and soak_arm and int(match.group(1)) == seconds:
                soak_pass = True
            if boots == 1 and soak_arm and not soak_pass and IPI_PASS.fullmatch(line):
                ipi_pass = True
            if boots == 1 and soak_arm and not soak_pass and line == CACHE_PASS:
                cache_pass = True
            if ((b"RPI5XNU:" in line and b":FAIL" in line) or
                    b"Kernel panic" in line or b"panic(cpu" in line):
                failure = True
            if soak_pass and boots >= 2 and b"Debian GNU/Linux" in line:
                linux_after_pass = True
    monotonic = all(all(current[cpu] > prior[cpu] for cpu in range(3))
                    for prior, current in zip(heartbeats, heartbeats[1:]))
    min_heartbeats = max(1, int(seconds / 60 * 0.95))
    final_acks = heartbeats[-1] if heartbeats else (0, 0, 0)
    heartbeat_gaps_bounded = all(
        all(current[cpu] - prior[cpu] <= 120 for cpu in range(3))
        for prior, current in zip(heartbeats, heartbeats[1:]))
    checks = {
        "capture_finished": manifest.get("status") == "finished",
        "capture_duration": manifest.get("requested_seconds", 0) >=
            seconds + min(180, seconds // 2),
        "actual_capture_duration": actual_seconds >= seconds - 10,
        "raw_size_matches": manifest.get("bytes") == size,
        "raw_sha256_matches": manifest.get("sha256") == digest.hexdigest(),
        "soak_arm": soak_arm,
        "soak_pass": soak_pass,
        "first_boot_contains_complete_soak": soak_arm and soak_pass,
        "ipi_pass": ipi_pass,
        "cache_visibility_pass": cache_pass,
        "no_failure_marker": not failure,
        "heartbeats_sufficient": len(heartbeats) >= min_heartbeats,
        "heartbeats_monotonic": monotonic,
        "heartbeat_gaps_bounded": heartbeat_gaps_bounded,
        "initial_acks_near_start": bool(heartbeats) and max(heartbeats[0]) <= 120,
        "final_acks_sufficient": min(final_acks) >= seconds - 120,
        "linux_serial_after_pass": linux_after_pass,
    }
    return {
        "capture": str(directory),
        "expected_seconds": seconds,
        "actual_capture_seconds": actual_seconds,
        "bytes": size,
        "sha256": digest.hexdigest(),
        "boot_banners": boots,
        "heartbeat_count": len(heartbeats),
        "first_acks": heartbeats[0] if heartbeats else None,
        "last_acks": final_acks,
        "checks": checks,
        "marker_check_pass": all(checks.values()),
    }


def inspect_tail(directory: Path, seconds: int, max_missing_seconds: int = 3600) -> dict:
    """Assess late-start evidence without ever claiming the formal soak exit."""
    manifest_path = directory / "state.json"
    if not manifest_path.exists():
        manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    started = datetime.fromisoformat(manifest["started_utc"].replace("Z", "+00:00"))
    ended = datetime.fromisoformat(manifest["ended_utc"].replace("Z", "+00:00"))
    if started.tzinfo is None or ended.tzinfo is None:
        raise ValueError("capture timestamps require UTC offsets")
    digest = hashlib.sha256()
    size = 0
    heartbeats = []
    pass_seen = False
    failure = False
    reset_before_pass = False
    with (directory / "serial.bin").open("rb") as stream:
        for raw_line in stream:
            size += len(raw_line)
            digest.update(raw_line)
            line = raw_line.rstrip(b"\r\n")
            if b"RPi: BOOTSYS" in line and not pass_seen:
                reset_before_pass = True
            match = HEARTBEAT.fullmatch(line)
            if match and not pass_seen and not reset_before_pass:
                heartbeats.append(tuple(int(value) for value in match.groups()))
            match = SOAK_PASS.fullmatch(line)
            if match and not reset_before_pass and int(match.group(1)) == seconds:
                pass_seen = True
            if ((b"RPI5XNU:" in line and b":FAIL" in line) or
                    b"Kernel panic" in line or b"panic(cpu" in line):
                failure = True
    first = heartbeats[0] if heartbeats else None
    last = heartbeats[-1] if heartbeats else None
    expected_heartbeats = (max(1, int((seconds - max(first)) / 60 * 0.95))
                           if first and max(first) < seconds else 1)
    checks = {
        "capture_finished": manifest.get("status") == "finished",
        "capture_duration": manifest.get("requested_seconds", 0) >= seconds,
        "actual_capture_duration": (ended - started).total_seconds() >= seconds - 10,
        "raw_size_matches": manifest.get("bytes") == size,
        "raw_sha256_matches": manifest.get("sha256") == digest.hexdigest(),
        "soak_pass_after_tail": pass_seen,
        "no_reset_before_pass": not reset_before_pass,
        "no_failure_marker": not failure,
        "first_acks_within_missing_window": bool(first) and
            120 <= min(first) <= max(first) <= max_missing_seconds,
        "heartbeats_sufficient": len(heartbeats) >= expected_heartbeats,
        "heartbeats_monotonic": len(heartbeats) >= 2 and all(
            all(current[cpu] > prior[cpu] for cpu in range(3))
            for prior, current in zip(heartbeats, heartbeats[1:])),
        "heartbeat_gaps_bounded": len(heartbeats) >= 2 and all(
            all(current[cpu] - prior[cpu] <= 120 for cpu in range(3))
            for prior, current in zip(heartbeats, heartbeats[1:])),
        "final_acks_sufficient": bool(last) and min(last) >= seconds - 120,
    }
    return {
        "capture": str(directory),
        "expected_seconds": seconds,
        "max_missing_seconds": max_missing_seconds,
        "heartbeat_count": len(heartbeats),
        "first_acks": first,
        "last_acks": last,
        "checks": checks,
        "tail_support_pass": all(checks.values()),
        "formal_soak_exit_proven": False,
        "limitation": "capture began after boot and SOAK:ARM; this is tail evidence only",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("--seconds", type=int, required=True)
    parser.add_argument("--tail-only", action="store_true",
                        help="assess late-start support without claiming formal soak exit")
    args = parser.parse_args()
    if args.seconds < 60:
        parser.error("expected soak duration must be at least 60 seconds")
    report = (inspect_tail(args.capture_dir, args.seconds) if args.tail_only else
              inspect(args.capture_dir, args.seconds))
    print(json.dumps(report, indent=2))
    if not report["tail_support_pass" if args.tail_only else "marker_check_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
