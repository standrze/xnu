#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Final strict-known-clock GEM prototype successor; no authority expansion."""
import argparse
import json
from pathlib import Path
from tools.rpi5 import build_pcie_gem_identify_kernel as prior
from tools.rpi5 import rp1_gem_known_clock_profile as profile
ROOT,audit,engine,private,BASE,BASE_SHA=prior.ROOT,prior.audit,prior.engine,prior.private,prior.BASE,prior.BASE_SHA
PROFILE='pcie-held-mapping-known-clock-gem-mid-kernel-v2'
TEST=ROOT/'tools/rpi5/tests/test_pcie_gem_known_kernel.py'
objects,compile_args=prior.objects,prior.compile_args


def contract():
    return dict(prior.contract(),pll_cs_known_bits_only=0x8000003f,pll_pwr_known_bits_only=0x3f,
        auxiliary_parent_selection='ETH/TSU num_std_parents=0; upstream get_parent always decodes CTRL.AUXSRC; require enabled, one-hot nonzero SEL and AUXSRC0',
        physical_frequency_counter_used=False,unknown_cs_modes_rejected=True)


def build(output):
    b=private.load_private(Path(prior.__file__).resolve(),'_gem_known_kernel')
    b.profile=profile;b.PROFILE=PROFILE;b.TEST=TEST;b.contract=contract
    original=b.inputs
    def inputs():
        parent,base,pins=original()
        for path in (Path(__file__).resolve(),ROOT/'tools/rpi5/tests/test_rp1_gem_known.py',
            Path(profile.prior.__file__).resolve()):
            value=audit.sha(path)
            if str(path) in pins and pins[str(path)]!=value:raise ValueError('Known-clock pin changed')
            pins[str(path)]=value
        return parent,base,pins
    b.inputs=inputs
    result=b.build(output)
    result['prototype_kernel_manifest_sha256']='2618ed4386e04a5d4793c1307e66ca7a94b7bf5e22a41af871f17827b7adbd56'
    result['prototype_not_used_for_hardware']=True
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True)
    result=build(parser.parse_args().output_dir.resolve())
    print(json.dumps({k:result[k] for k in ('profile','kernel','kernel_sha256','kernel_bytes')}))
