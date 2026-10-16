#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Admission checker binding the ring package to accepted board mapping proof."""
import hashlib
import json
from pathlib import Path
import types

from tools.rpi5 import build_gem_cpu_ring_physmap_trial as build
from tools.rpi5 import check_gem_cpu_ring_physmap_trial as package_checker
from tools.rpi5 import gem_cpu_ring_physmap_case_v1 as case

b = types.SimpleNamespace(retry=types.SimpleNamespace(trial=build.retry.trial))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_mapping_report(report):
    if not isinstance(report, dict):
        raise ValueError("Typed mapping report required")
    exact = {
        "profile": "rpi5-gem-physmap-mapping-board-evidence-v1",
        "status": "pass",
        "evidence_type": "physical-board-mapping-verification-only",
        "mapping_verification_pass": True,
        "reason": 41,
        "zero_transmit": True,
        "complete_capture": True,
        "discard_before_route": True,
        "route_dma_irq_queues_packets_tx_activated": False,
        "rp1_identity_or_link_success_claimed": False,
        "ethernet_proven": False,
    }
    if any(report.get(key) != value for key, value in exact.items()):
        raise ValueError("Accepted mapping evidence semantics differ")
    restoration = report.get("restoration", {})
    catalogs = restoration.get("catalogs", [])
    if (restoration.get("counts") != [512, 518, 524] or len(catalogs) != 3 or
            restoration.get("exact_triple_restored") is not True or
            restoration.get("independent_nvme_return") is not True or
            restoration.get("replay_chain_verified") is not True):
        raise ValueError("Mapping restoration ancestry differs")
    final = catalogs[-1]
    if (final.get("boot_id") != "2d237d96-a323-4df7-a8b4-ad9b4eb5f477" or
            final.get("count") != 524 or
            final.get("sha256") != "5aa6a9e2f2c94090e6ded0dfa27129d26924f8ea98479f6aebb61e97d4d54c20" or
            final.get("triple") != {
                "config.txt": "aaccab184135aca272db4123fcba34e20874ae0959a90aed1ef6fd4d5e18ed28",
                "bl31.bin": "413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46",
                "probe.bin": "f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536",
            }):
        raise ValueError("Exact catalog524 normal triple differs")
    return True


def inspect(package, expected_manifest_sha256, *_legacy_receipts):
    if (Path(package).resolve() != case.PACKAGE or
            expected_manifest_sha256 != case.MANIFEST_SHA):
        raise ValueError("Exact physmap CPU-ring package required")
    if sha(case.MAPPING_REPORT) != case.MAPPING_REPORT_SHA:
        raise ValueError("Accepted mapping report bytes differ")
    mapping = json.loads(case.MAPPING_REPORT.read_text())
    validate_mapping_report(mapping)
    report = package_checker.check(package, expected_manifest_sha256)
    report.update(
        marker=report["trial_marker"],
        image_bytes=case.IMAGE_BYTES,
        mapping_report=str(case.MAPPING_REPORT),
        mapping_report_sha256=case.MAPPING_REPORT_SHA,
        catalog_count=524,
        catalog_sha256="5aa6a9e2f2c94090e6ded0dfa27129d26924f8ea98479f6aebb61e97d4d54c20",
        baseline_boot_id="2d237d96-a323-4df7-a8b4-ad9b4eb5f477",
        automatic_watchdog_return_required=True,
        complete_capture_health_required=True,
        zero_serial_transmit=True,
        activation_authorized=False,
    )
    return report
