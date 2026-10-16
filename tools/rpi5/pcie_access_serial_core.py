# SPDX-License-Identifier: BSD-2-Clause
"""Strict fresh access-image observations; no link/network/reset acceptance."""
import re

IMAGE_SHA='f276e0be0d6c9d670189f425c623a86de70e5defce413315d03ab458dd02b10d'
PREFIX=b'RPI5XNU:ACCESS:'
REGISTERS=((0x1001504338,4),(0x1000119500,4),(0x1000119508,4))+tuple(
    (0x1000120000+offset,2 if i in (7,8,9) else 4)
    for i,offset in enumerate((0x4068,0x4064,0x406c,0x4008,0x043c,0x0188,0x04dc,0x00dc,0x00be,0x00bc,0x4304,0x184c)))


def fields(line,kind,keys):
    pattern=PREFIX+kind.encode()+b' '+b' '.join(k.encode()+rb'=(0x[0-9A-F]{16})' for k in keys)
    match=re.fullmatch(pattern,line)
    if not match: raise ValueError('Wrong access marker/fields/order')
    return dict(zip(keys,(int(v,16) for v in match.groups())))


def inventory(data):
    lines=[l.rstrip(b'\r') for l in data.split(b'\n') if l.startswith(PREFIX)]
    return dict(access_lines=len(lines),read_begins=sum(l.startswith(PREFIX+b'READ_BEGIN ') for l in lines),
        read_ends=sum(l.startswith(PREFIX+b'READ_END ') for l in lines),
        fault_lines=[l.decode('ascii',errors='replace') for l in lines if l.startswith(PREFIX+b'FAULT ')],
        last_access_line=lines[-1].decode('ascii',errors='replace') if lines else None)


def inspect(data,image_sha):
    if not isinstance(data,bytes) or len(data)>4*1024*1024 or image_sha!=IMAGE_SHA: raise ValueError('Exact bounded access image capture required')
    lines=[l.rstrip(b'\r') for l in data.split(b'\n') if l.startswith(PREFIX)]
    expected=(PREFIX+b'ENTRY EL2 READONLY_CANDIDATE NO_XNU NO_CPU_ON',
        PREFIX+b'EL1 MMU_CACHE_OFF DAIF_MASKED PRIMARY_ONLY',PREFIX+b'ARMED WATCHDOG_15S NO_RELOAD FATAL_ONLY')
    if len(lines)!=66 or tuple(lines[:3])!=expected: raise ValueError('Incomplete, duplicated or faulted access sequence')
    values=[]
    for read in range(30):
        before=fields(lines[3+read*2],'READ_BEGIN',('PASS','INDEX','PA','WIDTH'))
        after=fields(lines[4+read*2],'READ_END',('PASS','INDEX','VALUE'))
        address,width=REGISTERS[read%15]
        if before!=dict(PASS=read//15,INDEX=read%15,PA=address,WIDTH=width) or after['PASS']!=read//15 or after['INDEX']!=read%15:
            raise ValueError('Read pair differs from exact private allowlist')
        if not 0<=after['VALUE']<(1 << (width*8))-1: raise ValueError('Invalid/all-ones register observation')
        values.append(dict(pass_index=read//15,index=read%15,address=address,width=width,value=after['VALUE']))
    result=fields(lines[63],'RESULT',('RC','CALLBACKS'))
    if result!=dict(RC=0,CALLBACKS=184): raise ValueError('Access callback result failed')
    observed=PREFIX+b'OBSERVED READS=30 PCIE_WRITES=0 CONFIG_ACCESS=0 DMA=0 NIC_READY=0 ELAPSED_US='
    if not lines[64].startswith(observed) or not re.fullmatch(rb'0x[0-9A-F]{16}',lines[64][len(observed):]):
        raise ValueError('Exact no-NIC observation marker absent')
    elapsed=int(lines[64][len(observed):],16)
    if not 0<elapsed<=5000000: raise ValueError('Access deadline failed')
    if lines[65]!=PREFIX+b'STOP NO_RELOAD WAIT_FOR_RESET DESTINATION_UNPROVEN': raise ValueError('Non-servicing stop absent')
    return dict(access_observation_pass=True,image_sha256=image_sha,reads=30,callbacks=184,elapsed_us=elapsed,
        register_values=values,pcie_writes=0,config_access=False,dma=False,nic_ready=False,
        physical_reset_return_proven=False,scope='Thirty exact ordered actual register observations only; not stable state, link training, IRQ/DMA or Ethernet acceptance')
