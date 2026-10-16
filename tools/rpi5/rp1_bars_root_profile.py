# SPDX-License-Identifier: BSD-2-Clause
"""Contained six-BAR size/restore after root routing, with bounded diagnostics."""
try:
    from . import pcie_bounded_log_profile as logging
    from . import rp1_bars_elapsed_profile as bars
except ImportError:
    import pcie_bounded_log_profile as logging
    import rp1_bars_elapsed_profile as bars

ROOT=logging.ROOT
FROZEN=logging.FROZEN
once=bars.once
header=bars.header
transport=bars.transport
FIELDS='BARS_CALL=%u BARS_RC=%d BARS_STATE=%u BARS_SLOT=%u BARS_TXNS=%u BARS_WRITES=%u BARS_PRESENT=%02x'
BAR_FIELDS='ORIGINAL=%08x MASK=%08x SIZE=%08x PLAN=%08x CPU_START=%llu CPU_END=%llu'


def diagnostic_calls():
    values=['transport?transport->traceBars'+name+'():0' for name in
        ('Call','RC','State','Slot','Transactions','Writes')]+['observed.bars.present']
    result=['    kprintf("RPI5XNU:PCIEID:BARS '+FIELDS+'\\n",\n        '+',\n        '.join(values)+');']
    for i in range(6):
        arg=['observed.bars.bar['+str(i)+'].'+field for field in ('original','mask','size')]
        arg+=['observed.barsPlan.pci_base['+str(i)+']']
        arg+=['(unsigned long long)observed.barsPlan.cpu['+str(i)+'].'+field for field in ('start','end')]
        result.append('    kprintf("RPI5XNU:PCIEID:BAR'+str(i)+' '+BAR_FIELDS+'\\n",\n        '+',\n        '.join(arg)+');')
    return '\n'.join(result)+'\n'


def trial(text):
    split=logging.trial(text)
    return once(split,'    kprintf("RPI5XNU:PCIEID:END ',diagnostic_calls()+'    kprintf("RPI5XNU:PCIEID:END ')


def bar_transport(text):
    # Passive diagnostics around the original ordered store; no added MMIO.
    text=once(text,'    if(!self || rp1BarsAuthorize(context,&request))return -1;',
        '    if(!self || !self->onOwnerThread())return -1;\n'
        '    self->diagIOBank=BCM2712_PHY_BRIDGE;self->diagIOOffset=offset;\n'
        '    self->diagIODirection=1;self->diagIOStage=1;self->diagIOValue=value;\n'
        '    if(rp1BarsAuthorize(context,&request))return -1;\n'
        '    self->diagIOStage=2;')
    return once(text,'    __asm__ volatile("dsb sy" ::: "memory");\n    return self->guard()?0:-1;\n}',
        '    __asm__ volatile("dsb sy" ::: "memory");\n'
        '    self->diagIOStage=3;\n    if(!self->guard())return -1;\n'
        '    self->diagIOStage=4;return 0;\n}')


def emit(folder):
    folder.mkdir(exist_ok=False)
    for source in FROZEN.iterdir():
        if source.is_file():(folder/source.name).write_bytes(source.read_bytes())
    for name,fn in (('BCM2712PCIePHYTransport.h',header),('BCM2712RP1ConfigTransport.inc',transport),
        ('BCM2712PCIeIDTrialProgress.inc',trial)):
        path=folder/name;path.write_text(fn(path.read_text()))
    path=folder/'BCM2712RP1BarsTransport.inc'
    path.write_text(bar_transport((ROOT/'iokit/Kernel'/path.name).read_text()))
    cpp=folder/'BCM2712PCIePHYTransport.cpp'
    cpp.write_text(cpp.read_text()+'\n#include "BCM2712RP1BarsTransport.inc"\n')
    return (cpp,)
