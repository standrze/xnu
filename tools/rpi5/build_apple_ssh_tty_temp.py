#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original current Apple temporary-path and terminal-input closure inventory.

Uses the preserved whole-unit audit's compiler/link recording, with an explicit
different source set. No target runs, public FILE replacement or host TTY access.
Native and forced-link qualification are separate from this compile inventory.
"""
import json
from pathlib import Path
import types
from tools.rpi5 import build_apple_ssh_stdio_audit as old

UNITS = ('stdio/FreeBSD/mktemp.c', 'gen/FreeBSD/readpassphrase.c', 'gen/devname.c')


def build():
    original=Path(old.__file__).resolve();text=original.read_text()
    edits={"prefix='apple-ssh-stdio-audit-'":"prefix='apple-ssh-tty-temp-'",
        "out/'UNQUALIFIED-current-stdio.a'":"out/'UNQUALIFIED-apple-tty-temp.a'",
        "profile='original-current-apple-stdio-closure-unqualified-v1'":
        "profile='original-current-apple-tty-temp-closure-unqualified-v1'"}
    for before,after in edits.items():
        if text.count(before)!=1:raise ValueError('Original whole-unit builder differs')
        text=text.replace(before,after)
    module=types.ModuleType('_private_tty_temp_builder');module.__file__=__file__
    exec(compile(text,str(original),'exec'),module.__dict__);module.UNITS=UNITS
    out,report=module.build()
    report['source_inputs_sha256'][str(original)]=old.sha(original)
    report['stdio_sources_or_owners_replaced']=False
    report['native_boundary_tests_passed']=False
    (out/'manifest.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(manifest_sha256=old.sha(out/'manifest.json'),package=str(out))))
    return out,report


if __name__=='__main__':build()
