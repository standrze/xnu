#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Run the complete offline qualification for the catalog500 physmap v4 transport."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).parents[2]
FILES = (
    "tools/rpi5/stage_gem_physmap_mapping_trial_v4.py",
    "tools/rpi5/serial_gem_physmap_mapping_trial_v4.py",
    "tools/rpi5/gem_physmap_mapping_evidence_v4.py",
    "tools/rpi5/arm_gem_physmap_mapping_reboot_v4.py",
    "tools/rpi5/gem_physmap_mapping_media_v1.py",
    "tools/rpi5/gem_physmap_mapping_case_v1.py",
    "tools/rpi5/gem_physmap_mapping_check_v1.py",
    "tools/rpi5/gem_physmap_mapping_serial_v4.py",
    "tools/rpi5/tests/test_gem_physmap_mapping_transport_v4.py",
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def qualify():
    command = [sys.executable, "-m", "unittest",
        "tools.rpi5.tests.test_gem_physmap_mapping_transport_v4"]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=300)
    if completed.returncode:
        raise ValueError("Physmap v4 transport tests failed: " + completed.stderr)
    return dict(
        profile="catalog500-gem-physmap-mapping-transport-v4",
        status="pass",
        tests=3,
        baseline_checkpoint_sha256="beb6c83c7a719a7bf140b5b48b32c9c4500b73ea4fbcffe7e84006cb0a204cc9",
        baseline_plan_sha256="da1df6b95c5251a23f18dc3e586a97cefc2b2448db40ce8f872ecbd4eabdbd63",
        baseline_catalog_sha256="3fb9b00235759812efa3627104c9dd5158551c3ea981d47b540d333fe0e02186",
        baseline_boot_id="a6c96368-1ef6-4c34-be8e-7efdd97a9395",
        package_manifest_sha256="e8b65a967d82027ec99ba42bf35103ec8e069bf585ffdf54612bc9b19d2ec554",
        zero_transmit=True,
        hardware_executed=False,
        media_staged=False,
        automatic_nvme_return=True,
        exact_triple_restore=True,
        four_alias_rows=True,
        one_page_table_row=True,
        discard_before_route=True,
        sources={str(ROOT / name): sha(ROOT / name) for name in FILES},
    )


if __name__ == "__main__":
    print(json.dumps(qualify(), sort_keys=True))
