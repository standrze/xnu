# SPDX-License-Identifier: BSD-2-Clause
"""Exact GET-only standalone records; raw values grant no display authority."""
import re
PREFIX='RPI5XNU:DISPLAYGET:'
PROFILE='pi5-display-get-standalone-v1'
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
        return dict(diagnostic_pass=False,query_pass=False,precheck_failed=True,failed_stage=r['STAGE'],result_rc=-1,framebuffer_authority=False)
    if stages!=list(range(1,20)) or rows[i]!=PREFIX+'ARMED WATCHDOG=15 SOFTWARE=8 NO_RELOAD':raise ValueError('Bounded watchdog/prechecks required')
    i+=1
    cpu=fields(rows[i],'EL1',['SCTLR','DAIF'],' CPU_MMU_CACHE_OFF NO_XNU NO_CPU_ON RAW_ONLY');i+=1
    if cpu['SCTLR']&0x02001005 or cpu['DAIF']&0x3c0!=0x3c0:raise ValueError('CPU admission differs')
    live=fields(rows[i],'LIVE',['LOADER_START','LOADER_END','FDT_START','FDT_BYTES','STORAGE'],' STORAGE_BYTES=0x0000000000003000 RETAIN_UNTIL_RESET');i+=1
    if (live['LOADER_START']!=report['loader_live']['start'] or live['LOADER_END']!=report['loader_live']['end'] or
        live['STORAGE']!=report['query_storage']['start'] or report['query_storage']['bytes']!=12288 or
        not 40<=live['FDT_BYTES']<=1048576 or live['FDT_START']&7 or live['FDT_START']<0x80000 or
        live['FDT_START']+live['FDT_BYTES']>1<<32 or
        live['FDT_START']<live['LOADER_END'] and live['LOADER_START']<live['FDT_START']+live['FDT_BYTES']):raise ValueError('Linked live geometry differs')
    s=fields(rows[i],'SESSION',['RC','ADMIT','STATE','STAGE','SLOT','POLLS','CALLBACKS','TX','POP','DONE','QUARANTINE','CACHE','READS','WRITES']);i+=1
    bind=fields(rows[i],'BIND',['MMIO','END','FW','MBOX','EXPECTED','PEEK','POPPED','START_US','LAST_US','DEADLINE_US']);i+=1
    rc=signed(s['RC']);count=None;settings=[]
    if s['ADMIT']>1 or s['STATE']>3 or s['STAGE']>12 or s['SLOT']>2 or s['POLLS']>512 or s['CALLBACKS']>4096 or any(s[k]>7 for k in ('TX','POP','DONE','QUARANTINE')) or s['WRITES']>3 or s['CACHE']>9 or s['READS']>529:raise ValueError('Unbounded session metadata')
    if s['POP']&~s['TX'] or s['DONE']&~s['POP']:raise ValueError('Impossible progress masks')
    if not s['ADMIT'] and (any(s[k] for k in s if k!='RC') or any(bind.values())):raise ValueError('Unadmitted result has side effects')
    if not rc:
        count=fields(rows[i],'COUNT',['VALUE'])['VALUE'];i+=1
        if count>2:raise ValueError('Unbounded display count')
        mask=(1<<(count+1))-1
        if s['ADMIT']!=1 or s['STATE']!=2 or s['STAGE']!=12 or s['SLOT']!=count or any(s[k]!=mask for k in ('TX','POP','DONE')) or s['QUARANTINE'] or s['WRITES']!=count+1 or s['CACHE']!=5+2*count:raise ValueError('Incomplete successful query')
        expected=live['STORAGE']+4096*count|8
        if bind['MMIO']!=0x107c013880 or bind['END']!=0x107c0138c0 or not 0<bind['FW']<0xffffffff or not 0<bind['MBOX']<0xffffffff or any(bind[k]!=expected for k in ('EXPECTED','PEEK','POPPED')):raise ValueError('Binding/matched response differs')
        if not bind['START_US']<=bind['LAST_US']<bind['DEADLINE_US'] or bind['DEADLINE_US']-bind['START_US']!=1000000:raise ValueError('Query timing differs')
        for display in range(count):
            words=[]
            for index in range(16):
                r=fields(rows[i],'RAW',['DISPLAY','INDEX','VALUE']);i+=1
                if r['DISPLAY']!=display or r['INDEX']!=index or r['VALUE']>0xffffffff:raise ValueError('Raw result order/width differs')
                words.append(r['VALUE'])
            if words[0]!=display:raise ValueError('Selected display index changed')
            settings.append(words)
    elif rc not in (-1,-2,-3,-4,-5,-6,-7) or (s['ADMIT'] and (s['STATE']!=3 or s['QUARANTINE']!=7)):raise ValueError('Failure must quarantine')
    if i+2!=len(rows):raise ValueError('Partial/extra records')
    endrow=re.fullmatch(re.escape(PREFIX+f'RESULT TAG={tag} RC=')+'('+HEX+') GET_ONLY=1 MAX_TX=3 ALLOCATE=0 SET=0 DRAW=0 RAW_NO_FB_AUTHORITY',rows[i])
    if not endrow or signed(int(endrow[1],16))!=rc or rows[i+1]!=PREFIX+f'STOP TAG={tag} NO_RELOAD RETAIN_UNTIL_RESET':raise ValueError('Exact terminal outcome differs')
    return dict(diagnostic_pass=rc==0,query_pass=rc==0,precheck_failed=False,result_rc=rc,session=s,binding=bind,
        count=count,raw_settings=settings,cpu=cpu,live=live,observation_bytes=sum(len(x)+2 for x in rows),
        mailbox_requests=s['WRITES'],framebuffer_authority=False,allocation=False,drawing=False,receiver_path_qualified=False)
