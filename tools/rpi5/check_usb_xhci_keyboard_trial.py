#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Fail-closed checker for the bounded RP1 USB0 K65 first-report image."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.rpi5 import build_usb_xhci_keyboard_trial as build


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(package):
    package = Path(package).resolve()
    errors = []
    if (package.parent != build.ROOT / "build/rpi5" or
            not package.name.startswith("usb-xhci-keyboard-candidate-")):
        errors.append("distinct USB keyboard package required")
    manifest_path = package / "manifest.json"
    if not manifest_path.is_file():
        return {"accepted": False, "errors": [*errors, "manifest absent"]}
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {"accepted": False, "errors": [*errors,
            f"manifest unreadable: {exc}"]}
    expected = {
        "profile": build.PROFILE,
        "passed_usb_enumeration_parent_sha256": build.PARENT_SHA,
        "controller": 0,
        "root_port": 2,
        "keyboard_usb_id": "1b1c:1baf",
        "allocation_bytes": 0x50000,
        "mapping_pages": 20,
        "polling_only": True,
        "enumeration_leave_running": True,
        "controller_halt_after_report": True,
        "configure_endpoint": True,
        "endpoint": "0x81",
        "endpoint_id": 3,
        "endpoint_max_packet": 16,
        "endpoint_interval": 4,
        "setup_requests": ["set_configuration:1", "set_protocol:boot",
            "set_idle:1"],
        "report_bytes": 8,
        "report_count": 1,
        "bme_enable": True,
        "bme_restore_required": True,
        "watchdog_check_limit": 131072,
        "interrupt_enable": False,
        "vendor_interface_traffic": False,
        "console_injection": False,
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
    for table in ("inputs_sha256", "actual_headers_sha256",
            "generated_sha256"):
        for name, digest in manifest.get(table, {}).items():
            path = Path(name)
            if not path.is_file() or sha(path) != digest:
                errors.append(f"{table} changed: {name}")
                break
    for name in ("kernel-undefined.log", "loader-undefined.log"):
        path = package / name
        if not path.is_file() or path.read_bytes().strip():
            errors.append(name + " is not empty")
    if "stage_keyboard" not in manifest.get("actual_batch_leaf", {}):
        errors.append("Apple provider keyboard staging leaf absent")

    overlay = package / "overlay"
    joined = "\n".join(path.read_text(errors="replace")
        for path in overlay.iterdir() if path.is_file()) \
        if overlay.is_dir() else ""
    for token in (
            "stageK65Keyboard", "rpi5_rp1_xhci_k65_keyboard_input",
            "usbKeyboardEndpoint", "usbKeyboardSetup", "usbKeyboardInterrupt",
            "usbKeyboardObserved", "value==1||value==3",
            "usbBMEGuard", "usbDMAGuard"):
        if token not in joined:
            errors.append("composition token absent: " + token)
    symbols_path = package / "kernel-symbols.log"
    symbols = symbols_path.read_text() if symbols_path.is_file() else ""
    for token in (
            "_rpi5_rp1_xhci_enumerate_k65",
            "_rpi5_rp1_xhci_enumerate_k65_live",
            "_rpi5_usb_xhci_configure_k65_keyboard",
            "_rpi5_usb_k65_hid_boot_setup",
            "_rpi5_usb_xhci_k65_interrupt_plan",
            "_rpi5_rp1_xhci_k65_keyboard_input",
            "_rpi5_usb_hid_boot_keyboard_report",
            "_rpi5_rp1_usb_bme_enable", "_rpi5_rp1_usb_bme_disable"):
        if token not in symbols:
            errors.append("linked USB symbol absent: " + token)
    image_path = Path(manifest.get("image", ""))
    image_strings = ""
    if image_path.is_file():
        result = subprocess.run(["strings", str(image_path)],
            capture_output=True, text=True, timeout=30)
        if result.returncode:
            errors.append("image strings failed")
        image_strings = result.stdout
    for token in (
            "RPI5XNU:USB_XHCI_KBD:ENTRY",
            "RPI5XNU:USB_XHCI_KBD:KBD_PLAN",
            "RPI5XNU:USB_XHCI_KBD:KBD_RUN",
            "DCI3 HID_SETUP REPORT8 NO_IRQ BME_LEASE DMA"):
        if token not in image_strings:
            errors.append("linked image marker absent: " + token)
    return {
        "format": "rpi5-usb-xhci-keyboard-offline-check-v1",
        "accepted": not errors,
        "errors": errors,
        "package": str(package),
        "manifest_sha256": sha(manifest_path),
        "image_sha256": manifest.get("image_sha256"),
        "kernel_sha256": manifest.get("kernel_sha256"),
        "software_only": True,
        "hardware_executed": False,
        "claim": "polling K65 first-report path linked; no physical result",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    result = check(parser.parse_args().package)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["accepted"] else 1)
