# SPDX-License-Identifier: BSD-2-Clause
"""Private fixed root0 -> RP1 bus1 route, before PERST release.

Linux's generic pci_scan_bridge_extend programs PCI_PRIMARY_BUS before child
enumeration; the brcm map_bus selector does not replace that initialization.
Only root bridge 0x18 is newly written, preserving its latency-timer byte.
"""
from pathlib import Path
try:
    from . import rp1_config_trace_profile as config
except ImportError:
    import rp1_config_trace_profile as config

ROOT=config.ROOT
FROZEN=ROOT/'build/rpi5/rp1-config-trace-kernel-20261013-final/overlay'
once=config.once
ROOT_ID=0x271214e4

HEADER='''/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_ROOT_ROUTE_H
#define RPI5_PCIE_ROOT_ROUTE_H
#include "pcie_rc.h"
/* Partial diagnostics only. A failed call does not commit RC observation. */
struct rpi5_pcie_root_route_trace {
    unsigned step, reads, writes;
    uint32_t id, header, before, wanted, actual, after_link;
};
int rpi5_pcie_rc_configure_root_route(struct rpi5_pcie_rc *,
    struct rpi5_pcie_rc_observation *, struct rpi5_pcie_root_route_trace *);
#endif
'''


def core(text):
    text=once(text,'#include "pcie_rc.h"','#include "pcie_root_route.h"')
    text=once(text,'int rpi5_pcie_rc_configure(struct rpi5_pcie_rc *s, struct rpi5_pcie_rc_observation *out)\n{',
        'int rpi5_pcie_rc_configure_root_route(struct rpi5_pcie_rc *s, struct rpi5_pcie_rc_observation *out,\n'
        '    struct rpi5_pcie_root_route_trace *trace)\n{\n'
        '    struct rpi5_pcie_root_route_trace local = {0};\n'
        '    if (!trace) trace = &local;\n    *trace = local; trace->step = 1;')
    text=once(text,'    DO(read32(s, CAPABILITY, &r.capability));',
        '    trace->step = 2;\n'
        '    DO(read32(s, 0x00, &trace->id)); trace->reads++;\n'
        '    DO(read32(s, 0x0c, &trace->header)); trace->reads++;\n'
        f'    if (trace->id != UINT32_C(0x{ROOT_ID:08x}) ||\n'
        '        (trace->header & UINT32_C(0x00ff0000)) != UINT32_C(0x00010000))\n'
        '        return quarantine(s, RPI5_PCIE_RC_PROFILE);\n'
        '    DO(read32(s, CAPABILITY, &r.capability));')
    text=once(text,'    /* Independent final pass; reject cross-register aliases/late drift. */',
        '    /* Fixed topology only: root bus 0, directly attached endpoint bus 1.\n'
        '     * Configure route with PERST still held; never enable COMMAND or DMA. */\n'
        '    trace->step = 3;\n'
        '    DO(read32(s, 0x18, &trace->before)); trace->reads++;\n'
        '    trace->wanted = (trace->before & UINT32_C(0xff000000)) | UINT32_C(0x00010100);\n'
        '    DO(guard(s, &status, &control));\n'
        '    trace->step = 4; trace->writes = 1;\n'
        '    if (io->write32(io->context, 0x18, trace->wanted)) return quarantine(s, RPI5_PCIE_RC_IO);\n'
        '    s->completed_callbacks++;\n'
        '    if (io->order(io->context)) return quarantine(s, RPI5_PCIE_RC_IO);\n'
        '    s->completed_callbacks++;\n'
        '    trace->step = 5;\n'
        '    DO(read32(s, 0x18, &trace->actual)); trace->reads++;\n'
        '    if (trace->actual != trace->wanted) return quarantine(s, RPI5_PCIE_RC_READBACK);\n'
        '    /* Independent final pass; reject cross-register aliases/late drift. */')
    text=once(text,'    DO(guard(s, &r.final_status, &r.final_control));',
        '    trace->step = 6;\n'
        '    DO(read32(s, 0x18, &trace->actual)); trace->reads++;\n'
        '    if (trace->actual != trace->wanted) return quarantine(s, RPI5_PCIE_RC_READBACK);\n'
        '    DO(guard(s, &r.final_status, &r.final_control));')
    text=once(text,'    s->state = RPI5_PCIE_RC_COMPLETE;','    s->state = RPI5_PCIE_RC_COMPLETE;\n    trace->step = 7;')
    return text+'''
int rpi5_pcie_rc_configure(struct rpi5_pcie_rc *s, struct rpi5_pcie_rc_observation *out)
{
    return rpi5_pcie_rc_configure_root_route(s, out, 0);
}
'''


def policy(text):
    text=once(text,'    if (phase == BCM2712_PHY_RC_CONFIGURING) {\n',
        '    if (phase == BCM2712_PHY_RC_CONFIGURING) {\n'
        '        if (offset == 0x18) return 1;\n'
        '        if (!write && (offset == 0x00 || offset == 0x0c)) return 1;\n')
    text=once(text,'return !write && (offset == 0x4068 || offset == 0x4064 || offset == 0x04dc || offset == 0x416c);',
        'return !write && (offset == 0x18 || offset == 0x4068 || offset == 0x4064 || offset == 0x04dc || offset == 0x416c);')
    return once(text,'#endif','''/* Further restrict the one new root-config write by current core state/value.
 * No COMMAND, bridge windows, endpoint BAR or arbitrary bus route permission. */
static inline int bcm2712_root_route_write_allowed(unsigned phase, unsigned bank,
    uint32_t offset, uint32_t value, unsigned step, unsigned writes, uint32_t before)
{
    return phase == BCM2712_PHY_RC_CONFIGURING && bank == BCM2712_PHY_BRIDGE &&
        offset == 0x18 && step == 4 && writes == 1 &&
        value == ((before & UINT32_C(0xff000000)) | UINT32_C(0x00010100));
}
#endif''')


def header(text):
    text=once(text,'extern "C" {','extern "C" {\n#include "pcie_root_route.h"')
    text=once(text,'    unsigned diagLinkCall=0; int diagLinkRC=0;',
        '    struct rpi5_pcie_root_route_trace diagRoot = {};\n    int diagRootRC=0;\n'
        '    unsigned diagLinkCall=0; int diagLinkRC=0;')
    return once(text,'    unsigned traceRP1Call() const { return diagRP1Call; }',
        '    const struct rpi5_pcie_root_route_trace &traceRoot() const { return diagRoot; }\n'
        '    int traceRootRC() const { return diagRootRC; }\n'
        '    unsigned traceRP1Call() const { return diagRP1Call; }')


def run(text):
    text=once(text,'        rpi5_pcie_rc_configure(&rc, &result.rc) || !guard()) { fail(); return false; }',
        '        (diagRootRC=rpi5_pcie_rc_configure_root_route(&rc, &result.rc, &diagRoot)) || !guard()) { fail(); return false; }')
    return once(text,'    result.fresh_unused_checks = freshUnusedChecks;',
        '    /* Recheck routing after actual PERST release/link/clock completion. */\n'
        '    diagRoot.step=8;\n'
        '    if(bridgeRead(this,0x18,&diagRoot.after_link)){diagRootRC=RPI5_PCIE_RC_IO;fail();return false;}\n'
        '    diagRoot.reads++;\n'
        '    if(diagRoot.after_link!=diagRoot.wanted){diagRootRC=RPI5_PCIE_RC_READBACK;fail();return false;}\n'
        '    diagRoot.step=9;\n'
        '    result.fresh_unused_checks = freshUnusedChecks;')


def transport(text):
    return once(text,'    /* Reset SET/CLEAR must NEVER touch other controllers\' bits. */',
        '    if (bank == BCM2712_PHY_BRIDGE && offset == 0x18 &&\n'
        '        !bcm2712_root_route_write_allowed(getPhase(),bank,offset,value,\n'
        '            diagRoot.step,diagRoot.writes,diagRoot.before)) return fail();\n'
        '    /* Reset SET/CLEAR must NEVER touch other controllers\' bits. */')


FIELDS=('ROOT_STEP=%u ROOT_RC=%d ROOT_READS=%u ROOT_WRITES=%u ROOT_ID=%08x ROOT_HDR=%08x '
    'ROOT_BUS_BEFORE=%08x ROOT_BUS_WANTED=%08x ROOT_BUS_ACTUAL=%08x ROOT_BUS_POST_LINK=%08x')


def trial(text):
    text=once(text,'RP1_STATUS=%08x\\n','RP1_STATUS=%08x '+FIELDS+'\\n')
    values=['transport?transport->traceRoot().step:0','transport?transport->traceRootRC():0']
    values+=['transport?transport->traceRoot().'+n+':0' for n in ('reads','writes','id','header','before','wanted','actual','after_link')]
    return once(text,'        transport?transport->traceRP1Status():0);',
        '        transport?transport->traceRP1Status():0,\n        '+',\n        '.join(values)+');')


def emit(folder):
    folder.mkdir(exist_ok=False)
    for p in FROZEN.iterdir():
        if p.is_file():(folder/p.name).write_bytes(p.read_bytes())
    # Quote includes search the including file's directory before -iquote.
    # Keep this unchanged one-hop header beside the new controller policy.
    (folder/'BCM2712RP1ConfigPolicy.h').write_bytes((ROOT/'iokit/Kernel/BCM2712RP1ConfigPolicy.h').read_bytes())
    for name,fn in (('BCM2712PCIePHYTransport.h',header),('BCM2712PCIeControllerRun.inc',run),
        ('BCM2712PCIePHYTransport.cpp',transport),('BCM2712PCIeIDTrialProgress.inc',trial),
        ('BCM2712PCIeControllerPolicy.h',policy)):
        p=folder/name;source=p if p.exists() else ROOT/'iokit/Kernel'/name
        p.write_text(fn(source.read_text()))
    (folder/'pcie_root_route.h').write_text(HEADER)
    corepath=folder/'pcie_rc.c';corepath.write_text(core((ROOT/'loader/rpi5/pcie_rc.c').read_text()))
    return folder/'BCM2712PCIePHYTransport.cpp',corepath
