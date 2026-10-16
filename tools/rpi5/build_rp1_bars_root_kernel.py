#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""New root-route child: contained BAR inventory and bounded Apple logging."""
import argparse
import json
from pathlib import Path
try:
    from . import build_rp1_bars_elapsed_kernel as template
    from . import rp1_bars_root_profile as profile
except ImportError:
    import build_rp1_bars_elapsed_kernel as template
    import rp1_bars_root_profile as profile

ROOT,audit,verify=template.ROOT,template.audit,template.verify
BASE=ROOT/'build/rpi5/pcie-root-route-kernel-20261013-v3'
BASE_SHA='753ba1093e852d46a61f6b4804c69537279cc91390eb33af6b10f1e25896a355'
PROFILE='rp1-six-bars-root-route-bounded-log-kernel-v1'
TEST=ROOT/'tools/rpi5/tests/test_rp1_bars_root_kernel.py'


def configured():
    b=template.previous.loader.load_private(Path(template.__file__).resolve(),'_rp1_bars_root_kernel')
    b.BASE=BASE;b.BASE_SHA=BASE_SHA;b.PROFILE=PROFILE;b.TEST=TEST;b.profile=profile
    def inputs():
        pins={};parents=[]
        for folder,digest in ((BASE,BASE_SHA),(b.BARS,b.BARS_SHA)):
            if audit.sha(folder/'manifest.json')!=digest:raise ValueError('Frozen routing/BAR constituent changed')
            m=json.loads((folder/'manifest.json').read_text());parents.append(m)
            more=m['inputs_sha256']|m['generated_sha256']|{str(folder/'manifest.json'):digest}
            for name,value in more.items():
                if name in pins and pins[name]!=value:raise ValueError('Routing/BAR pin conflict')
                pins[name]=value
        for path in (Path(__file__).resolve(),Path(template.__file__).resolve(),Path(profile.__file__).resolve(),
            Path(profile.bars.__file__).resolve(),Path(profile.logging.__file__).resolve(),TEST,
            ROOT/'tools/rpi5/tests/test_rp1_bars_root.py',ROOT/'tools/rpi5/tests/test_pcie_bounded_log.py',
            ROOT/'libkern/os/log_encode.c',ROOT/'libkern/os/log_encode_types.h',ROOT/'libkern/os/log.h',
            ROOT/'pexpert/arm/pe_kprintf.c',
            ROOT/'build/rpi5/root-route-serial-20261013/serial.bin',
            ROOT/'build/rpi5/rp1-config-v3-serial-20261013/serial.bin'):
            digest=audit.sha(path)
            if str(path) in pins and pins[str(path)]!=digest:raise ValueError('New source expected pin conflict')
            pins[str(path)]=digest
        verify(pins)
        trace=json.loads((template.previous.previous.previous.BASE/'manifest.json').read_text())
        return parents[0],trace,pins
    b.inputs=inputs
    return b


def build(output):
    b=configured();result=b.build(output)
    trial=(output/'overlay/BCM2712PCIeIDTrialProgress.inc').read_text()
    if trial.count('kprintf(')!=14:raise ValueError('Bounded records missing')
    result.update(logging_format='framed-per-subsystem-v1',logging_calls=14,
        logging_max_scalar_arguments=15,logging_native_max_encoded_bytes=100,
        global_log_encoder_unchanged=True,logging_assertions_enabled=True,
        final_end_after_all_diagnostics=True,root_route_object_unchanged=True,
        reset_clock_axi_config_snapshot_objects_unchanged=True,
        logging_adds_mmio=False,logging_changes_guards=False,logging_changes_deadlines=False,
        endpoint_write_offsets=[0x10+4*i for i in range(6)],
        endpoint_write_values='All-ones size probe or exact saved original for currently selected BAR only',
        endpoint_bar_types='All six must be MEM32/non-prefetch; 64-bit pairs, IO, reserved and prefetch shapes rejected before writes',
        bar_failure_exact_restoration_claimed=False,
        root_route_cause_physically_confirmed=True,clean_preceding_runtime_trial=False,
        root_route_physical_capture_sha256='cd2027571ae6b55d64b77772a6ec0d5c6af4248d5ba2d3b0807093dbc192f1b9',
        physical_id_receipt_required_before_trial=False,
        required_next_evidence='Guarded six-BAR size/restore capture with complete fault-free runtime interval and independent NVMe recovery',
        trial_scope='Root-route, bounded diagnostic logging, six BAR size probes with exact originals restored on success and pure allocation plan; no assignment, COMMAND write, BAR MMIO, IRQ delivery, DMA or packets')
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True)
    r=build(parser.parse_args().output_dir.resolve())
    print(json.dumps({k:r[k] for k in ('profile','kernel','kernel_sha256','kernel_bytes')}))
