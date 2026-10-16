# SPDX-License-Identifier: BSD-2-Clause
"""Exact Fixed32 allocation records; no mapping, drawing or handoff authority."""
import re
PREFIX='RPI5XNU:DISPLAYALLOCZERO:'
PROFILE='pi5-display-allocate-zero-standalone-v1'
HEX='0x[0-9A-F]{16}'
def fields(row,kind,names,suffix=''):
    m=re.fullmatch(re.escape(PREFIX+kind)+''.join(' '+n+'=('+HEX+')' for n in names)+re.escape(suffix),row)
    if not m:raise ValueError('Malformed '+kind)
    return dict(zip(names,map(lambda s:int(s,16),m.groups())))
def signed(n):return n-(1<<64) if n>>63 else n
def inspect(data,report):
    try:return _inspect(data,report)
    except (IndexError,KeyError,TypeError) as e:raise ValueError('Truncated record or checked report') from e
def _inspect(data,report):
    if not isinstance(data,bytes) or len(data)>4*1024*1024:raise ValueError('Bounded raw capture required')
    tag=report.get('tag','')
    if report.get('profile')!=PROFILE or not re.fullmatch('[a-f0-9]{32}',tag):raise ValueError('Checked query package required')
    normal=data.replace(b'\r\n',b'\n')
    # Entire capture, including after result/STOP. Never project away a fault.
    if re.search(rb'(?i)(panic\(|panic:|Debugger message:|RPI5XNU:[^\r\n]*(?:FAULT|EXCEPTION)|Kernel BUG|Oops:)',normal):raise ValueError('Fault in whole capture')
    raw=[r for r in normal.split(b'\n') if PREFIX.encode() in r]
    try:rows=[r.decode('ascii') for r in raw]
    except UnicodeError as e:raise ValueError('Non-ASCII query record') from e
    if len(rows)<4 or sum(len(x)+2 for x in rows)>32768:raise ValueError('Missing/bounded records')
    start=normal.find(raw[0]);end=normal.find(raw[-1],start)+len(raw[-1])
    if normal[start:end]!=b'\n'.join(raw):raise ValueError('Interleaved or repeated query bytes')
    if rows[0]!=PREFIX+f'ENTRY TAG={tag} EL2 PRECHECK NO_XNU NO_CPU_ON ZERO_SERIAL_INPUT':raise ValueError('Exact fresh query entry required')
    uart=fields(rows[1],'UART',['CR','FR','IBRD','FBRD','LCRH'],' FIRMWARE_PRESERVED_CLOCK_UNVERIFIED')
    if any(v>0xffffffff for v in uart.values()) or uart['CR']&0x101!=0x101:raise ValueError('Firmware UART disabled')
    i=2;stages=[]
    while i<len(rows) and rows[i].startswith(PREFIX+'CHECK '):
        stage=fields(rows[i],'CHECK',['STAGE'])['STAGE']
        if stage!=len(stages)+1 or stage>19:raise ValueError('Precheck order differs')
        stages.append(stage);i+=1
    if i<len(rows) and rows[i].startswith(PREFIX+'REJECT '):
        r=fields(rows[i],'REJECT',['STAGE','RC'],' NO_RELOAD OBSERVATION_INCOMPLETE')
        if i!=len(rows)-1 or not stages or r['STAGE']!=stages[-1] or signed(r['RC'])!=-1:raise ValueError('Malformed rejection')
        return dict(diagnostic_pass=False,allocation_trial_pass=False,precheck_failed=True,failed_stage=r['STAGE'],result_rc=-1,framebuffer_authority=False)
    if stages!=list(range(1,20)) or rows[i]!=PREFIX+'ARMED WATCHDOG=15 SOFTWARE=8 NO_RELOAD':raise ValueError('Bounded watchdog/prechecks required')
    i+=1
    cpu=fields(rows[i],'EL1',['SCTLR','DAIF'],' CPU_MMU_CACHE_OFF NO_XNU NO_CPU_ON NO_FRAMEBUFFER_ACCESS');i+=1
    if cpu['SCTLR']&0x02001005 or cpu['DAIF']&0x3c0!=0x3c0:raise ValueError('CPU admission differs')
    live=fields(rows[i],'LIVE',['LOADER_START','LOADER_END','FDT_START','FDT_BYTES','STORAGE'],' STORAGE_BYTES=0x0000000000004000 RETAIN_UNTIL_RESET');i+=1
    if (live['LOADER_START']!=report['loader_live']['start'] or live['LOADER_END']!=report['loader_live']['end'] or
        live['STORAGE']!=report['allocation_storage']['start'] or report['allocation_storage']['bytes']!=16384 or
        not 40<=live['FDT_BYTES']<=1048576 or live['FDT_START']&7 or live['FDT_START']<0x80000 or
        live['FDT_START']+live['FDT_BYTES']>1<<32 or
        live['FDT_START']<live['LOADER_END'] and live['LOADER_START']<live['FDT_START']+live['FDT_BYTES']):raise ValueError('Linked live geometry differs')
    s=fields(rows[i],'SESSION',['RC','ADMIT','STATE','STAGE','SLOT','POLLS','CALLBACKS','TX','POP','DONE','QUARANTINE','CACHE','READS','WRITES']);i+=1
    bind=fields(rows[i],'BIND',['MMIO','END','FW','MBOX','EXPECTED','PEEK','POPPED','START_US','LAST_US','DEADLINE_US']);i+=1
    rc=signed(s['RC']);settings=[]
    if s['ADMIT']>1 or s['STATE']>3 or s['STAGE']>12 or s['SLOT']>3 or s['POLLS']>512 or s['CALLBACKS']>4096 or any(s[k]>15 for k in ('TX','POP','DONE','QUARANTINE')) or s['WRITES']>4 or s['CACHE']>12 or s['READS']>534:raise ValueError('Unbounded session metadata')
    if s['POP']&~s['TX'] or s['DONE']&~s['POP']:raise ValueError('Impossible progress masks')
    if not s['ADMIT'] and (any(s[k] for k in s if k!='RC') or any(bind.values())):raise ValueError('Unadmitted result has side effects')
    mask=fields(rows[i],'REPLIES',['MASK'])['MASK'];i+=1
    if mask!=s['DONE']:raise ValueError('Only completed exact replies may be decoded')
    replies={};lengths=(17,1,16,30)
    for slot in range(4):
        if not mask&(1<<slot):continue
        values=[]
        for index in range(lengths[slot]):
            r=fields(rows[i],'RAW',['SLOT','INDEX','VALUE']);i+=1
            if r['SLOT']!=slot or r['INDEX']!=index or r['VALUE']>0xffffffff:raise ValueError('Raw result order/width differs')
            values.append(r['VALUE'])
        replies[str(slot)]=values
    candidate=fields(rows[i],'CANDIDATE',['VALID','BUS','CPU','BYTES','RESERVE_START','RESERVE_END','WIDTH','HEIGHT','STRIDE','DEPTH','ORDER','ALPHA'],' NO_MAPPING_NO_DRAW');i+=1
    if not rc:
        if s['ADMIT']!=1 or s['STATE']!=2 or s['STAGE']!=12 or s['SLOT']!=3 or any(s[k]!=15 for k in ('TX','POP','DONE')) or s['QUARANTINE'] or s['WRITES']!=4 or s['CACHE']!=12:raise ValueError('Incomplete successful allocation exchange')
        expected=live['STORAGE']+3*4096|8
        if bind['MMIO']!=0x107c013880 or bind['END']!=0x107c0138c0 or not 0<bind['FW']<0xffffffff or not 0<bind['MBOX']<0xffffffff or any(bind[k]!=expected for k in ('EXPECTED','PEEK','POPPED')):raise ValueError('Binding/matched response differs')
        if not bind['START_US']<=bind['LAST_US']<bind['DEADLINE_US'] or bind['DEADLINE_US']-bind['START_US']!=1000000:raise ValueError('Query timing differs')
        if replies['0'][:10]!=[1,0,1920,1080,32,7680,1920,1080,0,0] or replies['1']!=[0]:raise ValueError('Live32 preflight or display selection differs')
        wanted=[1920,1080,1920,1080,32,0,2,0,0,0,0,0,0]
        a,b=replies['2'],replies['3']
        if a[:13]!=wanted or b[:13]!=wanted or a[15]!=7680 or b[13]!=7680 or b[14:23]!=[0,1920,1080,32,7680,1920,1080,0,0]:raise ValueError('Set and independent GET geometry disagree')
        bus,size=a[13:15];base=bus&0x3fffffff;end=base+size;reserved=(end+16383)&~16383
        if bus&0xc0000000!=0 or base&16383 or not 8294400<=size<=16*1024*1024 or not 0x3e000000<=base<end<=reserved<=0x40000000:raise ValueError('Explicit Pi5 zero-prefix/allocation range differs')
        wanted_candidate=dict(VALID=1,BUS=bus,CPU=base,BYTES=size,RESERVE_START=base,RESERVE_END=reserved,WIDTH=1920,HEIGHT=1080,STRIDE=7680,DEPTH=32,ORDER=0,ALPHA=2)
        if candidate!=wanted_candidate:raise ValueError('Candidate differs from exact returned allocation')
        if base<live['LOADER_END'] and live['LOADER_START']<reserved or base<live['FDT_START']+live['FDT_BYTES'] and live['FDT_START']<reserved:raise ValueError('Live framebuffer overlap')
    elif rc not in (-1,-2,-3,-4,-5,-6,-7,-8) or any(candidate.values()) or (s['ADMIT'] and (s['STATE']!=3 or s['QUARANTINE']!=15)):raise ValueError('Failure must quarantine without candidate')
    if i+2!=len(rows):raise ValueError('Partial/extra records')
    endrow=re.fullmatch(re.escape(PREFIX+f'RESULT TAG={tag} RC=')+'('+HEX+') FIXED_PROFILE=1 MAX_TX=4 ALLOCATE_MAX=1 RELEASE=0 DRAW=0 NO_HANDOFF_AUTHORITY',rows[i])
    if not endrow or signed(int(endrow[1],16))!=rc or rows[i+1]!=PREFIX+f'STOP TAG={tag} NO_RELOAD RETAIN_UNTIL_RESET':raise ValueError('Exact terminal outcome differs')
    return dict(diagnostic_pass=rc==0,allocation_trial_pass=rc==0,precheck_failed=False,result_rc=rc,session=s,binding=bind,
        raw_replies=replies,candidate=candidate,cpu=cpu,live=live,observation_bytes=sum(len(x)+2 for x in rows),
        mailbox_requests=s['WRITES'],framebuffer_authority=False,allocation_requests_authored=True,framebuffer_memory_access=False,drawing=False,receiver_path_qualified=False)

