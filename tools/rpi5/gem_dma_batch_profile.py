# SPDX-License-Identifier: BSD-2-Clause
"""CPU-owned batched successor; no active inbound route or DMA claim."""
from pathlib import Path
import hashlib
from tools.rpi5 import gem_dma_rings_recipe_v1 as prior
ROOT=prior.ROOT
BASE_PINS={'tools/rpi5/gem_dma_rings_profile.py': '61bc42eca7f1a7f0d9983b589c39005f3b32beb04df69db030a5dd9aa5ce86f0', 'tools/rpi5/gem_dma_rings_recipe_v1.py': '2d3fca2b3c2fad25c113e0525213a3a103baa6c07e16f57eb1565150e529e810', 'iokit/Kernel/BCM2712GEMDMARings.inc': 'c9c1b529a70b0d899cb09b4ec5f32717bf5b4dc82fd7ebb586369323123ff97f', 'iokit/Kernel/BCM2712GEMDMARingsMapping.inc': '359373b1593303bc2c37d8a4812065b9341596d5c80c9d6a300718efc2def510', 'iokit/Kernel/BCM2712GEMDMARingsRoute.inc': 'bb53b63182dea13fa0faf0e4c1b516db887908596c4a1f7ec1ddcfab1bc21c7d', 'iokit/Kernel/BCM2712GEMDMARingsLifecycle.inc': '00574429010013c6abceadcd5f8ac1557e890254ba2c5443d8d288927046ba55'}
def change(text,old,new,count=1):
    if text.count(old)!=count:raise ValueError('Frozen batch anchor differs: '+old)
    return text.replace(old,new)
def derive():
    for path,digest in BASE_PINS.items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=digest:raise ValueError('Frozen word provider drift: '+path)
    files=prior.derive()
    h=files.pop('BCM2712GEMDMARings.h').decode().replace('BCM2712GEMDMARings','BCM2712GEMDMABatch')
    h=h.replace('BCM2712_GEM_DMA_RINGS_H','BCM2712_GEM_DMA_BATCH_H')
    h=change(h,'#include "rpi5_gem_ring_stage.h"','#include "rpi5_gem_ring_batch.h"')
    h=h.replace('retained programmed inbound','retained independently disabled inbound')
    h=h.replace('Each of2564 ring checkpoints','Each of164 ring checkpoints')
    h=change(h,'unsigned,uint32_t,uint32_t);','unsigned,uint32_t,const uint32_t [16]);')
    h=change(h,'unsigned,uint32_t,uint32_t *);','unsigned,uint32_t,uint32_t [16]);')
    h=change(h,'    bool ringIntact() const;','    bool ringIntact() const;\n    bool disabled(const struct rpi5_pcie_window_plan *) const;')
    h=h.replace('struct rpi5_gem_stage_io ringIO_','struct rpi5_gem_batch_io ringIO_')
    h=h.replace('Successful output is qualified geometry only, not access authority.',
        'Successful output is candidate geometry only: every inbound slot remains disabled. It is NOT active DMA reachability.')
    c=files.pop('BCM2712GEMDMARings.cpp').decode().replace('BCM2712GEMDMARings','BCM2712GEMDMABatch')
    a=c.index('int BCM2712GEMDMABatch::ringWrite(');b=c.index('int BCM2712GEMDMABatch::ringBarrier(',a)
    c=c[:a]+(ROOT/'iokit/Kernel/BCM2712GEMDMABatchAccess.inc').read_text()+'\n'+c[b:]
    c=change(c,'rpi5_gem_ring_stage_access_allowed(s,RPI5_GEM_STAGE_BARRIER,0,0,0)',
        'rpi5_gem_ring_batch_access_allowed(s,RPI5_GEM_STAGE_BARRIER,0,0)')
    c=change(c,'rpi5_gem_ring_stage(&ringSession_,&ringRequest_,&ringIO_,&result)',
        'rpi5_gem_ring_batch(&ringSession_,&ringRequest_,&ringIO_,&result)')
    c=change(c,'!route(&windows->expected,&geometry)',
        '(!disabled(&windows->expected) || !route(&expected_,&geometry))',2)
    files['BCM2712GEMDMABatch.h']=h.encode();files['BCM2712GEMDMABatch.cpp']=c.encode()
    files['rpi5_gem_ring_batch.h']=(ROOT/'iokit/Kernel/rpi5_gem_ring_batch.h').read_bytes()
    return files
def emit(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    for name,data in derive().items():(folder/name).write_bytes(data)
    return folder/'BCM2712GEMDMABatch.h',folder/'BCM2712GEMDMABatch.cpp'
