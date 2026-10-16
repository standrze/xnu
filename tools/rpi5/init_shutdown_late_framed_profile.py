# SPDX-License-Identifier: BSD-2-Clause
"""Explicit newline framing for each bounded delayed PID1 report."""
from pathlib import Path
from . import init_shutdown_late_profile as prior
ROOT=prior.ROOT;ORIGINAL=prior.ORIGINAL;ORIGINAL_SHA=prior.ORIGINAL_SHA
BODY=prior.BODY;READY=prior.READY;MAX_REPORTS=prior.MAX_REPORTS;sha=prior.sha

def body():
    return prior.replace(prior.body(),
        'rt_put(1, "'+READY+'\\n");',
        'rt_put(1, "\\n'+READY+'\\n");')

def derive(raw):return prior.replace(prior.derive(raw),prior.body(),body())

def sources():return [*prior.sources(),Path(__file__).resolve(),
    ROOT/'tools/rpi5/tests/init_shutdown_late_framed_host.c',
    ROOT/'tools/rpi5/tests/test_init_shutdown_late_framed.py']
