#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Strict parser for the receive-only RP1 USB0/xHCI capability trial."""
import argparse
import json
from pathlib import Path
import re

from tools.rpi5 import parse_gem_full_provider_trial as provider


EXPECTED_PHYSICAL = 0x1F00200000
EXPECTED_BYTES = 0x100000
EXPECTED_READS = 16
CAP_KEYS = ("CAP", "HCS1", "HCS2", "HCS3", "HCC1", "DBOFF", "RTSOFF", "HCC2")


def _one(lines, prefix):
    found = [line for line in lines if line.startswith(prefix)]
    if len(found) != 1:
        raise ValueError(f"expected one {prefix!r} record, got {len(found)}")
    return found[0]


def _fields(line):
    return {key: value for key, value in re.findall(
        r"([A-Z][A-Z0-9_]*)=([0-9a-fA-F-]+)", line)}


def _decimal(fields, key):
    try:
        return int(fields[key], 10)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"invalid decimal field {key}") from exc


def _hex(fields, key):
    try:
        return int(fields[key], 16)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"invalid hexadecimal field {key}") from exc


def _decode(raw):
    cap_length = raw[0] & 0xff
    version = raw[0] >> 16
    result = {
        "VERSION": version,
        "CAPLEN": cap_length,
        "SLOTS": raw[1] & 0xff,
        "INTRS": (raw[1] >> 8) & 0x7ff,
        "PORTS": raw[1] >> 24,
        "SCRATCH": (((raw[2] >> 27) & 0x1f) << 5) | ((raw[2] >> 21) & 0x1f),
        "DB": raw[5] & ~3,
        "RT": raw[6] & ~31,
        "XECP": ((raw[4] >> 16) & 0xffff) * 4,
        "AC64": raw[4] & 1,
        "CSZ64": (raw[4] >> 2) & 1,
        "PPC": (raw[4] >> 3) & 1,
    }
    if (cap_length < 0x20 or cap_length > 0x100 or cap_length & 3 or
            version < 0x100 or version > 0x120 or result["SLOTS"] == 0 or
            result["INTRS"] == 0 or result["PORTS"] == 0 or
            result["DB"] < cap_length or result["RT"] < cap_length or
            result["DB"] >= EXPECTED_BYTES or result["RT"] >= EXPECTED_BYTES or
            (result["XECP"] and (result["XECP"] < 0x20 or
             result["XECP"] >= EXPECTED_BYTES))):
        raise ValueError("xHCI capability geometry is invalid")
    return result


def parse(text, expected_marker):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines.count(expected_marker) != 1:
        raise ValueError("exact USB trial marker not observed once")
    begin = _one(lines, "RPI5XNU:PCIEID:BEGIN ")
    expected_begin = ("RPI5XNU:PCIEID:BEGIN USB_XHCI_CAPS READ_ONLY "
                      "NO_RESET NO_PORT NO_IRQ NO_BME NO_DMA")
    if begin != expected_begin:
        raise ValueError("USB capability begin marker differs")

    state = _fields(_one(lines, "RPI5XNU:USB_XHCI_CAPS:STATE "))
    expected_state = {"STEP": 6, "ERROR": 0, "READS": EXPECTED_READS,
                      "PHYSICAL": EXPECTED_PHYSICAL, "BYTES": EXPECTED_BYTES}
    if any(_decimal(state, key) != value for key, value in expected_state.items()):
        raise ValueError("USB capability observation state differs")

    raw_rows = []
    for pass_index in range(2):
        fields = _fields(_one(lines, f"RPI5XNU:USB_XHCI_CAPS:RAW{pass_index} "))
        raw_rows.append([_hex(fields, key) for key in CAP_KEYS])
    if raw_rows[0] != raw_rows[1]:
        raise ValueError("double-read xHCI capability evidence differs")
    decoded = _decode(raw_rows[0])
    printed = _fields(_one(lines, "RPI5XNU:USB_XHCI_CAPS:DECODE "))
    for key, value in decoded.items():
        observed = _hex(printed, key) if key in ("VERSION", "DB", "RT", "XECP") else _decimal(printed, key)
        if observed != value:
            raise ValueError(f"printed xHCI decode differs for {key}")

    normalized = text.replace(
        "RPI5XNU:PCIEID:BEGIN USB_XHCI_CAPS READ_ONLY NO_RESET NO_PORT NO_IRQ NO_BME NO_DMA",
        "RPI5XNU:PCIEID:BEGIN FULL_PROVIDER PREFERRED_RAM_ONLY NO_QUEUE NO_BME NO_DMA",
        1)
    provider_result = provider.parse(normalized)
    return {
        "status": "pass",
        "controller": 0,
        "physical": EXPECTED_PHYSICAL,
        "window_bytes": EXPECTED_BYTES,
        "read_passes": 2,
        "reads": EXPECTED_READS,
        "raw": [f"{value:08x}" for value in raw_rows[0]],
        "decode": {key.lower(): value for key, value in decoded.items()},
        "read_only": True,
        "controller_reset": False,
        "port_reset": False,
        "bme": False,
        "dma": False,
        "irq": False,
        "full_provider": provider_result,
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
