#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""V2 admission checker for the unchanged ring package and mapping proof."""
import hashlib
import json
from pathlib import Path
import types

from tools.rpi5 import build_gem_cpu_ring_physmap_trial as build
from tools.rpi5 import check_gem_cpu_ring_physmap_trial as package_checker
from tools.rpi5 import check_gem_cpu_ring_physmap_transport_v1 as prior
from tools.rpi5 import gem_cpu_ring_physmap_case_v2 as case

b = types.SimpleNamespace(retry=types.SimpleNamespace(trial=build.retry.trial))
validate_mapping_report = prior.validate_mapping_report


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect(package, expected_manifest_sha256, *_legacy_receipts):
    if (Path(package).resolve() != case.PACKAGE or
            expected_manifest_sha256 != case.MANIFEST_SHA):
        raise ValueError("Exact physmap CPU-ring package required")
    if sha(case.MAPPING_REPORT) != case.MAPPING_REPORT_SHA:
        raise ValueError("Accepted mapping report bytes differ")
    validate_mapping_report(json.loads(case.MAPPING_REPORT.read_text()))
    report = package_checker.check(package, expected_manifest_sha256)
    report.update(
        marker=report["trial_marker"], image_bytes=case.IMAGE_BYTES,
        mapping_report=str(case.MAPPING_REPORT), mapping_report_sha256=case.MAPPING_REPORT_SHA,
        catalog_count=524,
        catalog_sha256="5aa6a9e2f2c94090e6ded0dfa27129d26924f8ea98479f6aebb61e97d4d54c20",
        baseline_boot_id="2d237d96-a323-4df7-a8b4-ad9b4eb5f477",
        automatic_watchdog_return_required=True, complete_capture_health_required=True,
        zero_serial_transmit=True, activation_authorized=False,
        self_contained_remote_transport_required=True,
    )
    return report
