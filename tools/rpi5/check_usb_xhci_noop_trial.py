#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Fail-closed checker for the bounded RP1 USB0 polling No-Op image."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.rpi5 import build_usb_xhci_noop_trial as build


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(package):
    package = Path(package).resolve()
    errors = []
    if (package.parent != build.ROOT / "build/rpi5" or
            not package.name.startswith("usb-xhci-noop-candidate-")):
        errors.append("distinct USB No-Op package required")
    manifest_path = package / "manifest.json"
    if not manifest_path.is_file():
        return {"accepted": False, "errors": [*errors, "manifest absent"]}
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {"accepted": False, "errors": [*errors, f"manifest unreadable: {exc}"]}
    expected = {
        "profile": build.PROFILE,
        "passed_usb_lifecycle_parent_sha256": build.PARENT_SHA,
        "controller": 0,
        "allocation_bytes": 0x50000,
        "mapping_pages": 20,
        "command_trbs": 256,
        "event_trbs": 256,
        "scratchpad_buffers": 64,
        "polling_only": True,
        "one_noop_command": True,
        "allowed_pci_command_offset": 4,
        "allowed_pci_command_width": 2,
        "bme_enable": True,
        "bme_restore_required": True,
        "watchdog_check_limit": 131072,
        "inherited_watchdog_check_limit": 65536,
        "dma_activation": True,
        "interrupt_enable": False,
        "port_writes": False,
        "slot_commands": False,
        "keyboard_enumeration": False,
        "hardware_executed": False,
        "staged": False,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            errors.append(f"manifest {key} differs")
    for key in ("image", "kernel"):
        path = Path(manifest.get(key, ""))
        if not path.is_file() or sha(path) != manifest.get(key + "_sha256"):
            errors.append(key + " bytes differ")
    for table in ("inputs_sha256", "actual_headers_sha256", "generated_sha256"):
        for name, digest in manifest.get(table, {}).items():
            path = Path(name)
            if not path.is_file() or sha(path) != digest:
                errors.append(f"{table} changed: {name}")
                break
    for name in ("kernel-undefined.log", "loader-undefined.log"):
        path = package / name
        if not path.is_file() or path.read_bytes().strip():
            errors.append(name + " is not empty")
    overlay = package / "overlay"
    joined = "\n".join(path.read_text(errors="replace")
        for path in overlay.iterdir() if path.is_file()) if overlay.is_dir() else ""
    required = (
        "rpi5_rp1_usb_bme_enable", "rpi5_rp1_usb_bme_disable",
        "rpi5_rp1_xhci_run_noop", "stageNoOpCommand",
        "RPI5_RP1_USB_BME_DISABLING", "offset==rt+0x20",
        "offset==db", "dmaMemory->qualify(&trialWindows",
    )
    for token in required:
        if token not in joined:
            errors.append("composition token absent: " + token)
    forbidden = ("PortReg", "Enable Slot Command", "Address Device Command")
    for token in forbidden:
        if token in joined:
            errors.append("forbidden USB operation present: " + token)
    symbols_path = package / "kernel-symbols.log"
    symbols = symbols_path.read_text() if symbols_path.is_file() else ""
    for token in ("_rpi5_rp1_usb_bme_enable", "_rpi5_rp1_usb_bme_disable",
            "_rpi5_rp1_xhci_run_noop", "usbNoopWrite"):
        if token not in symbols:
            errors.append("linked USB symbol absent: " + token)
    image_path = Path(manifest.get("image", ""))
    image_strings = ""
    if image_path.is_file():
        result = subprocess.run(["strings", str(image_path)], capture_output=True,
            text=True, timeout=30)
        if result.returncode:
            errors.append("image strings failed")
        image_strings = result.stdout
    for token in ("RPI5XNU:USB_XHCI_NOOP:ENTRY",
            "RPI5XNU:USB_XHCI_NOOP:MEMORY",
            "RPI5XNU:USB_XHCI_NOOP:BME", "RPI5XNU:USB_XHCI_NOOP:RUN",
            "POLLING ONE_NOOP NO_PORT NO_IRQ BME_LEASE DMA"):
        if token not in image_strings:
            errors.append("linked image marker absent: " + token)
    return {
        "format": "rpi5-usb-xhci-noop-offline-check-v1",
        "accepted": not errors,
        "errors": errors,
        "package": str(package),
        "manifest_sha256": sha(manifest_path),
        "image_sha256": manifest.get("image_sha256"),
        "kernel_sha256": manifest.get("kernel_sha256"),
        "software_only": True,
        "hardware_executed": False,
        "claim": "one polling xHCI No-Op linked; no physical result",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    result = check(parser.parse_args().package)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["accepted"] else 1)
