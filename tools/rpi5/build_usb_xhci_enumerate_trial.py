#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the bounded RP1 USB0 K65 enumeration trial; never stage media."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from tools.rpi5 import build_gem_dma_batch_trial as composer
from tools.rpi5 import build_usb_xhci_noop_trial as parent
from tools.rpi5 import gem_dma_batch_leaf as leaf
from tools.rpi5 import usb_xhci_enumerate_trial_profile as profile


ROOT = composer.ROOT
PROFILE = "bcm2712-rp1-usb0-xhci-k65-enumeration-v1"
PARENT = ROOT / "build/rpi5/usb-xhci-noop-candidate-20261015-v11/manifest.json"
PARENT_SHA = "044d6a63897f8318bbe403b2c55dd7a9836eab6b5383b4963238c0e3d5d2d6e5"


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
    functions = leaf.functions(data)
    required = {
        "prepare": "__ZN20BCM2712USBXHCIMemory7prepareEv",
        "qualify": "__ZN20BCM2712USBXHCIMemory7qualifyEP26rpi5_pcie_released_windowsPK18rpi5_rp1_xhci_caps",
        "stage_enumeration": "__ZN20BCM2712USBXHCIMemory19stageK65EnumerationEPK18rpi5_rp1_xhci_capsP20rpi5_xhci_noop_imageP30rpi5_usb_xhci_enable_slot_planP30rpi5_usb_xhci_descriptor_batch",
        "stage_address": "__ZN20BCM2712USBXHCIMemory15stageK65AddressEhP33rpi5_usb_xhci_address_device_plan",
        "observe": "__ZNK20BCM2712USBXHCIMemory21observeCPUOwnedLayoutEP32rpi5_usb_xhci_memory_observation",
    }
    result = {}
    for label, symbol in required.items():
        if symbol not in functions:
            raise ValueError("USB enumeration provider method differs: " + label)
        offset, body = functions[symbol]
        result[label] = {"symbol": symbol, "file_offset": offset,
            "instruction_bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest()}
    return result


def configure():
    if sha(PARENT) != PARENT_SHA:
        raise ValueError("exact passed USB-3 parent changed")
    parent.configure()
    configured_core_sources = composer.core_sources

    def enumeration_core_sources():
        return list(dict.fromkeys([*configured_core_sources(),
            ROOT / "loader/rpi5/rp1_usb_xhci_port_reset.c",
            ROOT / "loader/rpi5/usb_xhci_device_context.c",
            ROOT / "loader/rpi5/usb_xhci_control_transfer.c",
            ROOT / "loader/rpi5/usb_hid_boot_descriptor.c",
            ROOT / "loader/rpi5/rp1_usb_xhci_enumerate.c"]))

    composer.PROFILE = PROFILE
    composer.profile = _Profile
    composer.sources = sources
    composer.core_sources = enumeration_core_sources
    composer.leaf.inspect = _provider_leaf
    return composer


def build(output=None):
    output = Path(output).resolve() if output else Path(tempfile.mkdtemp(
        prefix="usb-xhci-enumerate-candidate-", dir=ROOT / "build/rpi5"))
    output, manifest = configure().build(output)
    manifest.update(
        profile=PROFILE,
        passed_usb_noop_parent=str(PARENT),
        passed_usb_noop_parent_sha256=PARENT_SHA,
        controller=0,
        root_port=2,
        keyboard_usb_id="1b1c:1baf",
        allocation_bytes=0x50000,
        mapping_pages=20,
        polling_only=True,
        port_reset=True,
        enable_slot=True,
        address_device=True,
        descriptor_transfers=["device:8", "device:18", "config:9", "config:91"],
        boot_interface="03/01/01",
        endpoint="0x81",
        bme_enable=True,
        bme_restore_required=True,
        watchdog_check_limit=131072,
        interrupt_enable=False,
        vendor_interface_traffic=False,
        keyboard_interrupt_transfer=False,
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
