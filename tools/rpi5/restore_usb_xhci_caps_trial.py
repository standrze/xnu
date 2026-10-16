#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Restore the exact working zsh loader after the USB capability trial."""
import argparse
import json
from pathlib import Path
import re
import subprocess

from tools.rpi5 import stage_usb_xhci_caps_trial as stage

CANDIDATE_SHA = "4435959ce5181d810a9e1638e6b68eabf94fe2c35c59685b63a4d380f74f0782"
RESTORE_PROFILE = "rpi5-usb-xhci-restore-v1"

REMOTE = r'''
import hashlib,json,os,pathlib,shutil,subprocess,tempfile
P=json.loads(__PLAN__)
def run(args,check=True):return subprocess.run(args,check=check,capture_output=True,text=True)
def digest(path):
 h=hashlib.sha256()
 with open(path,'rb',buffering=0) as f:
  while True:
   b=f.read(4*1024*1024)
   if not b:break
   h.update(b)
 return h.hexdigest()
if run(['findmnt','-no','SOURCE,FSTYPE','/']).stdout.strip()!='/dev/nvme0n1p2 ext4':raise ValueError('NVMe root required')
if pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=P['linux_boot_id']:raise ValueError('boot witness differs')
if run(['findmnt','-rn','-S','/dev/mmcblk0p1'],check=False).stdout.strip():raise ValueError('boot partition mounted')
archive=P['remote_run']+'/probe.before.bin'
firmware_archive=P['remote_run']+'/bl31.before.bin'
config_archive=P['remote_run']+'/config.before.txt'
if digest(archive)!=P['baseline_sha256']:raise ValueError('preserved baseline differs')
if digest(firmware_archive)!=P['baseline_firmware_sha256']:raise ValueError('preserved firmware differs')
if digest(config_archive)!=P['baseline_config_sha256']:raise ValueError('preserved config differs')
mount=tempfile.mkdtemp(prefix='xnu-usb-restore.',dir='/tmp')
try:
 run(['mount','/dev/mmcblk0p1',mount])
 if digest(mount+'/probe.bin')!=P['candidate_sha256']:raise ValueError('failed trial image no longer installed')
 if digest(mount+'/bl31.bin')!=P['candidate_firmware_sha256']:raise ValueError('trial firmware no longer installed')
 if digest(mount+'/config.txt')!=P['candidate_config_sha256']:raise ValueError('trial config no longer installed')
 temp=mount+'/.probe.usb-restore.tmp';firmware_temp=mount+'/.bl31.usb-restore.tmp';config_temp=mount+'/.config.usb-restore.tmp'
 shutil.copyfile(archive,temp);shutil.copyfile(firmware_archive,firmware_temp);shutil.copyfile(config_archive,config_temp)
 with open(temp,'rb') as f:os.fsync(f.fileno())
 with open(firmware_temp,'rb') as f:os.fsync(f.fileno())
 with open(config_temp,'rb') as f:os.fsync(f.fileno())
 if digest(temp)!=P['baseline_sha256']:raise ValueError('restore temp differs')
 if digest(firmware_temp)!=P['baseline_firmware_sha256']:raise ValueError('firmware restore temp differs')
 if digest(config_temp)!=P['baseline_config_sha256']:raise ValueError('config restore temp differs')
 os.replace(config_temp,mount+'/config.txt');os.replace(firmware_temp,mount+'/bl31.bin');os.replace(temp,mount+'/probe.bin')
 fd=os.open(mount,os.O_RDONLY);os.fsync(fd);os.close(fd)
 if digest(mount+'/probe.bin')!=P['baseline_sha256']:raise ValueError('restore write differs')
 if digest(mount+'/bl31.bin')!=P['baseline_firmware_sha256']:raise ValueError('firmware restore differs')
 if digest(mount+'/config.txt')!=P['baseline_config_sha256']:raise ValueError('config restore differs')
 for name,value in P['protected'].items():
  if digest(mount+'/'+name)!=value:raise ValueError('protected file differs: '+name)
finally:
 run(['umount',mount],check=False);pathlib.Path(mount).rmdir()
run(['sync'])
verify=tempfile.mkdtemp(prefix='xnu-usb-restored.',dir='/tmp')
try:
 run(['mount','-o','ro','/dev/mmcblk0p1',verify]);installed=digest(verify+'/probe.bin');firmware=digest(verify+'/bl31.bin');config=digest(verify+'/config.txt')
finally:
 run(['umount',verify],check=False);pathlib.Path(verify).rmdir()
if installed!=P['baseline_sha256']:raise ValueError('restored readback differs')
if firmware!=P['baseline_firmware_sha256']:raise ValueError('restored firmware readback differs')
if config!=P['baseline_config_sha256']:raise ValueError('restored config readback differs')
print(json.dumps({'status':'complete','restored_sha256':installed,'remote_run':P['remote_run'],
 'restored_firmware_sha256':firmware,'restored_config_sha256':config,
 'config_restored':True,'firmware_restored':True,'no_reboot':True},sort_keys=True))
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--remote-run',required=True)
    parser.add_argument('--linux-boot-id',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'/home/sandrzej/xnu-usb-xhci-[a-z0-9_]+',args.remote_run):
        raise ValueError('exact USB trial run required')
    output=args.output.resolve()
    if not output.is_relative_to(stage.ROOT/'build/rpi5'):raise ValueError('build/rpi5 evidence directory required')
    output.mkdir(exist_ok=False)
    plan={'profile':RESTORE_PROFILE,'remote_run':args.remote_run,
          'linux_boot_id':args.linux_boot_id,
          'candidate_sha256':CANDIDATE_SHA,
          'candidate_firmware_sha256':stage.TRIAL_FIRMWARE_SHA,
          'candidate_config_sha256':stage.TRIAL_CONFIG_SHA,
          'baseline_sha256':stage.BASELINE['probe.bin'][1],
          'baseline_firmware_sha256':stage.BASELINE['bl31.bin'][1],
          'baseline_config_sha256':stage.BASELINE['config.txt'][1],
          'protected':{},'no_reboot':True}
    (output/'plan.json').write_text(json.dumps(plan,indent=2,sort_keys=True)+'\n')
    source=REMOTE.replace('__PLAN__',repr(json.dumps(plan)))
    response=subprocess.run(stage.SSH+['sudo','-n','python3','-'],input=source,
        capture_output=True,text=True,timeout=180)
    (output/'remote.stdout').write_text(response.stdout);(output/'remote.stderr').write_text(response.stderr)
    response.check_returncode();result=json.loads(response.stdout)
    if (result.get('restored_sha256')!=plan['baseline_sha256'] or
            result.get('restored_firmware_sha256')!=plan['baseline_firmware_sha256'] or
            result.get('restored_config_sha256')!=plan['baseline_config_sha256'] or
            result.get('firmware_restored') is not True or result.get('config_restored') is not True or
            result.get('no_reboot') is not True):
        raise ValueError('restore receipt differs')
    (output/'result.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
