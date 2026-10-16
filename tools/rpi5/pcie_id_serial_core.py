# SPDX-License-Identifier: BSD-2-Clause
"""Exact receive-only RP1-ID progression; no packet, IRQ or DMA acceptance."""
import re

PREFIX=b'RPI5XNU:PCIEID:'
BEGIN=PREFIX+b'BEGIN INBOUND_DISABLED'
PREPARED=PREFIX+b'PREPARED OK=1 CPUS=1'
TRANSFER=b'RPI5XNU:BL33:XNU_TRANSFER_PENDING WATCHDOG_15S SEED_COMMIT_NEXT'
ENTRY=b'RPI5XNU:BL33:ENTRY EL='
COMMIT=b'RPI5XNU:BL33:BOOT_DATA_COMMITTED TRANSFER_NEXT'


def inventory(data):
    rows=[line.rstrip(b'\r') for line in data.split(b'\n') if line.startswith(PREFIX)]
    return dict(id_lines=len(rows),last_id_line=rows[-1].decode('ascii',errors='replace') if rows else None,
        failed_rows=[line.decode('ascii',errors='replace') for line in rows if b'OK=0' in line])


def return_positions(data):
    normalized=data.replace(b'\r',b'')
    start=normalized.find(PREFIX+b'END ')
    if start<0:start=normalized.find(TRANSFER)
    if start<0:return None
    tail=normalized[start:]
    tokens=(b'RPi: BOOTSYS release VERSION:',b'BOOT_ORDER override: 0x000000f6',
        b'RPi: BOOTLOADER release VERSION:',b'Boot mode: NVME (06)')
    if any(tail.count(v)>1 for v in tokens) or b'Boot mode: SD (01)' in tail or b'Boot mode: USB' in tail:
        raise ValueError('Repeated or wrong return boot')
    if not all(v in tail for v in tokens):return None
    positions=[data.index(v,data.index(TRANSFER)) for v in tokens]
    if positions!=sorted(positions):raise ValueError('Normal return boot order differs')
    return positions


def inspect(data,report):
    if not isinstance(data,bytes) or not 0<len(data)<=4*1024*1024:raise ValueError('Bounded nonempty serial stream required')
    lines=[line.rstrip(b'\r') for line in data.split(b'\n') if line.startswith(PREFIX)]
    if len(lines)!=3 or lines[:2]!=[BEGIN,PREPARED]:raise ValueError('Incomplete/failed/duplicate exact ID progression')
    end=re.fullmatch(PREFIX+rb'END OK=1 PHASE=5 LAST=5 LIFE=3 FLAGS=1f ID=00011de4 COMMAND=([0-9a-f]{4}) BAR1=([0-9a-f]{8}) GEN=([12]) LANES=([124])',lines[2])
    if not end:raise ValueError('RP1 ID/controller lifecycle result failed')
    command,bar,gen,lanes=[int(v,16 if i<2 else 10) for i,v in enumerate(end.groups())]
    if bar&15:raise ValueError('Observed RP1 BAR1 is not MEM32-aligned')
    prefix=data[:data.index(BEGIN)]
    if (prefix.count(b'Boot mode: SD (01)')!=1 or prefix.count(ENTRY)!=1 or prefix.count(TRANSFER)!=1 or
        re.findall(rb'Read probe\.bin bytes (\d+) hnd ',prefix)!=[str(report['image_bytes']).encode()]):
        raise ValueError('Exact fresh SD image/transfer required')
    ordered=[b'Boot mode: SD (01)',b'Read probe.bin bytes '+str(report['image_bytes']).encode()+b' hnd ',ENTRY,
        *[v.encode() for v in report['boot_markers']],TRANSFER,COMMIT,BEGIN,PREPARED,lines[2]]
    positions=[]
    for marker in ordered:
        if data.count(marker)!=1:raise ValueError('Missing or duplicate loader/kernel marker')
        positions.append(data.index(marker))
    if positions!=sorted(positions):raise ValueError('Loader/materialization/ID order differs')
    if any(marker in data[:data.index(lines[2])+len(lines[2])] for marker in
        (b'panic(cpu',b'RPI5XNU:BL33:STOP',b'RPI5XNU:BL33:EXCEPTION',b'REJECTED',b'RPI5XNU:SHELL:READY',b'RPI5XNU:SOAK:ARM')):
        raise ValueError('Faulted or unexpected userspace/soak trial')
    returned=return_positions(data)
    if returned is None:raise ValueError('Complete bounded normal NVMe return not recorded')
    return dict(rp1_id_trial_pass=True,rp1_id='00011de4',command=command,bar1_pci_base=bar,
        link_generation=gen,link_lanes=lanes,terminal_phase=5,lifecycle=3,claim_flags=31,
        endpoint_config_writes=0,inbound_dma_windows_enabled=0,builtin_msi_bar_enabled=False,
        normal_nvme_serial_boot_observed=True,independent_linux_return_proven=False,
        full_production_lifecycle_proven=False,ethernet_proven=False,irq_delivery=False,dma=False,
        scope='Actual single-CPU bounded controller/link and fixed RP1 header reads; no endpoint BAR writes, IRQ delivery, DMA, packets or usable Ethernet')
