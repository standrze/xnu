#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only Linux SD identity/sector reference. Never stage, mount or partition.

This initial profile deliberately requires the preserved one-partition XNU_PROBE
card and NVMe Linux root. Reject any layout change until explicitly reviewed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
REMOTE = r'''
import fcntl,hashlib,json,os,stat,struct,subprocess
from pathlib import Path
def command(*args):
    return subprocess.check_output(args,text=True,timeout=10).strip()
def identity():
    root=command('findmnt','-no','SOURCE,FSTYPE,UUID','/')
    if root.split()!=['/dev/nvme0n1p2','ext4','04570742-280b-43cb-9564-73d454243b1c']:
        raise RuntimeError('Not the verified NVMe Linux root')
    layout=json.loads(command('sfdisk','--json','/dev/mmcblk0'))['partitiontable']
    expected=[dict(node='/dev/mmcblk0p1',start=2048,size=1048576,type='c',bootable=True)]
    if (layout.get('label')!='dos' or layout.get('id')!='0x5ae1f07e' or
        layout.get('device')!='/dev/mmcblk0' or layout.get('unit')!='sectors' or
        layout.get('sectorsize')!=512 or layout.get('partitions')!=expected):
        raise RuntimeError('SD layout differs from preserved disposable card profile')
    part=dict(
        line.split('=',1) for line in command('blkid','-o','export','/dev/mmcblk0p1').splitlines() if '=' in line)
    for key,value in dict(TYPE='vfat',LABEL='XNU_PROBE',UUID='4FA7-3725',PARTUUID='5ae1f07e-01').items():
        if part.get(key)!=value: raise RuntimeError('SD partition identity mismatch: '+key)
    base=Path('/sys/block/mmcblk0/device')
    card={name:(base/name).read_text().strip() for name in ('cid','csd','scr','ocr','name','type','date','manfid','oemid','serial')}
    if card['type']!='SD' or len(card['cid'])!=32 or len(card['csd'])!=32:
        raise RuntimeError('Unsupported card identity')
    size=int(Path('/sys/block/mmcblk0/size').read_text())*512
    return dict(root=root,layout=layout,partition=part,card=card,bytes=size)
before=identity()
fd=os.open('/dev/mmcblk0',os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
try:
    info=os.fstat(fd)
    if not stat.S_ISBLK(info.st_mode) or info.st_rdev!=os.stat('/dev/mmcblk0').st_rdev:
        raise RuntimeError('SD descriptor is not the identified block device')
    size=struct.unpack('=Q',fcntl.ioctl(fd,0x80081272,bytes(8)))[0] # BLKGETSIZE64
    if size!=before['bytes'] or size%512 or size<=1050624*512:
        raise RuntimeError('SD size changed or is outside expected layout')
    # MBR/gap, FAT first/last, first free sector, middle and last whole-card LBA.
    lbas=sorted(set((0,1,2047,2048,1050623,1050624,size//1024,size//512-1)))
    sectors=[]
    for lba in lbas:
        a=os.pread(fd,512,lba*512); b=os.pread(fd,512,lba*512)
        if len(a)!=512 or a!=b: raise RuntimeError('Short or unstable sector '+str(lba))
        sectors.append(dict(lba=lba,bytes=512,sha256=hashlib.sha256(a).hexdigest(),reads=2))
finally:
    os.close(fd)
after=identity()
if before!=after: raise RuntimeError('Card, root or layout changed during read capture')
ios=Path('/sys/kernel/debug/mmc0/ios')
print(json.dumps(dict(identity=before,sectors=sectors,sd_write_operations=0,
    linux_mmc_ios=ios.read_text() if ios.exists() else None,
    scope='Independent Linux reads; not XNU SD I/O, rail measurements or mount evidence')))
'''


def validate_capture(report):
    identity = report['identity']
    layout, part, card = identity['layout'], identity['partition'], identity['card']
    if (report.get('sd_write_operations') != 0 or identity['bytes'] % 512
            or identity['bytes'] <= 1050624 * 512 or card['type'] != 'SD'
            or identity['root'].split() != ['/dev/nvme0n1p2', 'ext4', '04570742-280b-43cb-9564-73d454243b1c']
            or any(part.get(k) != v for k, v in dict(TYPE='vfat', LABEL='XNU_PROBE',
                   UUID='4FA7-3725', PARTUUID='5ae1f07e-01').items())
            or any(layout.get(k) != v for k, v in dict(label='dos', id='0x5ae1f07e',
                   device='/dev/mmcblk0', unit='sectors', sectorsize=512).items())
            or layout.get('partitions') != [dict(node='/dev/mmcblk0p1', start=2048,
                   size=1048576, type='c', bootable=True)]):
        raise ValueError('Invalid read-only card evidence')
    for key in ('cid', 'csd'):
        if len(card[key]) != 32 or any(c not in '0123456789abcdef' for c in card[key]):
            raise ValueError('Invalid card identity')
    csd = bytes.fromhex(card['csd'])
    size = ((csd[7] & 63) << 16) | (csd[8] << 8) | csd[9]
    if csd[0] >> 6 != 1 or csd[5] & 15 != 9 or (size + 1) * 1024 * 512 != identity['bytes']:
        raise ValueError('Card CSD and Linux capacity disagree')
    sectors = identity['bytes'] // 512
    expected = sorted(set((0, 1, 2047, 2048, 1050623, 1050624, sectors // 2, sectors - 1)))
    if [row['lba'] for row in report['sectors']] != expected:
        raise ValueError('Incomplete sector coverage')
    for row in report['sectors']:
        if (row['bytes'] != 512 or row['reads'] != 2 or len(row['sha256']) != 64
                or any(c not in '0123456789abcdef' for c in row['sha256'])):
            raise ValueError('Invalid sector reference')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host')
    args = parser.parse_args()
    if args.host.startswith('-'):
        parser.error('invalid host')
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                             '-o', 'ConnectTimeout=8', args.host, 'sudo -n python3 -'],
                            input=REMOTE, text=True, capture_output=True, timeout=60, check=True)
    report = json.loads(result.stdout)
    validate_capture(report)
    report['host'] = args.host
    report['captured_at'] = datetime.now(timezone.utc).isoformat()
    report['capture_source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    base = ROOT / 'build/rpi5'
    base.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='sd-linux-reference-', dir=base))
    (run / 'reference.json').write_text(json.dumps(report, indent=2) + '\n')
    print(run)


if __name__ == '__main__':
    main()
