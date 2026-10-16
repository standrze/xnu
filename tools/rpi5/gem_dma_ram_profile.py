# SPDX-License-Identifier: BSD-2-Clause
"""Distinct preferred-RAM-only route; CPU-owned rings, no bus mastering.

The frozen CPU-only trial stays unchanged. This successor uses its actual
held-reset window programmer and released90-register checks. Only inbound
hardware BAR2 is enabled. No endpoint/root COMMAND.BME or queue/MMIO-DMA/IRQ
activation exists. Programmed translation is not proof of device DMA.
"""
import hashlib
import json
from tools.rpi5 import gem_dma_batch_transport_profile as prior
ROOT=prior.ROOT
change=prior.change
BASE=ROOT/'build/rpi5/gem-dma-batch-trial-20261014-v8'
BASE_SHA='0439396fe0d74482c01ef6f22b291cbc8c8a848cc27f4b878ba94987e26e0f60'

def transform(files):
    files=dict(files)
    def edit(name,old,new,count=1):
        files[name]=change(files[name].decode(),old,new,count).encode()
    edit('BCM2712PCIePHYTransport.h','#include "BCM2712GEMDMABatch.h"',
         '#include "BCM2712GEMDMABatch.h"\n#include "rpi5_gem_ram_window.h"')
    edit('BCM2712PCIeControllerRun.inc',
        '    /* Diagnostic policy: no endpoint-originated RAM/MIP window. */\n'
        '    for (unsigned i=0;i<3;i++) windows.plan.inbound[i].bar_lo &= ~UINT32_C(31);',
        '    /* Fresh FDT-derived RAM-only viewport, programmed by the same\n'
        '     * per-window held-PERST/link-down ownership/readback sequence.\n'
        '     * Device/MIP decoders remain off; no BME is written. */\n'
        '    if(rpi5_gem_ram_window_plan(&binding,&windows.plan)){fail();return false;}')
    edit('BCM2712PCIeIDTrialProgress.inc',
        '    /* Ten inbound decoders remain disabled through PERST release, training\n'
        '     * and config reads. No RP1 DMA/MSI-target mapping is admitted here. */',
        '    /* Only exact preferred RAM BAR2 is admitted. Device/MIP/unused\n'
        '     * decoders and MSI stay disabled; both fresh full readback passes\n'
        '     * retain their original owner checks. No bus master is enabled. */')
    edit('BCM2712PCIeIDTrialProgress.inc',
        '    for(unsigned i=0;i<3;i++) if(self->windows.plan.inbound[i].bar_lo&31)return -1;',
        '    if(rpi5_gem_ram_window_match(&self->binding,&self->windows.plan))return -1;')
    edit('BCM2712PCIeIDTrialProgress.inc','RPI5XNU:PCIEID:BEGIN INBOUND_DISABLED',
        'RPI5XNU:PCIEID:BEGIN PREFERRED_RAM_ONLY NO_BME')
    edit('BCM2712RP1GEMIdentifyTransport.inc',
        '    for(unsigned i=0;i<3;i++)if(windows.plan.inbound[i].bar_lo&31)return -1;',
        '    if(rpi5_gem_ram_window_match(&binding,&windows.plan))return -1;')
    c=files['BCM2712GEMDMABatch.cpp'].decode()
    a=c.index('bool BCM2712GEMDMABatch::disabled(')
    b=c.index('int BCM2712GEMDMABatch::ringBarrier(',a)
    c=c[:a]+'''bool BCM2712GEMDMABatch::preferredRAM(const struct rpi5_pcie_window_plan *plan) const
{
    if(rpi5_gem_ram_window_match(&binding_,plan))return false;
    /* Actual RAM size/address/remap must already match; never reconstruct
     * an enabled RAM decoder from disabled live registers. Only inactive
     * device/MIP sizes are restored in this LOCAL semantic value for the
     * original full-FDT route validator, which selects RAM row1 exclusively.
     * Real released readbacks remain mandatory before/after qualification. */
    struct rpi5_pcie_window_plan encoded=*plan;
    encoded.inbound[0].bar_lo|=expected_.inbound[0].bar_lo&31;
    encoded.inbound[2].bar_lo|=expected_.inbound[2].bar_lo&31;
    struct rpi5_gem_dma_route ignored;
    return route(&encoded,&ignored);
}
'''+c[b:]
    c=change(c,'disabled(&windows->expected)','preferredRAM(&windows->expected)',2)
    c='#include "rpi5_gem_ram_window.h"\n'+c
    files['BCM2712GEMDMABatch.cpp']=c.encode()
    edit('BCM2712GEMDMABatch.h','bool disabled(', 'bool preferredRAM(')
    edit('BCM2712GEMDMABatch.h','retained independently disabled inbound',
        'retained independently read-back preferred-RAM-only inbound')
    edit('BCM2712GEMDMABatch.h',
        'Successful output is candidate geometry only: every inbound slot remains disabled. It is NOT active DMA reachability.',
        'Successful output is qualified preferred-RAM geometry backed by fresh decoder readbacks. It is NOT DMA-completion evidence or queue authority.')
    files['rpi5_gem_ram_window.h']=(ROOT/'iokit/Kernel/rpi5_gem_ram_window.h').read_bytes()
    return files

def derive():
    if hashlib.sha256((BASE/'manifest.json').read_bytes()).hexdigest()!=BASE_SHA:
        raise ValueError('Frozen CPU-only parent changed')
    parent=json.loads((BASE/'manifest.json').read_text())
    for relative in ('tools/rpi5/gem_dma_batch_transport_profile.py','tools/rpi5/gem_dma_batch_profile.py',
                     'iokit/Kernel/BCM2712GEMDMABatchAccess.inc','iokit/Kernel/BCM2712GEMDMABatchTransport.inc'):
        path=ROOT/relative
        if hashlib.sha256(path.read_bytes()).hexdigest()!=parent['inputs_sha256'][str(path)]:
            raise ValueError('Frozen CPU-only source changed: '+relative)
    return transform(prior.derive())
