# SPDX-License-Identifier: BSD-2-Clause
"""Exact project-PID1 derivation; no changes to original XNU or children."""
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ORIGINAL=ROOT/'tools/rpi5/user/init.c'
ORIGINAL_SHA='adb7b4c34cf6b905b628be6d04c4a6484c56c48f1a5747b3dbc6f80b220e2384'
BODY=ROOT/'tools/rpi5/user/init_shutdown_policy.inc'
READY='RPI5XNU:INIT:SHUTDOWN_READY SIGTERM_BLOCKED POLLED NO_RESPAWN_AFTER_OBSERVATION'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def derive(raw):
    if hashlib.sha256(raw.encode()).hexdigest()!=ORIGINAL_SHA:
        raise ValueError('Exact accepted project init source required')
    begin=raw.index('static _Noreturn void init_main(void)')
    end=raw.index('_Noreturn void user_start',begin)
    return raw[:begin]+BODY.read_text()+'\n'+raw[end:]
def sources():
    return [Path(__file__).resolve(),ORIGINAL,BODY,ROOT/'tools/rpi5/user/runtime.h',
        ROOT/'tools/rpi5/tests/init_shutdown_host.c',ROOT/'tools/rpi5/tests/test_init_shutdown.py',
        ROOT/'bsd/kern/kern_shutdown.c',ROOT/'bsd/kern/kern_sig.c',ROOT/'bsd/kern/kern_exit.c',
        ROOT/'bsd/kern/kern_fork.c',ROOT/'bsd/kern/syscalls.master',
        ROOT/'bsd/sys/signal.h',ROOT/'bsd/sys/wait.h',ROOT/'bsd/sys/reason.h']
