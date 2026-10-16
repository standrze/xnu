# SPDX-License-Identifier: BSD-2-Clause
"""New exact image admission; unchanged nineteen-row telemetry and full health scan."""
import copy
from tools.rpi5 import pcie_owner_trace_serial_core as prior
from tools.rpi5 import build_pcie_guard_composition_package as package_source
PREFIX,BEGIN,TRANSFER,ENTRY,COMMIT,PREPARED,PREPARED_PREFIX=(getattr(prior,n) for n in
    ('PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX'))
inventory,return_positions=prior.inventory,prior.return_positions
ORDER=prior.ORDER


def inspect(data,report):
    if (not prior.same(report.get('guard_composition'),package_source.guard_contract()) or
        not prior.same(report.get('owner_trace'),package_source.owner_contract()) or
        not prior.same(report.get('trace_contract'),package_source.trace_contract())):
        raise ValueError('Exact changed guard composition and unchanged owner contract required')
    marker=report.get('marker','')
    if (not marker.startswith('RPI5XNU:BL33:PCIE_GUARD_COMPOSITION_TRIAL TAG=') or
        not isinstance(data,bytes) or data.count(marker.encode())!=1):
        raise ValueError('Exact unique new guard image marker required')
    adapted=copy.deepcopy(report)
    adapted['boot_markers']=[m.replace('PCIE_GUARD_COMPOSITION_TRIAL','PCIE_OWNER_TRACE_TRIAL') for m in report['boot_markers']]
    adapted['owner_trace']=prior.package_source.owner_contract()
    adapted['trace_contract']=prior.package_source.trace_contract()
    result=prior.inspect(data.replace(b'PCIE_GUARD_COMPOSITION_TRIAL',b'PCIE_OWNER_TRACE_TRIAL'),adapted)
    if result['bars_trial_pass']:
        owner=result['owner_telemetry'];sequence=owner['fw']['seq'];checks=owner['pm']['checks']
        if (sequence%2!=1 or checks!=12+8*((sequence-1)//2) or owner['pm']['callbacks']!=8+4*checks):
            raise ValueError('Successful exact nested composition accounting differs')
    result.update(guard_composition=report['guard_composition'],guard_policy_unchanged=False,
        transport_mmio_guard_sites_unchanged=True,owner_implementations_unchanged=True)
    return result
