# SPDX-License-Identifier: BSD-2-Clause
"""Exact frozen corrected page-granular physmap mapping-verification package."""
from pathlib import Path

ROOT = Path(__file__).parents[2]
FROZEN = True
PACKAGE = ROOT / "build/rpi5/gem-physmap-mapping-verification-20261014-v10"
MANIFEST_SHA = "a73188d0234348025b151bc66ee7f5cb7763efd867871d23a4c5379eba7df141"
IMAGE_SHA = "5fad73f69c09f05431ece249204c7ae52b07e2f6df45b12370019f26ed1a39df"
IMAGE_BYTES = 20171072
TAG = "96a5f52e3bd546fc8687f63e9b6459e9"
REPORT = ROOT / "build/rpi5/gem-physmap-mapping-check-20261014-v2.json"
REPORT_SHA = "825ac8342516fe034ee008595a33bb712377aa95029024942969c7f3a91ba6b0"
QUALIFICATION = REPORT
QUALIFICATION_SHA = REPORT_SHA
FIRMWARE = ROOT / "build/rpi5/pcie-el3-verifier-20261012-checked/build/rpi5/debug/bl31.bin"
FIRMWARE_SHA = "dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b"
FIRMWARE_BYTES = 45174

