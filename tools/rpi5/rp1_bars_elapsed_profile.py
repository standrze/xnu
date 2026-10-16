# SPDX-License-Identifier: BSD-2-Clause
"""Offline all-six-BAR caller on the elapsed/config-trace transport lineage.

This expands the candidate's config-write scope to the existing guarded size
probe/restore protocol. It does not create a loader or authorize hardware use.
"""
from pathlib import Path
try:
    from . import rp1_config_trace_profile as config
except ImportError:
    import rp1_config_trace_profile as config

ROOT=config.ROOT
FROZEN=ROOT/'build/rpi5/rp1-config-trace-kernel-20261013-final/overlay'
once=config.once


def transport(text):
    text=once(text,'rp1DenyWrite,rp1Read,rp1Write,order','rp1BarsAuthorize,rp1Read,rp1BarsWrite,order')
    return once(text,'rp1_complete:\n    setPhase(BCM2712_PHY_COMPLETE);',
        'rp1_complete:\n'
        '    diagBarsCall=1;diagBarsRC=rpi5_rp1_bars_probe(&barsProbe,&rp1Config,&result.endpoint,&result.bars);\n'
        '    if(diagBarsRC)goto rp1_failed;\n'
        '    diagBarsCall=2;\n    if(!guard())goto rp1_failed;\n'
        '    diagBarsCall=3;diagBarsRC=rpi5_rp1_bars_assignment_plan(&binding,&barsProbe,&result.bars,&result.barsPlan);\n'
        '    if(diagBarsRC)goto rp1_failed;\n'
        '    diagBarsCall=4;\n    if(!guard())goto rp1_failed;\n    diagBarsCall=5;\n'
        '    setPhase(BCM2712_PHY_COMPLETE);')


def header(text):
    text=once(text,'extern "C" {','extern "C" {\n#include "rp1_bars_plan.h"')
    text=once(text,'    struct rpi5_rp1_config_snapshot endpoint;',
        '    struct rpi5_rp1_config_snapshot endpoint;\n'
        '    struct rpi5_rp1_bars_size bars;\n    struct rpi5_rp1_bars_plan barsPlan;')
    text=once(text,'    struct rpi5_pcie_config rp1Config = {};',
        '    struct rpi5_rp1_bars_probe barsProbe={};\n'
        '    unsigned diagBarsCall=0;int diagBarsRC=0;\n'
        '    static int rp1BarsAuthorize(void *,const struct rpi5_pcie_config_request *);\n'
        '    static int rp1BarsWrite(void *,uint32_t,uint32_t,uint32_t);\n'
        '    struct rpi5_pcie_config rp1Config = {};')
    return once(text,'    unsigned trialPhase() const { return getPhase(); }',
        '    unsigned traceBarsCall() const { return diagBarsCall; }\n'
        '    int traceBarsRC() const { return diagBarsRC; }\n'
        '    unsigned traceBarsState() const { return barsProbe.state; }\n'
        '    unsigned traceBarsSlot() const { return barsProbe.selected; }\n'
        '    unsigned traceBarsTransactions() const { return barsProbe.transactions; }\n'
        '    unsigned traceBarsWrites() const { return barsProbe.writes_started; }\n'
        '    unsigned trialPhase() const { return getPhase(); }')


FIELDS=('BARS_CALL=%u BARS_RC=%d BARS_STATE=%u BARS_SLOT=%u BARS_TXNS=%u BARS_WRITES=%u '
    'BARS_PRESENT=%02x BARS_SIZES=%08x,%08x,%08x,%08x,%08x,%08x '
    'BARS_PLAN=%08x,%08x,%08x,%08x,%08x,%08x')


def trial(text):
    text=text.replace('RPI5XNU:PCIEID:','RPI5XNU:PCIEBARS:')
    text=once(text,'RP1_STATUS=%08x\\n','RP1_STATUS=%08x '+FIELDS+'\\n')
    values=['transport?transport->traceBars'+name+'():0' for name in ('Call','RC','State','Slot','Transactions','Writes')]
    values+=['observed.bars.present']+['observed.bars.bar['+str(i)+'].size' for i in range(6)]
    values+=['observed.barsPlan.pci_base['+str(i)+']' for i in range(6)]
    return once(text,'        transport?transport->traceRP1Status():0);',
        '        transport?transport->traceRP1Status():0,\n        '+',\n        '.join(values)+');')


def emit(folder):
    folder.mkdir(exist_ok=False)
    for p in FROZEN.iterdir():
        if p.is_file():(folder/p.name).write_bytes(p.read_bytes())
    for name,fn in (('BCM2712PCIePHYTransport.h',header),('BCM2712RP1ConfigTransport.inc',transport),
                    ('BCM2712PCIeIDTrialProgress.inc',trial)):
        p=folder/name;p.write_text(fn(p.read_text()))
    cpp=folder/'BCM2712PCIePHYTransport.cpp'
    cpp.write_text(cpp.read_text()+'\n#include "BCM2712RP1BarsTransport.inc"\n')
    return (cpp,)
