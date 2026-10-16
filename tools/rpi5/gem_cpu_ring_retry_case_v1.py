# SPDX-License-Identifier: BSD-2-Clause
"""Exact frozen ring-only retry package; current media admission is separate."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FROZEN=True
PACKAGE=ROOT/'build/rpi5/gem-cpu-ring-retry-trial-20261014-v7'
MANIFEST_SHA='532968eb3df2fcd6fb8f5dc3addfd11ddd2d1442c66b2ffc7f6de9bf5b744b64'
IMAGE_SHA='18f0732fe432dfaf047b371fce0f4487523d85b902d4702ac734ed043a03b8ef'
IMAGE_BYTES=20169920
FIRMWARE=ROOT/'build/rpi5/pcie-el3-verifier-20261012-checked/build/rpi5/debug/bl31.bin'
FIRMWARE_SHA='dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b'
FIRMWARE_BYTES=45174
TAG='304dd3f376024efab8ef4d63ef1dad80'
REPORT=ROOT/'build/rpi5/gem-cpu-ring-retry-check-20261014-v1.json'
REPORT_SHA='2d15b2ce7e0c9dc68cadf459021543f9ebcbc2decc80c71e6909383cc5fbee39'
QUALIFICATION=ROOT/'build/rpi5/gem-cpu-ring-retry-stack-20261014-v4/qualification.json'
QUALIFICATION_SHA='2f6b60c5bb48764550dd515a232481bfec0f5dd103c52ce2df1cee90e927fb81'
