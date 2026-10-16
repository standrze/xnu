# SPDX-License-Identifier: BSD-2-Clause
"""Scoped unchanged register predicates, not inherited whole-image authority."""
import hashlib
import json
from tools.rpi5 import build_pcie_gem_capabilities_package as cap

DEVICE='RPI5XNU:BL33:RP1_DEVICE_HANDOFF RANGES=2 PAGES=6 GEM_CLOCK_ONLY DECLARATIONS_ONLY RP1_MMIO=0'
HOST='RPI5XNU:BL33:PCIE_DEVICE_HANDOFF RANGES=3 PAGES=5 DECLARATIONS_ONLY PCIE_MMIO=0 IRQ=0 DMA=0'
FDT='RPI5XNU:BL33:FIRMWARE_FDT RETAINED_DESCRIPTOR_ONLY NO_RAW_TREE_OR_SEED_PUBLISHED PCIE_MMIO=0'

def inherited():
    path=cap.PRIOR_PACKAGE/'manifest.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=cap.PRIOR_SHA:
        raise ValueError('Exact register-policy predecessor changed')
    previous=json.loads(path.read_bytes())
    result={n:previous[n] for n in ('bars_contract','link_elapsed','rp1_config_trace','root_route','rp1_device_handoff')}
    for name,factory in (('capabilities_contract','capabilities_contract'),('selected_clock_contract','selected_clock_contract'),
        ('root_forward_contract','root_forward_contract'),('gem_contract','gem_contract'),('decode_contract','decode_contract'),
        ('assignment_contract','assignment_contract'),('guard_composition','guard_contract'),('owner_trace','owner_contract'),
        ('trace_contract','trace_contract')):
        result[name]=getattr(cap,factory)()
    result['prior_component_contracts_are_scoped_not_whole_trial']=True
    return result

def contract():
    return dict(profile='real-retained-cpu-owned-rings-v1',record_bytes=1056,allocation_bytes=0x48000,
        allocation_alignment=0x4000,descriptor_bytes=16,slots_per_ring=64,ring_bytes=1280,
        prefetch_bytes=256,cpu_owned_descriptors=160,word_writes=640,word_reads=640,
        batch_callbacks=81,current_checks=164,batch_bytes=64,owner_limit=65536,
        stage_deadline_us=500000,inbound_enabled=False,queue_publication=False,bme=False,dma=False,irq=False,
        inherited_register_contracts_only=True,preparation_and_admission_caller_changed=True,
        candidate_addresses_not_dma_reachability=True,full_original_capture_health=True)
