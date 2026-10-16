# SPDX-License-Identifier: BSD-2-Clause
"""Private actual-Apple provider successor; leaves qualification prototype intact."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[2]
PINS={
    'iokit/Kernel/BCM2712GEMDMAMemory.cpp':'26d4a432679d5814b06d615098b68efdbe7d6609a946814c1e9781607e56ddc7',
    'iokit/Kernel/BCM2712GEMDMAMemory.h':'baf37cb9b4836c8add6627cdec4fe486b50c3825aecc63a6ae613dc7fe80d1d9',
    'iokit/Kernel/rpi5_gem_ring_stage.c':'b297cd649a9e9534cbfd51db33e00526aa40802376d05cf0f48ce6abc2b64fdf',
    'iokit/Kernel/rpi5_gem_ring_stage.h':'7f20e7a68a7589a3908ee290d8c4a0daa80a9a179d86d811a4d0f8e638b79364'}
LIVE='''
class BCM2712GEMDMARings;
struct BCM2712GEMDMALive {
    void *context;
    const void *owner;
    const struct rpi5_gem_cap_session *capabilities;
    uint64_t generation,not_before,deadline; /* monotonic microseconds */
    /* Genuine driver's fresh owner/phase/thread, retained programmed inbound
     * route, same live GEM identity/capabilities/Device maps and independently
     * proven no DMA or queue publication. Return fresh monotonic microseconds.
     * Must exclude competing writers/revocation throughout this call; no
     * receipts/boolean test shim as production authority. This new lifecycle
     * is NOT the nearly exhausted reset-test lease. No provider is installed
     * by this default-off TU: the actual driver's caller remains to be added. */
    int (*current)(void *,const BCM2712GEMDMARings *,const struct rpi5_gem_cap_session *,uint64_t *);
};
'''
PUBLIC='''
    static constexpr uint64_t StageMaximumUS=500000;
    /* At most640 CPU descriptor writes+640 readbacks+one DSB. All160 slots
     * (including32 padding entries) remain CPU-owned. No packet-memory access,
     * queue register, descriptor release, DMA enable or raw handle export.
     * The output/live objects must be stable and disjoint from this provider.
     * Each of2564 ring checkpoints checks retained mappings, then invokes the
     * fresh real owner returning current time; no guard or cache authority is
     * memoized. Failure retains all storage, including partially staged RAM. */
    bool stageCPUOwned(const struct BCM2712GEMDMALive *,struct rpi5_gem_stage_observation *);
'''
PRIVATE='''
    const struct rpi5_reservation_record *resolved_=nullptr;
    bool ringIntact() const;
    static int ringCurrent(void *,const struct rpi5_gem_stage_session *,const struct rpi5_gem_stage_request *,uint64_t *);
    static int ringWrite(void *,const struct rpi5_gem_stage_session *,unsigned,uint32_t,uint32_t);
    static int ringRead(void *,const struct rpi5_gem_stage_session *,unsigned,uint32_t,uint32_t *);
    static int ringBarrier(void *,const struct rpi5_gem_stage_session *);
    const struct BCM2712GEMDMALive *liveSource_=nullptr;
    struct BCM2712GEMDMALive live_={};
    struct rpi5_gem_cap_session capSnapshot_={};
    struct rpi5_gem_identify identitySnapshot_={};
    const struct rpi5_rp1_decode_cycle *decodeSource_=nullptr;
    struct rpi5_rp1_decode_cycle decodeSnapshot_={};
    const struct rpi5_rp1_assignment *assignmentSource_=nullptr;
    struct rpi5_rp1_assignment assignmentSnapshot_={};
    struct rpi5_gem_stage_session ringSession_={};
    struct rpi5_gem_stage_request ringRequest_={};
    struct rpi5_gem_stage_io ringIO_={};
'''
def replace(text,old,new,count=1):
    if text.count(old)!=count:raise ValueError('Unique frozen source anchor changed: '+old)
    return text.replace(old,new)
def emit(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    for path,digest in PINS.items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=digest:raise ValueError('Frozen source drift: '+path)
    # The independent historical DMA and GEM-identify APIs used the same enum
    # spelling. Preserve their numeric ABI and all frozen bodies; only this
    # private header's buffer-state enumerator gets an unambiguous name.
    dma=(ROOT/'iokit/Kernel/rpi5_gem_dma.h').read_text()
    (folder/'rpi5_gem_dma.h').write_text(dma.replace('RPI5_GEM_QUARANTINED','RPI5_GEM_BUFFER_QUARANTINED'))
    (folder/'rpi5_gem_ring_stage.h').write_bytes((ROOT/'iokit/Kernel/rpi5_gem_ring_stage.h').read_bytes())
    header=(ROOT/'iokit/Kernel/BCM2712GEMDMAMemory.h').read_text().replace('BCM2712GEMDMAMemory','BCM2712GEMDMARings')
    header=header.replace('BCM2712_GEM_DMA_MEMORY_H','BCM2712_GEM_DMA_RINGS_H')
    header=replace(header,'#include "rpi5_gem_dma_route.h"','#include "rpi5_gem_dma_route.h"\n#include "rpi5_gem_ring_stage.h"')
    header=replace(header,'#include "../../loader/rpi5/pcie_profile.h"','#include "pcie_profile.h"\n#include "rp1_gem_capabilities.h"\n#include "arm64/rpi5_reservation_kernel.h"\n#include "arm64/rpi5_reservation_api.h"')
    header=header.replace('"../../loader/rpi5/pcie_released_windows.h"','"pcie_released_windows.h"')
    header=replace(header,'class BCM2712GEMDMARings final {',LIVE+'\nclass BCM2712GEMDMARings final {')
    header=replace(header,'Quarantined, Discarding, Discarded','Quarantined, Discarding, Discarded, Staging, RingsHeld')
    header=replace(header,'    State state() const',PUBLIC+'    State state() const')
    header=replace(header,'private:\n','private:\n'+PRIVATE)
    header=replace(header,'    BCM2712GEMDMARings()=default;',
        '''    BCM2712GEMDMARings() {
        /* The original ring core requires all initial session bytes zero,
         * including padding. This is constructor-only, never a lease reset. */
        auto *p=(unsigned char *)&ringSession_;
        for(size_t i=0;i<sizeof ringSession_;i++)p[i]=0;
    }''')
    body=(ROOT/'iokit/Kernel/BCM2712GEMDMAMemory.cpp').read_text().replace('BCM2712GEMDMAMemory','BCM2712GEMDMARings')
    body=replace(body,'state_==Preparing || state_==Checking || state_==Discarding',
        'state_==Preparing || state_==Checking || state_==Discarding || state_==Staging',3)
    begin=body.index('bool BCM2712GEMDMARings::mapping()')
    end=body.index('bool BCM2712GEMDMARings::route(',begin)
    body=body[:begin]+(ROOT/'iokit/Kernel/BCM2712GEMDMARingsMapping.inc').read_text()+'\n'+body[end:]
    begin=body.index('bool BCM2712GEMDMARings::route(')
    end=body.index('bool BCM2712GEMDMARings::prepare()',begin)
    body=body[:begin]+(ROOT/'iokit/Kernel/BCM2712GEMDMARingsRoute.inc').read_text()+'\n'+body[end:]
    begin=body.index('bool BCM2712GEMDMARings::prepare()')
    end=body.index('bool BCM2712GEMDMARings::qualify(',begin)
    body=body[:begin]+(ROOT/'iokit/Kernel/BCM2712GEMDMARingsLifecycle.inc').read_text()+'\n'+body[end:]
    body+='\n'+(ROOT/'iokit/Kernel/BCM2712GEMDMARings.inc').read_text()
    hp=folder/'BCM2712GEMDMARings.h';cp=folder/'BCM2712GEMDMARings.cpp'
    hp.write_text(header);cp.write_text(body);return hp,cp
