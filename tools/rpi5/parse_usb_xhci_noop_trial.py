#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Strict parser for one bounded RP1 USB0 xHCI polling No-Op trial."""
import argparse
import json
from pathlib import Path

from tools.rpi5 import parse_usb_xhci_caps_trial as caps


def parse(text, expected_marker):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines.count(expected_marker) != 1:
        raise ValueError("exact USB No-Op marker not observed once")
    begin = caps._one(lines, "RPI5XNU:PCIEID:BEGIN ")
    expected_begin = ("RPI5XNU:PCIEID:BEGIN USB_XHCI_NOOP POLLING "
        "ONE_NOOP NO_PORT NO_IRQ BME_LEASE DMA")
    if begin != expected_begin:
        raise ValueError("USB No-Op begin marker differs")

    memory = caps._fields(caps._one(lines, "RPI5XNU:USB_XHCI_NOOP:MEMORY "))
    expected_memory = {"PREPARE": 2, "STATE": 6, "PSTEP": 17,
        "PERROR": 0, "QSTEP": 12, "QERROR": 0, "TRIAL_STEP": 6,
        "TRIAL_ERROR": 0, "PAGES": 20, "BITMAP": 0xfffff, "RECORD": 1}
    for key, value in expected_memory.items():
        actual = caps._hex(memory, key) if key == "BITMAP" else caps._decimal(memory, key)
        if actual != value:
            raise ValueError("USB memory evidence differs: " + key)
    cpu = caps._decimal(memory, "CPU")
    physical = caps._decimal(memory, "PHYSICAL")
    rp1 = caps._decimal(memory, "RP1")
    if not cpu or not physical or not rp1 or ((cpu | physical | rp1) & 0x3fff):
        raise ValueError("USB memory address evidence differs")

    image = caps._fields(caps._one(lines, "RPI5XNU:USB_XHCI_NOOP:IMAGE "))
    if any(caps._decimal(image, key) != value for key, value in {
            "VERSION": 1, "ZEROED": 0x50000, "SCRATCH": 64,
            "EVENTS": 256}.items()):
        raise ValueError("USB No-Op image evidence differs")
    addresses = {key: caps._decimal(image, key) for key in
        ("DCBAA", "CR", "NOOP", "LINK", "ER", "ERST")}
    if (addresses["NOOP"] != addresses["CR"] or
            addresses["LINK"] != addresses["CR"] + 0xff0 or
            any(value < rp1 or value >= rp1 + 0x50000 for value in addresses.values())):
        raise ValueError("USB No-Op image layout differs")

    bme = caps._fields(caps._one(lines, "RPI5XNU:USB_XHCI_NOOP:BME "))
    original = caps._hex(bme, "ORIGINAL")
    enabled = caps._hex(bme, "ENABLED")
    current = caps._hex(bme, "CURRENT")
    if (caps._decimal(bme, "STATE") != 4 or caps._decimal(bme, "STEP") != 8 or
            caps._decimal(bme, "ERROR") != 0 or original & 4 or
            enabled != original | 4 or current != original or
            caps._decimal(bme, "READS") < 4 or caps._decimal(bme, "WRITES") != 2):
        raise ValueError("USB BME lease evidence differs")

    run = caps._fields(caps._one(lines, "RPI5XNU:USB_XHCI_NOOP:RUN "))
    run_decimal = {key: caps._decimal(run, key) for key in
        ("STEP", "ERROR", "READS", "WRITES", "POLLS", "DELAY_US",
         "DMA_CHECKS", "EVENT", "CC", "TYPE", "PSC")}
    run_hex = {key: caps._hex(run, key) for key in
        ("OP", "RT", "DB", "HALT_CMD", "HALT_STS")}
    if (run_decimal["STEP"] != 6 or run_decimal["ERROR"] != 0 or
            not 7 <= run_decimal["READS"] <= 407 or
            not 0 <= run_decimal["PSC"] <= 8 or
            run_decimal["DMA_CHECKS"] != 6 + run_decimal["PSC"] or
            run_decimal["WRITES"] != 16 + 2 * run_decimal["PSC"] or
            not 3 <= run_decimal["POLLS"] <= 10400 or
            run_decimal["DELAY_US"] > 1040000 or run_decimal["EVENT"] != addresses["NOOP"] or
            run_decimal["CC"] != 1 or run_decimal["TYPE"] != 33 or
            run_hex["OP"] != 0x20 or not run_hex["RT"] or not run_hex["DB"] or
            run_hex["HALT_CMD"] & 0x0f or not run_hex["HALT_STS"] & 1 or
            run_hex["HALT_STS"] & (4 | 0x800)):
        raise ValueError("USB No-Op completion evidence differs")

    capability = caps._fields(caps._one(
        lines, "RPI5XNU:USB_XHCI_CAPS:STATE "))
    if any(caps._decimal(capability, key) != value for key, value in {
            "STEP": 8, "ERROR": 0, "READS": caps.EXPECTED_READS,
            "PHYSICAL": caps.EXPECTED_PHYSICAL,
            "BYTES": caps.EXPECTED_BYTES}.items()):
        raise ValueError("USB capability composite state differs")
    raw_rows = []
    for pass_index in range(2):
        fields = caps._fields(caps._one(
            lines, f"RPI5XNU:USB_XHCI_CAPS:RAW{pass_index} "))
        raw_rows.append([caps._hex(fields, key) for key in caps.CAP_KEYS])
    if raw_rows[0] != raw_rows[1]:
        raise ValueError("double-read xHCI capability evidence differs")
    decoded = caps._decode(raw_rows[0])
    printed = caps._fields(caps._one(
        lines, "RPI5XNU:USB_XHCI_CAPS:DECODE "))
    for key, value in decoded.items():
        observed = caps._hex(printed, key) if key in (
            "VERSION", "DB", "RT", "XECP") else caps._decimal(printed, key)
        if observed != value:
            raise ValueError("printed xHCI decode differs for " + key)

    life_fields = caps._fields(caps._one(
        lines, "RPI5XNU:USB_XHCI_LIFECYCLE:STATE "))
    life_decimal = {key: caps._decimal(life_fields, key) for key in
        ("STEP", "ERROR", "READS", "WRITES", "POLLS", "DELAY_US")}
    life_hex = {key: caps._hex(life_fields, key) for key in
        ("OP", "CMD0", "STS0", "HALT_CMD", "HALT_STS", "RESET_CMD",
         "CMD1", "STS1")}
    initially_halted = bool(life_hex["STS0"] & 1)
    if (life_decimal["STEP"] != 5 or life_decimal["ERROR"] != 0 or
            life_decimal["WRITES"] != (1 if initially_halted else 2) or
            not 4 <= life_decimal["READS"] <= 5206 or
            not 2 <= life_decimal["POLLS"] <= 5200 or
            not 1000 <= life_decimal["DELAY_US"] <= 521000 or
            life_hex["OP"] != 0x20 or life_hex["STS0"] & 4 or
            life_hex["HALT_CMD"] != (life_hex["CMD0"] & ~1) or
            not life_hex["HALT_STS"] & 1 or life_hex["HALT_STS"] & 4 or
            life_hex["RESET_CMD"] != (life_hex["HALT_CMD"] | 2) or
            life_hex["CMD1"] & 3 or life_hex["STS1"] & (4 | 0x800) or
            not life_hex["STS1"] & 1):
        raise ValueError("USB lifecycle evidence differs")

    decode = caps._fields(caps._one(lines, "RPI5XNU:PCIEID:DECODE "))
    if (any(caps._decimal(decode, key) != value for key, value in {
            "CALL": 3, "RC": 0, "STATE": 8, "TXNS": 34, "WRITES": 2}.items()) or
            caps._hex(decode, "MAPPED") != 3 or
            caps._hex(decode, "UNMAPPED") != 3):
        raise ValueError("PCIe decode teardown evidence differs")
    for prefix, expected in (
            ("RPI5XNU:PCIEID:DECODE_COMMAND ",
             {"BEFORE": 0, "ENABLED": 2, "AFTER": 0}),
            ("RPI5XNU:PCIEID:ROOT_MEM_COMMAND ",
             {"BEFORE": 0, "LIVE": 2, "AFTER": 0})):
        fields = caps._fields(caps._one(lines, prefix))
        if any(caps._hex(fields, key) != value for key, value in expected.items()):
            raise ValueError("PCIe command teardown evidence differs")
    firmware = caps._fields(caps._one(lines, "RPI5XNU:PCIEID:FW "))
    watchdog = caps._fields(caps._one(lines, "RPI5XNU:PCIEID:PM "))
    if (caps._decimal(firmware, "AVAILABLE") != 1 or
            caps._decimal(firmware, "STAGE") != 8 or
            caps._decimal(firmware, "RC") != 0 or
            caps._decimal(firmware, "STATE") != 3 or
            not 0 < caps._decimal(firmware, "SEQ") < 65536 or
            caps._decimal(watchdog, "STAGE") != 7 or
            caps._decimal(watchdog, "RC") != 0 or
            caps._decimal(watchdog, "STATE") != 3 or
            not 65536 < caps._decimal(watchdog, "CHECKS") < 131072):
        raise ValueError("bounded firmware/watchdog completion differs")
    end = caps._fields(caps._one(lines, "RPI5XNU:PCIEID:END "))
    if (caps._decimal(end, "OK") != 1 or caps._decimal(end, "PHASE") != 5 or
            caps._decimal(end, "LAST") != 5 or caps._decimal(end, "LIFE") != 3 or
            caps._hex(end, "COMMAND") & 4 or caps._hex(end, "ID") != 0x00011de4):
        raise ValueError("terminal PCIe completion evidence differs")

    result = dict(status="pass", polling=True, one_noop_command=True,
        port_writes=False, slot_commands=False, irq=False, dma=True,
        bme_restored=True, memory={key.lower(): value for key, value in
            expected_memory.items()}, bme={"original": original,
            "enabled": enabled, "current": current,
            "reads": caps._decimal(bme, "READS"),
            "writes": caps._decimal(bme, "WRITES")},
        noop={**run_decimal, **run_hex},
        capability={key.lower(): value for key, value in decoded.items()},
        lifecycle={**{key.lower(): value for key, value in life_decimal.items()},
                   **{key.lower(): value for key, value in life_hex.items()}},
        watchdog_checks=caps._decimal(watchdog, "CHECKS"),
        terminal_ok=True)
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
