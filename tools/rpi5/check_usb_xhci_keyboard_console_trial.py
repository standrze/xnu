#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Fail-closed checker for the one-CPU RP1 USB keyboard console image."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.rpi5 import build_usb_xhci_keyboard_console_trial as build


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _run(args, errors, label):
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if result.returncode:
        errors.append(label + " failed")
        return ""
    return result.stdout


def _function(disassembly, name):
    anchor = "<" + name + ">:"
    if anchor not in disassembly:
        return ""
    body = disassembly.split(anchor, 1)[1]
    return body.split("\n\n", 1)[0]


def check(package):
    package = Path(package).resolve()
    errors = []
    if (package.parent != build.ROOT / "build/rpi5" or
            not package.name.startswith(
                "usb-xhci-keyboard-console-candidate-")):
        errors.append("distinct USB keyboard console package required")
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
        "passed_usb_keyboard_parent_sha256": build.PARENT_SHA,
        "bootargs": build.profile.BOOTARGS,
        "controller": 0,
        "root_port": 2,
        "keyboard_usb_id": "1b1c:1baf",
        "polling_only": True,
        "poll_interval_ms": 16,
        "stream_reports": 255,
        "interrupt_enable": False,
        "console_sink": "cons_cinput",
        "serial_input": False,
        "terminal_watchdog_service_preserved": True,
        "console_watchdog_writes": 0,
        "bme_enable": True,
        "bme_restore_required_on_live_exit": False,
        "automatic_watchdog_recovery_required": True,
        "iokit_matching_continues": True,
        "zsh_present_in_inherited_root": True,
        "keyboard_console_physical_pass": False,
        "hardware_executed": False,
        "staged": False,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            errors.append(f"manifest {key} differs")

    if not build.PARENT.is_file() or sha(build.PARENT) != build.PARENT_SHA:
        errors.append("passed USB keyboard parent changed")
    else:
        parent = json.loads(build.PARENT.read_text())
        if (manifest.get("root_sha256") != parent.get("root_sha256") or
                manifest.get("root_bytes") != parent.get("root_bytes")):
            errors.append("inherited zsh root differs")

    for key in ("image", "kernel"):
        path = Path(manifest.get(key, ""))
        if (not path.is_file() or path.parent != package or
                sha(path) != manifest.get(key + "_sha256")):
            errors.append(key + " bytes differ")
    for table in ("inputs_sha256", "actual_headers_sha256",
            "generated_sha256"):
        values = manifest.get(table)
        if not isinstance(values, dict) or not values:
            errors.append(table + " absent")
            continue
        for name, digest in values.items():
            path = Path(name)
            if not path.is_file() or sha(path) != digest:
                errors.append(f"{table} changed: {name}")
                break
    for name in ("kernel-undefined.log", "loader-undefined.log"):
        path = package / name
        if not path.is_file() or path.read_bytes().strip():
            errors.append(name + " is not empty")

    replacements = manifest.get("replaced_objects", {})
    replacement_names = {Path(key).name: Path(value).name
        for key, value in replacements.items()}
    if replacement_names.get("IOKitBSDInit.cpo") != "IOKitBSDInit-console.o":
        errors.append("IOKit-BSD replacement differs")
    if "IOStartIOKit.cpo" in replacement_names:
        errors.append("early IOKit-start replacement is forbidden")
    if replacement_names.get("pe_fiq.o") != "pe_fiq-console.o":
        errors.append("pexpert watchdog replacement differs")
    leaf = manifest.get("actual_batch_leaf", {})
    if set(leaf).isdisjoint({"stage_keyboard_stream"}):
        errors.append("Apple provider stream-staging leaf absent")

    overlay = package / "overlay"
    joined = "\n".join(path.read_text(errors="replace")
        for path in overlay.iterdir() if path.is_file()) \
        if overlay.is_dir() else ""
    for token in (
            "stageK65KeyboardStream", "rpi5_rp1_xhci_k65_keyboard_stream_start",
            "rpi5_rp1_xhci_k65_keyboard_stream_poll",
            "cons_cinput((char)bytes[index])", "IOSleep(16)",
            "usbKeyboardThread=current_thread()", "runUSBKeyboardConsole",
            "kernel_thread_start(rpi5_usb_console_entry",
            'serviceMatching("BCM2712PlatformExpert")', "waitForService(",
            "rpi5_terminal_watchdog_start()", "usbCapabilityMap",
            "pe_rpi5_watchdog_claim_usb_console",
            "pe_rpi5_watchdog_check_usb_console"):
        if token not in joined:
            errors.append("composition token absent: " + token)
    for token in ("startUSBKeyboardWorker", 'volatile("wfi"',
            "rpi5_rp1_usb_bme_disable(&usbBME)",
            "usbCapabilityMap->unmap()"):
        if token in joined:
            errors.append("forbidden live-console token present: " + token)

    irq_owner = overlay / "rpi5_pcie_irq_console_owner.inc"
    irq_text = irq_owner.read_text() if irq_owner.is_file() else ""
    if ("pe_rpi5_watchdog_check_usb_console" not in irq_text or
            "pe_rpi5_watchdog_check_pcie(" in irq_text):
        errors.append("IRQ owner is not chained to the console lease")
    pe_text = (overlay / "pe_fiq.c").read_text() \
        if (overlay / "pe_fiq.c").is_file() else ""
    for token in ('#include "rpi5_pcie_watchdog_console_owner.inc"',
            '#include "rpi5_pcie_irq_console_owner.inc"',
            '#include "rpi5_pcie_fw_console_owner.inc"'):
        if token not in pe_text:
            errors.append("console pexpert composition differs: " + token)

    symbols_path = package / "kernel-symbols.log"
    symbols = symbols_path.read_text() if symbols_path.is_file() else ""
    for token in (
            "_rpi5_rp1_xhci_k65_keyboard_stream_start",
            "_rpi5_rp1_xhci_k65_keyboard_stream_poll", "_cons_cinput",
            "_rpi5_terminal_watchdog_start", "_rpi5_pcie_id_trial_start",
            "_pe_rpi5_watchdog_claim_usb_console",
            "_pe_rpi5_watchdog_check_usb_console",
            "runUSBKeyboardConsole", "usbConsoleWorker"):
        if token not in symbols:
            errors.append("linked console symbol absent: " + token)

    image_path = Path(manifest.get("image", ""))
    strings = _run(["strings", str(image_path)], errors, "image strings") \
        if image_path.is_file() else ""
    for token in (
            "RPI5XNU:USB_XHCI_CONSOLE:ENTRY",
            "STREAM255 IRQ_OFF TERMINAL_WDOG CONS_CINPUT",
            "RPI5XNU:USB_XHCI_CONSOLE:DISPATCH",
            "RPI5XNU:USB_XHCI_CONSOLE:PLATFORM READY=",
            "RPI5XNU:USB_XHCI_CONSOLE:WORKER READY=1 IRQ=0 POLL_MS=16",
            "RPI5XNU:USB_XHCI_CONSOLE:WORKER_STOP"):
        if token not in strings:
            errors.append("linked image marker absent: " + token)

    unstripped = package / "kernel.unstripped"
    disassembly = _run(["xcrun", "objdump", "--disassemble", "--demangle",
        "--symbolize-operands", str(unstripped)], errors,
        "kernel disassembly") if unstripped.is_file() else ""
    start = _function(disassembly, "_rpi5_pcie_id_trial_start")
    entry = _function(disassembly, "rpi5_usb_console_entry(void*, int)")
    if "<_kernel_thread_start>" not in start or "runUSBKeyboardConsole" in start:
        errors.append("boot thread does not only dispatch the console worker")
    required_calls = ("<IOService::waitForService(OSDictionary*, mach_timespec*)>",
        "<_rpi5_terminal_watchdog_start>",
        "<BCM2712PCIePHYTransport::runUSBKeyboardConsole()>",
        "<_thread_terminate_self>")
    if any(token not in entry for token in required_calls):
        errors.append("same-thread console worker call chain differs")
    elif not (entry.index(required_calls[0]) < entry.index(required_calls[1]) <
            entry.index(required_calls[2])):
        errors.append("same-thread console worker call order differs")

    return {
        "format": "rpi5-usb-xhci-keyboard-console-offline-check-v1",
        "accepted": not errors,
        "errors": errors,
        "package": str(package),
        "manifest_sha256": sha(manifest_path),
        "image_sha256": manifest.get("image_sha256"),
        "kernel_sha256": manifest.get("kernel_sha256"),
        "software_only": True,
        "hardware_executed": False,
        "staged": False,
        "claim": "same-thread polling keyboard console linked; no physical keypress result",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    result = check(parser.parse_args().package)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["accepted"] else 1)
