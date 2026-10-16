# SPDX-License-Identifier: BSD-2-Clause
"""Strict zero-input observation record oracle; never claims scanout ownership."""
import re
PREFIX='RPI5XNU:FBOBS:'
HEX='0x[0-9A-F]{16}'
def fields(row,kind,names,suffix=''):
    pattern=PREFIX+kind+''.join(' '+name+'=('+HEX+')' for name in names)+re.escape(suffix)
    m=re.fullmatch(pattern,row)
    if not m:raise ValueError('Malformed '+kind+' record')
    return dict(zip(names,(int(v,16) for v in m.groups())))
def signed(v):return v-(1<<64) if v>>63 else v
def inspect(data,report):
    if not isinstance(data,bytes) or len(data)>4*1024*1024:raise ValueError('Bounded raw capture required')
    tag=report['tag']
    if not re.fullmatch('[a-f0-9]{32}',tag):raise ValueError('Bad checked tag')
    normalized=data.replace(b'\r\n',b'\n')
    rows=[r for r in normalized.split(b'\n') if b'RPI5XNU:FBOBS:' in r]
    try:rows=[r.decode('ascii') for r in rows]
    except UnicodeDecodeError as e:raise ValueError('Non-ASCII observation') from e
    if not rows or sum(len(r)+2 for r in rows)>32768:raise ValueError('Missing/oversized observation')
    if rows[0]!=PREFIX+f'ENTRY TAG={tag} EL2 NO_XNU NO_CPU_ON ZERO_SERIAL_INPUT' or rows[-1]!=PREFIX+f'STOP TAG={tag} NO_RELOAD DESTINATION_UNPROVEN':
        raise ValueError('Fresh exact image start/stop required')
    start=normalized.find(rows[0].encode());stop=normalized.find(rows[-1].encode(),start)+len(rows[-1])
    if normalized[start:stop]!=('\n'.join(rows)).encode():raise ValueError('Unexpected interleaved observation bytes')
    if rows[1]!=PREFIX+'ARMED WATCHDOG=15 SOFTWARE=8 NO_RELOAD':raise ValueError('One bounded watchdog required')
    cpu=fields(rows[2],'EL1',['SCTLR','DAIF'],' CPU_MMU_CACHE_OFF SCANOUT_CACHE_CONTRACT_UNKNOWN')
    if cpu['SCTLR']&0x02001005 or cpu['DAIF']&0x3c0!=0x3c0:raise ValueError('Actual CPU/cache contract differs')
    live=fields(rows[3],'LIVE',['LOADER_START','LOADER_END','FDT_START','FDT_BYTES'],' TF_A_POLICY_EXCLUSION_END=0x0000000000080000')
    if (live['LOADER_START']!=report['loader_live']['start'] or live['LOADER_END']!=report['loader_live']['end'] or
        not 40<=live['FDT_BYTES']<=1048576 or live['FDT_START']<0x80000 or live['FDT_START']&7 or live['FDT_START']+live['FDT_BYTES']>1<<32):
        raise ValueError('Actual live extents differ')
    if live['FDT_START']<live['LOADER_END'] and live['LOADER_START']<live['FDT_START']+live['FDT_BYTES']:raise ValueError('FDT overlaps loader')
    result=re.fullmatch(re.escape(PREFIX+f'RESULT TAG={tag} RC=')+'('+HEX+') FRAMEBUFFER_ACCESSES=0 MAILBOX_REQUESTS=0 DRAW=0 MIRROR=0',rows[-2])
    if not result:raise ValueError('Missing complete exact result')
    rc=signed(int(result.group(1),16));body=rows[4:-2]
    if rc:
        if body:raise ValueError('Partial record body is not a complete observation')
        return dict(diagnostic_pass=False,result_rc=rc,ownership_proven=False,scanout_cache_contract_proven=False)
    at=0
    def take():
        nonlocal at
        if at>=len(body):raise ValueError('Truncated observation')
        value=body[at];at+=1;return value
    inventory=fields(take(),'INVENTORY',['BYTES','SIMPLE','MAILBOX_FB','NODES','ROOT_AC','ROOT_SC','CHOSEN_AC','CHOSEN_SC'])
    if inventory['BYTES']!=live['FDT_BYTES'] or inventory['NODES']>4 or inventory['SIMPLE']+inventory['MAILBOX_FB']!=inventory['NODES']:
        raise ValueError('Invalid inventory cardinality')
    memory=fields(take(),'MEMORY',['RC','BANKS','RES_RC','FIXED','DYNAMIC'],' OWNERSHIP_PROVEN=0 CACHE_CONTRACT_PROVEN=0')
    if memory['BANKS']>8 or memory['FIXED']>32 or memory['DYNAMIC']>8:raise ValueError('Unbounded memory inventory')
    if signed(memory['RC']) not in (0,-1,-2) or signed(memory['RES_RC']) not in (0,-1,-2):raise ValueError('Unexpected parser status')
    if memory['RC'] and memory['BANKS'] or memory['RES_RC'] and (memory['FIXED'] or memory['DYNAMIC']):raise ValueError('Invalid partial parser output')
    ranges=[]
    for kind,count in [('RAM',memory['BANKS']),('FIXED',memory['FIXED'])]:
        for i in range(count):
            v=fields(take(),kind,['INDEX','START','END'])
            if v['INDEX']!=i or not 0<=v['START']<v['END']<=1<<40:raise ValueError('Bad range')
            if kind=='RAM':ranges.append((v['START'],v['END']))
    for i in range(memory['DYNAMIC']):
        v=fields(take(),'DYNAMIC',['INDEX','SIZE','ALIGN','WINDOWS','NO_MAP'],' NOT_ALLOCATED')
        if v['INDEX']!=i or v['WINDOWS']>8 or v['NO_MAP']>1 or not v['SIZE'] or not v['ALIGN'] or v['ALIGN']&(v['ALIGN']-1):raise ValueError('Bad dynamic request')
        for j in range(v['WINDOWS']):
            w=fields(take(),'WINDOW',['INDEX','WINDOW','START','END'])
            if w['INDEX']!=i or w['WINDOW']!=j or not w['START']<w['END']<=1<<40:raise ValueError('Bad dynamic window')
    nodes=[]
    for i in range(inventory['NODES']):
        row=take();m=re.fullmatch(PREFIX+'NODE INDEX=('+HEX+') KIND=('+HEX+') PATH=(/[A-Za-z0-9/@,._+-]{0,126}) PRESENT=('+HEX+') MALFORMED=('+HEX+')',row)
        if not m:raise ValueError('Malformed node path')
        index,kind,path,present,malformed=m.groups();index,kind,present,malformed=map(lambda v:int(v,16),(index,kind,present,malformed))
        if index!=i or kind not in (1,2) or present>127 or malformed>127:raise ValueError('Bad node facts')
        p=fields(take(),'PROPERTIES',['INDEX','WIDTH','HEIGHT','STRIDE','FORMAT','STATUS','FIRMWARE'])
        r=fields(take(),'REG',['INDEX','WORDS','W0','W1','W2','W3'],' RAW_CELLS_NOT_GUESSED_PA')
        d=fields(take(),'DESCRIPTOR',['INDEX','RC','PLAN_RC','APPLE_XRGB','LIVE_OVERLAP','FIXED_OVERLAP'])
        if any(v['INDEX']!=i for v in (p,r,d)) or r['WORDS']>4 or any(p[k]>0xffffffff for k in p if k!='INDEX') or any(r[k]>0xffffffff for k in ('W0','W1','W2','W3')):
            raise ValueError('Out-of-range or misordered node properties')
        if p['FORMAT']>4 or p['STATUS']>3 or any(d[k]>1 for k in ('APPLE_XRGB','LIVE_OVERLAP','FIXED_OVERLAP')):raise ValueError('Bad node flag')
        if any(signed(d[k]) not in (0,-1) for k in ('RC','PLAN_RC')):raise ValueError('Unexpected geometry status')
        geometry=None
        if not d['RC'] and not d['PLAN_RC']:
            geometry=fields(take(),'GEOMETRY',['INDEX','START','END','VISIBLE','RETAIN_START','RETAIN_END'],' NO_MAPPING NO_DRAW NO_OWNERSHIP_CLAIM')
            g=geometry
            if (kind!=1 or g['INDEX']!=i or not g['RETAIN_START']<=g['START']<g['END']<=g['RETAIN_END']<=1<<40 or g['RETAIN_START']&16383 or g['RETAIN_END']&16383 or
                g['VISIBLE']!=p['STRIDE']*p['HEIGHT'] or not 0<g['VISIBLE']<=g['END']-g['START']<=16*1024*1024):
                raise ValueError('Impossible descriptor geometry')
            if not any(a<=g['RETAIN_START']<g['RETAIN_END']<=z for a,z in ranges):raise ValueError('Descriptor outside advertised RAM')
        if kind==2 and (d['RC']!=0xffffffffffffffff or d['PLAN_RC']!=0xffffffffffffffff or d['APPLE_XRGB']):raise ValueError('Mailbox provider is not a framebuffer allocation')
        nodes.append(dict(path=path,kind=kind,present=present,malformed=malformed,properties=p,raw_reg=r,descriptor=d,geometry=geometry))
    if at!=len(body) or sum(n['kind']==1 for n in nodes)!=inventory['SIMPLE']:raise ValueError('Unexpected/repeated records')
    start=data.find(rows[0].encode());stop=data.find(rows[-1].encode(),start)+len(rows[-1])
    if re.search(rb'(?i)(?:panic\(|panic:|Debugger message:|RPI5XNU:FBOBS:FAULT)',data[start:stop]):raise ValueError('Fault in observation interval')
    return dict(diagnostic_pass=True,result_rc=0,inventory=inventory,memory=memory,nodes=nodes,cpu=cpu,live=live,
        observation_bytes=sum(len(r)+2 for r in rows),ownership_proven=False,scanout_cache_contract_proven=False,
        framebuffer_access=False,mailbox_requests=False,drawing=False,mirror_enabled=False,reset_destination_proven=False)
