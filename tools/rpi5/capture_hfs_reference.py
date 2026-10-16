#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read/hash the exact future HFS SD partition from verified NVMe Linux.

Never partitions, formats, mounts, stages or reboots. The one-partition SD
reference tool remains unchanged. This separate two-partition profile is only
usable after the SD read trial and deliberate fixture staging have succeeded.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

try:
    from .capture_sd_reference import validate_capture as validate_sd_capture
    from .hfs_read_results import FILE_PATHS, validate_entry
    from .prepare_hfs_fixture import IMAGE_BYTES, VOLUME, digest, inspect_image
except ImportError:
    from capture_sd_reference import validate_capture as validate_sd_capture
    from hfs_read_results import FILE_PATHS, validate_entry
    from prepare_hfs_fixture import IMAGE_BYTES, VOLUME, digest, inspect_image

ROOT = Path(__file__).resolve().parents[2]
PARTITION_START = 1050624
PARTITION_SECTORS = IMAGE_BYTES // 512


def validate_fixture(fixture):
    """Recheck the immutable local raw image, not merely a success boolean."""
    image = Path(fixture['image'])
    if (fixture.get('mac_readonly_mount_verified') is not True or
            fixture.get('readonly_fsck_verified') is not True or
            fixture.get('mac_attachment_detached') is not True or
            type(fixture.get('pi_sd_changes')) is not int or fixture['pi_sd_changes'] != 0 or
            fixture.get('image_bytes') != IMAGE_BYTES or
            fixture.get('image_sectors') != PARTITION_SECTORS or fixture.get('volume_name') != VOLUME or
            inspect_image(image) != fixture.get('volume_header') or
            digest(image) != fixture.get('image_sha256')):
        raise ValueError('Missing, changed or unverified standalone HFS fixture')
    entries = fixture.get('files', [])
    if len(entries) != len(FILE_PATHS):
        raise ValueError('Incomplete fixture file coverage')
    for entry in entries:
        validate_entry(entry)
        if entry.get('mode') != (0o555 if entry['path'] == '/bin/echo' else 0o444):
            raise ValueError('Unexpected fixture file permissions')
    if {entry['path'] for entry in entries} != FILE_PATHS:
        raise ValueError('Duplicate or missing fixture file')


def expected_identity(baseline):
    # Do not weaken the existing initial one-partition capture validator.
    validate_sd_capture(baseline)
    original = baseline['identity']
    if original['bytes'] != 128177930240:
        raise ValueError('Not the verified disposable SD capacity')
    return {
        'root': '/dev/nvme0n1p2 ext4 04570742-280b-43cb-9564-73d454243b1c',
        'layout': {'label': 'dos', 'id': '0x5ae1f07e', 'device': '/dev/mmcblk0',
                   'unit': 'sectors', 'sectorsize': 512,
                   'partitions': [dict(node='/dev/mmcblk0p1', start=2048,
                                       size=1048576, type='c', bootable=True),
                                  dict(node='/dev/mmcblk0p2', start=PARTITION_START,
                                       size=PARTITION_SECTORS, type='af')]},
        'boot_partition': dict(TYPE='vfat', LABEL='XNU_PROBE', UUID='4FA7-3725',
                               PARTUUID='5ae1f07e-01'),
        'hfs_partition': dict(TYPE='hfsplus', LABEL=VOLUME, PARTUUID='5ae1f07e-02'),
        'card': {key: original['card'][key] for key in ('cid', 'csd')},
        'bytes': original['bytes'], 'partition_start': PARTITION_START,
        'partition_sectors': PARTITION_SECTORS,
    }


# EXPECTED and IMAGE_SHA256 are inserted as JSON Python literals, never as shell
# code. All device paths and ioctl requests are fixed, and identity is checked
# before open as well as after both complete read passes.
REMOTE = r'''
import fcntl,hashlib,json,os,stat,struct,subprocess
from pathlib import Path
def command(*args):
    return subprocess.check_output(args,text=True,timeout=10).strip()
def identity():
    root=' '.join(command('findmnt','-no','SOURCE,FSTYPE,UUID','/').split())
    layout=json.loads(command('sfdisk','--json','/dev/mmcblk0'))['partitiontable']
    parts={}
    for name,node in (('boot_partition','/dev/mmcblk0p1'),('hfs_partition','/dev/mmcblk0p2')):
        fields=dict(line.split('=',1) for line in command('blkid','-o','export',node).splitlines() if '=' in line)
        parts[name]={key:fields.get(key) for key in EXPECTED[name]}
    base=Path('/sys/block/mmcblk0/device')
    card={key:(base/key).read_text().strip() for key in ('cid','csd')}
    result=dict(root=root,layout=layout,card=card,**parts,
        bytes=int(Path('/sys/block/mmcblk0/size').read_text())*512,
        partition_start=int(Path('/sys/class/block/mmcblk0p2/start').read_text()),
        partition_sectors=int(Path('/sys/class/block/mmcblk0p2/size').read_text()))
    if result!=EXPECTED: raise RuntimeError('Root, exact SD identity or two-partition layout changed')
    mounted=subprocess.run(['findmnt','-rn','-S','/dev/mmcblk0p2'],capture_output=True,text=True,timeout=10)
    if mounted.returncode!=1 or mounted.stdout.strip():
        raise RuntimeError('HFS partition is mounted or mount lookup failed')
    return result
before=identity()
fd=os.open('/dev/mmcblk0p2',os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
passes=[]
try:
    info=os.fstat(fd)
    if not stat.S_ISBLK(info.st_mode) or info.st_rdev!=os.stat('/dev/mmcblk0p2').st_rdev:
        raise RuntimeError('HFS descriptor is not the identified block device')
    size=struct.unpack('=Q',fcntl.ioctl(fd,0x80081272,bytes(8)))[0] # BLKGETSIZE64
    if size!=EXPECTED['partition_sectors']*512:
        raise RuntimeError('HFS partition descriptor capacity differs')
    for attempt in range(2):
        digest=hashlib.sha256()
        for offset in range(0,size,1024*1024):
            length=min(1024*1024,size-offset)
            data=os.pread(fd,length,offset)
            if len(data)!=length: raise RuntimeError('Short HFS partition read')
            digest.update(data)
        actual=digest.hexdigest()
        if actual!=IMAGE_SHA256: raise RuntimeError('Complete HFS partition differs from Mac fixture')
        passes.append(dict(pass_number=attempt+1,bytes=size,sha256=actual))
finally:
    os.close(fd)
after=identity()
if before!=after: raise RuntimeError('Identity changed during complete HFS partition reads')
print(json.dumps(dict(identity=before,partition_reads=passes,sd_write_operations=0,
    scope='Independent complete Linux partition reads; not XNU HFS mount/read or durability evidence')))
'''


def remote_source(identity, image_sha256):
    return ('import json\nEXPECTED=json.loads(' + repr(json.dumps(identity)) + ')\n' +
            'IMAGE_SHA256=' + repr(image_sha256) + '\n' + REMOTE)


def validate_capture(report, baseline, fixture):
    expected = expected_identity(baseline)
    if (report.get('identity') != expected or type(report.get('sd_write_operations')) is not int or
            report['sd_write_operations'] != 0 or
            report.get('partition_reads') != [dict(pass_number=n, bytes=IMAGE_BYTES,
                                                 sha256=fixture['image_sha256']) for n in (1, 2)]):
        raise ValueError('Invalid independent complete HFS partition reference')
    if any(type(row['pass_number']) is not int or type(row['bytes']) is not int
           for row in report['partition_reads']):
        raise ValueError('Non-integer complete partition read coverage')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host')
    parser.add_argument('--fixture', required=True, type=Path)
    parser.add_argument('--sd-baseline-reference', required=True, type=Path)
    args = parser.parse_args()
    if args.host != 'sandrzej@192.168.4.23':
        parser.error('Use the verified Pi host sandrzej@192.168.4.23')
    fixture_raw = args.fixture.read_bytes()
    baseline_raw = args.sd_baseline_reference.read_bytes()
    fixture = json.loads(fixture_raw)
    baseline = json.loads(baseline_raw)
    fixture_sha256 = hashlib.sha256(fixture_raw).hexdigest()
    baseline_sha256 = hashlib.sha256(baseline_raw).hexdigest()
    validate_fixture(fixture)
    expected = expected_identity(baseline)
    source = remote_source(expected, fixture['image_sha256'])
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                             '-o', 'ConnectTimeout=8', args.host, 'sudo -n python3 -'],
                            input=source, text=True, capture_output=True, timeout=180, check=True)
    report = json.loads(result.stdout)
    validate_capture(report, baseline, fixture)
    # Revalidate the local source image after the remote capture too.
    validate_fixture(fixture)
    if digest(args.fixture) != fixture_sha256 or digest(args.sd_baseline_reference) != baseline_sha256:
        raise ValueError('Local reference changed during remote capture')
    report.update(host=args.host, captured_at=datetime.now(timezone.utc).isoformat(),
                  fixture_reference_sha256=fixture_sha256,
                  sd_baseline_reference_sha256=baseline_sha256,
                  capture_source_sha256=digest(Path(__file__)),
                  remote_source_sha256=hashlib.sha256(source.encode()).hexdigest())
    run = Path(tempfile.mkdtemp(prefix='hfs-linux-reference-', dir=ROOT / 'build/rpi5'))
    (run / 'reference.json').write_text(json.dumps(report, indent=2) + '\n')
    print(run)


if __name__ == '__main__':
    main()
