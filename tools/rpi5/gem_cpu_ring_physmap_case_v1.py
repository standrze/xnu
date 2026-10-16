#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Immutable software case for the physmap-enabled CPU-owned-ring trial."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FROZEN = True
PACKAGE = ROOT / "build/rpi5/gem-cpu-ring-physmap-trial-20261014-v2"
MANIFEST_SHA = "9cc31e53c773af491806b2cee60a794679034da042df4fd4a6c50ab1522b6b80"
IMAGE_SHA = "fbfca7c3e40893ddd383b5183b5f5f3db9a52fbbfb3b87c749523c2d6a3fcbae"
IMAGE_BYTES = 20170496
KERNEL_SHA = "6afdabf0ca98b0e854f7ee27e29e9868ee31b60cf955899867eb39572a14d128"
FIRMWARE = ROOT / "build/rpi5/pcie-el3-verifier-20261012-checked/build/rpi5/debug/bl31.bin"
FIRMWARE_SHA = "dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b"
FIRMWARE_BYTES = 45174
TAG = "4c9d25d41fbd43b2a08f27d147b46171"
REPORT = ROOT / "build/rpi5/gem-cpu-ring-physmap-check-20261014-v1.json"
REPORT_SHA = "509b8c60bd6a1f892b48a880f3cea34d8083f687f2e5250189058f02db9cb591"
QUALIFICATION = REPORT
QUALIFICATION_SHA = REPORT_SHA
MAPPING_REPORT = ROOT / "build/rpi5/gem-physmap-mapping-board-evidence-20261014-v1.json"
MAPPING_REPORT_SHA = "fca45a8a3c17d9d5d7ef9acbf2d879c6c8adf351f82465d75727b5789ff8b5f6"
