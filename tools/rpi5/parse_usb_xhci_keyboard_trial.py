#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Strict parser for one bounded RP1 USB0 K65 first-report trial."""
import argparse
import json
from pathlib import Path
import re

from tools.rpi5 import parse_usb_xhci_caps_trial as caps
from tools.rpi5 import parse_usb_xhci_enumerate_trial as enumeration


def parse(text, expected_marker):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines.count(expected_marker) != 1:
        raise ValueError("exact USB keyboard marker not observed once")
    memory = caps._fields(caps._one(lines, "RPI5XNU:USB_XHCI_KBD:MEMORY "))
    if (caps._decimal(memory, "STATE") != 6 or
            caps._decimal(memory, "TRIAL_STEP") != 8 or
            caps._decimal(memory, "TRIAL_ERROR") != 0):
        raise ValueError("USB keyboard owner completion differs")
    enumeration_run_line = caps._one(lines,
        "RPI5XNU:USB_XHCI_KBD:RUN ")
    enumeration_run = caps._fields(enumeration_run_line)
    enumeration_command = caps._hex(enumeration_run, "HALT_CMD")
    enumeration_status = caps._hex(enumeration_run, "HALT_STS")
    if (caps._decimal(enumeration_run, "LIVE") != 1 or
            not enumeration_command & 1 or enumeration_command & 0x0e or
            enumeration_status & (1 | 4 | 0x800)):
        raise ValueError("USB enumeration live continuation differs")

    normalized = text.replace("USB_XHCI_KBD", "USB_XHCI_ENUM")
    begin = ("BEGIN USB_XHCI_ENUM POLLING PORT2 SLOT ADDRESS EP0 K65 "
        "DCI3 HID_SETUP REPORT8 NO_IRQ BME_LEASE DMA")
    normalized = normalized.replace(begin,
        "BEGIN USB_XHCI_ENUM POLLING PORT2 SLOT ADDRESS EP0 K65 "
        "NO_IRQ BME_LEASE DMA")
    normalized_run = enumeration_run_line.replace(
        "USB_XHCI_KBD", "USB_XHCI_ENUM")
    halted_run = re.sub(
        r"HALT_CMD=[0-9a-fA-F]+ HALT_STS=[0-9a-fA-F]+ LIVE=1",
        "HALT_CMD=00000000 HALT_STS=00000001 LIVE=1", normalized_run)
    if normalized_run == halted_run or normalized.count(normalized_run) != 1:
        raise ValueError("USB enumeration live row normalization failed")
    normalized = normalized.replace(normalized_run, halted_run)
    old = "TRIAL_STEP=8 TRIAL_ERROR=0"
    if normalized.count(old) != 1:
        raise ValueError("USB keyboard owner row differs")
    normalized = normalized.replace(old, "TRIAL_STEP=6 TRIAL_ERROR=0")
    base = enumeration.parse(normalized,
        expected_marker.replace("USB_XHCI_KBD", "USB_XHCI_ENUM"))

    plan = caps._fields(caps._one(lines,
        "RPI5XNU:USB_XHCI_KBD:KBD_PLAN "))
    rp1 = caps._decimal(memory, "RP1")
    exact_plan = {
        "SLOT": base["slot"],
        "DCI": 3,
        "COMMAND": rp1 + 0x1020,
        "SETUP_FIRST": 12,
        "SETUP_COUNT": 3,
        "REPORT_DMA": rp1 + 0x49000,
        "REPORT_BYTES": 8,
    }
    if any(caps._decimal(plan, key) != value
            for key, value in exact_plan.items()):
        raise ValueError("USB keyboard plan differs")

    run = caps._fields(caps._one(lines,
        "RPI5XNU:USB_XHCI_KBD:KBD_RUN "))
    decimal = {key: caps._decimal(run, key) for key in (
        "STEP", "ERROR", "READS", "WRITES", "POLLS", "DELAY_US",
        "DMA_CHECKS", "EVENT_INDEX", "PSC", "SLOT", "DCI",
        "TRANSFER", "EVENT_PARAM", "OUTPUT_COUNT")}
    hexadecimal = {key: caps._hex(run, key) for key in
        ("EVENT_STATUS", "EVENT_CONTROL", "OUTPUT0", "HALT_CMD",
         "HALT_STS")}
    report = run.get("REPORT", "")
    enumeration_event_index = 6 + base["port_status_events"]
    if (decimal["STEP"] != 7 or decimal["ERROR"] != 0 or
            not 5 <= decimal["READS"] <= 405 or
            not 14 <= decimal["WRITES"] <= 34 or
            not 6 <= decimal["POLLS"] <= 10006 or
            decimal["DELAY_US"] > 1000000 or
            not 9 <= decimal["DMA_CHECKS"] <= 19 or
            not 0 <= decimal["PSC"] <= 8 or
            decimal["EVENT_INDEX"] != enumeration_event_index + 5 +
                decimal["PSC"] or
            decimal["SLOT"] != base["slot"] or decimal["DCI"] != 3 or
            decimal["TRANSFER"] != 3 or
            decimal["EVENT_PARAM"] != rp1 + 0x47000 or
            hexadecimal["EVENT_STATUS"] != 0x01000000 or
            hexadecimal["EVENT_CONTROL"] !=
                (base["slot"] << 24) | (3 << 16) | (32 << 10) | 1 or
            not re.fullmatch(r"[0-9a-f]{16}", report) or
            decimal["OUTPUT_COUNT"] > 18 or
            (decimal["OUTPUT_COUNT"] == 0 and hexadecimal["OUTPUT0"] != 0) or
            hexadecimal["HALT_CMD"] & 0x0f or
            not hexadecimal["HALT_STS"] & 1 or
            hexadecimal["HALT_STS"] & (4 | 0x800)):
        raise ValueError("USB keyboard first-report run differs")
    return {**base,
        "status": "pass",
        "configure_endpoint": True,
        "endpoint_id": 3,
        "setup_transfers": 3,
        "interrupt_reports": 1,
        "report": report,
        "decoded_output_count": decimal["OUTPUT_COUNT"],
        "decoded_output0": hexadecimal["OUTPUT0"],
        "keyboard_event_index": decimal["EVENT_INDEX"],
        "keyboard_port_status_events": decimal["PSC"],
        "enumeration_left_running": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = parse(args.transcript.read_text(errors="replace"), args.marker)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded)
    print(encoded, end="")
