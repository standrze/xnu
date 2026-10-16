#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Isolated 96-node Pi RAM-root profile; never mutates the accepted packer."""
import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKER = Path(__file__).with_name('ramroot.py')
PACKER_SHA = 'f0f9d37a0771d7b826f76b14c7067879136702f8dd1338c43739ddcef66c7218'
HEADER = ROOT / 'bsd/miscfs/mockfs/rpi5_ramroot_format.h'
HEADER_SHA = 'effa1bd1debc0742126fcdfdd533e02200b366f13e513aecbe3b02ec614b5dc8'
MAX_NODES = 96


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def packer():
    if sha(PACKER.read_bytes()) != PACKER_SHA:
        raise ValueError('Preserved Pi RAM-root packer changed')
    # A private module instance keeps the original module's 32-node limit intact.
    name = (__package__ + '.' if __package__ else '') + '_root_capacity_packer'
    spec = importlib.util.spec_from_file_location(name, PACKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.MAX_NODES != 32 or 32 + MAX_NODES * module.RECORD.size > module.PAGE:
        raise ValueError('RAM-root metadata capacity or original profile changed')
    module.MAX_NODES = MAX_NODES
    return module


def build(files):
    return packer().build(files)


def inspect(image):
    return packer().inspect(image)


def files_from(image):
    return {row['path']: (image[row['offset']:row['offset'] + row['size']], row['mode'])
            for row in inspect(image)['entries'] if row['type'] == 'file'}


def kernel_header():
    original = HEADER.read_bytes()
    if sha(original) != HEADER_SHA or original.count(b'#define RPI5_RFS_NODES 32u') != 1:
        raise ValueError('Preserved Pi RAM-root kernel header changed')
    return original.replace(b'#define RPI5_RFS_NODES 32u', b'#define RPI5_RFS_NODES 96u')
