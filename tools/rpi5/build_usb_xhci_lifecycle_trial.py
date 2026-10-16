#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the bounded RP1 USB0 xHCI halt/reset trial; never stage media."""
import argparse
import json
from pathlib import Path
import tempfile

from tools.rpi5 import build_gem_dma_batch_trial as composer
from tools.rpi5 import build_usb_xhci_caps_trial as parent
from tools.rpi5 import usb_xhci_lifecycle_trial_profile as profile


ROOT = composer.ROOT
PROFILE = "bcm2712-rp1-usb0-xhci-bounded-lifecycle-v1"
PARENT = ROOT / "build/rpi5/usb-xhci-caps-candidate-20261014-v4/manifest.json"
PARENT_SHA = "09cc872d8765553377e6121dec1b0b8c4a63d2f593616ecf4d7494de0149c956"


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


def configure():
    if sha(PARENT) != PARENT_SHA:
        raise ValueError("exact passed USB-1 parent changed")
    parent.configure()
    configured_core_sources = composer.core_sources
    def lifecycle_core_sources():
        return [*configured_core_sources(),
            ROOT / "loader/rpi5/rp1_usb_xhci_lifecycle.c"]
    composer.PROFILE = PROFILE
    composer.profile = _Profile
    composer.sources = sources
    composer.core_sources = lifecycle_core_sources
    return composer


def build(output=None):
    output = Path(output).resolve() if output else Path(tempfile.mkdtemp(
        prefix="usb-xhci-lifecycle-trial-", dir=ROOT / "build/rpi5"))
    output, manifest = configure().build(output)
    manifest.update(
        profile=PROFILE,
        passed_usb_caps_parent=str(PARENT),
        passed_usb_caps_parent_sha256=PARENT_SHA,
        controller=0,
        operational_base=0x20,
        allowed_write_offsets=[0x20],
        halt_poll_limit=200,
        reset_poll_limit=2500,
        poll_interval_us=100,
        halt_reset_only=True,
        usb_status_writes=False,
        port_writes=False,
        doorbell_writes=False,
        runtime_writes=False,
        bme_enable=False,
        dma_activation=False,
        irq_activation=False,
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
    print(json.dumps({
        "package": str(package),
        "manifest_sha256": sha(package / "manifest.json"),
        "kernel_sha256": manifest["kernel_sha256"],
        "image_sha256": manifest["image_sha256"],
    }, sort_keys=True))
