#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Also replace the old runetype owner reached by forced current ctype."""
import json
from pathlib import Path
import types
from tools.rpi5 import link_apple_ssh_current_locale as old


def build():
    module=types.ModuleType('current_locale_explicit_eight_owners')
    module.__file__=__file__
    source=Path(old.__file__).read_text()
    needle="('table','tolower','toupper','none','nomacros','lconv','localeconv'))"
    if source.count(needle)!=1:raise ValueError('Old exact member contract changed')
    source=source.replace(needle,"('table','tolower','toupper','none','nomacros','lconv','localeconv','runetype'))")
    exec(compile(source,old.__file__,'exec'),module.__dict__)
    pins={str(Path(p).resolve()):old.sha(p) for p in (__file__,old.__file__)}
    out,report=module.build()
    for name,digest in pins.items():
        if old.sha(name)!=digest:raise ValueError('Owner selection source changed')
    report['source_inputs_sha256'].update(pins)
    report['profile']='original-apple-current-locale-explicit-runtime-owners-v2'
    report['forced_owner_collision_evidence']='apple-ssh-current-locale-contract-v9rdldp6/target-link.stderr'
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),manifest_sha256=old.sha(out/'manifest.json')),indent=2))
    return out,report


if __name__=='__main__':build()
