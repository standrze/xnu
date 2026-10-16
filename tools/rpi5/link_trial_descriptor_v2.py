# SPDX-License-Identifier: BSD-2-Clause
"""Fixed next-link descriptor; AXI selection is an offline test seam only."""
from pathlib import Path
import importlib
import sys

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
LINK_MANIFEST_SHA='56e3ee8a55a0f6df251d14875e7f5400da2b467b5179975a61e012db1302863d'


def get(kind):
    if kind=='axi-offline':
        return dict(kind=kind,hardware_allowed=False,
            checker=importlib.import_module('tools.rpi5.check_pcie_axi_trace_package'),
            protocol=importlib.import_module('tools.rpi5.pcie_axi_serial_core'),
            manifest_sha256='3e21f6fa338f3b9b274befbef14630d3f8fac2c24f543f78935e52c04209d322',
            marker_prefix='RPI5XNU:BL33:PCIE_ID_AXI_TRACE_TRIAL TAG=')
    if kind!='link' or LINK_MANIFEST_SHA is None:raise ValueError('Frozen next-link package is not selected yet')
    return dict(kind=kind,hardware_allowed=True,
        checker=importlib.import_module('tools.rpi5.check_pcie_link_elapsed_package'),
        protocol=importlib.import_module('tools.rpi5.pcie_link_elapsed_serial_core'),
        manifest_sha256=LINK_MANIFEST_SHA,marker_prefix='RPI5XNU:BL33:PCIE_ID_LINK_ELAPSED_TRIAL TAG=',
        additional_sources=[ROOT/'tools/rpi5/tests/test_pcie_link_elapsed_serial.py'])
