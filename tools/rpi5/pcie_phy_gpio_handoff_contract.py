# SPDX-License-Identifier: BSD-2-Clause
"""Actual serializer + kernel decoder proof for six old and three GPIO pages."""
from pathlib import Path
from types import SimpleNamespace
from tools.rpi5 import pcie_decode_handoff_contract as prior
from tools.rpi5.tests.test_rp1_phy_gpio_observe import fixture_tree
ROOT=prior.ROOT
EXPECTED=prior.EXPECTED.replace('DEVICE_RESOURCES=5 RP1_PAGES=6','DEVICE_RESOURCES=8 RP1_PAGES=9')
def host_source():
    text=prior.host_source().replace('#include "rp1_device_handoff.h"','#include "phy_gpio_device_handoff.h"')
    text=text.replace('rpi5_rp1_device_handoff(fdt, bytes, &types, &rp1_types)','rpi5_phy_gpio_device_handoff(fdt, bytes, &types, &rp1_types)')
    text=text.replace('types.device.count==8','types.device.count==11')
    anchor='    /* Descriptor may not name Device memory or overlap the loaded kernel. */'
    if text.count(anchor)!=1:raise ValueError('Exact native handoff anchor required')
    text=text.replace(anchor,r'''
    for(unsigned n=0;n<3;n++){
        uint64_t a=0x1f000d4000ull+n*0x10000u;
        assert(rpi5_map_type(&map,a,a+0x4000)==2);
        assert(rpi5_map_type(&map,a-0x4000,a)==0);
        assert(rpi5_map_type(&map,a+0x4000,a+0x8000)==0);
    }
'''+anchor)
    return text.replace('DEVICE_RESOURCES=5 RP1_PAGES=6','DEVICE_RESOURCES=8 RP1_PAGES=9')
def audit(loader):
    # Same actual emitted-tree test body, explicit new helper/TU and fixture.
    text=Path(prior.__file__).read_text();start=text.index('def audit(');body=text[start:]
    old="prior.CORES+('rp1_device_handoff',)"
    if body.count(old)!=1:raise ValueError('Exact native core list required')
    body=body.replace(old,"prior.CORES+('rp1_device_handoff','phy_gpio_device_handoff')")
    body=body.replace('exact_rp1_pages=6','exact_rp1_pages=9')
    inherited=SimpleNamespace(**vars(prior.prior));inherited._synthetic_tree=fixture_tree
    namespace=dict(vars(prior),__file__=__file__,prior=inherited,EXPECTED=EXPECTED,host_source=host_source)
    exec(compile(body,__file__,'exec'),namespace)
    result=namespace['audit'](loader)
    for path in (Path(prior.__file__),ROOT/'tools/rpi5/tests/test_rp1_phy_gpio_observe.py'):
        result['inputs_sha256'][str(path.resolve())]=prior.prior.digest(path)
    return result
