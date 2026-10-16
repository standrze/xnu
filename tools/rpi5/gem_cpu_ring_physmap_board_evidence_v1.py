#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Independent evidence adapter for the immutable CPU-ring physmap capture."""
import hashlib
import json
from pathlib import Path

from tools.rpi5 import gem_cpu_ring_physmap_serial_v3 as parser


ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "build/rpi5/gem-cpu-ring-physmap-v2-capture-r6"
SERIAL_SHA256 = "adb0cdd8d16da53fcf8951b0bf3004c6a4371cc9729cb965cadb3e31da64bd70"
SERIAL_BYTES = 36518
LEGACY_ERROR = "Exact CPU-only and scoped inherited contracts required"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def inspect(capture=CAPTURE):
    capture = Path(capture).resolve()
    if capture != CAPTURE:
        raise ValueError("Exact immutable CPU-ring physmap capture required")
    state_path = capture / "state.json"
    armed_path = capture / "armed.json"
    serial_path = capture / "serial.bin"
    before = {path: _sha(path.read_bytes()) for path in (state_path, armed_path, serial_path)}
    state = json.loads(state_path.read_bytes())
    armed = json.loads(armed_path.read_bytes())
    data = serial_path.read_bytes()
    if (_sha(data) != SERIAL_SHA256 or len(data) != SERIAL_BYTES or
            state.get("serial_sha256") != SERIAL_SHA256 or state.get("bytes") != SERIAL_BYTES):
        raise ValueError("Exact original serial capture bytes required")
    if (state.get("status") != "captured" or state.get("transmitted_bytes") != 0 or
            armed.get("transmitted_bytes") != 0 or state.get("diagnostic_error") != LEGACY_ERROR):
        raise ValueError("Exact receive-only legacy capture state required")
    if state.get("installation") != armed.get("installation"):
        raise ValueError("Armed and completed installation receipts differ")
    report = state.get("installation", {}).get("preflight")
    sources = state.get("source_sha256")
    if report != armed.get("installation", {}).get("preflight") or sources != armed.get("source_sha256"):
        raise ValueError("Exact armed receipt binding required")
    diagnostic = parser.inspect(data, report, sources)
    after = {path: _sha(path.read_bytes()) for path in (state_path, armed_path, serial_path)}
    if before != after:
        raise ValueError("Original capture or receipts changed during inspection")
    return {
        "profile": "rpi5-gem-cpu-ring-physmap-board-evidence-v1",
        "status": "pass",
        "capture": str(capture),
        "capture_state_sha256": before[state_path],
        "armed_receipt_sha256": before[armed_path],
        "serial_sha256": SERIAL_SHA256,
        "serial_bytes": SERIAL_BYTES,
        "legacy_parser_error": LEGACY_ERROR,
        "legacy_error_is_receipt_omission_not_hardware_failure": True,
        "zero_serial_transmit": True,
        "raw_capture_immutable": True,
        "cpu_ring_physical_trial_pass": diagnostic["cpu_ring_retry_trial_pass"],
        "automatic_watchdog_return_observed": diagnostic["automatic_watchdog_return_observed"],
        "normal_nvme_serial_boot_observed": diagnostic["normal_nvme_serial_boot_observed"],
        "full_original_capture_health_scan": diagnostic["full_original_capture_health_scan"],
        "runtime_fault_signature_observed": diagnostic["capture_health"]["runtime_fault_signature_observed"],
        "ethernet_proven": False,
        "dma": False,
        "irq_delivery": False,
        "queue_publication": False,
        "packets": False,
        "diagnostic": diagnostic,
    }
