#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Check one opt-in Gate 3 trial raw serial capture."""

import argparse
import hashlib
import json
from pathlib import Path
import re


DETAIL = {
    "SMP_CONCURRENCY": re.compile(
        rb"^RPI5XNU:SMP_CONCURRENCY:DETAIL CPUS=(\d+),(\d+),(\d+),(\d+) "
        rb"COUNT=(\d+) OVERLAP=(\d+)$"),
    "TLB": re.compile(
        rb"^RPI5XNU:TLB:DETAIL REMAP_ROUNDS=(\d+) PERMISSION_ROUNDS=(\d+) "
        rb"STRESS_ROUNDS=(\d+) STRESS_PERMISSION_ROUNDS=(\d+) CPUS=1-3$"),
    "USER_TLB": re.compile(
        rb"^RPI5XNU:USER_TLB:DETAIL REMAP_ROUNDS=(\d+) CPUS=1-3$"),
}
TIMING = {
    stage: re.compile(
        rb"^RPI5XNU:" + stage.encode() + rb":TIMING TICKS=(\d+) FREQ=(\d+)$")
    for stage in DETAIL
}


def inspect(path: Path, stage: str) -> dict:
    digest = hashlib.sha256()
    details = []
    timings = []
    passes = 0
    boots_at_pass = []
    pass_lines = []
    failures = []
    boots = 0
    online_lines = []
    pid1_lines = []
    with path.open("rb") as stream:
        for number, raw in enumerate(stream, 1):
            digest.update(raw)
            line = raw.rstrip(b"\r\n")
            boots += b"RPi: BOOTSYS" in line
            if line == b"RPI5XNU:CPU_ON:ONLINE_MASK=0xf":
                online_lines.append((boots, number))
            if line in (b"XNU-RPI5 USERSPACE PID1 OK",
                        b"XNU-RPI5 USERSPACE PID1 TICK"):
                pid1_lines.append((boots, number))
            if line == b"RPI5XNU:" + stage.encode() + b":PASS":
                passes += 1
                boots_at_pass.append(boots)
                pass_lines.append(number)
            if ((b"RPI5XNU:" in line and b":FAIL" in line) or
                    b"panic(cpu" in line or b"Kernel panic" in line):
                failures.append(number)
            match = DETAIL[stage].fullmatch(line)
            if match:
                details.append((boots, number,
                                tuple(int(value) for value in match.groups())))
            match = TIMING[stage].fullmatch(line)
            if match:
                timings.append((boots, number,
                                tuple(int(value) for value in match.groups())))
    if stage == "SMP_CONCURRENCY":
        expected = (0, 1, 2, 3, 4000000, 1)
    elif stage == "USER_TLB":
        expected = (64,)
    else:
        expected = (16, 8, 64, 32)
    detail_check = (len(details) == 1 and details[0][0] == 1 and
                    len(pass_lines) == 1 and details[0][1] < pass_lines[0] and
                    details[0][2] == expected)
    timing_check = (len(timings) == 1 and timings[0][0] == 1 and
                    len(pass_lines) == 1 and timings[0][1] < pass_lines[0] and
                    timings[0][2][0] > 0 and timings[0][2][1] > 0)
    online = (len(pass_lines) == 1 and any(
        boot == 1 and number < pass_lines[0] for boot, number in online_lines))
    # A short kernel trial can finish before PID 1 emits its first intact UART
    # line. A later PID 1 tick in the same XNU boot still proves userspace
    # liveness; a tick from watchdog-recovery Linux cannot satisfy this.
    pid1 = len(pass_lines) == 1 and any(boot == 1 for boot, _ in pid1_lines)
    return {
        "capture": str(path), "sha256": digest.hexdigest(), "stage": stage,
        "boots": boots, "boots_at_pass": boots_at_pass,
        "online_four_cores": online, "pid1_ready": pid1,
        "passes": passes, "failure_lines": failures,
        "details": [values for _, _, values in details], "detail_check": detail_check,
        "timings": [values for _, _, values in timings], "timing_check": timing_check,
        "duration_seconds": timings[0][2][0] / timings[0][2][1] if timing_check else None,
        "trial_check_pass": boots_at_pass == [1] and online and pid1 and
        passes == 1 and not failures and
        detail_check and timing_check,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=sorted(DETAIL))
    parser.add_argument("serial", type=Path)
    args = parser.parse_args()
    report = inspect(args.serial, args.stage)
    print(json.dumps(report, indent=2))
    if not report["trial_check_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
