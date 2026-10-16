# SPDX-License-Identifier: BSD-2-Clause
"""Distinct genuine sleepable preparation and finite CPU-only controller caller."""
from pathlib import Path
from tools.rpi5 import gem_dma_batch_profile as memory
ROOT=memory.ROOT
FROZEN=ROOT/'build/rpi5/pcie-gem-capabilities-kernel-20261013-v1/overlay'
change=memory.change
def header(text):
    text=change(text,'#include "BCM2712RP1ConfigPolicy.h"',
        '#include "BCM2712RP1ConfigPolicy.h"\n#include "BCM2712GEMDMABatch.h"')
    text=change(text,'    bool runBoundedRP1Trial(',
        '    bool prepareCPUOwnedRings();\n    bool runBoundedRP1Trial(')
    return change(text,'    struct rpi5_gem_cap_observation capabilityObserved={};',
        '''    struct rpi5_gem_cap_observation capabilityObserved={};
    BCM2712GEMDMABatch *dmaMemory=nullptr;
    unsigned dmaPreparePhase=0; /*0empty,1preparing,2ready,3quarantined*/
    bool dmaRingAttempted=false,dmaRingActive=false,dmaRingRevoked=false;
    struct rpi5_gem_dma_route dmaCandidate={};
    struct BCM2712GEMDMALive dmaLive={};
    struct rpi5_gem_stage_observation dmaRingsObserved={};
    int dmaRingSource() const;
    static int dmaRingCurrent(void *,const BCM2712GEMDMABatch *,const struct rpi5_gem_cap_session *,uint64_t *);
    bool stagePreparedCPUOwnedRings();''')
def admission(text):
    return change(text,'''    struct rpi5_pcie_released_observation observed;
    return rpi5_pcie_released_windows_check(&self->trialWindows,&observed);''',
        '''    /* The one real memory qualification replaces this exact existing
     *90-read callback; it does not add a nested transport guard or lease. */
    if(!self->dmaMemory)return -1;
    if(self->dmaMemory->state()==BCM2712GEMDMABatch::Prepared)
        return self->dmaMemory->qualify(&self->trialWindows,&self->dmaCandidate)?0:-1;
    auto state=self->dmaMemory->state();
    if(state!=BCM2712GEMDMABatch::Held && state!=BCM2712GEMDMABatch::Staging &&
        state!=BCM2712GEMDMABatch::RingsHeld)return -1;
    struct rpi5_pcie_released_observation observed;
    return rpi5_pcie_released_windows_check(&self->trialWindows,&observed);''')
def gem(text):
    return change(text,'    self->diagGemCall=2;return 0;',
        '''    if(!self->stagePreparedCPUOwnedRings())return -7;
    self->diagGemCall=2;return 0;''')+'\n'+(ROOT/'iokit/Kernel/BCM2712GEMDMABatchTransport.inc').read_text()
def caller(text):
    return change(text,'    if(prepared)ok=transport->runBoundedRP1Trial(&observed);',
        '    if(prepared)prepared=transport->prepareCPUOwnedRings();\n'
        '    if(prepared)ok=transport->runBoundedRP1Trial(&observed);')
def derive():
    files={p.name:p.read_bytes() for p in FROZEN.iterdir() if p.is_file()}
    for name,transform in (
        ('BCM2712PCIePHYTransport.h',header),('BCM2712PCIeIDTrialProgress.inc',lambda s:caller(admission(s))),
        ('BCM2712RP1GEMIdentifyTransport.inc',gem)):
        files[name]=transform(files[name].decode()).encode()
    for name,data in memory.derive().items():
        if name in files and files[name]!=data:raise ValueError('Private header conflict: '+name)
        files[name]=data
    return files
def emit(folder):
    folder=Path(folder);folder.mkdir(exist_ok=False)
    for name,data in derive().items():(folder/name).write_bytes(data)
    return folder/'BCM2712PCIePHYTransport.cpp'
