# SPDX-License-Identifier: BSD-2-Clause
"""Exact successor platform include and tag; every accepted input stays intact."""
import hashlib
from . import psci_restart_candidate_profile as original

ROOT = original.ROOT


def platform(raw):
    text = original.derive(raw)
    old = '#include "iokit/Kernel/rpi5_psci_restart_candidate.inc"'
    if text.count(old) != 1:
        raise ValueError('Exact original default-off platform derivation required')
    return text.replace(old, '#include "iokit/Kernel/rpi5_psci_restart_diagnostic.inc"')


def main(raw):
    old = 'RPI5XNU:DISPLAYRESTART:ENTRY TAG='
    if raw.count(old) != 1:
        raise ValueError('Exact restart candidate entry required')
    return raw.replace(old, 'RPI5XNU:DISPLAYRESTART_DIAG:ENTRY TAG=')
