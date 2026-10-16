# SPDX-License-Identifier: BSD-2-Clause
"""Explicit reviewed immutable case data for the fixed zero-TX PCIe workflow."""
import importlib
import json
from pathlib import Path
import re
import sys
try:
    from . import trial_checkpoint_v2 as seals
except ImportError:
    import trial_checkpoint_v2 as seals

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
FORMAT='rpi5-zero-tx-pcie-case-v3'
FIRMWARE_SHA='dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b'
ADAPTERS={
    'elapsed-reference-offline':('tools.rpi5.check_pcie_link_elapsed_package','tools.rpi5.pcie_link_elapsed_serial_core',
        'RPI5XNU:BL33:PCIE_ID_LINK_ELAPSED_TRIAL TAG=',False),
    'rp1-config-trace':('tools.rpi5.check_rp1_config_trace_package','tools.rpi5.rp1_config_trace_serial_core',
        'RPI5XNU:BL33:RP1_CONFIG_TRACE_TRIAL TAG=',True)}


def get(reference):
    if not isinstance(reference,dict) or set(reference)!={'path','sha256'}:raise ValueError('Exact separately retained descriptor reference required')
    path=Path(reference['path'])
    if path.resolve()!=path or not path.is_relative_to(ROOT/'build/rpi5') or path.suffix!='.json':
        raise ValueError('Explicit canonical local descriptor required')
    if seals.sha(path)!=reference['sha256']:raise ValueError('Reviewed descriptor digest differs')
    value=json.loads(path.read_text())
    if (set(value)!={'format','name','adapter','package','package_manifest_sha256','checker','protocol','source_sha256','marker','firmware_sha256','hardware_allowed'} or
        value['format']!=FORMAT or not isinstance(value['name'],str) or not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}',value['name']) or
        type(value['hardware_allowed']) is not bool or value['firmware_sha256']!=FIRMWARE_SHA or
        not re.fullmatch('[0-9a-f]{64}',value['package_manifest_sha256']) or
        not isinstance(value['marker'],str) or not re.fullmatch(r'RPI5XNU:BL33:[A-Z0-9_]+ TAG=[0-9a-f]{32} CPUS=1 NO_CPU_ON NO_INIT ZERO_SERIAL_INPUT',value['marker'])):
        raise ValueError('Exact fixed no-init single-CPU zero-TX case required')
    adapter=ADAPTERS.get(value['adapter'])
    if (adapter is None or (value['checker'],value['protocol'])!=adapter[:2] or
        not value['marker'].startswith(adapter[2]) or value['hardware_allowed'] is not adapter[3]):
        raise ValueError('Fixed reviewed execution adapter required')
    package=Path(value['package'])
    if package.resolve()!=package or package.parent!=ROOT/'build/rpi5':raise ValueError('Exact immutable package directory required')
    pins=value['source_sha256'];seals.check_pins(pins)
    result=dict(record=value,reference=reference,hardware_allowed=value['hardware_allowed'])
    for key in ('checker','protocol'):
        name=value[key]
        if not isinstance(name,str) or not re.fullmatch(r'tools\.rpi5\.[a-z][a-z0-9_]+',name):raise ValueError('Explicit repository checker/protocol module required')
        source=ROOT/(name.replace('.','/')+'.py')
        if pins.get(str(source))!=seals.sha(source):raise ValueError('Checker/protocol must be explicitly source-pinned before import')
        module=importlib.import_module(name)
        if Path(module.__file__).resolve()!=source:raise ValueError('Imported source differs from selected descriptor')
        result[key]=module
    return result
