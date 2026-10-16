#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Offline composition of contained all-six-BAR inventory and proven C1 policy.

No loader or hardware trial is created. The BAR caller still performs no memory
decode enable, bus mastering, device MMIO or assignment; access failures retain
the original terminal-quarantine semantics, not an exact-restoration promise.
"""
import argparse
import importlib.util
import json
from pathlib import Path
try:
    from . import build_pcie_axi_trace_kernel as ancestor
except ImportError:
    import build_pcie_axi_trace_kernel as ancestor

ROOT=ancestor.ROOT
BASE=ROOT/'build/rpi5/rp1-all-bars-kernel-20261013-checked'
BASE_SHA='1402041446cde952c27b18e6ce10894bd7f0845df1a5a6c152ceb3b99a4ec14e'
AXI=ROOT/'build/rpi5/pcie-axi-trace-kernel-20261013-v2'
AXI_SHA='fa38950c85264d4a635f1b20b511071f7af9d564f53c9600756312dc6924d644'
SOURCE=ROOT/'tools/rpi5/build_pcie_axi_trace_kernel.py'
TEST=ROOT/'tools/rpi5/tests/test_rp1_bars_axi_kernel.py'


def configured_builder():
    # The frozen relinker has one marker-identity assertion. Adapt only that
    # assertion and its metadata name; all real compile/link checks stay exact.
    text=SOURCE.read_text()
    text=ancestor.profile.once(text,"b'RPI5XNU:PCIEID:END OK='","b'RPI5XNU:PCIEBARS:END OK='")
    text=ancestor.profile.once(text,'passive_trace_unchanged=True','bar_diagnostics_unchanged=True')
    spec=importlib.util.spec_from_file_location('_rp1_bars_c1_relink',SOURCE)
    b=importlib.util.module_from_spec(spec)
    exec(compile(text,str(SOURCE),'exec'),b.__dict__)
    b.BASE=BASE;b.BASE_SHA=BASE_SHA;b.PROFILE='rp1-all-bars-size-restore-c1-axi-kernel-v1'
    old_inputs=b.inputs
    def inputs():
        old,pins=old_inputs()
        if b.audit.sha(AXI/'manifest.json')!=AXI_SHA:raise ValueError('Frozen corrected AXI kernel changed')
        prior=json.loads((AXI/'manifest.json').read_text())
        inherited=prior['inputs_sha256']|prior['generated_sha256']|{str(AXI/'manifest.json'):AXI_SHA}
        for p in (Path(__file__).resolve(),TEST):inherited[str(p)]=b.audit.sha(p)
        for name,digest in inherited.items():
            if name in pins and pins[name]!=digest:raise ValueError('Combined BAR/AXI pin conflict: '+name)
            pins[name]=digest
        b.verify(pins);return old,pins
    b.inputs=inputs
    return b


def build(output):
    b=configured_builder();r=b.build(output)
    r.pop('hardware_failure_receipt',None)
    r.update(axi_parent_manifest_sha256=AXI_SHA,bar_parent_manifest_sha256=BASE_SHA,
        loader_created=False,physical_trial_admitted=False,
        required_next_evidence='Fresh controller/link/RP1 ID success before any BAR sizing hardware trial',
        trial_scope='Offline composition only: exact original contained all-BAR caller plus three C1-aware AXI objects')
    (output/'manifest.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
    return r


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',required=True,type=Path)
    r=build(p.parse_args().output_dir.resolve())
    print(json.dumps({k:r[k] for k in ('profile','kernel','kernel_bytes','kernel_sha256')}))
