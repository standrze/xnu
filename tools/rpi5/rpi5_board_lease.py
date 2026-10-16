# SPDX-License-Identifier: BSD-2-Clause
"""Nonblocking local OS lock for this Pi's publication/capture coordinators.

Metadata alone is never a live-owner or process-completion signal. Other tools
must cooperate; the recorder also rejects any existing serial-port opener.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat


@contextmanager
def hold(root,purpose):
    directory=Path(root)/'build/rpi5'
    if directory.resolve()!=directory or not directory.is_dir():raise ValueError('Canonical board-lease directory required')
    fd=os.open(directory/'.rpi5-board.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_dev!=directory.stat().st_dev:
            raise ValueError('Unexpected board-lease file')
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Another live cooperating Pi coordinator holds the board lease') from None
        raw=(json.dumps(dict(pid=os.getpid(),purpose=purpose))+'\n').encode()
        os.ftruncate(fd,0)
        if os.pwrite(fd,raw,0)!=len(raw):raise RuntimeError('Short board-lease metadata write')
        os.fsync(fd)
        yield fd
    finally:os.close(fd)
