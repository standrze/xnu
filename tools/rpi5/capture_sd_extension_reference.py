#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Guarded Linux read-only control for the exact preserved failed W3 boot.

Local validation only unless --execute. No serial, media writes, staging,
mounts, retries, resets or reboot. A Linux reply never admits XNU writes.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

import capture_hfs_persistence as history
import sd_extension_reference_core as observer
import wait_nvme_linux as linux

installer=history.installer
ROOT=installer.ROOT
PINS={'plan':'f26e245b905aa5b70cd330eed61a477b9cf97ca0d353072d8c67ead52798bb51',
      'installed':'a87c38afb168c0470c99c1d4995088b22bd59fe0862c19d1e05d9142e7cd95ba',
      'trial':'09e287eed22d657f4ea0822070bcef6c05ae19b2bb8037b8631120722638ccb1',
      'serial':'7588028a78b77b05209484c44f05e2febfcaab6d97a42f039e4d5e36ca638453'}
W3_IMAGE='79d5b90aa9821c639e6f9476bd3c7dfd2727d26c4c551b8072dd06570ded0ec3'
ZERO_SHA=hashlib.sha256(bytes(512)).hexdigest()
HEADER=b'RPI5XNU:SD:CACHE_PROBE_FAIL STAGE=7 RC=-5 SPEC=6 FUNCTION=0 ADDRESS=0x0 SCR=0205848700000000 BYTES=512'


def failed_w3(plan,result,state,raw):
    installer.validate_result(result,plan)
    expected={'status':'failed','image_sha256':W3_IMAGE,'transmitted_bytes':0,
              'write_batch_attempts':0,'hfs_mounted':False,'durability_verified':False,
              'checks':[],'reads':[],'error':'Unsafe, old or failed boot before write input',
              'linux_boot_id_before_write':plan['linux_boot_id'],'bytes':len(raw)}
    if (plan.get('profile')!='write-cache-diagnostic' or plan.get('new_image_sha256')!=W3_IMAGE
            or any(type(state.get(k)) is not type(v) or state[k]!=v for k,v in expected.items())
            or state.get('write_input_sha256')!=plan['evidence_sha256']
            or state.get('serial_sha256')!=hashlib.sha256(raw).hexdigest()
            or raw.count(HEADER)!=1
            or not re.search(rb'(?m)^'+re.escape(HEADER)+rb'\r{0,2}\n',raw)
            or any(marker in raw for marker in (b'RPI5XNU:SD:WRITE_ADMITTED',b'RPI5XNU:HFSRW:',b'RPI5XNU:HFSWRITE:'))):
        raise ValueError('The exact zero-input W3 cache failure is required')
    rows=re.findall(rb'(?m)^RPI5XNU:SD:CACHE_PROBE_BYTES OFFSET=([0-9]+) HEX=([0-9a-f]{32})\r{0,2}\n',raw)
    payload=b''.join(bytes.fromhex(row.decode()) for _,row in rows)
    if [int(offset) for offset,_ in rows]!=list(range(0,512,16)) or payload!=bytes(512):
        raise ValueError('Complete ordered W3 zero-byte register evidence required')
    return ZERO_SHA


def load_plan(installed,trial,ready,now=None):
    paths={key:installer.evidence_path(str(path)) for key,path in
           (('plan',installed/'plan.json'),('installed',installed/'result.json'),
            ('trial',trial),('serial',trial.with_name('serial.bin')),('ready',ready))}
    bound={key:history.recorder.sha256(path) for key,path in paths.items()}
    if any(bound[key]!=value for key,value in PINS.items()):
        raise ValueError('Original W3 installation/failure bytes changed')
    reports={key:json.loads(paths[key].read_text()) for key in ('plan','installed','trial','ready')}
    raw=paths['serial'].read_bytes(); plan=reports['plan']; result=reports['installed']
    failed_w3(plan,result,reports['trial'],raw)
    state=reports['ready']; identity=state.get('identity',{})
    now=now or datetime.now(timezone.utc)
    ended=history.timestamp(state['ended_utc']) if state.get('status')=='ready' else None
    if (ended is None or not 0<=(now-ended).total_seconds()<=1800
            or identity.get('hostname')!='kamidana' or identity.get('root')!=linux.ROOT
            or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',identity.get('boot_id',''))
            or identity['boot_id']==plan['linux_boot_id']):
        raise ValueError('Fresh exact SSD Linux return after W3 is required')
    backups=history.backup_rows(plan,result)
    protected=result['write_trial_backups']['after']
    if (len(backups)!=20 or protected['hfs']['sha256']!=plan['fixture_sha256']
            or protected['mbr']['sha256']!=plan['current_mbr_sha256']):
        raise ValueError('Complete W3 preservation/protection chain required')
    # Reuse the exact read-only identity checker; its internal historical field
    # names do not mean writes occurred. W3 proved zero input/batch/mount.
    binding=dict(expected=plan['expected'],linux_boot_id_before_write=plan['linux_boot_id'],
                 linux_boot_id_after_write=identity['boot_id'])
    source_hashes={name:history.recorder.sha256(path) for name,path in
        (('observer',Path(observer.__file__)),('capture_core',Path(history.core.__file__)),('controller',Path(__file__)))}
    if any(history.recorder.sha256(path)!=bound[key] for key,path in paths.items()):
        raise ValueError('Linux control evidence changed during validation')
    return dict(host=linux.HOST,identity_binding=binding,nvme_backups=backups,
        protected_sha256={key:protected[key]['sha256'] for key in ('mbr','boot','hfs')},
        evidence_sha256=bound,source_sha256=source_hashes,xnu_payload_sha256=ZERO_SHA,
        cache_admission=False,durability_verified=False)


REMOTE=r'''
def protected_control(plan):
    records={key:snapshot(node,capacity,length) for key,node,capacity,length in
        (('mbr','/dev/mmcblk0',128177930240,512),
         ('boot','/dev/mmcblk0p1',536870912,536870912),
         ('hfs','/dev/mmcblk0p2',134217728,134217728))}
    if {key:row['sha256'] for key,row in records.items()}!=plan['protected_sha256']:
        raise ValueError('Complete protected MBR/FAT/HFS bytes differ')
    return records

binding=PLAN['identity_binding']
before=identity(binding)
verify_backups(PLAN)
protected_before=protected_control(PLAN)
result=observe(binding)
protected_after=protected_control(PLAN)
verify_backups(PLAN)
after=identity(binding)
if before!=after or protected_before!=protected_after:
    raise ValueError('Card/Linux/protected bytes changed during control')
result.update(protected_before=protected_before,protected_after=protected_after,
    nvme_backups_verified=PLAN['nvme_backups'],sd_write_operations=0,sd_mount_operations=0,
    xnu_payload_sha256=PLAN['xnu_payload_sha256'],
    same_payload_as_xnu=result['general_information']['payload_sha256']==PLAN['xnu_payload_sha256'])
print(json.dumps(result))
'''


def remote_source(plan):
    sources={name:Path(path).read_bytes() for name,path in
             (('capture_core',history.core.__file__),('observer',observer.__file__),('controller',__file__))}
    if any(hashlib.sha256(data).hexdigest()!=plan['source_sha256'][name] for name,data in sources.items()):
        raise ValueError('Control source changed before rendering remote program')
    return (sources['capture_core'].decode()+'\n'+sources['observer'].decode()+
            '\nPLAN=json.loads('+repr(json.dumps(plan))+')\n'+REMOTE)


def validate_report(result,plan):
    expected=dict(status='linux_reference_only',cache_admission=False,durability_verified=False,
        userspace_cmd48_ioctls=1,userspace_write_commands=0,sd_write_operations=0,sd_mount_operations=0,
        identity=dict(identity=plan['identity_binding']['expected'],
                      boot_id=plan['identity_binding']['linux_boot_id_after_write'],hostname='kamidana'),
        nvme_backups_verified=plan['nvme_backups'],xnu_payload_sha256=ZERO_SHA)
    if any(type(result.get(k)) is not type(v) or result[k]!=v for k,v in expected.items()):
        raise ValueError('Incomplete fixed Linux reference/control identity')
    record=result['general_information']; payload=bytes.fromhex(record['payload_hex'])
    fields=dict(opcode=48,argument=511,write_flag=0,is_acmd=0,blocks=1,bytes=512,flags=0x35)
    response=record.get('response',[])
    if (any(type(record.get(k)) is not type(v) or record[k]!=v for k,v in fields.items())
            or len(payload)!=512 or record['payload_sha256']!=hashlib.sha256(payload).hexdigest()
            or len(response)!=4 or any(type(v) is not int or not 0<=v<=0xffffffff for v in response)
            or response[0]&0xfff98088 or (response[0]&0x1f00)!=0x900
            or type(record.get('sentinel_unchanged')) is not bool
            or record['sentinel_unchanged']!=(payload==bytes([0xa5])*512)
            or type(result.get('same_payload_as_xnu')) is not bool
            or result['same_payload_as_xnu']!=(payload==bytes(512))):
        raise ValueError('Malformed complete CMD48 read/control response')
    for name in ('protected_before','protected_after'):
        expected_rows={key:dict(device=node,bytes=size,sha256=plan['protected_sha256'][key])
            for key,node,size in (('mbr','/dev/mmcblk0',512),('boot','/dev/mmcblk0p1',536870912),('hfs','/dev/mmcblk0p2',134217728))}
        if result.get(name)!=expected_rows: raise ValueError('Full protected bytes do not match')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('installed','trial','linux-ready','output'): parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--execute',action='store_true'); args=parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'build/rpi5'): parser.error('Use a fresh build/rpi5 directory')
    plan=load_plan(args.installed,args.trial,args.linux_ready)
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    if not args.execute:
        print('LOCAL_PLAN_ONLY_NO_NETWORK_OR_DEVICE_ACCESS '+str(args.output)); return 0
    if load_plan(args.installed,args.trial,args.linux_ready)!=plan: raise ValueError('Control inputs changed before SSH')
    source=remote_source(plan)
    (args.output/'remote-source.sha256').write_text(hashlib.sha256(source.encode()).hexdigest()+'\n')
    try:
        response=subprocess.run(installer.boot.SSH+['sudo -n python3 -'],input=source,text=True,
                                capture_output=True,timeout=300)
    except subprocess.TimeoutExpired as error:
        for name,value in (('remote.stdout',error.stdout),('remote.stderr',error.stderr)):
            (args.output/name).write_bytes(value.encode() if isinstance(value,str) else value or b'')
        (args.output/'outcome-unknown.txt').write_text('Inspect existing attempt; never automatically repeat CMD48.\n')
        raise
    (args.output/'remote.stdout').write_text(response.stdout); (args.output/'remote.stderr').write_text(response.stderr)
    response.check_returncode(); result=json.loads(response.stdout); validate_report(result,plan)
    if load_plan(args.installed,args.trial,args.linux_ready)!=plan: raise ValueError('Control inputs changed during SSH')
    result.update(captured_utc=datetime.now(timezone.utc).isoformat(),source_sha256=plan['source_sha256'],
                  evidence_sha256=plan['evidence_sha256'],remote_source_sha256=hashlib.sha256(source.encode()).hexdigest())
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(args.output); return 0


if __name__=='__main__': raise SystemExit(main())
