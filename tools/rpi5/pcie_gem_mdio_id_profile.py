# SPDX-License-Identifier: BSD-2-Clause
"""One-predicate C22 no-device refinement; all accesses/owners unchanged."""
from tools.rpi5 import pcie_gem_mdio_trace_profile as prior
ROOT,FROZEN,core,FIELDS=prior.ROOT,prior.FROZEN,prior.core,prior.FIELDS
records=prior.records
OLD='if(!id||id==UINT32_MAX||'
NEW='if(!id||(id&0x1fffffffu)==0x1fffffffu||'


def refined(source):
    return core.util.once(source,OLD,NEW)


def emit(folder):
    sources=prior.emit(folder)
    path=folder/'rp1_gem_mdio.c';path.write_text(refined(path.read_text()))
    return sources
