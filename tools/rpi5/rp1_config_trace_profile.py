# SPDX-License-Identifier: BSD-2-Clause
"""Passive complete RP1 read-path diagnostics; no added device transactions."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
FROZEN=ROOT/'build/rpi5/pcie-link-elapsed-kernel-20261013-final/overlay'


def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Frozen RP1 diagnostic boundary changed: '+old[:80])
    return text.replace(old,new)


HEADER='''/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_CONFIG_TRACE_H
#define RPI5_RP1_CONFIG_TRACE_H
#include "rp1_config_snapshot_checked.h"
struct rpi5_rp1_config_trace {
    unsigned step, pass, index, reads;
    int transfer_rc;
    uint32_t previous, value, id, header, bar0, bar1;
};
int rpi5_rp1_config_snapshot_trace(struct rpi5_pcie_config *,
    struct rpi5_rp1_config_snapshot *, struct rpi5_rp1_config_trace *);
#endif
'''


def core(text):
    text=once(text,'#include "rp1_config_snapshot_checked.h"','#include "rp1_config_trace.h"')
    text=once(text,'int rpi5_rp1_config_snapshot(struct rpi5_pcie_config *config,\n'
        '    struct rpi5_rp1_config_snapshot *out)\n{',
        'int rpi5_rp1_config_snapshot_trace(struct rpi5_pcie_config *config,\n'
        '    struct rpi5_rp1_config_snapshot *out, struct rpi5_rp1_config_trace *trace)\n{\n'
        '    struct rpi5_rp1_config_trace local = {0};\n'
        '    if (!trace) trace = &local;\n    *trace = local;\n    trace->step = 1;')
    text=once(text,'            if (rpi5_pcie_config_transfer(config, &request, &value)) return -2;\n'
        '            if (pass && value != result.header[index]) return -3;\n'
        '            result.header[index] = value;',
        '            trace->step = 2; trace->pass = pass; trace->index = index;\n'
        '            trace->transfer_rc = rpi5_pcie_config_transfer(config, &request, &value);\n'
        '            if (trace->transfer_rc) return -2;\n'
        '            trace->reads++; trace->previous = result.header[index]; trace->value = value;\n'
        '            if (index == 0) trace->id = value;\n'
        '            if (index == 3) trace->header = value;\n'
        '            if (index == 4) trace->bar0 = value;\n'
        '            if (index == 5) trace->bar1 = value;\n'
        '            trace->step = 3;\n'
        '            if (pass && value != result.header[index]) return -3;\n'
        '            result.header[index] = value;')
    text=once(text,'    if (result.header[0] != UINT32_C(0x00011de4) ||',
        '    trace->step = 4;\n    if (result.header[0] != UINT32_C(0x00011de4) ||')
    text=once(text,'    *out = result;','    *out = result;\n    trace->step = 5;')
    return text+'''\nint rpi5_rp1_config_snapshot(struct rpi5_pcie_config *config,
    struct rpi5_rp1_config_snapshot *out)
{
    return rpi5_rp1_config_snapshot_trace(config, out, 0);
}
'''


def transport(text):
    # Existing access order/barriers/guards remain identical. Cache only values
    # already acquired; neither telemetry nor failure paths perform extra MMIO.
    text=once(text,'    if (!out || !self->rp1Locked || self->getPhase()',
        '    self->diagIOBank=BCM2712_PHY_BRIDGE;self->diagIOOffset=offset;\n'
        '    self->diagIODirection=0;self->diagIOStage=1;self->diagIOValue=0;\n'
        '    if (!out || !self->rp1Locked || self->getPhase()')
    text=once(text,'    if (!self->rp1Locked || self->getPhase() != BCM2712_PHY_RP1_INSPECTING ||\n'
        '        !bcm2712_rp1_config_access(offset,width,1)',
        '    self->diagIOBank=BCM2712_PHY_BRIDGE;self->diagIOOffset=offset;\n'
        '    self->diagIODirection=1;self->diagIOStage=1;self->diagIOValue=value;\n'
        '    if (!self->rp1Locked || self->getPhase() != BCM2712_PHY_RP1_INSPECTING ||\n'
        '        !bcm2712_rp1_config_access(offset,width,1)')
    if text.count('    __asm__ volatile("dmb osh" ::: "memory");')!=2:raise ValueError('RP1 access count changed')
    text=text.replace('    __asm__ volatile("dmb osh" ::: "memory");',
        '    self->diagIOStage=2;\n    __asm__ volatile("dmb osh" ::: "memory");')
    text=once(text,'    if (!self->guard()) return -1;\n    *out = value;',
        '    self->diagIOValue=value;self->diagIOStage=3;\n'
        '    if(offset==0x4068)self->diagRP1Status=value;\n'
        '    if(offset==0x9000)self->diagRP1Selector=value;\n'
        '    if (!self->guard()) return -1;\n    self->diagIOStage=4;\n    *out = value;')
    text=once(text,'    return self->guard() ? 0 : -1;\n}\nbool BCM2712PCIePHYTransport::runControllerAndObserveRP1(',
        '    self->diagIOStage=3;\n    if(!self->guard())return -1;\n'
        '    self->diagIOStage=4;return 0;\n}\nbool BCM2712PCIePHYTransport::runControllerAndObserveRP1(')
    return once(text,'    if (!guard() || rpi5_pcie_config_init(&rp1Config,&link,&io) ||\n'
        '        rpi5_rp1_config_snapshot(&rp1Config,&result.endpoint) || !guard()) {\n'
        '        rp1Config.state = RPI5_PCIE_CONFIG_QUARANTINED;\n'
        '        fail(); return false;\n    }',
        '    diagRP1Call=1;\n    if(!guard())goto rp1_failed;\n'
        '    diagRP1Call=2;diagRP1RC=rpi5_pcie_config_init(&rp1Config,&link,&io);\n'
        '    if(diagRP1RC)goto rp1_failed;\n'
        '    diagRP1Call=3;diagRP1RC=rpi5_rp1_config_snapshot_trace(&rp1Config,&result.endpoint,&diagRP1);\n'
        '    if(diagRP1RC)goto rp1_failed;\n'
        '    diagRP1Call=4;\n    if(!guard())goto rp1_failed;\n'
        '    diagRP1Call=5;\n    goto rp1_complete;\n'
        'rp1_failed:\n    rp1Config.state=RPI5_PCIE_CONFIG_QUARANTINED;\n    fail();return false;\n'
        'rp1_complete:')


def header(text):
    text=once(text,'extern "C" {','extern "C" {\n#include "rp1_config_trace.h"')
    text=once(text,'    unsigned diagLinkCall=0; int diagLinkRC=0;',
        '    unsigned diagLinkCall=0; int diagLinkRC=0;\n'
        '    struct rpi5_rp1_config_trace diagRP1 = {};\n'
        '    unsigned diagRP1Call=0; int diagRP1RC=0;\n'
        '    uint32_t diagRP1Selector=0,diagRP1Status=0;')
    return once(text,'    unsigned traceGuard() const { return diagGuard; }',
        '    unsigned traceRP1Call() const { return diagRP1Call; }\n'
        '    int traceRP1RC() const { return diagRP1RC; }\n'
        '    const struct rpi5_rp1_config_trace &traceRP1() const { return diagRP1; }\n'
        '    uint32_t traceRP1Selector() const { return diagRP1Selector; }\n'
        '    uint32_t traceRP1Status() const { return diagRP1Status; }\n'
        '    unsigned traceGuard() const { return diagGuard; }')


FIELDS=('RP1_CALL=%u RP1_RC=%d RP1_STEP=%u RP1_PASS=%u RP1_INDEX=%u RP1_XFER_RC=%d RP1_READS=%u '
    'RP1_PREV=%08x RP1_VALUE=%08x RP1_ID=%08x RP1_HDR=%08x RP1_BAR0=%08x RP1_BAR1=%08x '
    'RP1_SELECTOR=%08x RP1_STATUS=%08x')


def trial(text):
    text=once(text,'POLL_US=%llu\\n','POLL_US=%llu '+FIELDS+'\\n')
    values=['transport?transport->traceRP1Call():0','transport?transport->traceRP1RC():0']
    values+=['transport?transport->traceRP1().'+name+':0' for name in
        ('step','pass','index','transfer_rc','reads','previous','value','id','header','bar0','bar1')]
    values+=['transport?transport->traceRP1Selector():0','transport?transport->traceRP1Status():0']
    return once(text,'        (unsigned long long)(transport?transport->traceLink().poll_elapsed_us:0));',
        '        (unsigned long long)(transport?transport->traceLink().poll_elapsed_us:0),\n        '+',\n        '.join(values)+');')


def emit(folder):
    folder.mkdir(exist_ok=False)
    for p in FROZEN.iterdir():
        if p.is_file():(folder/p.name).write_bytes(p.read_bytes())
    for name,fn in (('BCM2712PCIePHYTransport.h',header),('BCM2712RP1ConfigTransport.inc',transport),
                    ('BCM2712PCIeIDTrialProgress.inc',trial)):
        p=folder/name;source=p if p.exists() else ROOT/'iokit/Kernel'/name
        p.write_text(fn(source.read_text()))
    (folder/'rp1_config_trace.h').write_text(HEADER)
    source=folder/'rp1_config_snapshot_checked.c'
    source.write_text(core((ROOT/'loader/rpi5/rp1_config_snapshot_checked.c').read_text()))
    return folder/'BCM2712PCIePHYTransport.cpp',source
