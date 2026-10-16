#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the one-CPU RP1 USB keyboard console candidate; never stage media."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from tools.rpi5 import build_gem_dma_batch_trial as composer
from tools.rpi5 import build_pcie_watchdog_owner as watchdog_owner
from tools.rpi5 import build_usb_xhci_enumerate_trial as enumeration
from tools.rpi5 import build_usb_xhci_keyboard_trial as parent
from tools.rpi5 import gem_dma_batch_leaf as leaf
from tools.rpi5 import usb_xhci_keyboard_console_trial_profile as profile


ROOT = composer.ROOT
PROFILE = "bcm2712-rp1-usb0-xhci-k65-console-v1"
PARENT = ROOT / "build/rpi5/usb-xhci-keyboard-candidate-20261015-v7/manifest.json"
PARENT_SHA = "4b73b5f4888665238fe9a4e2c666d5dc70f542ec42eda9b29ca3f960cca737fe"
IOKITBSD_TEMPLATE = ROOT / "build/rpi5/obj/DEVELOPMENT_ARM64_BCM2712/iokit/DEVELOPMENT/IOKitBSDInit.cpo.json"


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
    return list(dict.fromkeys([
        *parent.sources(), *profile.sources(), Path(__file__).resolve(),
        PARENT, IOKITBSD_TEMPLATE, ROOT / "iokit/bsddev/IOKitBSDInit.cpp",
        ROOT / "tools/rpi5/tests/test_usb_xhci_keyboard_console_trial_profile.py",
        ROOT / "tools/rpi5/tests/test_pcie_watchdog_console_lease.py",
    ]))


def _provider_leaf(data):
    result = enumeration._provider_leaf(data)
    functions = leaf.functions(data)
    matches = [(symbol, row) for symbol, row in functions.items()
        if "stageK65KeyboardStream" in symbol]
    if len(matches) != 1:
        raise ValueError("USB keyboard stream provider method differs")
    symbol, (offset, body) = matches[0]
    result["stage_keyboard_stream"] = {
        "symbol": symbol,
        "file_offset": offset,
        "instruction_bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }
    return result


def _iokitbsd_source():
    source = (ROOT / "iokit/bsddev/IOKitBSDInit.cpp").read_text()
    declaration_anchor = '''extern "C" {
#include <libkern/amfi/amfi.h>'''
    if source.count(declaration_anchor) != 1:
        raise ValueError("IOKit BSD declaration boundary differs")
    source = source.replace(declaration_anchor,
        '''extern "C" {
void rpi5_pcie_id_trial_start(void);
#include <libkern/amfi/amfi.h>''')
    dispatch_anchor = '''\tIOService::publishResource("IOBSD");

#if IOPOLLED_COREFILE'''
    if source.count(dispatch_anchor) != 1:
        raise ValueError("IOKit BSD publication boundary differs")
    return source.replace(dispatch_anchor,
        '''\tIOService::publishResource("IOBSD");
\trpi5_pcie_id_trial_start(); /* Platform and BSD console are ready. */

#if IOPOLLED_COREFILE''')


def configure():
    if sha(PARENT) != PARENT_SHA:
        raise ValueError("exact passed USB-5 parent changed")
    parent.configure()
    configured_core_sources = composer.core_sources
    configured_derived_sources = composer.derived_sources
    configured_kernel_objects = composer.kernel_objects
    configured_plan = composer.plan

    def console_core_sources():
        return list(dict.fromkeys([
            *configured_core_sources(),
            ROOT / "loader/rpi5/rp1_usb_xhci_keyboard_stream.c",
            ROOT / "loader/rpi5/pcie_watchdog_console_lease.c",
        ]))

    def console_derived_sources():
        result = configured_derived_sources()
        result["IOKitBSDInit-console.cpp"] = _iokitbsd_source().encode()
        return result

    def console_kernel_objects(output):
        objects, replacements, extras, added = configured_kernel_objects(output)
        base_objects = (composer.BASE / "kernel.display.filelist").read_text().splitlines()
        base_by_name = {}
        for item in base_objects:
            base_by_name.setdefault(Path(item).name, []).append(item)
        if (len(base_by_name.get("IOStartIOKit.cpo", [])) != 1 or
                len(base_by_name.get("IOKitBSDInit.cpo", [])) != 1):
            raise ValueError("exact base IOKit startup objects differ")
        early_iokit = base_by_name["IOStartIOKit.cpo"][0]
        late_iokit = base_by_name["IOKitBSDInit.cpo"][0]
        targets = {
            # The capability ancestry deliberately started diagnostics from
            # IOStartIOKit.  Restore the proven display kernel's exact early
            # object so no private IOService work races platform matching.
            "IOStartIOKit.cpp.o": early_iokit,
            "IOKitBSDInit.cpo": output / "IOKitBSDInit-console.o",
            "pe_fiq.c.o": output / "pe_fiq-console.o",
        }
        found = {}
        changed = []
        for item in objects:
            name = Path(item).name
            if name in targets:
                if name in found:
                    raise ValueError("ambiguous inherited console object: " + name)
                found[name] = item
                changed.append(str(targets[name]))
            else:
                changed.append(item)
        if set(found) != set(targets):
            raise ValueError("inherited console objects differ")
        updated = {}
        for key, value in replacements.items():
            name = Path(value).name
            if name == "IOStartIOKit.cpp.o":
                continue
            updated[key] = str(targets[name]) if name in targets else value
        updated[late_iokit] = str(targets["IOKitBSDInit.cpo"])
        replacements = updated
        return changed, replacements, extras, added

    def console_plan(output, tag):
        rows, scans = configured_plan(output, tag)
        link_index = next(index for index, row in enumerate(rows)
            if row[0] == "kernel-link")
        extra = []
        argv = lambda values: [str(value) for value in values]

        template = json.loads(IOKITBSD_TEMPLATE.read_text().strip().removesuffix(","))
        source = output / "IOKitBSDInit-console.cpp"
        flags = composer.old.display.compiler_flags(
            template["arguments"], ROOT / "iokit/bsddev/IOKitBSDInit.cpp")
        flags[1:1] = ["-iquote", str(ROOT / "iokit/bsddev")]
        label = "IOKitBSDInit-console"
        extra.append((label + "-scan", argv([*flags, "-M", "-MF",
            output / (label + ".scan.d"), source]), template["directory"]))
        extra.append((label + "-compile", argv([*flags, "-c", "-MD", "-MF",
            output / (label + ".d"), source, "-o",
            output / (label + ".o")]), template["directory"]))
        scans[label] = {"source": str(source), "cwd": str(template["directory"])}

        pe_template = json.loads(watchdog_owner.TEMPLATE.read_text().strip().removesuffix(","))
        pe_source = output / "overlay/pe_fiq.c"
        pe_object = output / "pe_fiq-console.o"
        pe_flags = watchdog_owner.command(pe_template, pe_source, pe_object)
        pe_flags[1:1] = ["-DRPI5_PCIE_IRQ_MASK=1", "-DRPI5_PCIE_FW_CLIENT=1"]
        pe_flags = pe_flags[:-2]
        label = "pe_fiq-console"
        extra.append((label + "-scan", argv([arg for arg in pe_flags if arg != "-c"] +
            ["-M", "-MG", "-MF", output / (label + ".scan.d")]),
            pe_template["directory"]))
        extra.append((label + "-compile", argv([*pe_flags, "-c", "-MD", "-MF",
            output / (label + ".d"), "-o", pe_object]),
            pe_template["directory"]))
        scans[label] = {"source": str(pe_source), "cwd": str(pe_template["directory"])}
        return rows[:link_index] + extra + rows[link_index:], scans

    composer.PROFILE = PROFILE
    composer.profile = _Profile
    composer.sources = sources
    composer.core_sources = console_core_sources
    composer.derived_sources = console_derived_sources
    composer.kernel_objects = console_kernel_objects
    composer.plan = console_plan
    composer.leaf.inspect = _provider_leaf
    return composer


def build(output=None):
    output = Path(output).resolve() if output else Path(tempfile.mkdtemp(
        prefix="usb-xhci-keyboard-console-candidate-", dir=ROOT / "build/rpi5"))
    output, manifest = configure().build(output)
    manifest.update(
        profile=PROFILE,
        passed_usb_keyboard_parent=str(PARENT),
        passed_usb_keyboard_parent_sha256=PARENT_SHA,
        controller=0,
        root_port=2,
        keyboard_usb_id="1b1c:1baf",
        polling_only=True,
        poll_interval_ms=16,
        stream_reports=255,
        interrupt_enable=False,
        console_sink="cons_cinput",
        serial_input=False,
        terminal_watchdog_service_preserved=True,
        console_watchdog_writes=0,
        bme_enable=True,
        bme_restore_required_on_live_exit=False,
        automatic_watchdog_recovery_required=True,
        iokit_matching_continues=True,
        zsh_present_in_inherited_root=True,
        keyboard_console_physical_pass=False,
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
