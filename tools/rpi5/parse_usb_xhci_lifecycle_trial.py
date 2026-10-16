#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Strict parser for one bounded RP1 USB0 xHCI halt/reset trial."""
import argparse
import json
from pathlib import Path

from tools.rpi5 import parse_usb_xhci_caps_trial as caps


def parse(text, expected_marker):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines.count(expected_marker) != 1:
        raise ValueError("exact USB lifecycle marker not observed once")
    begin = caps._one(lines, "RPI5XNU:PCIEID:BEGIN ")
    expected_begin = ("RPI5XNU:PCIEID:BEGIN USB_XHCI_LIFECYCLE "
        "HALT_RESET_ONLY NO_PORT NO_IRQ NO_BME NO_DMA")
    if begin != expected_begin:
        raise ValueError("USB lifecycle begin marker differs")
    capability = caps._fields(caps._one(lines, "RPI5XNU:USB_XHCI_CAPS:STATE "))
    expected_capability = {
        "STEP": 8, "ERROR": 0, "READS": caps.EXPECTED_READS,
        "PHYSICAL": caps.EXPECTED_PHYSICAL, "BYTES": caps.EXPECTED_BYTES,
    }
    if any(caps._decimal(capability, key) != value
            for key, value in expected_capability.items()):
        raise ValueError("USB capability/lifecycle composite state differs")
    fields = caps._fields(caps._one(lines, "RPI5XNU:USB_XHCI_LIFECYCLE:STATE "))
    decimal = {key: caps._decimal(fields, key) for key in
        ("STEP", "ERROR", "READS", "WRITES", "POLLS", "DELAY_US")}
    hexadecimal = {key: caps._hex(fields, key) for key in
        ("OP", "CMD0", "STS0", "HALT_CMD", "HALT_STS", "RESET_CMD", "CMD1", "STS1")}
    initially_halted = bool(hexadecimal["STS0"] & 1)
    expected_writes = 1 if initially_halted else 2
    if (decimal["STEP"] != 5 or decimal["ERROR"] != 0 or
            decimal["WRITES"] != expected_writes or
            not 4 <= decimal["READS"] <= 5206 or
            not 2 <= decimal["POLLS"] <= 5200 or
            not 1000 <= decimal["DELAY_US"] <= 521000 or
            hexadecimal["OP"] != 0x20 or
            hexadecimal["STS0"] & 4 or
            hexadecimal["HALT_CMD"] != (hexadecimal["CMD0"] & ~1) or
            not hexadecimal["HALT_STS"] & 1 or
            hexadecimal["HALT_STS"] & 4 or
            hexadecimal["RESET_CMD"] != (hexadecimal["HALT_CMD"] | 2) or
            hexadecimal["CMD1"] & 3 or
            hexadecimal["STS1"] & (4 | 0x800) or
            not hexadecimal["STS1"] & 1):
        raise ValueError("USB lifecycle evidence differs")

    synthetic_marker = expected_marker.replace(
        "USB_XHCI_LIFECYCLE:ENTRY", "USB_XHCI_CAPS:ENTRY").replace(
        "HALT_RESET_ONLY", "READ_ONLY NO_RESET")
    normalized = text.replace(expected_marker, synthetic_marker, 1).replace(
        expected_begin,
        "RPI5XNU:PCIEID:BEGIN USB_XHCI_CAPS READ_ONLY NO_RESET NO_PORT NO_IRQ NO_BME NO_DMA",
        1).replace(
        "RPI5XNU:USB_XHCI_CAPS:STATE STEP=8",
        "RPI5XNU:USB_XHCI_CAPS:STATE STEP=6", 1)
    result = caps.parse(normalized, synthetic_marker)
    result.update(
        status="pass",
        read_only=False,
        controller_reset=True,
        halt_reset_only=True,
        port_reset=False,
        bme=False,
        dma=False,
        irq=False,
        lifecycle={**{key.lower(): value for key, value in decimal.items()},
                   **{key.lower(): value for key, value in hexadecimal.items()}},
    )
    return result


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
