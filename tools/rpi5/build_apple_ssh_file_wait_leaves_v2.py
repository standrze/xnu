#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Close the original pselect ENOSYS fallback's real pthread_sigmask syscall."""
import hashlib
from pathlib import Path

SOURCE=Path(__file__).with_name('build_apple_ssh_file_wait_leaves.py')
EXPECTED='5a6632fc2b382edb724713e8dad014be0e7407eacd83967698316b27b50b1f1b'


def implementation():
    raw=SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXPECTED:raise ValueError('Frozen file/wait precursor changed')
    source=raw.decode()
    changes={
        "for name in ('pselect','select'):":"for name in ('pselect','select','pthread_sigmask'):",
        "profile='apple-ssh-file-wait-hooks-byte-tail-v1'":"profile='apple-ssh-file-wait-hooks-byte-tail-v2'",
        "for p in [Path(__file__).resolve(),HARNESS,*sources]:":"for p in [Path(__file__).resolve(),_original_builder,HARNESS,*sources]:",
    }
    for old,new in changes.items():
        if source.count(old)!=1:raise ValueError('Exact file/wait derivation changed')
        source=source.replace(old,new)
    scope=dict(__file__=str(Path(__file__).resolve()),__name__=__name__+'.private',_original_builder=SOURCE)
    exec(compile(source,str(SOURCE),'exec'),scope)
    return scope


if __name__=='__main__':implementation()['build']()
