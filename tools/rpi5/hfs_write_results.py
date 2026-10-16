# SPDX-License-Identifier: BSD-2-Clause
"""Exact future persistence vectors and read-only file checks.

The caller must independently prove the mounted device, card/partition,
read-only mount and intervening reboot. This helper proves only file bytes;
it never mounts, formats, opens a raw device or claims durability on its own.
"""
import hashlib
import os
from pathlib import Path
import stat

VECTORS=(('xnu-gate4-small.bin',32,1),('xnu-gate4-empty.bin',0,2),
         ('xnu-gate4-cross-page.bin',33034,3),('xnu-gate4-overwrite.bin',257,6),
         ('xnu-gate4-extend.bin',4633,5))


def payload(length,seed):
    return bytes(((offset*73+19+seed)^(offset>>8))&255 for offset in range(length))


def expected_entries():
    return [dict(path='/'+name,bytes=length,sha256=hashlib.sha256(payload(length,seed)).hexdigest())
            for name,length,seed in VECTORS]


def verify_files(root):
    root=Path(root)
    directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        before=os.fstat(directory)
        records=[]
        for expected in expected_entries():
            fd=os.open(expected['path'][1:],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
            try:
                info=os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_dev!=before.st_dev
                        or info.st_size!=expected['bytes']):
                    raise ValueError('Unexpected persistence file type/length: '+expected['path'])
                data=os.read(fd,expected['bytes']+1)
                after=os.fstat(fd)
                if (len(data)!=expected['bytes'] or os.read(fd,1)
                        or any(getattr(info,key)!=getattr(after,key) for key in
                               ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns'))
                        or hashlib.sha256(data).hexdigest()!=expected['sha256']):
                    raise ValueError('Persistence file changed or differs: '+expected['path'])
                records.append(dict(expected))
            finally:
                os.close(fd)
        after=os.fstat(directory)
        if any(getattr(before,key)!=getattr(after,key) for key in ('st_dev','st_ino','st_mtime_ns','st_ctime_ns')):
            raise ValueError('Persistence mount directory changed during readback')
        return records
    finally:
        os.close(directory)
