# SPDX-License-Identifier: BSD-2-Clause
"""Exact frozen software package; controller/baseline admission is separate."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FROZEN=True
PACKAGE=ROOT/'build/rpi5/gem-dma-batch-trial-20261014-v8'
MANIFEST_SHA='0439396fe0d74482c01ef6f22b291cbc8c8a848cc27f4b878ba94987e26e0f60'
IMAGE_SHA='67a77d2e587af5afde1f804e97d6cb39a4ff013e59584ed5dc58473a5fe175f6'
IMAGE_BYTES=20170240
FIRMWARE=ROOT/'build/rpi5/pcie-el3-verifier-20261012-checked/build/rpi5/debug/bl31.bin'
FIRMWARE_SHA='dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b'
FIRMWARE_BYTES=45174
TAG='fbdfd61ecd474811897872e2adf99284'
REPORT=ROOT/'build/rpi5/gem-dma-batch-qualification-20261014-v8/checker-report.json'
REPORT_SHA='798e8645da204b29fb81b2eacc72389e60271ac732535f740c9360a491a5c4d3'
QUALIFICATION=ROOT/'build/rpi5/gem-dma-batch-qualification-20261014-v8/qualification.json'
QUALIFICATION_SHA='2f86b97b7da8cf80104070f1f28bf3c849bcbdd3e025deff2cb3389536e99199'
