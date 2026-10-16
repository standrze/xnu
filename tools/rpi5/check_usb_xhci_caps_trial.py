#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Fail-closed offline checker for the read-only RP1 USB0/xHCI image."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.rpi5 import build_usb_xhci_caps_trial as build


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(package):
    package = Path(package).resolve()
    errors = []
    if package.parent != build.ROOT / "build/rpi5" or not package.name.startswith("usb-xhci-caps-candidate-"):
        errors.append("distinct USB capability package required")
    manifest_path = package / "manifest.json"
    if not manifest_path.is_file():
        return {"accepted": False, "errors": [*errors, "manifest absent"]}
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {"accepted": False, "errors": [*errors, f"manifest unreadable: {exc}"]}
    expected = {
        "profile": build.PROFILE,
        "passed_full_provider_parent_sha256": build.PARENT_SHA,
        "controller": 0,
        "bar1_child_offset": 0x200000,
        "controller_window_bytes": 0x100000,
        "read_offsets": [i * 4 for i in range(8)],
        "read_passes": 2,
        "expected_reads": 16,
        "read_only": True,
        "usb_mmio_writes": False,
        "controller_reset": False,
        "port_reset": False,
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
    overlay = package / "overlay/BCM2712RP1GEMIdentifyTransport.inc"
    text = overlay.read_text() if overlay.is_file() else ""
    required = (
        "observePreparedFullProvider()",
        "observeUSB0Capabilities()",
        "rpi5_rp1_usb_bar1_range(0",
        "rpi5_rp1_xhci_caps_decode",
        "kIODirectionNone",
        "kIOMapInhibitCache",
        "usbCapabilityMap->unmap()",
        'uint32_t value=*reinterpret_cast<volatile uint32_t *>',
    )
    for token in required:
        if token not in text:
            errors.append("transport token absent: " + token)
    usb_body = text.split("bool BCM2712PCIePHYTransport::observeUSB0Capabilities()", 1)[-1]
    if usb_body.count('uint32_t value=*reinterpret_cast<volatile uint32_t *>') != 1:
        errors.append("USB capability read expression count differs")
    progress_path = package / "overlay/BCM2712PCIeIDTrialProgress.inc"
    progress = progress_path.read_text() if progress_path.is_file() else ""
    if not progress:
        errors.append("progress overlay absent")
    for token in (
        "BEGIN USB_XHCI_CAPS READ_ONLY NO_RESET NO_PORT NO_IRQ NO_BME NO_DMA",
        "RPI5XNU:USB_XHCI_CAPS:STATE",
        "RPI5XNU:USB_XHCI_CAPS:RAW0",
        "RPI5XNU:USB_XHCI_CAPS:RAW1",
        "RPI5XNU:USB_XHCI_CAPS:DECODE",
    ):
        if token not in progress:
            errors.append("progress token absent: " + token)
    symbols_path = package / "kernel-symbols.log"
    symbols = symbols_path.read_text() if symbols_path.is_file() else ""
    if not symbols:
        errors.append("kernel symbol log absent")
    for token in ("_rpi5_rp1_usb_bar1_range", "_rpi5_rp1_xhci_caps_decode",
            "observeUSB0Capabilities"):
        if token not in symbols:
            errors.append("linked symbol absent: " + token)
    loader_symbols_path = package / "loader-symbols.log"
    loader_symbols = loader_symbols_path.read_text() if loader_symbols_path.is_file() else ""
    if "rpi5_rp1_usb_device_handoff" not in loader_symbols:
        errors.append("linked loader USB Device handoff absent")
    image_path = Path(manifest.get("image", ""))
    if image_path.is_file():
        strings = subprocess.run(["strings", str(image_path)], capture_output=True,
            text=True, timeout=30)
        if strings.returncode:
            errors.append("image strings failed")
        image_strings = strings.stdout
    else:
        errors.append("image unavailable for linked-marker check")
        image_strings = ""
    for token in ("RPI5XNU:USB_XHCI_CAPS:ENTRY", "RPI5XNU:USB_XHCI_CAPS:DECODE",
            "RANGES=3 PAGES=70 GEM_CLOCK_USB0_ONLY DECLARATIONS_ONLY RP1_MMIO=0"):
        if token not in image_strings:
            errors.append("linked image marker absent: " + token)
    return {
        "format": "rpi5-usb-xhci-caps-offline-check-v1",
        "accepted": not errors,
        "errors": errors,
        "package": str(package),
        "manifest_sha256": sha(manifest_path),
        "image_sha256": manifest.get("image_sha256"),
        "kernel_sha256": manifest.get("kernel_sha256"),
        "software_only": True,
        "hardware_executed": False,
        "claim": "read-only observer linked and qualified; no physical USB result",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    result = check(parser.parse_args().package)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["accepted"] else 1)
