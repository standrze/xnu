#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the read-only RP1 USB0/xHCI capability image; never stage media."""
import argparse
import json
from pathlib import Path
import tempfile

from tools.rpi5 import build_gem_dma_batch_trial as composer
from tools.rpi5 import build_gem_full_provider_trial as parent
from tools.rpi5 import usb_xhci_caps_trial_profile as profile


ROOT = composer.ROOT
PROFILE = "bcm2712-rp1-usb0-xhci-read-only-capabilities-v1"
PARENT = ROOT / "build/rpi5/gem-full-provider-trial-20261014-v13/manifest.json"
PARENT_SHA = "c91ed69c129103004ad92f2aa74424c8730203ea42040d697123ced46e88d402"


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
        raise ValueError("exact passed full-provider parent changed")
    parent.configure()
    configured_core_sources = composer.core_sources
    configured_plan = composer.plan
    def usb_core_sources():
        return [*configured_core_sources(), ROOT / "loader/rpi5/rp1_usb_xhci_caps.c"]
    def usb_plan(output, tag):
        rows, scans = configured_plan(output, tag)
        old_unit = "loader-rp1_device_handoff"
        new_unit = "loader-rp1_usb_device_handoff"
        old_source = str(ROOT / "loader/rpi5/rp1_device_handoff.c")
        new_source = str(ROOT / "loader/rpi5/rp1_usb_device_handoff.c")
        additions = []
        for suffix in ("-scan", "-compile"):
            label = old_unit + suffix
            matches = [row for row in rows if row[0] == label]
            if len(matches) != 1:
                raise ValueError("exact RP1 loader helper command absent")
            old_label, args, cwd = matches[0]
            if args.count(old_source) != 1:
                raise ValueError("exact RP1 loader helper source absent")
            cloned = [arg.replace(old_unit, new_unit).replace(old_source, new_source)
                for arg in args]
            additions.append((new_unit + suffix, cloned, cwd))
        if old_unit not in scans:
            raise ValueError("RP1 loader helper dependency scan absent")
        scans[new_unit] = dict(source=new_source, cwd=scans[old_unit]["cwd"])
        link_indexes = [index for index, row in enumerate(rows)
            if row[0] == "loader-link"]
        if len(link_indexes) != 1:
            raise ValueError("exact loader link command absent")
        link_index = link_indexes[0]
        label, args, cwd = rows[link_index]
        old_object = str(output / (old_unit + ".o"))
        new_object = str(output / (new_unit + ".o"))
        if args.count(old_object) != 1 or new_object in args or args.count("-o") != 1:
            raise ValueError("exact RP1 loader helper link owner changed")
        linked = list(args)
        linked.insert(linked.index("-o"), new_object)
        rows[link_index:link_index + 1] = [*additions, (label, linked, cwd)]
        return rows, scans
    composer.PROFILE = PROFILE
    composer.profile = _Profile
    composer.sources = sources
    composer.core_sources = usb_core_sources
    composer.plan = usb_plan
    return composer


def build(output=None):
    output = Path(output).resolve() if output else Path(tempfile.mkdtemp(
        prefix="usb-xhci-caps-trial-", dir=ROOT / "build/rpi5"))
    output, manifest = configure().build(output)
    manifest.update(
        profile=PROFILE,
        passed_full_provider_parent=str(PARENT),
        passed_full_provider_parent_sha256=PARENT_SHA,
        controller=0,
        bar1_child_offset=0x200000,
        controller_window_bytes=0x100000,
        read_offsets=[i * 4 for i in range(8)],
        read_passes=2,
        expected_reads=16,
        read_only=True,
        usb_mmio_writes=False,
        controller_reset=False,
        port_reset=False,
        bme_enable=False,
        dma_activation=False,
        irq_activation=False,
        keyboard_enumeration=False,
        hardware_executed=False,
        staged=False,
        generated_sha256={str(path): sha(path) for path in output.rglob("*")
            if path.is_file() and path.name != "manifest.json"},
    )
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
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
