#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Strict byte/package checker for the mapping-predicate diagnostic."""
import argparse,ast,json,re,struct
from pathlib import Path
from tools.rpi5 import build_gem_mapping_predicate_trial as b
from tools.rpi5 import check_display_xnu_console as macho

def inspect(package,manifest_sha256):
    package=Path(package).resolve();mp=package/'manifest.json'
    if b.sha(mp)!=manifest_sha256:raise ValueError('Exact manifest pin differs')
    m=json.loads(mp.read_bytes())
    if package.parent!=b.ROOT/'build/rpi5' or not package.name.startswith('gem-mapping-predicate-'):
        raise ValueError('Distinct mapping diagnostic package required')
    if m.get('profile')!=b.PROFILE or m.get('parent_retry_manifest_sha256')!=b.profile.PARENT_SHA or m.get('step14_evidence_sha256')!=b.profile.EVIDENCE_SHA:
        raise ValueError('Diagnostic provenance differs')
    for group in ('inputs_sha256','generated_sha256'):
        for path,pin in m[group].items():
            if b.sha(path)!=pin:raise ValueError('Pinned bytes changed: '+path)
    for path in b.required_sources():
        if m['inputs_sha256'].get(str(Path(path).resolve()))!=b.sha(path):raise ValueError('Required source omitted')
    files=b.derived_sources();c=files['overlay/BCM2712GEMDMABatch.cpp'].decode();p=files['overlay/BCM2712PCIeIDTrialProgress.inc'].decode()
    if c.count('return fail(')!=31 or 'mappingReason_=41;return true;' not in c:
        raise ValueError('Complete mapping predicate table differs')
    if c.count('translated_nc(')!=3 or c.count('pmap_cache_attributes(')!=2:
        raise ValueError('Translation/cache predicate ownership differs')
    body=c[c.index('bool BCM2712GEMDMABatch::mapping() const'):c.index('\n}\n\n/* SPDX-License-Identifier: BSD-2-Clause */\nbool BCM2712GEMDMABatch::route')]
    if any(word in body for word in ('kprintf','IOLog','printf','bcopy','memcpy','flush','invalidate','clean_dcache')):
        raise ValueError('Logging/copy/cache-maintenance operation entered mapping predicate')
    row='RPI5XNU:PCIEID:DMA_MAP REASON=%u PAGE=%u ATTR=%u VA=%u PA=%llu PAR_R=%llu PAR_W=%llu\\n'
    if p.count(row)!=1:raise ValueError('Unique bounded diagnostic row absent')
    raw=(package/'kernel.cpu-rings').read_bytes();symbols,_=macho.macho(raw)
    if struct.unpack_from('<II',raw)[:2]!=(0xfeedfacf,0x0100000c) or '_rpi5_gem_ring_only_batch' not in symbols:
        raise ValueError('Actual AArch64 ring-only kernel required')
    if raw.count(ast.literal_eval('"'+row+'"').encode()+b'\0')!=1:raise ValueError('Diagnostic row not linked exactly once')
    false=('queue_publication','bme_enable','dma_activation','irq_activation','packet_mapping','hardware_executed','staged')
    if any(m.get(k) is not False for k in false) or m.get('allocation_bytes')!=32768 or m.get('packet_spans')!=0:
        raise ValueError('Passive diagnostic contract differs')
    return dict(profile=b.PROFILE,package=str(package),manifest_sha256=manifest_sha256,
        image_sha256=m['image_sha256'],kernel_sha256=m['kernel_sha256'],mapping_steps=41,
        allocation_bytes=32768,packet_spans=0,bme=False,dma=False,irq=False,queues=False,
        hardware_executed=False,software_qualified=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path);p.add_argument('--manifest-sha256',required=True);p.add_argument('--report',type=Path)
    a=p.parse_args();r=inspect(a.package,a.manifest_sha256)
    if a.report:
        with a.report.resolve().open('x') as f:json.dump(r,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps(r,sort_keys=True))
