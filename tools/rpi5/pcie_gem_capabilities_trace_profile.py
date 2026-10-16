# SPDX-License-Identifier: BSD-2-Clause
"""Bounded passive trace for the accepted held-map capability reader."""
import json
from tools.rpi5 import rp1_gem_capabilities_profile as core

ROOT, FROZEN = core.ROOT, core.FROZEN
FIELDS = json.loads((FROZEN.parent / 'manifest.json').read_text())['link_trace_fields']
NAMES = ('CAPS', 'CAP_BEFORE0', 'CAP_BEFORE1', 'CAP_AFTER0', 'CAP_AFTER1')


def records():
    rows = ['    const auto *cap=transport?transport->traceCapabilities():nullptr;\n',
        '    kprintf("RPI5XNU:PCIEID:CAPS STATE=%u RC=%d READS=%u PASS=%u INDEX=%u PENDING=%u\\n",\n'
        '        cap?cap->state:0,cap?cap->error:0,cap?cap->reads:0,\n'
        '        cap?cap->pass:0,cap?cap->index:0,cap?cap->pending:0);\n']
    labels = ('MID','DCFG1','DCFG2','DCFG5','DCFG6','DCFG8','DCFG10','DCFG12')
    for p, side in enumerate(('BEFORE','AFTER')):
        for half in range(2):
            indexes = range(half * 4, half * 4 + 4)
            fmt = ' '.join(labels[i] + '=%08x' for i in indexes)
            args = ','.join('cap?cap->words[%u][%u]:0' % (p,i) for i in indexes)
            rows.append('    kprintf("RPI5XNU:PCIEID:CAP_' + side + str(half) + ' ' + fmt + '\\n",\n        ' + args + ');\n')
    return ''.join(rows)


def emit(folder):
    sources = core.emit(folder)
    header = folder / 'BCM2712PCIePHYTransport.h'
    header.write_text(core.util.once(header.read_text(),
        '    const struct rpi5_gem_identify *traceGem() const { return &gemSession; }',
        '    const struct rpi5_gem_identify *traceGem() const { return &gemSession; }\n'
        '    const struct rpi5_gem_cap_session *traceCapabilities() const { return &capabilitySession; }'))
    progress = folder / 'BCM2712PCIeIDTrialProgress.inc'
    needle = '    kprintf("RPI5XNU:PCIEID:END '
    progress.write_text(core.util.once(progress.read_text(), needle, records() + needle))
    return sources
