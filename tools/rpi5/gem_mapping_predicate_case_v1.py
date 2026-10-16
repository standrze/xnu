# SPDX-License-Identifier: BSD-2-Clause
"""Exact frozen mapping-predicate package for the v3 transport."""
from pathlib import Path

ROOT=Path(__file__).parents[2]
FROZEN=True
PACKAGE=ROOT/'build/rpi5/gem-mapping-predicate-trial-20261014-v2'
MANIFEST_SHA='5183c60634238406a165ce9d4774fd2dd67df36f7792f410b670633b6d5c6b43'
IMAGE_SHA='5e9ecb82d44c923a2bf8559aa899759d9eca2d90af6bdd611fbb9dabc04d27c4'
IMAGE_BYTES=20170304
TAG='1fa354ffa536404db46d998d0db9c3fd'
REPORT=ROOT/'build/rpi5/gem-mapping-predicate-check-20261014-v2.json'
REPORT_SHA='a8de403bd1599e0956411bb305d29f13bc0f1d29e5206f495deab31c0520d44b'
QUALIFICATION=REPORT
QUALIFICATION_SHA=REPORT_SHA
FIRMWARE=ROOT/'build/rpi5/pcie-el3-verifier-20261012-checked/build/rpi5/debug/bl31.bin'
FIRMWARE_SHA='dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b'
FIRMWARE_BYTES=45174
