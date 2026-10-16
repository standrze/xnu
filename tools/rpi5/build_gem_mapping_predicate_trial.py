#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the default-off GEM mapping-predicate diagnostic; never stage media."""
import argparse,json,tempfile
from pathlib import Path
from tools.rpi5 import build_gem_cpu_ring_retry_trial as inherited
from tools.rpi5 import gem_mapping_predicate_profile as profile

ROOT=inherited.ROOT
PROFILE='bcm2712-gem-mapping-predicate-diagnostic-v1'
_BASE_SOURCES=inherited.base.sources

class _Profile:
    derive=staticmethod(profile.derive)
    sources=staticmethod(profile.sources)
    marker=staticmethod(inherited.retry.trial.marker)
    loader=staticmethod(inherited.retry.trial.loader)
    psci=staticmethod(inherited.retry.trial.psci)
    BOOTARGS=inherited.retry.trial.BOOTARGS

def sha(path):return inherited.sha(path)
def sources():
    own=[Path(__file__).resolve(),ROOT/'tools/rpi5/check_gem_mapping_predicate_trial.py',
        ROOT/'tools/rpi5/tests/test_gem_mapping_predicate_trial.py']
    return list(dict.fromkeys([*_BASE_SOURCES(),*profile.sources(),*own]))
def required_sources():
    return [Path(__file__).resolve(),Path(profile.__file__).resolve(),
        ROOT/'tools/rpi5/check_gem_mapping_predicate_trial.py',
        ROOT/'tools/rpi5/tests/test_gem_mapping_predicate_trial.py',
        profile.PARENT/'manifest.json',profile.EVIDENCE]
def configure():
    inherited.configure();base=inherited.base
    base.PROFILE=PROFILE;base.profile=_Profile;base.sources=sources;base.core_sources=inherited.core_sources
    return base
def derived_sources():configure();return inherited.base.derived_sources()
def kernel_objects(output):configure();return inherited.base.kernel_objects(output)
def build(output=None):
    output=Path(output).resolve() if output else Path(tempfile.mkdtemp(prefix='gem-mapping-predicate-',dir=ROOT/'build/rpi5'))
    base=configure();output,m=base.build(output)
    m.update(profile=PROFILE,parent_retry_manifest=str(profile.PARENT/'manifest.json'),
        parent_retry_manifest_sha256=profile.PARENT_SHA,step14_evidence=str(profile.EVIDENCE),
        step14_evidence_sha256=profile.EVIDENCE_SHA,mapping_diagnostic=True,mapping_diagnostic_version=1,
        allocation_bytes=0x8000,descriptor_pages=2,packet_spans=0,
        all_inbound_windows_disabled=False,preferred_ram_route_only=True,
        queue_publication=False,bme_enable=False,dma_activation=False,irq_activation=False,
        packet_mapping=False,hardware_executed=False,staged=False,
        generated_sha256={str(p):sha(p) for p in output.rglob('*') if p.is_file() and p.name!='manifest.json'})
    (output/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    return output,m
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path)
    out,m=build(p.parse_args().output_dir)
    print(json.dumps(dict(package=str(out),manifest_sha256=sha(out/'manifest.json'),kernel_sha256=m['kernel_sha256'],image_sha256=m['image_sha256']),sort_keys=True))
