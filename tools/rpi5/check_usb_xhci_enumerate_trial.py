#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Fail-closed checker for the bounded RP1 USB0 K65 enumeration image."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.rpi5 import build_usb_xhci_enumerate_trial as build


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(package):
    package = Path(package).resolve()
    errors = []
    if (package.parent != build.ROOT / "build/rpi5" or
            not package.name.startswith("usb-xhci-enumerate-candidate-")):
        errors.append("distinct USB enumeration package required")
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
        "passed_usb_noop_parent_sha256": build.PARENT_SHA,
        "controller": 0,
        "root_port": 2,
        "keyboard_usb_id": "1b1c:1baf",
        "allocation_bytes": 0x50000,
        "mapping_pages": 20,
        "polling_only": True,
        "port_reset": True,
        "enable_slot": True,
        "address_device": True,
        "descriptor_transfers": ["device:8", "device:18", "config:9",
            "config:91"],
        "boot_interface": "03/01/01",
        "endpoint": "0x81",
        "bme_enable": True,
        "bme_restore_required": True,
        "watchdog_check_limit": 131072,
        "interrupt_enable": False,
        "vendor_interface_traffic": False,
        "keyboard_interrupt_transfer": False,
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
    replacements = manifest.get("replaced_objects", {})
    watchdog = [value for key, value in replacements.items()
        if Path(key).name == "pcie_watchdog_lease.c.o"]
    if len(watchdog) != 1 or Path(watchdog[0]).name != \
            "kernel-pcie_watchdog_lease_usb_noop.o":
        errors.append("finite USB watchdog replacement differs")

    overlay = package / "overlay"
    joined = "\n".join(path.read_text(errors="replace")
        for path in overlay.iterdir() if path.is_file()) if overlay.is_dir() else ""
    required = (
        "rpi5_rp1_xhci_enumerate_k65", "stageK65Enumeration",
        "stageK65Address", "offset==op+0x410", "controllerDoorbell",
        "slotDoorbell", "usbEnumerationSlot=slot", "value==1",
        "usbBMEGuard", "usbDMAGuard",
    )
    for token in required:
        if token not in joined:
            errors.append("composition token absent: " + token)
    symbols_path = package / "kernel-symbols.log"
    symbols = symbols_path.read_text() if symbols_path.is_file() else ""
    for token in ("_rpi5_rp1_xhci_enumerate_k65",
            "_rpi5_rp1_xhci_reset_k65_port",
            "_rpi5_usb_xhci_enable_slot_plan",
            "_rpi5_usb_xhci_address_k65_plan",
            "_rpi5_usb_k65_descriptor_batch",
            "_rpi5_usb_k65_boot_keyboard_identify",
            "_rpi5_rp1_usb_bme_enable", "_rpi5_rp1_usb_bme_disable"):
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
    for token in ("RPI5XNU:USB_XHCI_ENUM:ENTRY",
            "RPI5XNU:USB_XHCI_ENUM:MEMORY",
            "RPI5XNU:USB_XHCI_ENUM:BME", "RPI5XNU:USB_XHCI_ENUM:PLAN",
            "RPI5XNU:USB_XHCI_ENUM:RUN", "RPI5XNU:USB_XHCI_ENUM:PORT",
            "RPI5XNU:USB_XHCI_ENUM:DEVICE",
            "POLLING PORT2 SLOT ADDRESS EP0 K65 NO_IRQ BME_LEASE DMA"):
        if token not in image_strings:
            errors.append("linked image marker absent: " + token)
    return {
        "format": "rpi5-usb-xhci-enumerate-offline-check-v1",
        "accepted": not errors,
        "errors": errors,
        "package": str(package),
        "manifest_sha256": sha(manifest_path),
        "image_sha256": manifest.get("image_sha256"),
        "kernel_sha256": manifest.get("kernel_sha256"),
        "software_only": True,
        "hardware_executed": False,
        "claim": "polling K65 enumeration linked; no physical result",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    result = check(parser.parse_args().package)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["accepted"] else 1)
