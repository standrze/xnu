#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Explicit user-requested repeat from an exact completed compact restoration.

The frozen package, publisher, recorder and recovery bodies stay unchanged.
Only the typed predecessor changes: the immediately completed compact restore,
never the old GPIO catalog or a previous boot's framebuffer allocation.
"""
from pathlib import Path
from tools.rpi5 import stage_display_compact_trial as stage


def source_pins():
    paths=(Path(__file__).resolve(),stage.ROOT/'tools/rpi5/tests/test_repeat_display_compact_trial.py')
    return stage.source_pins()|{str(p):stage.sha(p) for p in paths}


prepare_install=stage.private(stage.prepare_install,baseline=stage.restoration,source_pins=source_pins)
main=stage.private(stage.main,prepare_install=prepare_install,__doc__=__doc__)


if __name__=='__main__':raise SystemExit(main())
