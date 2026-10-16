#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Strict parser for one observation-only full-provider board transcript."""
import argparse
import json
from pathlib import Path
import re


RP1_GEM_ALL_INTERRUPTS_MASKED = "3fffffff"


def _one(lines, prefix):
    found = [line for line in lines if line.startswith(prefix)]
    if len(found) != 1:
        raise ValueError(f"expected one {prefix!r} record, got {len(found)}")
    return found[0]


def _fields(line):
    return {key: value for key, value in re.findall(
        r"([A-Z][A-Z0-9_]*)=([0-9a-fA-F-]+)", line)}


def _number(value, base=10):
    return int(value, base)


def parse(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    begin = _one(lines, "RPI5XNU:PCIEID:BEGIN ")
    if "FULL_PROVIDER PREFERRED_RAM_ONLY NO_QUEUE NO_BME NO_DMA" not in begin:
        raise ValueError("full-provider inert begin marker differs")
    end = _fields(_one(lines, "RPI5XNU:PCIEID:END "))
    if end.get("OK") != "1" or _number(end.get("COMMAND", "4"), 16) & 4:
        raise ValueError("trial did not complete with endpoint BME clear")

    owner = _fields(_one(lines, "RPI5XNU:PCIEID:FULL_OWNER "))
    required_owner = {"PREPARE": "2", "STATE": "4", "ATTEMPTED": "1",
        "ACTIVE": "0", "REVOKED": "0", "DISABLED": "0", "RECORD": "1"}
    if any(owner.get(key) != value for key, value in required_owner.items()):
        raise ValueError("retained provider owner record differs")

    route = _fields(_one(lines, "RPI5XNU:PCIEID:FULL_ROUTE "))
    cpu = _number(route.get("CPU", "0")); physical = _number(route.get("PHYSICAL", "0"))
    rp1 = _number(route.get("RP1", "0")); byte_count = _number(route.get("BYTES", "0"))
    if not cpu or not physical or not rp1 or byte_count != 0x48000 or route.get("BITMAP") != "3ffff":
        raise ValueError("full-provider route differs")
    layout = _fields(_one(lines, "RPI5XNU:PCIEID:FULL_LAYOUT "))
    expected_layout = {"VERSION": "2", "PAGES": "18", "RINGS": "2", "PACKETS": "128",
        "PACKET_BYTES": "2048", "MAPPED": "262144", "CPU_OWNED": "128"}
    if any(layout.get(key) != value for key, value in expected_layout.items()):
        raise ValueError("full-provider layout differs")

    before = _fields(_one(lines, "RPI5XNU:PCIEID:FULL_QUIESCE_BEFORE "))
    after = _fields(_one(lines, "RPI5XNU:PCIEID:FULL_QUIESCE_AFTER "))
    if before.get("NCR") != "00000000" or after.get("NCR") != "00000000" or \
            before.get("IMR") != RP1_GEM_ALL_INTERRUPTS_MASKED or \
            after.get("IMR") != RP1_GEM_ALL_INTERRUPTS_MASKED:
        raise ValueError("GEM engine or interrupt mask is not quiescent")
    if any(before.get(key) != after.get(key) for key in ("RBQP", "TBQP", "TBQPH", "RBQPH")):
        raise ValueError("queue register changed during observation")

    for prefix in ("RPI5XNU:PCIEID:DECODE_COMMAND ", "RPI5XNU:PCIEID:ROOT_MEM_COMMAND "):
        values = _fields(_one(lines, prefix))
        if not values or any(_number(value, 16) & 4 for value in values.values()):
            raise ValueError("endpoint bus mastering appeared in " + prefix)

    page_lines = [line for line in lines if line.startswith("RPI5XNU:PCIEID:FULL_PAGE ")]
    if len(page_lines) != 18:
        raise ValueError("exact 18 page records required")
    par_mask = 0x0000FFFFFFFFF000
    for index, line in enumerate(page_lines):
        page = _fields(line)
        pa = physical + index * 0x4000
        if (_number(page.get("INDEX", "-1")) != index or page.get("ATTR") != "6" or
                page.get("RETAINED_OK") != "1" or page.get("STATIC_OK") != "1" or
                _number(page.get("RETAINED", "0")) != cpu + index * 0x4000 or
                _number(page.get("PA", "0")) != pa or not _number(page.get("STATIC", "0"))):
            raise ValueError(f"page {index} geometry differs")
        for key in ("RETAINED_R", "RETAINED_W", "STATIC_R", "STATIC_W"):
            par = _number(page.get(key, "0"))
            if par >> 56 != 0x44 or (par & par_mask) != (pa & par_mask):
                raise ValueError(f"page {index} {key} translation differs")

    span_lines = [line for line in lines if line.startswith("RPI5XNU:PCIEID:FULL_SPAN ")]
    if len(span_lines) != 128:
        raise ValueError("exact 128 packet-span records required")
    for index, line in enumerate(span_lines):
        span = _fields(line); offset = 0x8000 + index * 0x800
        if (_number(span.get("INDEX", "-1")) != index or
                _number(span.get("CPU", "0")) != cpu + offset or
                _number(span.get("RP1", "0")) != rp1 + offset or
                span.get("BYTES") != "2048" or
                _number(span.get("PAGE", "-1")) != offset // 0x4000 or
                span.get("OWNER") != "1"):
            raise ValueError(f"packet span {index} differs")
    return {"status": "pass", "provider_bytes": byte_count,
        "page_records": 18, "packet_span_records": 128,
        "detailed_evidence_records": 146, "bme": False,
        "gem_imr": RP1_GEM_ALL_INTERRUPTS_MASKED, "interrupts_masked": True,
        "queues_changed": False,
        "dma": False, "irq": False, "packets_submitted": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = parse(args.transcript.read_text(errors="replace"))
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded)
    print(encoded, end="")
