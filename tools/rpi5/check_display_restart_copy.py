#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Byte-only exact one-loader-owner successor; no compiler or hardware."""
from pathlib import Path
import re
from . import build_display_restart_copy as b
same=b.previous_check.same

def inspect(package,expected=None):
    p=Path(package).resolve();mp=p/'manifest.json'
    if p.parent!=b.ROOT/'build/rpi5' or not p.name.startswith('display-restart-copy-'):raise ValueError('Distinct copy-phase package')
    if expected is not None and b.sha(mp)!=expected:raise ValueError('Exact manifest')
    m=b.document(mp);pins=m['inputs_sha256'];generated=m['generated_sha256']
    if set(generated)!={str(f) for f in p.iterdir() if f.is_file() and f!=mp}:raise ValueError('Complete generated closure')
    for name,digest in {**pins,**generated}.items():
        if not re.fullmatch('[a-f0-9]{64}',digest) or b.sha(name)!=digest:raise ValueError('Changed closure '+name)
    if pins.get(str(b.BASE/'manifest.json'))!=b.BASE_SHA:raise ValueError('Exact parent pin')
    base=b.document(b.BASE/'manifest.json')
    for key in ('inputs_sha256','headers_sha256','generated_sha256'):
        if any(pins.get(n)!=v for n,v in base[key].items()):raise ValueError('Inherited closure omission')
    for path in b.sources():
        if pins.get(str(path))!=b.sha(path):raise ValueError('New source omission')
    if (p/'probe_main.c').read_text()!=b.generated_main():raise ValueError('Exact minimal phase derivation')
    tag=m['tag']
    if not re.fullmatch('[0-9a-f]{32}',tag):raise ValueError('Unique tag')
    plan=b.command_plan(p,tag)
    if len(m['commands'])!=len(plan):raise ValueError('Complete commands')
    for actual,wanted in zip(m['commands'],plan):
        if any(not same(actual.get(k),v) for k,v in wanted.items()) or not same(actual.get('returncode'),0):raise ValueError('Exact compile/link flags and objects')
        if actual['log']!=str(p/(wanted['label']+'.log')) or actual['log_sha256']!=b.sha(actual['log']):raise ValueError('Exact command log')
    before=sorted(b.prior.original.display.dependencies(p/'loader-main.scan.d',b.ROOT))
    after=sorted(b.prior.original.display.dependencies(p/'loader-main.actual.d',b.ROOT))
    if before!=after or not same(m['compiler_scans'],{'loader-main':before}) or not same(m['headers_sha256'],{n:pins[n] for n in before}):raise ValueError('Actual header closure')
    for name in b.COPIES:
        if (p/name).read_bytes()!=(b.BASE/name).read_bytes():raise ValueError('Frozen kernel/root/payload changed')
    raw=(p/'probe.bin').read_bytes();payload=(p/'payload.bin').read_bytes();offset=m['payload_offset']
    if type(offset)is not int or offset%64 or raw.find(payload)!=offset or raw.find(payload,offset+1)>=0:raise ValueError('Actual payload embedding')
    marker=b.MARKER+tag+' SAME_BOOT OWNED_FRAMEBUFFER_CONSOLE_V1'
    if raw.count(marker.encode())!=1:raise ValueError('Actual unique tag')
    symbols=b.prior.original.formats.elf((p/'display_restart.elf').read_bytes(),raw)
    if symbols['__stack_top'][0]-symbols['__bss_end'][0]!=32768:raise ValueError('Unchanged loader stack required')
    if (p/'loader-undefined.log').read_text().strip():raise ValueError('Loader undefined')
    def frames(path):
        rows=[line.split('\t') for line in path.read_text().splitlines()]
        if any(len(r)!=3 or r[2]!='static' for r in rows):raise ValueError('Static bounded frames required')
        return {r[0].rsplit(':',1)[-1]:int(r[1]) for r in rows}
    old_frames=frames(b.BASE/'loader-main.su');new_frames=frames(p/'loader-main.su')
    if set(new_frames)-set(old_frames)-{'copy_phase_equal','copy_phase_transfer'}:raise ValueError('Unexpected loader function set')
    if any(size>max(old_frames.get(n,0)+256,256) for n,size in new_frames.items()):raise ValueError('Unexpected loader frame increase')
    contract=dict(profile=b.PROFILE,parent=str(b.BASE),parent_manifest_sha256=b.BASE_SHA,
        image=str(p/'probe.bin'),image_sha256=b.sha(p/'probe.bin'),image_bytes=len(raw),
        kernel_sha256=base['kernel_sha256'],root_sha256=base['root_sha256'],root_bytes=base['root_bytes'],root_nodes=33,
        copy_phase_contract=b.CONTRACT)
    if any(not same(m.get(k),v) for k,v in contract.items()):raise ValueError('Exact limits and workload')
    report=b.previous_check.inspect(b.BASE,b.BASE_SHA)
    # The inherited conservative budget already sums the original loader's
    # frames. Add every positive new-frame delta rather than reporting stale
    # stack/live-range metadata from the parent composition.
    budget=report['stack_budget']+sum(max(0,size-old_frames.get(n,0)) for n,size in new_frames.items())
    if budget>32768:raise ValueError('Conservative stack budget exceeds original stack')
    report.update(contract,package=str(p),manifest_sha256=b.sha(mp),tag=tag,trial_marker=marker,
        root_catalog=str(p/'root-catalog.json'),root_catalog_sha256=b.sha(p/'root-catalog.json'),
        actual_loader_end=symbols['__probe_end'][0],stack_budget=budget,
        source_members=len(pins),generated_members=len(generated),
        copy_phase_checks=dict(one_loader_owner_replaced=True,unchanged_kernel_root_payload=True,
            actual_original_object_link=True,exact_two_phase_renewals=True,unchanged_limits=True,
            phase_order_fail_closed=True,late_transfer_fail_closed=True,complete_source_header_closure=True),
        loader_stack_frames=new_frames)
    return report
