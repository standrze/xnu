# SPDX-License-Identifier: BSD-2-Clause
"""Exact same-boot display admission and bounded real interactive-zsh proof.

Serial output proves executed software and its mirrored route, not photons or
monitor visibility. No port, disk, reboot or hardware operation occurs here.
"""
import hashlib
import re
try:
    from . import serial_zsh_trial as zsh
except ImportError:
    import serial_zsh_trial as zsh

SD=b'Boot mode: SD (01)'
BOOTSYS=b'RPi: BOOTSYS release VERSION:'
BOOTLOADER=b'RPi: BOOTLOADER release VERSION:'
NVME=b'Boot mode: NVME (06)'
ENTRY=b'RPI5XNU:DISPLAYXNU:ENTRY TAG='
MIRROR=b'RPI5XNU:DISPLAYXNU:MIRROR_READY NORMAL_NC NX UART_FIRST INPUT_UART ONLY_MAPPING_RETAINED_UNTIL_RESET'
ROOT_READY=b'RPI5XNU:TERMINAL:ROOT_READY SECONDS=180 NODES=32 BYTES=1916928 READONLY'
WATCHDOG=b'RPI5XNU:TERMINAL:WATCHDOG_READY SECONDS=180'
HANDOFF=b'RPI5XNU:DISPLAYXNU:HANDOFF VIDEO_PHYSICAL NORMAL_NC_NX REQUIRED UART_FIRST'
DEVICE=b'RPI5XNU:BL33:PCIE_DEVICE_HANDOFF RANGES=3 PAGES=5 DECLARATIONS_ONLY PCIE_MMIO=0 IRQ=0 DMA=0'
FDT=b'RPI5XNU:BL33:FIRMWARE_FDT RETAINED_DESCRIPTOR_ONLY NO_RAW_TREE_OR_SEED_PUBLISHED PCIE_MMIO=0'
COMMIT=b'RPI5XNU:BL33:BOOT_DATA_COMMITTED TRANSFER_NEXT'
PROMPT=re.compile(rb'(?:^|\n)xnu:/# ')
ZPROMPT=re.compile(rb'pi-zsh# ')
MAX_BYTES=4*1024*1024
FAULT=re.compile(rb'(?i)(panic\(|panic:|Debugger message:|RPI5XNU:[^\r\n]*(?:FAULT|EXCEPTION)|Segmentation fault|Illegal instruction)')

def normalized(raw):return raw.replace(b'\r',b'')
def healthy(raw):
    if len(raw)>MAX_BYTES or FAULT.search(raw) or any(v in raw for v in (*zsh.FORBIDDEN,b'FAILED_STOP',b'RPI5XNU:RAMROOT:REJECT')):
        raise ValueError('Runtime/fault marker in complete display capture')

def return_positions(raw):
    sd=raw.find(SD);a=raw.find(BOOTSYS,sd+len(SD)) if sd>=0 else -1
    b=raw.find(BOOTLOADER,a+len(BOOTSYS)) if a>=0 else -1
    c=raw.find(NVME,b+len(BOOTLOADER)) if b>=0 else -1
    return (sd,a,b,c) if c>=0 else None

def exact_lines(raw,required):
    lines=normalized(raw).splitlines()
    if any(lines.count(v)!=1 for v in required):raise ValueError('Missing/duplicate actual zsh output')
    order=[lines.index(v) for v in required]
    if order!=sorted(order):raise ValueError('Zsh output order differs')

def runtime_lines(raw):
    data=normalized(raw)
    roots=re.findall(rb'RPI5XNU:TERMINAL:ROOT_READY[^\n]*\n',data)
    if len(roots)>3 or any(v!=ROOT_READY+b'\n' for v in roots):raise ValueError('Contradictory/unbounded late mounted-root report')
    for prefix,want in ((b'RPI5XNU:TERMINAL:WATCHDOG_READY',WATCHDOG),(b'RPI5XNU:DISPLAYXNU:MIRROR_READY',MIRROR)):
        rows=re.findall(re.escape(prefix)+rb'[^\n]*\n',data)
        if len(rows)>1 or any(v!=want+b'\n' for v in rows):raise ValueError('Contradictory/duplicate display readiness')
    return data

def boot_ready(raw,report):
    healthy(raw);data=runtime_lines(raw)
    if data.count(SD)>1 or data.count(b'Boot mode:')>1 or data.count(zsh.ENTRY)>1:
        raise ValueError('Fresh single SD boot required; no serial input')
    marker=report['trial_marker'].encode()
    if not re.fullmatch(rb'RPI5XNU:DISPLAYXNU:ENTRY TAG=[0-9a-f]{32} SAME_BOOT OWNED_FRAMEBUFFER_CONSOLE_V1',marker):
        raise ValueError('Actual unique display loader tag required')
    if report.get('root_ready_marker')!=ROOT_READY.decode() or report.get('mirror_ready_marker')!=MIRROR.decode():
        raise ValueError('Exact mounted32-root/mirror package required')
    tags=re.findall(re.escape(ENTRY)+rb'[^\n]*\n',data)
    if tags and tags!=[marker+b'\n']:raise ValueError('Old/duplicate display loader tag')
    reads=re.findall(rb'Read probe\.bin bytes (\d+) hnd ',data)
    if reads and reads!=[str(report['image_bytes']).encode()]:raise ValueError('Wrong firmware image extent')
    allocation=b'RPI5XNU:DISPLAYXNU:ALLOCATE RC=0000000000000000 COMPLETED=000000000000000f QUARANTINED=0000000000000000'
    allocated=re.findall(rb'RPI5XNU:DISPLAYXNU:ALLOCATE RC=[^\n]*\n',data)
    if allocated and allocated!=[allocation+b'\n']:raise ValueError('Same-boot allocation failed or contradicted')
    owned=re.findall(rb'RPI5XNU:DISPLAYXNU:OWNED START=([0-9a-f]{16}) END=([0-9a-f]{16}) MANAGED_UNCHANGED NO_LOADER_DRAW RETAIN_UNTIL_RESET\n',data)
    owner_rows=re.findall(rb'RPI5XNU:DISPLAYXNU:OWNED[^\n]*\n',data)
    if len(owned)>1 or len(owned)!=len(owner_rows):raise ValueError('Duplicate/malformed framebuffer owner')
    if owned:
        start,end=(int(v,16) for v in owned[0])
        if start&16383 or not 0x3e000000<=start<end<=0x40000000 or end-start!=0x7ec000:
            raise ValueError('Owned framebuffer rounded geometry differs')
    # These are the actual frozen generated-loader paths, not generic PCIe
    # success rows. Only geometry-dependent rows come from its checked report.
    markers=[zsh.ENTRY,zsh.TERMINAL_LOADER,marker,DEVICE,FDT,HANDOFF,
        report['root_copy_marker'].encode(),report['kernel_copy_marker'].encode(),
        zsh.package_check.TOPOLOGY_PASS,zsh.TRANSFER,COMMIT]
    ordered=[SD,b'Read probe.bin bytes '+str(report['image_bytes']).encode()+b' hnd ',*markers]
    if marker not in ordered or HANDOFF not in ordered or zsh.TRANSFER not in ordered:
        raise ValueError('Complete actual emitted handoff marker contract required')
    if any(data.count(v)>1 for v in ordered):raise ValueError('Repeated boot/handoff marker')
    if any(v not in data for v in [*ordered,allocation,MIRROR,WATCHDOG,ROOT_READY]) or not owned:return False
    places=[data.index(v) for v in ordered]
    if places!=sorted(places) or not data.index(marker)<data.index(allocation)<data.index(b'RPI5XNU:DISPLAYXNU:OWNED START=')<data.index(HANDOFF):
        raise ValueError('Fresh allocation/transfer order differs')
    if min(data.index(MIRROR),data.index(WATCHDOG),data.index(ROOT_READY))<=places[-1]:
        raise ValueError('Readiness before actual kernel commit')
    last=max(data.index(v)+len(v) for v in (MIRROR,WATCHDOG,ROOT_READY))
    ready=re.search(rb'(?:^|\n)'+re.escape(zsh.READY)+rb'\n',data[last:])
    return ready is not None and PROMPT.search(data[last+ready.end():]) is not None

def nonce_valid(n):
    if not isinstance(n,str) or not re.fullmatch('D[0-9a-f]{16}',n):raise ValueError('Fresh exact display nonce required')

def exchanges(n):
    nonce_valid(n);prefix='DX:'+n+':'
    # The launch is the already exercised original recovery-shell quoting path.
    proof=('print -r -- "'+prefix+'VERSION:$ZSH_VERSION"; a=(pi xnu); '
        'print -r -- "'+prefix+'BUILTIN:${a[2]}:$((6*7))"; /bin/echo '+prefix+'EXTERNAL; '
        'print -r -- "'+prefix+'EXEC_STATUS:$?"; /bin/zsh -f /etc/zsh-smoke.zsh; '
        'print -r -- "'+prefix+'SMOKE_STATUS:$?"')
    rows=[('launch',zsh.LAUNCH,[b'DARWIN:ZSH:MAIN'],ZPROMPT),
        ('proof',proof,[(prefix+'VERSION:5.9').encode(),(prefix+'BUILTIN:xnu:42').encode(),
          (prefix+'EXTERNAL').encode(),(prefix+'EXEC_STATUS:0').encode(),*zsh.SMOKE_LINES,
          (prefix+'SMOKE_STATUS:0').encode()],ZPROMPT),
        ('exit','exit',[],PROMPT),
        ('recovery','echo '+prefix+'RECOVERY_STATUS:$?',[(prefix+'RECOVERY_STATUS:0').encode()],PROMPT)]
    if any(len(command.encode())>1023 for _,command,_,_ in rows):raise ValueError('Actual recovery line limit exceeded')
    return rows

def response_complete(raw,expected,prompt):return zsh.response_complete(raw,expected,prompt)

def inspect_exchange(raw,name,n):
    healthy(raw)
    if any(v in raw for v in (BOOTSYS,BOOTLOADER,b'Boot mode:',b'Linux version ',b' login:',ENTRY,zsh.ENTRY)):
        raise ValueError('Reset/foreign boot during interactive command')
    _,command,expected,prompt=next(v for v in exchanges(n) if v[0]==name)
    if not response_complete(raw,expected,prompt):raise ValueError('Actual output and subsequent prompt required')
    if name=='launch':
        if normalized(raw).splitlines().count(b'DARWIN:ZSH:MAIN')!=2:raise ValueError('Real launcher and interactive startup required')
    else:exact_lines(raw,expected)
    actual=[v for v in normalized(raw).splitlines() if v.startswith(b'DX:')]
    if actual!=[v for v in expected if v.startswith(b'DX:')]:raise ValueError('Unexpected/duplicate/nonzero nonce result')
    return dict(name=name,command=command,actual_output_verified=True,response_sha256=hashlib.sha256(raw).hexdigest())

def pending_safe(raw):
    data=normalized(raw)
    data=data.replace(b'\nRPI5XNU:SHELL:READY\nxnu:/# ',b'')
    data=re.sub(rb'RPI5XNU:TERMINAL:WATCHDOG_KICK RELOADS=[1-9][0-9]{0,5}\n',b'',data)
    data=data.replace(ROOT_READY+b'\n',b'')
    if data.strip():raise ValueError('Unrecognized pending RX; no more input')
