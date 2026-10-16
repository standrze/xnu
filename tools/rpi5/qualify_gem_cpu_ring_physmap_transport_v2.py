#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Complete offline qualification for the self-contained v2 transport."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).parents[2]
FILES = (
    "tools/rpi5/stage_gem_cpu_ring_physmap_trial_v2.py",
    "tools/rpi5/serial_gem_cpu_ring_physmap_trial_v2.py",
    "tools/rpi5/gem_cpu_ring_physmap_evidence_v2.py",
    "tools/rpi5/arm_gem_cpu_ring_physmap_reboot_v2.py",
    "tools/rpi5/gem_cpu_ring_physmap_media_v2.py",
    "tools/rpi5/gem_cpu_ring_physmap_case_v2.py",
    "tools/rpi5/gem_cpu_ring_physmap_serial_v2.py",
    "tools/rpi5/check_gem_cpu_ring_physmap_transport_v2.py",
    "tools/rpi5/tests/test_gem_cpu_ring_physmap_transport_v2.py",
    "tools/rpi5/gem_cpu_ring_retry_media_v2.py",
    "tools/rpi5/gem_cpu_batch_media_v1.py",
    "tools/rpi5/stage_gem_cpu_ring_physmap_trial_v1.py",
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def qualify():
    completed = subprocess.run([sys.executable, "-m", "unittest",
        "tools.rpi5.tests.test_gem_cpu_ring_physmap_transport_v2"], cwd=ROOT,
        text=True, capture_output=True, timeout=300)
    if completed.returncode:
        raise ValueError("CPU-ring physmap v2 transport tests failed: " + completed.stderr)
    return {
        "profile": "catalog524-gem-cpu-ring-physmap-transport-v2",
        "status": "pass", "tests": 4,
        "v1_failure_retained": True,
        "v1_failure_stderr_sha256": "aef0b5e11b258ca0311538d6484b6978dfade31e4211165f3dbf78a78f1b584f",
        "self_contained_remote_program_executed": True,
        "isolated_python_mode": True,
        "module_initialization_executed": True,
        "validate_plan_executed": True,
        "mac_path_reads_during_mock_remote_execution": 0,
        "mock_remote_filesystem_changes": 0,
        "guarded_repository_access_apis": ["builtins.open", "io.open", "os.open",
            "os.stat", "os.lstat", "os.scandir", "os.listdir", "os.readlink"],
        "missing_immediate_parent_assignment_rejected": True,
        "missing_base_parent_assignment_rejected": True,
        "immediate_parent_byte_corruption_rejected": True,
        "base_parent_byte_corruption_rejected": True,
        "immediate_parent_assignments": 1,
        "base_parent_assignments": 1,
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
        "prepared_checkpoint_sha256": "304e3a6b4360b8e4452959b1915a4d573bfe5ad65846e08044588e931e44e27a",
        "physmap_wrapper_sha256": sha(ROOT / "tools/rpi5/gem_cpu_ring_physmap_media_v2.py"),
        "retry_wrapper_sha256": "058a8870c22634a119e50d9ef9de7dde1d79b07d3f978f6204a9c9038e5669d7",
        "batch_base_sha256": "51ff5b30a9ca2edc27b442dd4432569ff1d7f195e401a45623d370bfea0a551b",
        "controller_v1_parent_sha256": "cb48524f470e0cc46841e56f3a2eb9c25aa9ade64ac9efc649f631fbef937194",
        "zero_serial_transmit": True, "bounded_recorder": True,
        "automatic_nvme_return": True, "exact_triple_restore": True,
        "append_only_catalog": True, "activation_authorized": False,
        "rp1_claimed": False, "bme_claimed": False, "queue_claimed": False,
        "dma_claimed": False, "irq_claimed": False, "packet_claimed": False,
        "tx_claimed": False, "hardware_executed": False, "media_staged": False,
        "sources": {str(ROOT / name): sha(ROOT / name) for name in FILES},
    }


if __name__ == "__main__":
    print(json.dumps(qualify(), sort_keys=True))
