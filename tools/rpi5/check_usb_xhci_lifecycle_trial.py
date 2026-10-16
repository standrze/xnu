#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Fail-closed offline checker for the bounded RP1 USB0 xHCI lifecycle image."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.rpi5 import build_usb_xhci_lifecycle_trial as build


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(package):
    package = Path(package).resolve()
    errors = []
    if (package.parent != build.ROOT / "build/rpi5" or
            not package.name.startswith("usb-xhci-lifecycle-candidate-")):
        errors.append("distinct USB lifecycle package required")
    manifest_path = package / "manifest.json"
    if not manifest_path.is_file():
        return {"accepted": False, "errors": [*errors, "manifest absent"]}
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {"accepted": False, "errors": [*errors, f"manifest unreadable: {exc}"]}
    expected = {
        "profile": build.PROFILE,
        "passed_usb_caps_parent_sha256": build.PARENT_SHA,
        "controller": 0,
        "operational_base": 0x20,
        "allowed_write_offsets": [0x20],
        "halt_poll_limit": 200,
        "reset_poll_limit": 2500,
        "poll_interval_us": 100,
        "halt_reset_only": True,
        "usb_status_writes": False,
        "port_writes": False,
        "doorbell_writes": False,
        "runtime_writes": False,
        "bme_enable": False,
        "dma_activation": False,
        "irq_activation": False,
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
    firmware = Path(manifest.get("firmware", ""))
    if (not firmware.is_file() or
            manifest.get("firmware_sha256") !=
            "dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b" or
            sha(firmware) != manifest.get("firmware_sha256")):
        errors.append("required PCIe verifier firmware differs")
    trial_config = build.ROOT / "build/rpi5/display-allocate-config32-20261013/config.txt"
    if (not trial_config.is_file() or trial_config.stat().st_size != 299 or
            sha(trial_config) !=
            "359263f7f9776c6300ebeba344aeb0e2dd2d07df7064fb344b55236219f4cde7"):
        errors.append("required 32-bit display trial config differs")
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
    transport_path = package / "overlay/BCM2712RP1GEMIdentifyTransport.inc"
    transport = transport_path.read_text() if transport_path.is_file() else ""
    required = (
        "rpi5_rp1_xhci_halt_reset",
        "offset!=self->usbCapabilityObserved.capability_length",
        "usbLifecycleWrite",
        "usbCapabilityMap->unmap()",
    )
    for token in required:
        if token not in transport:
            errors.append("transport token absent: " + token)
    if "PortReg" in transport or "doorbell" in transport.lower():
        errors.append("forbidden USB lifecycle register class present")
    symbols_path = package / "kernel-symbols.log"
    symbols = symbols_path.read_text() if symbols_path.is_file() else ""
    for token in ("_rpi5_rp1_xhci_halt_reset", "usbLifecycleWrite"):
        if token not in symbols:
            errors.append("linked lifecycle symbol absent: " + token)
    image_path = Path(manifest.get("image", ""))
    if image_path.is_file():
        strings = subprocess.run(["strings", str(image_path)], capture_output=True,
            text=True, timeout=30)
        image_strings = strings.stdout if strings.returncode == 0 else ""
        if strings.returncode:
            errors.append("image strings failed")
    else:
        image_strings = ""
        errors.append("image unavailable for marker check")
    for token in (
        "RPI5XNU:USB_XHCI_LIFECYCLE:ENTRY",
        "RPI5XNU:USB_XHCI_LIFECYCLE:STATE",
        "HALT_RESET_ONLY NO_PORT NO_IRQ NO_BME NO_DMA",
        "RANGES=3 PAGES=70 GEM_CLOCK_USB0_ONLY DECLARATIONS_ONLY RP1_MMIO=0",
    ):
        if token not in image_strings:
            errors.append("linked image marker absent: " + token)
    return {
        "format": "rpi5-usb-xhci-lifecycle-offline-check-v1",
        "accepted": not errors,
        "errors": errors,
        "package": str(package),
        "manifest_sha256": sha(manifest_path),
        "image_sha256": manifest.get("image_sha256"),
        "kernel_sha256": manifest.get("kernel_sha256"),
        "software_only": True,
        "hardware_executed": False,
        "claim": "bounded xHCI halt/reset linked; no physical lifecycle result",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    result = check(parser.parse_args().package)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["accepted"] else 1)
