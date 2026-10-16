#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Fail-closed assessment for the future full-provider physical transport.

This emits requirements, not a stageable package.  Passing this assessment
means the default-off software candidate is intact and the physical evidence
still required is explicit; it never authorizes publication or hardware use.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rpi5 import check_gem_full_provider_candidate as candidate

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "build/rpi5/gem-full-provider-candidate-20261014-v1"
PACKAGE_MANIFEST_SHA256 = "a78512231a31a43d2810664610bc47a35c9b54bee086b66b0a224dcf66a3f4ef"
OFFLINE_REPORT = ROOT / "build/rpi5/gem-full-provider-offline-qualification-20261014-v1.json"
OFFLINE_REPORT_SHA256 = "b1b751daa49e7d67af6ae7022b52c41f60bdd22d2e580d0c66b224d38818bc56"
CATALOG_COUNT = 536


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def assess():
    if sha(PACKAGE / "manifest.json") != PACKAGE_MANIFEST_SHA256:
        raise ValueError("Exact default-off full-provider candidate required")
    if sha(OFFLINE_REPORT) != OFFLINE_REPORT_SHA256:
        raise ValueError("Exact full-provider offline qualification required")
    checked = candidate.check(PACKAGE)
    offline = json.loads(OFFLINE_REPORT.read_bytes())
    if (not checked["software_qualified"] or checked["board_qualified"] or
            checked["activation"] != offline["activation"] or
            any(checked["activation"].values())):
        raise ValueError("Candidate must remain software-only and default-off")
    return {
        "profile": "rpi5-gem-full-provider-board-transport-assessment-v1",
        "catalog_baseline_count": CATALOG_COUNT,
        "candidate": str(PACKAGE),
        "candidate_manifest_sha256": PACKAGE_MANIFEST_SHA256,
        "candidate_kernel_sha256": checked["kernel_sha256"],
        "offline_report": str(OFFLINE_REPORT),
        "offline_report_sha256": OFFLINE_REPORT_SHA256,
        "software_candidate_qualified": True,
        "physical_transport_qualified": False,
        "stageable": False,
        "publish_authorized": False,
        "hardware_touched": False,
        "activation": checked["activation"],
        "bounded_target": {
            "provider_bytes": 0x48000,
            "mapping_pages": 18,
            "mapping_page_bytes": 0x4000,
            "ring_pages": 2,
            "packet_spans": 128,
            "packet_bytes": 0x800,
            "packet_mapped_bytes": 0x40000,
            "packet_owner": "CPU",
        },
        "required_physical_evidence": [
            "18 ordered page records, each binding retained CPU VA, physical PA, RP1 DMA address, page index, and both retained/static Normal-NC translation proofs",
            "128 ordered packet-span records, each binding index, CPU VA, RP1 DMA address, 2048-byte bounds, containing page, CPU owner, and global non-overlap",
            "fresh before-and-after endpoint PCI command observations proving BME bit clear",
            "fresh before-and-after GEM NCR observations proving RE and TE clear",
            "fresh before-and-after queue-base register observations proving all queue registers unchanged",
            "fresh interrupt-mask observation proving GEM interrupts remain masked and no IRQ ownership is claimed",
            "strict unique ordered parser binding the actual serial bytes to package-derived boot markers and automatic watchdog/NVMe return",
            "zero-transmit recorder proof and an explicit UART_TX=0 transport receipt",
            "exact SD baseline hashes, append-only catalog transition from count 536, and exact post-return restoration",
        ],
        "blocking_defects": [
            "the inherited ring recipe cannot currently regenerate because its frozen BCM2712GEMDMAMemory.cpp pin predates the full-provider source",
            "the candidate intentionally has no boot caller or board marker schema",
            "the candidate exports only an aggregate page bitmap and layout; it does not export per-page retained/static translation evidence",
            "no strict parser exists for 18 page records plus 128 span records and the fresh quiescence observations",
            "no self-contained remote publisher/restorer is pinned to catalog baseline 536 for this distinct trial",
        ],
        "claim": "offline default-off candidate intact; physical full-provider board trial blocked and not stageable",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = assess()
    encoded = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded)
    print(encoded, end="")
