#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the distinct ring-only allocation retry image; offline only.

This deliberately reuses the frozen v8 boot/root/loader composition and the
already-audited complete recipe.  Only the qualified provider overlay and the
ring-only C core replace their v8 counterparts.  It never stages an SD card.
"""
import argparse
import json
from pathlib import Path
import tempfile
from tools.rpi5 import build_gem_dma_batch_trial as base
from tools.rpi5 import gem_cpu_ring_retry_profile as retry

ROOT=base.ROOT
PROFILE='bcm2712-gem-ring-only-allocation-retry-trial-v1'
QUALIFICATION=ROOT/'build/rpi5/gem-cpu-ring-retry-qualification-20261014/qualification.json'
QUALIFICATION_SHA='3461e0c10d4bcea8ba5a725f2abc1df57c0b4763896e9a572555c6885fbc92c7'
FAILED_CAPTURE=retry.CAPTURE
FAILED_CAPTURE_SHA=retry.CAPTURE_SHA
_BASE_SOURCES=base.sources
_BASE_CORE_SOURCES=base.core_sources

class _Profile:
    derive=staticmethod(retry.derive)
    sources=staticmethod(retry.sources)
    marker=staticmethod(retry.trial.marker)
    loader=staticmethod(retry.trial.loader)
    psci=staticmethod(retry.trial.psci)
    BOOTARGS=retry.trial.BOOTARGS

def sha(path):return base.sha(path)

def sources():
    own=[Path(__file__).resolve(),QUALIFICATION,FAILED_CAPTURE,
        ROOT/'tools/rpi5/tests/gem_ring_only_host.c',
        ROOT/'tools/rpi5/tests/test_gem_cpu_ring_retry.py',
        ROOT/'tools/rpi5/gem_cpu_ring_retry_completeness_v1.py',
        ROOT/'tools/rpi5/check_gem_cpu_ring_retry_trial.py',
        ROOT/'tools/rpi5/qualify_gem_cpu_ring_retry_trial.py',
        ROOT/'tools/rpi5/gem_cpu_ring_retry_serial.py',
        ROOT/'tools/rpi5/tests/test_gem_cpu_ring_retry_trial.py',
        ROOT/'tools/rpi5/tests/test_gem_cpu_ring_retry_serial.py']
    return list(dict.fromkeys([*_BASE_SOURCES(),*retry.sources(),*own]))

def core_sources():
    result=[]
    for path in _BASE_CORE_SOURCES():
        result.append(ROOT/'iokit/Kernel/rpi5_gem_ring_only_batch.c'
            if path.name=='rpi5_gem_ring_batch.c' else path)
    result.append(ROOT/'iokit/Kernel/rpi5_gem_ram_window.c')
    return result

def configure():
    """Install the retry recipe in the inherited deterministic composer."""
    base.PROFILE=PROFILE;base.profile=_Profile;base.sources=sources;base.core_sources=core_sources
    return base

def derived_sources():configure();return base.derived_sources()
def kernel_objects(output):configure();return base.kernel_objects(output)
def plan(output,tag):configure();return base.plan(output,tag)
def parents():return base.parents()

def build(output=None):
    if sha(QUALIFICATION)!=QUALIFICATION_SHA:raise ValueError('Exact retry qualification changed')
    if sha(FAILED_CAPTURE)!=FAILED_CAPTURE_SHA:raise ValueError('Actual failed-board evidence changed')
    if output is None:
        output=Path(tempfile.mkdtemp(prefix='gem-cpu-ring-retry-trial-',dir=ROOT/'build/rpi5'))
    output=Path(output).resolve();configure();output,m=base.build(output)
    # Correct the inherited conservative manifest vocabulary.  The preferred
    # RAM aperture is read-back qualified, but BME, queues, DMA, IRQ and packet
    # spans remain absent.  generated_sha256 deliberately excludes manifest.
    m.update(profile=PROFILE,qualification=str(QUALIFICATION),qualification_sha256=QUALIFICATION_SHA,
        failed_capture=str(FAILED_CAPTURE),failed_capture_sha256=FAILED_CAPTURE_SHA,
        allocation_bytes=0x8000,descriptor_pages=2,packet_spans=0,
        preparation_steps=17,ring_expected_packets=0,
        all_inbound_windows_disabled=False,preferred_ram_route_only=True,
        candidate_addresses_not_dma_authority=False,dma_completion_proven=False,
        queue_publication=False,bme_enable=False,dma_activation=False,irq_activation=False,
        packet_mapping=False,hardware_executed=False,staged=False,
        generated_sha256={str(p):sha(p) for p in output.rglob('*') if p.is_file() and p.name!='manifest.json'})
    (output/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    return output,m

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path)
    output,m=build(p.parse_args().output_dir)
    print(json.dumps(dict(package=str(output),manifest_sha256=sha(output/'manifest.json'),
        kernel_sha256=m['kernel_sha256'],image_sha256=m['image_sha256']),sort_keys=True))
