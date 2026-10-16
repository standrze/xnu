# SPDX-License-Identifier: BSD-2-Clause
"""Bound diagnostic kprintf metadata without disabling the Apple log encoder.

The old serial line was visible before kprintf entered os_log_with_args. Each
new independently framed record has at most 15 scalar arguments. The final
END is emitted only after the four diagnostic kprintf calls have returned.
This changes no controller operations, guards, ownership or watchdog deadline.
"""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
FROZEN=ROOT/'build/rpi5/pcie-root-route-kernel-20261013-v3/overlay'
GROUPS=(('UBUS',10,19),('LINK',19,28),('RP1',28,43),('ROOT',43,53),('END',0,10))


def original_call(text):
    pattern=r'    kprintf\("(RPI5XNU:PCIEID:END [^"\n]+\\n)",\n(.*?)\);'
    matches=list(re.finditer(pattern,text,re.S))
    if len(matches)!=1:raise ValueError('One exact original diagnostic END required')
    match=matches[0]
    fields=match[1].removeprefix('RPI5XNU:PCIEID:END ').removesuffix('\\n').split(' ')
    args=[a.strip() for a in match[2].split(',')]
    if len(fields)!=53 or len(args)!=53 or any(
        not re.fullmatch(r'[A-Z0-9_]+=%(?:0[248])?(?:llu|[udx])',f) for f in fields):
        raise ValueError('Exact 53 scalar field/argument schema required')
    return match,fields,args


def records(text):
    _,fields,args=original_call(text)
    return [(name,'RPI5XNU:PCIEID:'+name+' '+' '.join(fields[start:end])+'\\n',args[start:end])
        for name,start,end in GROUPS]


def trial(text):
    match,_,_=original_call(text)
    calls=['    /* Bounded scalar metadata: keep normal kprintf -> os_log enabled.\n'
           '     * END follows all diagnostic calls; no claim of cross-call atomicity. */']
    for _,fmt,args in records(text):
        calls.append('    kprintf("'+fmt+'",\n        '+',\n        '.join(args)+');')
    return text[:match.start()]+'\n'.join(calls)+text[match.end():]


def emit(folder):
    folder.mkdir(exist_ok=False)
    for source in FROZEN.iterdir():
        if source.is_file():(folder/source.name).write_bytes(source.read_bytes())
    path=folder/'BCM2712PCIeIDTrialProgress.inc'
    path.write_text(trial(path.read_text()))
    return (folder/'BCM2712PCIePHYTransport.cpp',)
