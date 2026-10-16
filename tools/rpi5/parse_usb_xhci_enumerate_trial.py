#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Strict parser for one bounded RP1 USB0 K65 polling-enumeration trial."""
import argparse
import json
from pathlib import Path

from tools.rpi5 import parse_usb_xhci_caps_trial as caps


def parse(text, expected_marker):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines.count(expected_marker) != 1:
        raise ValueError("exact USB enumeration marker not observed once")
    if caps._one(lines, "RPI5XNU:PCIEID:BEGIN ") != (
            "RPI5XNU:PCIEID:BEGIN USB_XHCI_ENUM POLLING PORT2 SLOT "
            "ADDRESS EP0 K65 NO_IRQ BME_LEASE DMA"):
        raise ValueError("USB enumeration inherited begin marker differs")

    memory = caps._fields(caps._one(lines, "RPI5XNU:USB_XHCI_ENUM:MEMORY "))
    expected_memory = {"PREPARE": 2, "STATE": 6, "PSTEP": 17,
        "PERROR": 0, "QSTEP": 12, "QERROR": 0, "TRIAL_STEP": 6,
        "TRIAL_ERROR": 0, "PAGES": 20, "BITMAP": 0xfffff, "RECORD": 1}
    for key, value in expected_memory.items():
        actual = caps._hex(memory, key) if key == "BITMAP" else \
            caps._decimal(memory, key)
        if actual != value:
            raise ValueError("USB memory evidence differs: " + key)
    rp1 = caps._decimal(memory, "RP1")
    if not rp1 or rp1 & 0x3fff:
        raise ValueError("USB DMA base differs")

    image = caps._fields(caps._one(lines, "RPI5XNU:USB_XHCI_ENUM:IMAGE "))
    if any(caps._decimal(image, key) != value for key, value in {
            "VERSION": 1, "ZEROED": 0x50000, "SCRATCH": 64,
            "EVENTS": 256}.items()):
        raise ValueError("USB base image differs")
    addresses = {key: caps._decimal(image, key) for key in
        ("DCBAA", "CR", "NOOP", "LINK", "ER", "ERST")}
    if (addresses["NOOP"] != addresses["CR"] or
            addresses["LINK"] != addresses["CR"] + 0xff0 or
            any(value < rp1 or value >= rp1 + 0x50000
                for value in addresses.values())):
        raise ValueError("USB base image layout differs")

    plan = caps._fields(caps._one(lines, "RPI5XNU:USB_XHCI_ENUM:PLAN "))
    if (caps._decimal(plan, "ENABLE") != addresses["CR"] or
            caps._hex(plan, "ENABLE_CTL") != 0x2401 or
            caps._decimal(plan, "TD_COUNT") != 4 or
            caps._decimal(plan, "TRB_COUNT") != 12 or
            caps._decimal(plan, "RING") != rp1 + 0x46000):
        raise ValueError("USB enumeration plan differs")

    run = caps._fields(caps._one(lines, "RPI5XNU:USB_XHCI_ENUM:RUN "))
    rd = {key: caps._decimal(run, key) for key in
        ("STEP", "ERROR", "READS", "WRITES", "POLLS", "DELAY_US",
         "DMA_CHECKS", "SLOT", "PSC", "EVENT_INDEX")}
    rh = {key: caps._hex(run, key) for key in ("HALT_CMD", "HALT_STS")}
    if (rd["STEP"] != 10 or rd["ERROR"] != 0 or
            not 7 <= rd["READS"] <= 407 or not 1 <= rd["SLOT"] <= 64 or
            not 0 <= rd["PSC"] <= 8 or rd["EVENT_INDEX"] != 6 + rd["PSC"] or
            not 14 <= rd["DMA_CHECKS"] <= 24 or
            not 28 <= rd["WRITES"] <= 48 or
            not 8 <= rd["POLLS"] <= 11000 or rd["DELAY_US"] > 1100000 or
            rh["HALT_CMD"] & 0x0f or not rh["HALT_STS"] & 1 or
            rh["HALT_STS"] & (4 | 0x800)):
        raise ValueError("USB enumeration run differs")

    port = caps._fields(caps._one(lines, "RPI5XNU:USB_XHCI_ENUM:PORT "))
    pd = {key: caps._decimal(port, key) for key in
        ("STEP", "ERROR", "PORT", "SPEED", "LINK", "WRITES", "POLLS")}
    ph = {key: caps._hex(port, key) for key in
        ("OFFSET", "BEFORE", "AFTER", "FINAL")}
    if (pd != {"STEP": 4, "ERROR": 0, "PORT": 2, "SPEED": 3,
            "LINK": 0, "WRITES": 2, "POLLS": pd["POLLS"]} or
            not 1 <= pd["POLLS"] <= 2500 or ph["OFFSET"] != 0x430 or
            ph["BEFORE"] & 0x201 != 0x201 or
            ph["AFTER"] & 0x200003 != 0x200003 or ph["AFTER"] & 0x10 or
            ph["FINAL"] & 0x203 != 0x203 or ph["FINAL"] & 0x200010):
        raise ValueError("USB port reset evidence differs")

    device = caps._fields(caps._one(lines, "RPI5XNU:USB_XHCI_ENUM:DEVICE "))
    exact_decimal = {"SLOT": rd["SLOT"], "PORT": 2, "SPEED": 3,
        "EP0": 64, "ADDRESS_CMD": addresses["CR"] + 16,
        "CONFIG_BYTES": 91, "INTERFACES": 3, "INTERFACE": 0,
        "PACKET": 16, "INTERVAL": 4, "REPORT": 154}
    if (any(caps._decimal(device, key) != value
            for key, value in exact_decimal.items()) or
            caps._hex(device, "VENDOR") != 0x1b1c or
            caps._hex(device, "PRODUCT") != 0x1baf or
            caps._hex(device, "USB") != 0x0200 or
            caps._hex(device, "ENDPOINT") != 0x81):
        raise ValueError("USB K65 identity differs")

    bme = caps._fields(caps._one(lines, "RPI5XNU:USB_XHCI_ENUM:BME "))
    original, enabled, current = (caps._hex(bme, key)
        for key in ("ORIGINAL", "ENABLED", "CURRENT"))
    if (caps._decimal(bme, "STATE") != 4 or caps._decimal(bme, "STEP") != 8 or
            caps._decimal(bme, "ERROR") != 0 or original & 4 or
            enabled != original | 4 or current != original or
            caps._decimal(bme, "WRITES") != 2):
        raise ValueError("USB BME lease evidence differs")

    capability = caps._fields(caps._one(lines, "RPI5XNU:USB_XHCI_CAPS:STATE "))
    if any(caps._decimal(capability, key) != value for key, value in {
            "STEP": 8, "ERROR": 0, "READS": caps.EXPECTED_READS,
            "PHYSICAL": caps.EXPECTED_PHYSICAL,
            "BYTES": caps.EXPECTED_BYTES}.items()):
        raise ValueError("USB capability state differs")
    life = caps._fields(caps._one(lines,
        "RPI5XNU:USB_XHCI_LIFECYCLE:STATE "))
    if (caps._decimal(life, "STEP") != 5 or caps._decimal(life, "ERROR") != 0 or
            caps._hex(life, "OP") != 0x20 or caps._hex(life, "CMD1") & 3 or
            caps._hex(life, "STS1") & (4 | 0x800) or
            not caps._hex(life, "STS1") & 1):
        raise ValueError("USB lifecycle state differs")

    decode = caps._fields(caps._one(lines, "RPI5XNU:PCIEID:DECODE "))
    if (any(caps._decimal(decode, key) != value for key, value in {
            "CALL": 3, "RC": 0, "STATE": 8, "TXNS": 34,
            "WRITES": 2}.items()) or caps._hex(decode, "MAPPED") != 3 or
            caps._hex(decode, "UNMAPPED") != 3):
        raise ValueError("PCIe teardown differs")
    firmware = caps._fields(caps._one(lines, "RPI5XNU:PCIEID:FW "))
    watchdog = caps._fields(caps._one(lines, "RPI5XNU:PCIEID:PM "))
    if (caps._decimal(firmware, "STAGE") != 8 or
            caps._decimal(firmware, "RC") != 0 or
            caps._decimal(watchdog, "STAGE") != 7 or
            caps._decimal(watchdog, "RC") != 0 or
            not 65536 < caps._decimal(watchdog, "CHECKS") < 131072):
        raise ValueError("watchdog completion differs")
    end = caps._fields(caps._one(lines, "RPI5XNU:PCIEID:END "))
    if (caps._decimal(end, "OK") != 1 or caps._decimal(end, "PHASE") != 5 or
            caps._decimal(end, "LAST") != 5 or caps._decimal(end, "LIFE") != 3 or
            caps._hex(end, "COMMAND") & 4 or caps._hex(end, "ID") != 0x00011de4):
        raise ValueError("terminal PCIe completion differs")
    return {"status": "pass", "polling": True, "root_port": 2,
        "slot": rd["SLOT"], "descriptor_transfers": 4,
        "keyboard": {"vendor": 0x1b1c, "product": 0x1baf,
            "interface": 0, "endpoint": 0x81},
        "port_status_events": rd["PSC"], "bme_restored": True,
        "irq": False, "controller_halted": True,
        "watchdog_checks": caps._decimal(watchdog, "CHECKS"),
        "terminal_ok": True}


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
