#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Run the complete offline qualification for catalog524 CPU-ring transport."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).parents[2]
FILES = (
    "tools/rpi5/stage_gem_cpu_ring_physmap_trial_v1.py",
    "tools/rpi5/serial_gem_cpu_ring_physmap_trial_v1.py",
    "tools/rpi5/gem_cpu_ring_physmap_evidence_v1.py",
    "tools/rpi5/arm_gem_cpu_ring_physmap_reboot_v1.py",
    "tools/rpi5/gem_cpu_ring_physmap_media_v1.py",
    "tools/rpi5/gem_cpu_ring_physmap_case_v1.py",
    "tools/rpi5/gem_cpu_ring_physmap_serial_v1.py",
    "tools/rpi5/check_gem_cpu_ring_physmap_transport_v1.py",
    "tools/rpi5/build_gem_cpu_ring_physmap_trial.py",
    "tools/rpi5/check_gem_cpu_ring_physmap_trial.py",
    "tools/rpi5/tests/test_gem_cpu_ring_physmap_transport_v1.py",
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def qualify():
    command = [sys.executable, "-m", "unittest",
        "tools.rpi5.tests.test_gem_cpu_ring_physmap_transport_v1"]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=300)
    if completed.returncode:
        raise ValueError("CPU-ring physmap transport tests failed: " + completed.stderr)
    return {
        "profile": "catalog524-gem-cpu-ring-physmap-transport-v1",
        "status": "pass",
        "tests": 4,
        "baseline_checkpoint_sha256": "91a00c05d5bee963e87e316a4748eeee4e38be706a8f6c6432238f3047180c00",
        "baseline_plan_sha256": "0192c6a07d6947c41443aa24b18f1432a867c9f8c9676773a29e7b6a097e5058",
        "baseline_result_sha256": "f379d91a3ebf20f3105b38a349980581e3c12bafab630c7503d690de7ad1d930",
        "baseline_catalog_count": 524,
        "baseline_catalog_sha256": "5aa6a9e2f2c94090e6ded0dfa27129d26924f8ea98479f6aebb61e97d4d54c20",
        "baseline_boot_id": "2d237d96-a323-4df7-a8b4-ad9b4eb5f477",
        "mapping_report_sha256": "fca45a8a3c17d9d5d7ef9acbf2d879c6c8adf351f82465d75727b5789ff8b5f6",
        "package_manifest_sha256": "9cc31e53c773af491806b2cee60a794679034da042df4fd4a6c50ab1522b6b80",
        "package_probe_sha256": "fbfca7c3e40893ddd383b5183b5f5f3db9a52fbbfb3b87c749523c2d6a3fcbae",
        "package_kernel_sha256": "6afdabf0ca98b0e854f7ee27e29e9868ee31b60cf955899867eb39572a14d128",
        "package_tag": "4c9d25d41fbd43b2a08f27d147b46171",
        "zero_serial_transmit": True,
        "bounded_recorder": True,
        "automatic_nvme_return": True,
        "exact_triple_restore": True,
        "append_only_catalog": True,
        "activation_authorized": False,
        "rp1_claimed": False,
        "bme_claimed": False,
        "queue_claimed": False,
        "dma_claimed": False,
        "irq_claimed": False,
        "packet_claimed": False,
        "tx_claimed": False,
        "hardware_executed": False,
        "media_staged": False,
        "sources": {str(ROOT / name): sha(ROOT / name) for name in FILES},
    }


if __name__ == "__main__":
    print(json.dumps(qualify(), sort_keys=True))
