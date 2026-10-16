#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""User-requested visible repeat from a completed corrected console restoration.

Image, publisher, marker-gated input, capture window and recovery stay frozen.
Only the typed predecessor and two additional source pins change. Framebuffer
allocation is still fresh on this boot, never inherited from a prior trial.
"""
from pathlib import Path
from tools.rpi5 import stage_display_xnu_trial_v2 as stage


def source_pins():
    paths=(Path(__file__).resolve(),stage.ROOT/'tools/rpi5/tests/test_repeat_display_xnu_trial_v2.py')
    return stage.source_pins()|{str(p):stage.sha(p) for p in paths}


prepare_install=stage.private(stage.prepare_install,baseline=stage.restoration,source_pins=source_pins)
main=stage.private(stage.main,prepare_install=prepare_install,__doc__=__doc__)


if __name__=='__main__':raise SystemExit(main())
