# SPDX-License-Identifier: BSD-2-Clause
"""Pure canonical recipe for the frozen word-provider prototype; no file writes."""
from tools.rpi5.gem_dma_rings_profile import ROOT,PINS,LIVE,PUBLIC,PRIVATE,replace
import hashlib
PROFILE_SHA='61bc42eca7f1a7f0d9983b589c39005f3b32beb04df69db030a5dd9aa5ce86f0'
def derive():
    if hashlib.sha256((ROOT/'tools/rpi5/gem_dma_rings_profile.py').read_bytes()).hexdigest()!=PROFILE_SHA:
        raise ValueError('Frozen provider recipe changed')
    for path,digest in PINS.items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=digest:raise ValueError('Frozen source drift: '+path)
    # The independent historical DMA and GEM-identify APIs used the same enum
    # spelling. Preserve their numeric ABI and all frozen bodies; only this
    # private header's buffer-state enumerator gets an unambiguous name.
    dma=(ROOT/'iokit/Kernel/rpi5_gem_dma.h').read_text()
    result={'rpi5_gem_dma.h':dma.replace('RPI5_GEM_QUARANTINED','RPI5_GEM_BUFFER_QUARANTINED').encode()}
    result['rpi5_gem_ring_stage.h']=(ROOT/'iokit/Kernel/rpi5_gem_ring_stage.h').read_bytes()
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
    result['BCM2712GEMDMARings.h']=header.encode();result['BCM2712GEMDMARings.cpp']=body.encode()
    return result
