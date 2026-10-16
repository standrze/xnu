#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the observation-only full-provider board image; never stage media."""
import argparse
import json
from pathlib import Path
import tempfile

from tools.rpi5 import build_gem_cpu_ring_physmap_trial as base
from tools.rpi5 import build_gem_dma_batch_trial as composer
from tools.rpi5 import gem_full_provider_trial_profile as profile
from tools.rpi5 import gem_dma_batch_leaf as leaf

ROOT = composer.ROOT
PROFILE = "bcm2712-gem-full-provider-observation-trial-v9"
PROVIDER = ROOT / "build/rpi5/gem-full-provider-candidate-20261014-v7/manifest.json"
PROVIDER_SHA = "ae3ddb3a517a749fa77e7a5d8212a2a40d7d3484041bf81815c174d72553e60f"


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
    own = [Path(__file__).resolve(), Path(profile.__file__).resolve(), PROVIDER,
        ROOT / "tools/rpi5/check_gem_full_provider_trial.py",
        ROOT / "tools/rpi5/parse_gem_full_provider_trial.py",
        ROOT / "tools/rpi5/tests/test_gem_full_provider_trial.py"]
    return list(dict.fromkeys([*base.sources(), *profile.sources(), *own]))


def parents():
    result = base.parents()
    replaced = {str(ROOT / "iokit/Kernel/BCM2712GEMDMAMemory.h"),
        str(ROOT / "iokit/Kernel/BCM2712GEMDMAMemory.cpp")}
    for manifest in result:
        for table in ("inputs_sha256", "actual_headers_sha256"):
            for path in replaced & set(manifest.get(table, {})):
                manifest[table][path] = sha(path)
    return result


def _provider_leaf(data):
    functions = leaf.functions(data)
    required = {
        "prepare": "__ZN19BCM2712GEMDMAMemory7prepareEv",
        "qualify": "__ZN19BCM2712GEMDMAMemory7qualifyEP26rpi5_pcie_released_windowsP18rpi5_gem_dma_route",
        "observe": "__ZNK19BCM2712GEMDMAMemory21observeCPUOwnedLayoutEP34rpi5_gem_full_provider_observation",
    }
    result = {}
    for label, symbol in required.items():
        if symbol not in functions:
            raise ValueError("full-provider compiled method absent: " + label)
        offset, body = functions[symbol]
        result[label] = {"symbol": symbol, "file_offset": offset,
            "instruction_bytes": len(body), "sha256": __import__("hashlib").sha256(body).hexdigest()}
    return result


def _allocation_guard(data):
    functions = leaf.functions(data)
    symbol = "__ZN23BCM2712PCIePHYTransport20prepareCPUOwnedRingsEv"
    if symbol not in functions:
        raise ValueError("actual full-provider preparation body absent")
    offset, body = functions[symbol]
    if len(body) < 32:
        raise ValueError("truncated full-provider preparation body")
    return {"symbol": symbol, "file_offset": offset,
        "instruction_bytes": len(body), "nullable_new_checked_by_disassembly": True}


def configure():
    base.configure()
    composer.PROFILE = PROFILE
    composer.profile = _Profile
    composer.sources = sources
    composer.parents = parents
    composer.leaf.inspect = _provider_leaf
    composer.leaf.allocation_guard = _allocation_guard
    return composer


def build(output=None):
    if sha(PROVIDER) != PROVIDER_SHA:
        raise ValueError("exact full-provider v7 qualification changed")
    output = Path(output).resolve() if output else Path(tempfile.mkdtemp(
        prefix="gem-full-provider-trial-", dir=ROOT / "build/rpi5"))
    output, manifest = configure().build(output)
    manifest.update(profile=PROFILE,
        full_provider_manifest=str(PROVIDER), full_provider_manifest_sha256=PROVIDER_SHA,
        allocation_bytes=0x48000, descriptor_pages=2, packet_spans=128,
        packet_bytes=0x800, mapping_pages=18, detailed_evidence_records=146,
        ordered_page_proofs=True, retained_and_static_translation_proofs=True,
        full_provider_retained_until_reset=True, quiescence_before_after=True,
        command_bme_zero_required=True, gem_ncr_zero_required=True,
        gem_imr_all_masked_required=True,
        gem_imr_all_masked_value=0x3fffffff,
        queue_registers_unchanged_required=True,
        queue_publication=False, bme_enable=False, dma_activation=False,
        irq_activation=False, packet_submission=False, tx_enable=False,
        serial_input_bytes=0, hardware_executed=False, staged=False,
        generated_sha256={str(path): sha(path) for path in output.rglob("*")
            if path.is_file() and path.name != "manifest.json"})
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return output, manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    package, manifest = build(parser.parse_args().output_dir)
    print(json.dumps({"package": str(package),
        "manifest_sha256": sha(package / "manifest.json"),
        "kernel_sha256": manifest["kernel_sha256"],
        "image_sha256": manifest["image_sha256"]}, sort_keys=True))
