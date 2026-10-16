#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Guard and stage one USB0/xHCI read-only observer; never reboot."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from tools.rpi5 import check_usb_xhci_caps_trial as package_check


ROOT = Path(__file__).resolve().parents[2]
HOST = "sandrzej@192.168.4.23"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
       "-o", "ConnectTimeout=8", HOST]
MANIFEST_SHA = "09cc872d8765553377e6121dec1b0b8c4a63d2f593616ecf4d7494de0149c956"
STAGE_PROFILE = "rpi5-usb-xhci-caps-stage-v1"
TRIAL_FIRMWARE_SHA = "dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b"
TRIAL_CONFIG = ROOT / "build/rpi5/display-allocate-config32-20261013/config.txt"
TRIAL_CONFIG_SHA = "359263f7f9776c6300ebeba344aeb0e2dd2d07df7064fb344b55236219f4cde7"
BASELINE = {
    "config.txt": (278, "aaccab184135aca272db4123fcba34e20874ae0959a90aed1ef6fd4d5e18ed28"),
    "bl31.bin": (45174, "413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46"),
    "probe.bin": (19384000, "f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536"),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


REMOTE = r'''
import hashlib,json,os,pathlib,shutil,subprocess,tempfile
P=json.loads(__PLAN__)
def run(args,check=True):
    return subprocess.run(args,check=check,capture_output=True,text=True)
def digest(path):
    h=hashlib.sha256()
    with open(path,'rb',buffering=0) as f:
        while True:
            b=f.read(4*1024*1024)
            if not b:break
            h.update(b)
    return h.hexdigest()
def copy_exact(source,target,count=None):
    h=hashlib.sha256();n=0
    with open(source,'rb',buffering=0) as r,open(target,'xb',buffering=0) as w:
        while count is None or n<count:
            want=4*1024*1024 if count is None else min(4*1024*1024,count-n)
            b=r.read(want)
            if not b:break
            w.write(b);h.update(b);n+=len(b)
        w.flush();os.fsync(w.fileno())
    if count is not None and n!=count:raise ValueError('short raw backup')
    return {'path':target,'bytes':n,'sha256':h.hexdigest()}
if run(['findmnt','-no','SOURCE,FSTYPE','/']).stdout.strip()!='/dev/nvme0n1p2 ext4':
    raise ValueError('NVMe Linux root required')
if pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=P['linux_boot_id']:
    raise ValueError('Linux boot witness changed')
for dev in ('/dev/mmcblk0p1','/dev/mmcblk0p2'):
    mounted=run(['findmnt','-rn','-S',dev],check=False)
    if mounted.stdout.strip():raise ValueError('SD partition mounted')
identity=run(['blkid','-o','export','/dev/mmcblk0p1']).stdout
for value in ('LABEL=XNU_PROBE','UUID=4FA7-3725','PARTUUID=5ae1f07e-01','TYPE=vfat'):
    if value not in identity.splitlines():raise ValueError('boot identity differs: '+value)
hfs=run(['blkid','-o','export','/dev/mmcblk0p2']).stdout
for value in ('LABEL=XNU_G4_READ','PARTUUID=5ae1f07e-02','TYPE=hfsplus'):
    if value not in hfs.splitlines():raise ValueError('HFS identity differs: '+value)
if int(run(['blockdev','--getsize64','/dev/mmcblk0p1']).stdout)!=536870912:raise ValueError('boot size differs')
if int(run(['blockdev','--getsize64','/dev/mmcblk0p2']).stdout)!=134217728:raise ValueError('HFS size differs')
run_dir=P['remote_run'];candidate=run_dir+'/candidate.bin';firmware=run_dir+'/candidate-bl31.bin';config=run_dir+'/candidate-config.txt'
if os.path.getsize(candidate)!=P['candidate_bytes'] or digest(candidate)!=P['candidate_sha256']:
    raise ValueError('uploaded candidate differs')
if os.path.getsize(firmware)!=P['firmware_bytes'] or digest(firmware)!=P['firmware_sha256']:
    raise ValueError('uploaded trial firmware differs')
if os.path.getsize(config)!=P['config_bytes'] or digest(config)!=P['config_sha256']:
    raise ValueError('uploaded trial config differs')
backups=[]
backups.append(copy_exact('/dev/mmcblk0',run_dir+'/mbr.before.bin',512))
backups.append(copy_exact('/dev/mmcblk0p1',run_dir+'/boot.before.img',536870912))
backups.append(copy_exact('/dev/mmcblk0p2',run_dir+'/hfs.before.img',134217728))
mount=tempfile.mkdtemp(prefix='xnu-usb-mount.',dir='/tmp')
try:
    run(['mount','/dev/mmcblk0p1',mount])
    for name,row in P['baseline'].items():
        path=mount+'/'+name
        if os.path.getsize(path)!=row[0] or digest(path)!=row[1]:raise ValueError('baseline differs: '+name)
    archive=run_dir+'/probe.before.bin';firmware_archive=run_dir+'/bl31.before.bin';config_archive=run_dir+'/config.before.txt'
    if os.path.exists(archive) or os.path.exists(firmware_archive) or os.path.exists(config_archive):raise ValueError('remote trial archive already exists')
    shutil.copyfile(mount+'/probe.bin',archive)
    shutil.copyfile(mount+'/bl31.bin',firmware_archive)
    shutil.copyfile(mount+'/config.txt',config_archive)
    with open(archive,'rb') as f:os.fsync(f.fileno())
    with open(firmware_archive,'rb') as f:os.fsync(f.fileno())
    with open(config_archive,'rb') as f:os.fsync(f.fileno())
    if digest(archive)!=P['baseline']['probe.bin'][1]:raise ValueError('remote archive differs')
    if digest(firmware_archive)!=P['baseline']['bl31.bin'][1]:raise ValueError('remote firmware archive differs')
    if digest(config_archive)!=P['baseline']['config.txt'][1]:raise ValueError('remote config archive differs')
    staged=mount+'/.probe.usb-xhci.tmp';staged_firmware=mount+'/.bl31.usb-xhci.tmp';staged_config=mount+'/.config.usb-xhci.tmp'
    shutil.copyfile(candidate,staged)
    shutil.copyfile(firmware,staged_firmware)
    shutil.copyfile(config,staged_config)
    with open(staged,'rb') as f:os.fsync(f.fileno())
    with open(staged_firmware,'rb') as f:os.fsync(f.fileno())
    with open(staged_config,'rb') as f:os.fsync(f.fileno())
    if digest(staged)!=P['candidate_sha256']:raise ValueError('staged temp differs')
    if digest(staged_firmware)!=P['firmware_sha256']:raise ValueError('staged firmware temp differs')
    if digest(staged_config)!=P['config_sha256']:raise ValueError('staged config temp differs')
    os.replace(staged_config,mount+'/config.txt')
    os.replace(staged_firmware,mount+'/bl31.bin')
    os.replace(staged,mount+'/probe.bin')
    fd=os.open(mount,os.O_RDONLY);os.fsync(fd);os.close(fd)
    if digest(mount+'/probe.bin')!=P['candidate_sha256']:raise ValueError('installed image differs')
    if digest(mount+'/bl31.bin')!=P['firmware_sha256']:raise ValueError('installed trial firmware differs')
    if digest(mount+'/config.txt')!=P['config_sha256']:raise ValueError('installed trial config differs')
finally:
    run(['umount',mount],check=False);pathlib.Path(mount).rmdir()
run(['sync'])
with open('/dev/mmcblk0','rb',buffering=0) as f:after_mbr=hashlib.sha256(f.read(512)).hexdigest()
if after_mbr!=backups[0]['sha256']:raise ValueError('MBR changed')
if digest('/dev/mmcblk0p2')!=backups[2]['sha256']:raise ValueError('HFS changed')
verify=tempfile.mkdtemp(prefix='xnu-usb-verify.',dir='/tmp')
try:
    run(['mount','-o','ro','/dev/mmcblk0p1',verify])
    installed=digest(verify+'/probe.bin');installed_firmware=digest(verify+'/bl31.bin');installed_config=digest(verify+'/config.txt')
    archived=digest(run_dir+'/probe.before.bin');archived_firmware=digest(run_dir+'/bl31.before.bin');archived_config=digest(run_dir+'/config.before.txt')
finally:
    run(['umount',verify],check=False);pathlib.Path(verify).rmdir()
if (installed!=P['candidate_sha256'] or installed_firmware!=P['firmware_sha256'] or installed_config!=P['config_sha256'] or
    archived!=P['baseline']['probe.bin'][1] or archived_firmware!=P['baseline']['bl31.bin'][1] or archived_config!=P['baseline']['config.txt'][1]):
    raise ValueError('readback verification differs')
result={'status':'complete','profile':P['profile'],'linux_boot_id':P['linux_boot_id'],
 'remote_run':run_dir,'backups':backups,'archive_path':run_dir+'/probe.before.bin',
 'archive_sha256':archived,'firmware_archive_sha256':archived_firmware,'config_archive_sha256':archived_config,
 'installed_sha256':installed,'installed_firmware_sha256':installed_firmware,'installed_config_sha256':installed_config,
 'candidate_bytes':P['candidate_bytes'],'trial_config_installed':True,'trial_firmware_installed':True,
 'hfs_unchanged':True,'mbr_unchanged':True,
 'no_reboot':True,'normal_return_not_yet_observed':True}
print(json.dumps(result,sort_keys=True))
'''


def plan(package, boot_id):
    package = package.resolve()
    report = package_check.check(package)
    manifest_path = package / "manifest.json"
    if not report.get("accepted") or sha(manifest_path) != MANIFEST_SHA:
        raise ValueError("exact offline-qualified USB capability candidate required")
    if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", boot_id):
        raise ValueError("exact Linux boot UUID required")
    manifest = json.loads(manifest_path.read_text())
    return {
        "profile": STAGE_PROFILE, "linux_boot_id": boot_id,
        "package": str(package), "manifest_sha256": MANIFEST_SHA,
        "candidate": manifest["image"], "candidate_sha256": manifest["image_sha256"],
        "candidate_bytes": Path(manifest["image"]).stat().st_size,
        "firmware": manifest["firmware"], "firmware_sha256": manifest["firmware_sha256"],
        "firmware_bytes": Path(manifest["firmware"]).stat().st_size,
        "config": str(TRIAL_CONFIG), "config_sha256": TRIAL_CONFIG_SHA,
        "config_bytes": TRIAL_CONFIG.stat().st_size,
        "baseline": {name: list(row) for name, row in BASELINE.items()},
        "archive_name": "probe.before.bin",
        "boot_identity": {"label": "XNU_PROBE", "uuid": "4FA7-3725",
                          "partuuid": "5ae1f07e-01"},
        "replace_only": ["probe.bin", "bl31.bin", "config.txt"],
        "normal_config_preserved": True, "normal_firmware_preserved": True,
        "no_hfs_change": True, "no_reboot": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--linux-boot-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "build/rpi5"):
        raise ValueError("new build/rpi5 evidence directory required")
    value = plan(args.package, args.linux_boot_id)
    output.mkdir(exist_ok=False)
    (output / "plan.json").write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    if not args.execute:
        print("LOCAL_PLAN_ONLY_NO_DEVICE_WRITE " + str(output))
        return 0
    if plan(args.package, args.linux_boot_id) != value:
        raise ValueError("staging inputs changed before execution")
    prepared = subprocess.run(SSH + ["python3", "-"], input=(
        "import tempfile\n"
        "print(tempfile.mkdtemp(prefix='xnu-usb-xhci-',dir='/home/sandrzej'))\n"),
        capture_output=True, text=True, check=True, timeout=30)
    remote_run = prepared.stdout.strip()
    if not re.fullmatch(r"/home/sandrzej/xnu-usb-xhci-[a-z0-9_]+", remote_run):
        raise ValueError("unexpected remote run directory")
    value["remote_run"] = remote_run
    (output / "plan.json").write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    subprocess.run(["scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=8", value["candidate"], HOST + ":" + remote_run + "/candidate.bin"],
        check=True, timeout=600)
    subprocess.run(["scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=8", value["firmware"], HOST + ":" + remote_run + "/candidate-bl31.bin"],
        check=True, timeout=120)
    subprocess.run(["scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=8", value["config"], HOST + ":" + remote_run + "/candidate-config.txt"],
        check=True, timeout=120)
    source = REMOTE.replace("__PLAN__", repr(json.dumps(value)))
    (output / "remote-source.sha256").write_text(hashlib.sha256(source.encode()).hexdigest() + "\n")
    response = subprocess.run(SSH + ["sudo", "-n", "python3", "-"], input=source,
        capture_output=True, text=True, timeout=600)
    (output / "remote.stdout").write_text(response.stdout)
    (output / "remote.stderr").write_text(response.stderr)
    response.check_returncode()
    result = json.loads(response.stdout)
    if (result.get("status") != "complete" or result.get("installed_sha256") != value["candidate_sha256"] or
            result.get("archive_sha256") != BASELINE["probe.bin"][1] or
            result.get("firmware_archive_sha256") != BASELINE["bl31.bin"][1] or
            result.get("config_archive_sha256") != BASELINE["config.txt"][1] or
            result.get("installed_firmware_sha256") != TRIAL_FIRMWARE_SHA or
            result.get("installed_config_sha256") != TRIAL_CONFIG_SHA or
            not all(result.get(key) is True for key in
                    ("trial_config_installed", "trial_firmware_installed", "hfs_unchanged", "mbr_unchanged", "no_reboot"))):
        raise ValueError("remote staging receipt differs")
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "complete", "output": str(output),
                      "installed_sha256": result["installed_sha256"],
                      "remote_run": remote_run}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
