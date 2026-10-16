#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact root43 late-state recorder; three exchanges, ten diagnostic commands."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_root43_packet_trial as staging
import serial_root42_pthread_trial as base
import root43_packet_trial_core as core

t,lease,root_profile=base.t,base.lease,base.root_profile


def bound_sources(context):
    pins=staging.source_pins()
    if any(context['evidence'].get(n)!=h for n,h in pins.items()):raise ValueError('Root43 sealed source closure differs')
    return pins


def revalidate(context):staging.seals.check_pins(context['evidence']);bound_sources(context)
package_pins=staging.private(base.package_pins,staging=staging)


def armed_line(report):
    return 'ROOT43_PACKET_CAPTURE_ARMED ZERO_TX_UNTIL_STATE_CONFIRMED_ROOT WATCHDOG_180_SECONDS IMAGE_SHA='+report['image_sha256']


def bindings(context):
    checked=core.bind(context['installed']['preflight'])
    fn=staging.private(base.bindings,staging=staging,core=core,checked_core=checked,
        bound_sources=bound_sources,revalidate=revalidate,package_pins=package_pins,armed_line=armed_line,__file__=__file__,__doc__=__doc__)
    return fn(context)


main=staging.private(base.main,staging=staging,bindings=bindings,__file__=__file__,__doc__=__doc__)


if __name__=='__main__':raise SystemExit(main())
