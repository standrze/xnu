# SPDX-License-Identifier: BSD-2-Clause
"""Full42-row health/restoration with corrected narrow SYS source admission."""
import copy
import hashlib
from pathlib import Path
from tools.rpi5 import pcie_root_forward_serial_core as prior
from tools.rpi5 import build_pcie_gem_selected_package as package_source
PREFIX,BEGIN,TRANSFER,ENTRY,COMMIT,PREPARED,PREPARED_PREFIX=(getattr(prior,n) for n in
    ('PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX'))
inventory,return_positions,health,same,ORDER=prior.inventory,prior.return_positions,prior.health,prior.same,prior.ORDER


def clock_profile(values):
    if len(values)!=15 or values[0] not in (2,0x802):return False
    # Only the SYS admission predicate differs. Preserve all prior PLL/rate,
    # ETH/TSU predicates exactly; do not assign semantics to opaque bit28.
    selected=list(values);selected[0]=0x802
    return prior.prior.clock_profile(selected)


def configured_parser():
    root=package_source.private.load_private(Path(prior.__file__).resolve(),'_selected_root_serial')
    gem=package_source.private.load_private(Path(prior.prior.__file__).resolve(),'_selected_gem_serial')
    gem.clock_profile=clock_profile;root.prior=gem;root.package_source=package_source
    return root


def inspect(data,report):
    if not isinstance(data,bytes) or not 0<len(data)<=4*1024*1024:raise ValueError('Bounded original selected-source capture required')
    if health.inspect(data,hashlib.sha256(data).hexdigest())['runtime_fault_signature_observed']:
        raise ValueError('Fault in complete original selected-source capture including after END')
    if not same(report.get('selected_clock_contract'),package_source.selected_clock_contract()):
        raise ValueError('Exact selected-source clock contract required')
    marker=report.get('marker','')
    if not marker.startswith('RPI5XNU:BL33:PCIE_GEM_SELECTED_TRIAL TAG=') or data.count(marker.encode())!=1:
        raise ValueError('Exact unique selected-source image marker required')
    adapted=copy.deepcopy(report)
    adapted['marker']=marker.replace('PCIE_GEM_SELECTED_TRIAL','PCIE_ROOT_FORWARD_TRIAL')
    adapted['boot_markers']=[v.replace('PCIE_GEM_SELECTED_TRIAL','PCIE_ROOT_FORWARD_TRIAL') for v in report['boot_markers']]
    result=configured_parser().inspect(data.replace(b'PCIE_GEM_SELECTED_TRIAL',b'PCIE_ROOT_FORWARD_TRIAL'),adapted)
    result.update(selected_clock_trial_pass=result['root_forward_trial_pass'],
        selected_clock_contract=report['selected_clock_contract'],gem_contract=report['gem_contract'],
        selected_source_register_profile_admitted=result['root_forward_trial_pass'],
        clock_readiness_independently_proven=False,physical_frequency_or_gate_measurement=False,
        full_original_capture_health_scan=True,
        scope='Exact selected SYS source register profile plus repeated GEM MID and complete root/endpoint/maps/BAR restoration; no independently measured clock gating/frequency and no packet driver')
    return result
