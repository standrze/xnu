# SPDX-License-Identifier: BSD-2-Clause
"""Narrow CPU-ring retry after the first real allocation rejection.

The frozen v8 image and its board evidence remain immutable.  This successor
uses the already-qualified preferred-RAM route, but allocates only two aligned
descriptor pages.  Packet mappings remain absent and all descriptors stay CPU
owned with zero packet addresses.  Preparation progress is retained so the
next board capture identifies the exact rejected Apple/FDT/IODMA boundary.
"""
from pathlib import Path
import hashlib
from tools.rpi5 import gem_dma_batch_trial_profile as trial
from tools.rpi5 import gem_dma_ram_profile as ram

ROOT=trial.ROOT
change=trial.change
FROZEN=ROOT/'build/rpi5/gem-dma-batch-trial-20261014-v8'
FROZEN_SHA='0439396fe0d74482c01ef6f22b291cbc8c8a848cc27f4b878ba94987e26e0f60'
CAPTURE=ROOT/'build/rpi5/gem-cpu-batch-capture-20261014/return.json'
CAPTURE_SHA='366c9bcbf0124c25c91530d1f4c6f161239a8749a725fe358d97d2f97034ab00'

def derive():
    if hashlib.sha256((FROZEN/'manifest.json').read_bytes()).hexdigest()!=FROZEN_SHA:
        raise ValueError('Frozen v8 parent changed')
    if hashlib.sha256(CAPTURE.read_bytes()).hexdigest()!=CAPTURE_SHA:
        raise ValueError('Actual failed-board evidence changed')
    files=ram.transform(trial.derive())
    def edit(name,old,new,count=1):
        files[name]=change(files[name].decode(),old,new,count).encode()

    edit('BCM2712GEMDMABatch.h','#include "rpi5_gem_ring_batch.h"',
        '#include "rpi5_gem_ring_only_batch.h"')
    edit('BCM2712GEMDMABatch.h','static constexpr uint64_t AllocationBytes=0x48000;',
        'static constexpr uint64_t AllocationBytes=0x8000;')
    edit('BCM2712GEMDMABatch.h',
        '    const struct rpi5_gem_stage_session &stageTrace() const { return ringSession_; }',
        '''    const struct rpi5_gem_stage_session &stageTrace() const { return ringSession_; }
    unsigned preparationStep() const { return prepareStep_; }
    int preparationError() const { return prepareError_; }''')
    edit('BCM2712GEMDMABatch.h',
        '    const struct rpi5_reservation_record *resolved_=nullptr;',
        '''    const struct rpi5_reservation_record *resolved_=nullptr;
    unsigned prepareStep_=0;
    int prepareError_=0;''')
    edit('BCM2712GEMDMABatch.h','struct rpi5_gem_batch_io ringIO_',
        'struct rpi5_gem_ring_only_io ringIO_')

    # Retain every original rejection and revocation condition.  Codes locate
    # the first failed boundary; they do not turn a failure into a retry.
    edit('BCM2712GEMDMABatch.cpp',
        '    state_=Preparing;thread_=(void *)current_thread();',
        '    state_=Preparing;thread_=(void *)current_thread();prepareStep_=1;prepareError_=0;')
    edit('BCM2712GEMDMABatch.cpp','    if (!fdt_) goto reject;',
        '    if (!fdt_) { prepareError_=-2;goto reject; }\n    prepareStep_=2;')
    edit('BCM2712GEMDMABatch.cpp',
        '        if (!bytes || rpi5_pcie_profile_decode(bytes,length,&binding_,&profile)) goto reject;',
        '        if (!bytes || rpi5_pcie_profile_decode(bytes,length,&binding_,&profile)) { prepareError_=-3;goto reject; }\n        prepareStep_=3;')
    edit('BCM2712GEMDMABatch.cpp','        if (rpi5_fdt_memory(bytes,length,&ram_)) goto reject;',
        '        if (rpi5_fdt_memory(bytes,length,&ram_)) { prepareError_=-4;goto reject; }\n        prepareStep_=4;')
    edit('BCM2712GEMDMABatch.cpp','        if (rpi5_fdt_reservation_plan(bytes,length,&reservations_)) goto reject;',
        '        if (rpi5_fdt_reservation_plan(bytes,length,&reservations_)) { prepareError_=-5;goto reject; }\n        prepareStep_=5;')
    edit('BCM2712GEMDMABatch.cpp','        if (rpi5_pcie_windows_plan(&binding_,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES,&expected_)) goto reject;',
        '        if (rpi5_pcie_windows_plan(&binding_,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES,&expected_)) { prepareError_=-6;goto reject; }\n        prepareStep_=6;')
    edit('BCM2712GEMDMABatch.cpp','        if (rc!=0 && rc!=1) goto reject;',
        '        if (rc!=0 && rc!=1) { prepareError_=-7;goto reject; }')
    edit('BCM2712GEMDMABatch.cpp','        if (!resolved_ || rpi5_reservation_record_validate_fdt(resolved_,bytes,length)) goto reject;',
        '        if (!resolved_ || rpi5_reservation_record_validate_fdt(resolved_,bytes,length)) { prepareError_=-8;goto reject; }\n        prepareStep_=7;')
    edit('BCM2712GEMDMABatch.cpp',
        '    buffer_=IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task,',
        '    prepareStep_=8;\n    buffer_=IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task,')
    edit('BCM2712GEMDMABatch.cpp','    if (!buffer_) goto reject;',
        '    if (!buffer_) { prepareError_=-9;goto reject; }\n    prepareStep_=9;')
    edit('BCM2712GEMDMABatch.cpp','    if (!command_) goto reject;',
        '    if (!command_) { prepareError_=-10;goto reject; }\n    prepareStep_=10;')
    edit('BCM2712GEMDMABatch.cpp','        if (rc!=kIOReturnSuccess) goto reject;',
        '        if (rc!=kIOReturnSuccess) { prepareError_=(int)rc;goto reject; }\n        prepareStep_=11;',1)
    edit('BCM2712GEMDMABatch.cpp',
        '        rc=command_->prepare(0,AllocationBytes);\n        if (rc!=kIOReturnSuccess) goto quarantine;',
        '        rc=command_->prepare(0,AllocationBytes);\n        if (rc!=kIOReturnSuccess) { prepareError_=(int)rc;goto quarantine; }\n        prepareStep_=12;')
    edit('BCM2712GEMDMABatch.cpp','        if (!physical_ || bytes!=AllocationBytes) goto reject;',
        '        if (!physical_ || bytes!=AllocationBytes) { prepareError_=-11;goto reject; }\n        prepareStep_=13;')
    edit('BCM2712GEMDMABatch.cpp',
        '            segment.fIOVMAddr!=physical_ || segment.fLength!=AllocationBytes || !mapping()) goto reject;',
        '''            segment.fIOVMAddr!=physical_ || segment.fLength!=AllocationBytes) { prepareError_=-12;goto reject; }
        prepareStep_=14;
        if (!mapping()) { prepareError_=-13;goto reject; }
        prepareStep_=15;''')
    edit('BCM2712GEMDMABatch.cpp','        if (!route(&expected_,&geometry)) goto reject;',
        '        if (!route(&expected_,&geometry)) { prepareError_=-14;goto reject; }\n        prepareStep_=16;',1)
    edit('BCM2712GEMDMABatch.cpp','    state_=Prepared;return true;',
        '    state_=Prepared;prepareStep_=17;return true;',1)

    edit('BCM2712GEMDMABatch.cpp','rpi5_gem_ring_batch_access_allowed',
        'rpi5_gem_ring_only_access_allowed',3)
    edit('BCM2712GEMDMABatch.cpp','rpi5_gem_ring_batch_values',
        'rpi5_gem_ring_only_values')
    edit('BCM2712GEMDMABatch.cpp','rpi5_gem_ring_batch(&ringSession_',
        'rpi5_gem_ring_only_batch(&ringSession_')
    edit('BCM2712GEMDMABatch.cpp',
        'ringRequest_.descriptor_memory=RPI5_GEM_MEMORY_UNCACHED;ringRequest_.packet_granule=256;',
        'ringRequest_.descriptor_memory=RPI5_GEM_MEMORY_UNCACHED;ringRequest_.packet_granule=0;')
    edit('BCM2712GEMDMABatch.cpp',
        '''            for(unsigned i=0;i<RPI5_GEM_STAGE_SLOTS;i++) {
                uint64_t offset=2*Alignment+(r*RPI5_GEM_STAGE_SLOTS+i)*RPI5_GEM_BUFFER_BYTES;
                ringRequest_.packet[r][i]={(void *)(uintptr_t)(cpu_+offset),geometry.rp1+offset,RPI5_GEM_BUFFER_BYTES};
            }
''','')
    edit('BCM2712PCIePHYTransport.h',
        '    unsigned dmaState() const { return dmaMemory?(unsigned)dmaMemory->state():0; }',
        '''    unsigned dmaState() const { return dmaMemory?(unsigned)dmaMemory->state():0; }
    unsigned dmaPreparationStep() const { return dmaMemory?dmaMemory->preparationStep():0; }
    int dmaPreparationError() const { return dmaMemory?dmaMemory->preparationError():0; }''')
    edit('BCM2712PCIeIDTrialProgress.inc',
        '    kprintf("RPI5XNU:PCIEID:DMA_OWNER PREPARE=%u',
        '''    kprintf("RPI5XNU:PCIEID:DMA_PREP STEP=%u ERROR=%d BYTES=%llu PACKETS=0\\n",
        transport?transport->dmaPreparationStep():0,transport?transport->dmaPreparationError():0,
        (unsigned long long)BCM2712GEMDMABatch::AllocationBytes);
    kprintf("RPI5XNU:PCIEID:DMA_OWNER PREPARE=%u''')
    files['rpi5_gem_ring_only_batch.h']=(ROOT/'iokit/Kernel/rpi5_gem_ring_only_batch.h').read_bytes()
    return files

def sources():
    return [Path(__file__).resolve(),Path(trial.__file__).resolve(),Path(ram.__file__).resolve(),
        ROOT/'iokit/Kernel/rpi5_gem_ring_only_batch.h',ROOT/'iokit/Kernel/rpi5_gem_ring_only_batch.c',
        CAPTURE,FROZEN/'manifest.json']
