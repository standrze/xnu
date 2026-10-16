#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct MDIO no-device-ID refinement; predecessor remains immutable."""
import argparse
import json
from pathlib import Path
from tools.rpi5 import build_pcie_gem_mdio_kernel as prior
from tools.rpi5 import pcie_gem_mdio_id_profile as profile
ROOT,audit,engine,private=prior.ROOT,prior.audit,prior.engine,prior.private
PROFILE='pcie-held-device-gem-c22-mdio-kernel-v2'
TEST=ROOT/'tools/rpi5/tests/test_pcie_gem_mdio_id.py'


def contract():
    return dict(prior.contract(),phy_id_reject_zero=True,phy_id_no_device_mask=0x1fffffff,
        phy_id_no_device_value=0x1fffffff,phy_id_rule_source='get_phy_c22_id in pinned phy_device.c',
        no_other_runtime_predicate_or_callback_change=True)


def configured():
    b=private.load_private(Path(prior.__file__).resolve(),'_mdio_id_kernel_v2')
    b.PROFILE=PROFILE;b.TEST=TEST;b.profile=profile;b.contract=contract
    previous=b.inputs
    def inputs():
        first,second,pins=previous()
        for path in (Path(__file__).resolve(),Path(prior.profile.__file__).resolve(),
            ROOT/'tools/rpi5/tests/test_pcie_gem_mdio_kernel.py'):
            value=audit.sha(path)
            if str(path) in pins and pins[str(path)]!=value:raise ValueError('Refinement source pin conflict')
            pins[str(path)]=value
        engine.verify(pins);return first,second,pins
    b.inputs=inputs
    return b


def build(output):return configured().build(output)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True)
    r=build(p.parse_args().output_dir.resolve());print(json.dumps({k:r[k] for k in ('profile','kernel','kernel_sha256','kernel_bytes')}))
