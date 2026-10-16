#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the bounded RP1 USB0 polling No-Op trial; never stage media."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from tools.rpi5 import build_gem_dma_batch_trial as composer
from tools.rpi5 import build_usb_xhci_lifecycle_trial as parent
from tools.rpi5 import gem_dma_batch_leaf as leaf
from tools.rpi5 import usb_xhci_noop_trial_profile as profile


ROOT = composer.ROOT
PROFILE = "bcm2712-rp1-usb0-xhci-polling-noop-v1"
PARENT = ROOT / "build/rpi5/usb-xhci-lifecycle-candidate-20261014-v2/manifest.json"
PARENT_SHA = "9d9b7e1624409d77ffd5fe0dec3c43b963356143946c6abd11ea269f51c3851b"


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
        "stage": "__ZN20BCM2712USBXHCIMemory16stageNoOpCommandEPK18rpi5_rp1_xhci_capsP20rpi5_xhci_noop_image",
        "observe": "__ZNK20BCM2712USBXHCIMemory21observeCPUOwnedLayoutEP32rpi5_usb_xhci_memory_observation",
    }
    result = {}
    for label, symbol in required.items():
        if symbol not in functions:
            raise ValueError("USB provider compiled method absent: " + label)
        offset, body = functions[symbol]
        result[label] = {"symbol": symbol, "file_offset": offset,
            "instruction_bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest()}
    return result


def configure():
    if sha(PARENT) != PARENT_SHA:
        raise ValueError("exact passed USB lifecycle parent changed")
    parent.configure()
    configured_core_sources = composer.core_sources
    configured_kernel_objects = composer.kernel_objects

    def noop_core_sources():
        return [*configured_core_sources(),
            ROOT / "iokit/Kernel/rpi5_rp1_dma_route.c",
            ROOT / "loader/rpi5/rp1_usb_xhci_dma_layout.c",
            ROOT / "loader/rpi5/rp1_usb_xhci_noop.c",
            ROOT / "loader/rpi5/rp1_usb_xhci_noop_run.c",
            ROOT / "loader/rpi5/rp1_usb_bme.c",
            ROOT / "loader/rpi5/pcie_watchdog_lease_usb_noop.c"]

    def noop_kernel_objects(output):
        result, replacements, extras, added = configured_kernel_objects(output)
        old = [path for path in result
            if Path(path).name == "pcie_watchdog_lease.c.o"]
        replacement = str(output / "kernel-pcie_watchdog_lease_usb_noop.o")
        if (len(old) != 1 or result.count(replacement) != 1 or
                added.count(replacement) != 1):
            raise ValueError("exact watchdog object replacement changed")
        result = [replacement if path == old[0] else path for path in result
            if path != replacement]
        replacements[old[0]] = replacement
        added.remove(replacement)
        if len(result) != len(set(result)):
            raise ValueError("duplicate watchdog replacement")
        return result, replacements, extras, added

    composer.PROFILE = PROFILE
    composer.profile = _Profile
    composer.sources = sources
    composer.core_sources = noop_core_sources
    composer.kernel_objects = noop_kernel_objects
    composer.leaf.inspect = _provider_leaf
    return composer


def build(output=None):
    output = Path(output).resolve() if output else Path(tempfile.mkdtemp(
        prefix="usb-xhci-noop-candidate-", dir=ROOT / "build/rpi5"))
    output, manifest = configure().build(output)
    manifest.update(
        profile=PROFILE,
        passed_usb_lifecycle_parent=str(PARENT),
        passed_usb_lifecycle_parent_sha256=PARENT_SHA,
        controller=0,
        allocation_bytes=0x50000,
        mapping_pages=20,
        command_trbs=256,
        event_trbs=256,
        scratchpad_buffers=64,
        polling_only=True,
        one_noop_command=True,
        allowed_pci_command_offset=4,
        allowed_pci_command_width=2,
        bme_enable=True,
        bme_restore_required=True,
        watchdog_check_limit=131072,
        inherited_watchdog_check_limit=65536,
        dma_activation=True,
        interrupt_enable=False,
        port_writes=False,
        slot_commands=False,
        keyboard_enumeration=False,
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
