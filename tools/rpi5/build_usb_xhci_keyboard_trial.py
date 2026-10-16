#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the bounded RP1 USB0 K65 first-report trial; never stage media."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from tools.rpi5 import build_gem_dma_batch_trial as composer
from tools.rpi5 import build_usb_xhci_enumerate_trial as parent
from tools.rpi5 import gem_dma_batch_leaf as leaf
from tools.rpi5 import usb_xhci_keyboard_trial_profile as profile


ROOT = composer.ROOT
PROFILE = "bcm2712-rp1-usb0-xhci-k65-first-report-v1"
PARENT = ROOT / "build/rpi5/usb-xhci-enumerate-candidate-20261015-v4/manifest.json"
PARENT_SHA = "5928699eab7e62f07d2bc061bf37fbe11585afaeae2ae9c2fb4a9da900ab4dcb"


class _Profile:
    derive = staticmethod(profile.derive)
    sources = staticmethod(profile.sources)
    marker = staticmethod(profile.marker)
    loader = staticmethod(profile.loader)
    psci = staticmethod(profile.psci)
    BOOTARGS = profile.BOOTARGS


def sha(path):
    return composer.sha(path)


def sources():
    return list(dict.fromkeys([*parent.sources(), *profile.sources(),
        Path(__file__).resolve(), PARENT]))


def _provider_leaf(data):
    result = parent._provider_leaf(data)
    functions = leaf.functions(data)
    matches = [symbol for symbol in functions if "stageK65Keyboard" in symbol]
    if len(matches) != 1:
        raise ValueError("USB keyboard provider method differs")
    symbol = matches[0]
    offset, body = functions[symbol]
    result["stage_keyboard"] = {"symbol": symbol, "file_offset": offset,
        "instruction_bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest()}
    return result


def configure():
    if sha(PARENT) != PARENT_SHA:
        raise ValueError("exact passed USB-4 parent changed")
    parent.configure()
    configured_core_sources = composer.core_sources

    def keyboard_core_sources():
        return list(dict.fromkeys([*configured_core_sources(),
            ROOT / "loader/rpi5/usb_hid_boot_keyboard.c",
            ROOT / "loader/rpi5/usb_hid_boot_setup.c",
            ROOT / "loader/rpi5/usb_xhci_keyboard_endpoint.c",
            ROOT / "loader/rpi5/rp1_usb_xhci_keyboard_input.c"]))

    composer.PROFILE = PROFILE
    composer.profile = _Profile
    composer.sources = sources
    composer.core_sources = keyboard_core_sources
    composer.leaf.inspect = _provider_leaf
    return composer


def build(output=None):
    output = Path(output).resolve() if output else Path(tempfile.mkdtemp(
        prefix="usb-xhci-keyboard-candidate-", dir=ROOT / "build/rpi5"))
    output, manifest = configure().build(output)
    manifest.update(
        profile=PROFILE,
        passed_usb_enumeration_parent=str(PARENT),
        passed_usb_enumeration_parent_sha256=PARENT_SHA,
        controller=0,
        root_port=2,
        keyboard_usb_id="1b1c:1baf",
        allocation_bytes=0x50000,
        mapping_pages=20,
        polling_only=True,
        enumeration_leave_running=True,
        controller_halt_after_report=True,
        configure_endpoint=True,
        endpoint="0x81",
        endpoint_id=3,
        endpoint_max_packet=16,
        endpoint_interval=4,
        setup_requests=["set_configuration:1", "set_protocol:boot",
            "set_idle:1"],
        report_bytes=8,
        report_count=1,
        bme_enable=True,
        bme_restore_required=True,
        watchdog_check_limit=131072,
        interrupt_enable=False,
        vendor_interface_traffic=False,
        console_injection=False,
        hardware_executed=False,
        staged=False,
        generated_sha256={str(path): sha(path) for path in output.rglob("*")
            if path.is_file() and path.name != "manifest.json"},
    )
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return output, manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    package, manifest = build(parser.parse_args().output_dir)
    print(json.dumps({"package": str(package),
        "manifest_sha256": sha(package / "manifest.json"),
        "kernel_sha256": manifest["kernel_sha256"],
        "image_sha256": manifest["image_sha256"]}, sort_keys=True))
