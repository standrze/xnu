# SPDX-License-Identifier: BSD-2-Clause
"""Exact, default-off platform fallback; no accepted source/object mutation."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / 'iokit/Kernel/IOPlatformExpert.cpp'
ORIGINAL_SHA = '2dff047ecfb18cdedcdc6f9f97c8fa6f730e088176598865c586b91545f74a56'
INCLUDE = '''#if defined(RPI5_PSCI_RESTART_CANDIDATE) && RPI5_PSCI_RESTART_CANDIDATE == 1
#include "iokit/Kernel/rpi5_psci_restart_candidate.inc"
#endif
'''
BEFORE = '''\tif (PE_halt_restart) {
\t\treturn (*PE_halt_restart)(type);
\t} else {
\t\treturn -1;
\t}
'''
AFTER = '''\tif (PE_halt_restart) {
\t\treturn (*PE_halt_restart)(type);
\t} else {
#if defined(RPI5_PSCI_RESTART_CANDIDATE) && RPI5_PSCI_RESTART_CANDIDATE == 1
\t\treturn rpi5_restart_candidate_platform(type);
#else
\t\treturn -1;
#endif
\t}
'''


def derive(raw):
    if hashlib.sha256(raw.encode()).hexdigest() != ORIGINAL_SHA:
        raise ValueError('Exact original IOPlatformExpert bytes required')
    marker = 'int (*PE_halt_restart)(unsigned int type) = NULL;\n'
    if raw.count(marker) != 1 or raw.count(BEFORE) != 1:
        raise ValueError('Exact platform callback fallback required')
    return raw.replace(marker, INCLUDE + '\n' + marker).replace(BEFORE, AFTER)
