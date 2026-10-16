#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Fixed root-route binding for the unchanged zero-TX recorder engine."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import root_route_trial_v1 as stage
import serial_link_trial_v2 as original

bound_sources = stage.private(original.bound_sources, stage=stage, __name__=__name__)
revalidate = stage.private(original.revalidate, stage=stage, bound_sources=bound_sources)
bindings = stage.private(original.bindings, stage=stage, revalidate=revalidate,
    __file__=__file__, __doc__=__doc__)
main = stage.private(original.main, stage=stage, bindings=bindings, __doc__=__doc__)

if __name__ == '__main__':
    raise SystemExit(main())
