#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Force actual creation/join paths live without claiming a runtime startup."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PARENT=ROOT/'tools/rpi5/build_apple_pthread_dyld_bootstrap.py'


def build():
    raw=PARENT.read_text()
    replacements={
        "prefix='apple-pthread-dyld-bootstrap-'":"prefix='apple-pthread-dyld-threads-'",
        "commands,headers=[],{}":"""commands,headers=[],{}
    pins[str(ROOT/'tools/rpi5/build_apple_pthread_dyld_bootstrap.py')]=sha(ROOT/'tools/rpi5/build_apple_pthread_dyld_bootstrap.py')""",
        "link+=[str(archive)]":"link+=[str(archive),'-u','_pthread_create','-u','_pthread_join']",
        "profile='original-apple-dyld-bootstrap-owner-private-link-v1'":"profile='original-apple-dyld-thread-create-join-closure-v2'",
        "normal_pthread_apis_remain_normal_variant=True,":"normal_pthread_apis_remain_normal_variant=True,original_create_join_forced_live=True,",
    }
    for a,b in replacements.items():
        if raw.count(a)!=1:raise ValueError('Frozen bootstrap builder changed')
        raw=raw.replace(a,b)
    scope={'__name__':'private_dyld_threads_builder','__file__':str(Path(__file__).resolve())}
    exec(compile(raw,str(PARENT),'exec'),scope)
    return scope['build']()


if __name__=='__main__':build()
