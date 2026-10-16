# SPDX-License-Identifier: BSD-2-Clause
"""Strict image/tag-bound ABI observations, not autonomous recovery acceptance.

An installer-bound receive-only capture, continuous reset/boot evidence and a
fresh independently verified normal NVMe Linux boot are separate requirements.
This parser never opens a device, sends commands or accepts a reset alone.
"""
import re
PREFIX=b'RPI5XNU:FWABI:'
EVENT_KEYS=('FID','TOKEN','X0','X1','X2','X3','PM_WRITES','GIC_WRITES','RPC_CALLS','PM_CHECKS')


def fields(line,kind,tag,keys):
    pattern=PREFIX+kind.encode()+b' TAG='+tag.encode()+b' '+b' '.join(k.encode()+rb'=(0x[0-9A-F]{16})' for k in keys)
    match=re.fullmatch(pattern,line)
    if not match:raise ValueError('Wrong ABI marker/tag/fields/order')
    return dict(zip(keys,(int(v,16) for v in match.groups())))


def inspect(data,tag,image_sha,firmware_sha):
    if not isinstance(data,bytes) or len(data)>4*1024*1024 or not isinstance(tag,str) or not re.fullmatch('[0-9a-f]{32}',tag):
        raise ValueError('Bounded tagged ABI capture required')
    if any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for v in (image_sha,firmware_sha)):
        raise ValueError('Externally verified installed image and firmware hashes required')
    lines=[line.rstrip(b'\r') for line in data.split(b'\n') if line.startswith(PREFIX)]
    def head(kind):return PREFIX+kind.encode()+b' TAG='+tag.encode()
    if len(lines)!=19 or lines[0]!=head('ENTRY')+b' EL2 NO_XNU NO_CPU_ON CONTROLLER_WRITES=0 DMA=0':
        raise ValueError('Incomplete/duplicated/faulted fresh ABI sequence')
    match=re.fullmatch(re.escape(head('EL1'))+rb' MMU_CACHE_OFF DAIF_MASKED PRIMARY_ONLY FREQUENCY=(0x[0-9A-F]{16})',lines[1])
    if not match or not 1000000<=(frequency:=int(match[1],16))<=1000000000:raise ValueError('Bad counter frequency')
    position=2
    def event(kind):
        nonlocal position
        result=fields(lines[position],kind,tag,EVENT_KEYS);position+=1
        return result
    def expected(kind,pm,gic,rpc,checks,fid=0,token=0,raw=(0,0,0,0)):
        want=dict(FID=fid,TOKEN=token,**dict(zip(('X0','X1','X2','X3'),raw)),
            PM_WRITES=pm,GIC_WRITES=gic,RPC_CALLS=rpc,PM_CHECKS=checks)
        got=event(kind)
        if got!=want:raise ValueError('ABI event counters/order/result differ: '+kind)
    expected('ARMED',1,0,0,0);expected('MASKED',1,3,0,71)
    token=0;last_counter=0;claim_counter=0;observations=[]
    # Exact actual PM/IRQ core composition: 41 PM checks per IRQ check, two
    # IRQ checks per RPC, plus one PM check after each bounded 2ms wait.
    for index,(fid,checks) in enumerate(((0xc2007f10,112),(0xc2007f11,194),
                                        (0xc2007f12,277),(0xc2007f12,360),(0xc2007f12,443)),1):
        begin=event('RPC_BEGIN')
        if index==2:token=begin['TOKEN']
        if index>=2 and not token:raise ValueError('Nonzero retained owner missing')
        expected_begin=dict(FID=fid,TOKEN=0 if index==1 else token,X0=0,X1=0,X2=0,X3=0,
            PM_WRITES=1,GIC_WRITES=3,RPC_CALLS=index-1,PM_CHECKS=checks)
        if begin!=expected_begin:raise ValueError('Wrong RPC invocation/owner/PM budget')
        result=event('RPC_END');counter=result['X2'];sequence=1 if index<=2 else index-1;facts=3 if index==1 else 31
        if counter<=last_counter:raise ValueError('Firmware counter not strictly advancing')
        if index==2:claim_counter=counter
        if index>2 and (counter>=claim_counter+9*frequency or counter-last_counter<(frequency+499)//500):
            raise ValueError('Firmware check outside bounded deadline/minimum wait')
        expected_end=expected_begin|dict(X1=sequence,X2=counter,X3=facts,RPC_CALLS=index)
        if result!=expected_end:raise ValueError('Malformed firmware status/ABI/sequence/facts')
        observations.append(dict(fid=fid,sequence=sequence,counter=counter,facts=facts))
        if index>2:expected('CHECKED',1,3,index,checks+41,raw=(0,sequence,counter,facts))
        last_counter=counter
    result=fields(lines[position],'RESULT',tag,('RC','PHASE','PM_WRITES','GIC_WRITES','RPC_CALLS','SEQUENCE','FACTS','PM_CHECKS'))
    if result!=dict(RC=0,PHASE=2,PM_WRITES=1,GIC_WRITES=3,RPC_CALLS=5,SEQUENCE=4,FACTS=31,PM_CHECKS=485):
        raise ValueError('Trial terminal result differs')
    position+=1
    if lines[position]!=head('STOP')+b' NO_RELOAD WAIT_FOR_RESET CONTROLLER_WRITES=0 DMA=0 RESET_RETURN_PROVEN=0':
        raise ValueError('Non-servicing stop absent')
    return dict(firmware_abi_observation_pass=True,trial_tag=tag,image_sha256=image_sha,
        firmware_sha256=firmware_sha,frequency=frequency,observations=observations,
        pm_writes=1,selective_gic_disable_writes=3,pm_checks=485,firmware_checks=3,
        controller_writes=0,dma=False,ethernet_proven=False,xnu_pe_runtime_proven=False,
        physical_reset_return_proven=False,
        scope='Complete tagged ABI observations only; caller must independently bind installed hashes and continuous autonomous NVMe return')
