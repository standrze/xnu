#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Stage only the pinned v2 socket image on the exact disposable card.

Plan by default; preserve all 40 prior artifacts and fresh complete snapshots.
No reboot, firmware/config change, HFS mount, retries or automatic rollback.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess

try:
    from . import stage_apple_network_trial as previous
    from . import check_socket_identity_package as package_check
except ImportError:
    import stage_apple_network_trial as previous
    import check_socket_identity_package as package_check

base=previous.base
ROOT,HOST,SSH=base.ROOT,base.HOST,base.SSH
HISTORY=ROOT/'build/rpi5/apple-network-installed-20261012'
HISTORY_SHA={'plan.json':'4eef009e31488479d8a8d34f6548ad5b22c1e76c57a63a06700769fe33b11e2a',
             'result.json':'1dadcc9be3a8513bdff363a62e74cdc5bd4999a52160eff9b133cf12a836a49e'}
OLD_SHA=previous.NEW_SHA
NEW_SHA='f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536'
FAT_SHA='ed51edc3c7209a5bb1efb72d8dfd17d4824db9314fd968075b8915f45134b205'
PROFILE='socket-identity-trial'
PREVIOUS_NAME='apple-network-diagnosed.bin'
NAMES=('probe.apple-network-diagnosed-20261012.bin','probe.socket-identity-trial-20261012.tmp')


def remote_template():
    source=previous.remote_template()
    if source.count(repr(previous.PREVIOUS_NAME))!=3 or source.count(",'apple-network-trial')")!=1:
        raise ValueError('Reviewed previous installation template changed')
    source=source.replace(repr(previous.PREVIOUS_NAME),repr(PREVIOUS_NAME)).replace(
        ",'apple-network-trial')",",'socket-identity-trial')")
    # Extend only the isolated remote execution namespace, never mutate the
    # frozen shared helper/map or historical validators in the local process.
    return 'INSTALL_NAMES['+repr(PROFILE)+']='+repr(NAMES)+'\n'+source


if previous.PREPARE.count("prefix='xnu-gate6-apple-net-'")!=1:
    raise ValueError('Reviewed SSD preparation template changed')
PREPARE=previous.PREPARE.replace("prefix='xnu-gate6-apple-net-'","prefix='xnu-gate6-socket-id-'")


def load_plan(package,boot_id):
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot_id):
        raise ValueError('Verified SSD Linux boot UUID required')
    for name,pin in HISTORY_SHA.items():
        if base.terminal.sha256(HISTORY/name)!=pin: raise ValueError('Pinned installation history changed')
    plan=json.loads((HISTORY/'plan.json').read_text()); result=json.loads((HISTORY/'result.json').read_text())
    previous.validate_result(result,plan)
    if result['image_sha256']!=OLD_SHA or result['protected_after']['boot']['sha256']!=FAT_SHA:
        raise ValueError('Not the accepted Apple network baseline')
    if boot_id==result['identity']['boot_id']: raise ValueError('Distinct SSD return required')
    report=package_check.inspect(package)
    if report['image_sha256']!=NEW_SHA or report['image_bytes']!=19384000:
        raise ValueError('Pinned v2 identity/socket package required')
    binding=copy.deepcopy(plan['identity_binding'])
    binding['linux_boot_id_before_write']=result['identity']['boot_id']
    binding['linux_boot_id_after_write']=boot_id
    backups=copy.deepcopy(plan['nvme_backups'])
    backups.extend(dict(path=result['run']+'/'+row['saved_as'],bytes=row['bytes'],sha256=row['sha256'])
                   for row in result['backups'])
    prior=ROOT/'build/rpi5/bl33-probe-wdmzdtem/probe.bin'
    if base.terminal.sha256(prior)!=previous.OLD_SHA: raise ValueError('Preserved zsh image changed')
    backups.append(dict(path=result['run']+'/'+previous.PREVIOUS_NAME,
                        bytes=prior.stat().st_size,sha256=previous.OLD_SHA))
    if len(backups)!=40 or len({row['path'] for row in backups})!=40:
        raise ValueError('Incomplete/duplicate preservation chain')
    protected=dict(result['protected_files_sha256']); del protected['probe.bin']
    sources=[Path(__file__),Path(previous.__file__),Path(base.capture.__file__),
             Path(base.install_core.__file__),Path(base.snapshots.__file__),Path(package_check.__file__)]
    return dict(host=HOST,profile=PROFILE,candidate=report['image'],old_image_sha256=OLD_SHA,
        new_image_sha256=NEW_SHA,linux_boot_id=boot_id,identity_binding=binding,nvme_backups=backups,
        protected_sha256={key:row['sha256'] for key,row in result['protected_after'].items()},
        protected_files=protected,preflight=report,history_sha256=HISTORY_SHA,
        source_sha256={str(path):base.terminal.sha256(path) for path in sources},
        no_hfs_mount=True,no_pcie_access=True,no_config_change=True,no_reboot=True)


def remote_source(plan):
    for name,pin in plan['source_sha256'].items():
        if base.terminal.sha256(Path(name))!=pin: raise ValueError('Staging source changed')
    modules=[base.capture,base.install_core,base.snapshots]
    return '\n'.join(Path(module.__file__).read_text() for module in modules)+\
        '\nPLAN=json.loads('+repr(json.dumps(plan))+')\n'+remote_template()


def validate_result(result,plan):
    required=dict(status='installed',run=plan['run'],image_sha256=NEW_SHA,
        preserved_sd_image_sha256=OLD_SHA,nvme_previous_image_sha256=OLD_SHA,
        boot_unmounted=True,no_hfs_mount=True,no_config_change=True,no_reboot=True,
        power_loss_atomicity_claimed=False,temporary_published=True,sd_backup=NAMES[0],
        nvme_backups_verified=plan['nvme_backups'])
    if any(type(result.get(k)) is not type(v) or result[k]!=v for k,v in required.items()):
        raise ValueError('Incomplete install result; inspect existing run, never retry')
    files=dict(plan['protected_files'],**{'probe.bin':NEW_SHA,NAMES[0]:OLD_SHA})
    identity=dict(identity=plan['identity_binding']['expected'],boot_id=plan['linux_boot_id'],hostname='kamidana')
    if result.get('identity')!=identity or result.get('protected_files_sha256')!=files:
        raise ValueError('Post-install identity/files differ')
    rows=[('mbr','/dev/mmcblk0',512,'mbr.before-write.bin'),
          ('boot','/dev/mmcblk0p1',536870912,'boot-partition.before-write.img'),
          ('hfs','/dev/mmcblk0p2',134217728,'hfs-partition.before.img')]
    expected=[dict(device=node,bytes=size,sha256=plan['protected_sha256'][key],saved_as=name)
              for key,node,size,name in rows]
    if result.get('backups')!=expected: raise ValueError('Incomplete fresh snapshots')
    for key,node,size,_ in rows:
        row=result.get('protected_after',{}).get(key,{})
        if row.get('device')!=node or row.get('bytes')!=size or not re.fullmatch('[0-9a-f]{64}',row.get('sha256','')):
            raise ValueError('Incomplete post-install block coverage')
        if key!='boot' and row['sha256']!=plan['protected_sha256'][key]: raise ValueError('Protected MBR/HFS changed')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',type=Path); parser.add_argument('--linux-boot-id',required=True)
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'build/rpi5'): parser.error('New build/rpi5 output required')
    plan=load_plan(args.package,args.linux_boot_id); args.output.mkdir(parents=True,exist_ok=False)
    def save(): (args.output/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    save()
    if not args.execute:
        print('LOCAL_PLAN_ONLY_NO_NETWORK_OR_DEVICE_ACCESS '+str(args.output)); return 0
    if load_plan(args.package,args.linux_boot_id)!=plan: raise ValueError('Inputs changed before SSH')
    prepared=subprocess.run(SSH+['python3 -'],input=PREPARE,text=True,capture_output=True,check=True,timeout=30)
    run=json.loads(prepared.stdout)['run']
    if not re.fullmatch(r'/home/sandrzej/xnu-gate6-socket-id-[a-z0-9_]{8}',run): raise ValueError('Unexpected SSD run')
    plan['run']=run; save()
    subprocess.run(['scp','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',
                    plan['candidate'],HOST+':'+run+'/candidate.bin'],check=True,timeout=120)
    source=remote_source(plan)
    (args.output/'remote-source.sha256').write_text(hashlib.sha256(source.encode()).hexdigest()+'\n')
    try:
        response=subprocess.run(SSH+['sudo -n python3 -'],input=source,text=True,capture_output=True,timeout=300)
    except subprocess.TimeoutExpired as error:
        for name,value in (('remote.stdout',error.stdout),('remote.stderr',error.stderr)):
            (args.output/name).write_bytes(value.encode() if isinstance(value,str) else value or b'')
        (args.output/'outcome-unknown.txt').write_text('Inspect existing remote run; do not retry or roll back.\n')
        raise
    for name,value in (('remote.stdout',response.stdout),('remote.stderr',response.stderr)):
        (args.output/name).write_text(value)
    response.check_returncode(); result=json.loads(response.stdout); validate_result(result,plan)
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n'); print(args.output)
    return 0


if __name__=='__main__': raise SystemExit(main())
