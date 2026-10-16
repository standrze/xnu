#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Run the complete offline qualification for catalog512 physmap v5 transport."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).parents[2]
FILES = (
    "tools/rpi5/stage_gem_physmap_mapping_trial_v5.py",
    "tools/rpi5/serial_gem_physmap_mapping_trial_v5.py",
    "tools/rpi5/gem_physmap_mapping_evidence_v5.py",
    "tools/rpi5/arm_gem_physmap_mapping_reboot_v5.py",
    "tools/rpi5/gem_physmap_mapping_media_v5.py",
    "tools/rpi5/gem_physmap_mapping_case_v1.py",
    "tools/rpi5/gem_physmap_mapping_check_v1.py",
    "tools/rpi5/gem_physmap_mapping_serial_v5.py",
    "tools/rpi5/tests/test_gem_physmap_mapping_transport_v5.py",
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def qualify():
    command = [sys.executable, "-m", "unittest",
        "tools.rpi5.tests.test_gem_physmap_mapping_transport_v5"]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=300)
    if completed.returncode:
        raise ValueError("Physmap v5 transport tests failed: " + completed.stderr)
    return dict(
        profile="catalog512-gem-physmap-mapping-transport-v5",
        status="pass",
        tests=4,
        baseline_checkpoint_sha256="6b55bf9cf939bb70a58e3781cf1f54eb0633167a95bde75db6bc663df6bdb2b3",
        baseline_plan_sha256="f77a4e94248d6df7b215086ff32aa18acf94ad570509e48a3d384b7cd9a0ce37",
        baseline_result_sha256="20345faa425243b43f1578aa30f1c0c3983192cd21fde92a9906ee2555f38298",
        baseline_catalog_count=512,
        baseline_catalog_sha256="8f7be2df370eb5a6951e645fca95d0609db141cf07ac53da020e7bcd26964566",
        baseline_boot_id="5a1f5c04-c3d6-463a-8785-d737a3d59935",
        package_manifest_sha256="a73188d0234348025b151bc66ee7f5cb7763efd867871d23a4c5379eba7df141",
        package_probe_sha256="5fad73f69c09f05431ece249204c7ae52b07e2f6df45b12370019f26ed1a39df",
        package_tag="96a5f52e3bd546fc8687f63e9b6459e9",
        maximum_page_table_pages=259,
        maximum_page_table_bytes=4243456,
        preallocated_upper_pages=1,
        zero_transmit=True,
        hardware_executed=False,
        media_staged=False,
        automatic_nvme_return=True,
        exact_triple_restore=True,
        four_alias_rows=True,
        one_page_table_row=True,
        reason=41,
        discard_before_route=True,
        all_enabled_units_linked=True,
        captured_v9_rejected=True,
        sources={str(ROOT / name): sha(ROOT / name) for name in FILES},
    )


if __name__ == "__main__":
    print(json.dumps(qualify(), sort_keys=True))
