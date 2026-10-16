#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Freeze the Pi profile with a native test that cannot load libnetwork.

The original public getaddrinfo implementation and target bytes are unchanged.
Only the named-host fixture's supplied flags use original AI_PASSIVE. A native
abort-only dlopen boundary rejects any unexpected dynamic service loading.
"""
import json
from pathlib import Path
import tempfile
from tools.rpi5 import build_libinfo_pi_files as original

ROOT,sha=original.ROOT,original.sha
PROTOTYPE=ROOT/'build/rpi5/pi-libinfo-files-8tiqz9yr'
PROTOTYPE_SHA='3bc1570ab30e98fd1a70b6168a2cd6b6346163a6bc32fb0adaf749ce6851ed25'


def build():
    if sha(PROTOTYPE/'manifest.json')!=PROTOTYPE_SHA:raise ValueError('Preserved prototype changed')
    receipt=json.loads((PROTOTYPE/'manifest.json').read_text())
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
        for n,h in receipt[key].items():
            if sha(n)!=h:raise ValueError('Preserved prototype input changed: '+n)
    seed=Path(tempfile.mkdtemp(prefix='pi-libinfo-files-checked-input-',dir=ROOT/'build/rpi5'))
    harness=seed/'checked-host.c'
    text=original.HARNESS.read_text()
    old='hints.ai_flags=0;a=NULL;'
    if text.count(old)!=1:raise ValueError('Host flag boundary changed')
    text=text.replace(old,'hints.ai_flags=AI_PASSIVE;a=NULL;')
    text+='\n/* Native-only negative boundary: no dynamic network service may load. */\nvoid *rpi5_forbidden_dlopen(const char *path, int mode)\n{ (void)path; (void)mode; abort(); }\n'
    harness.write_text(text)
    source=Path(original.__file__).resolve();body=source.read_text()
    changes={
        "HARNESS=ROOT/'tools/rpi5/tests/libinfo_pi_files_host.c'":'HARNESS=Path('+repr(str(harness))+')',
        'base=json.loads((BASE/\'manifest.json\').read_text());pins={str(BASE/\'manifest.json\'):BASE_SHA}':
            'base=json.loads((BASE/\'manifest.json\').read_text());pins={str(BASE/\'manifest.json\'):BASE_SHA}\n    pins[str(Path('+repr(str(source))+'))]='+repr(sha(source))+'\n    pins[str(Path('+repr(str(PROTOTYPE/'manifest.json'))+'))]='+repr(PROTOTYPE_SHA)+'\n    pins[str(Path('+repr(str(original.HARNESS))+'))]='+repr(sha(original.HARNESS)),
        "'-Dgeteuid=rpi5_fixture_geteuid']":"'-Dgeteuid=rpi5_fixture_geteuid','-Ddlopen=rpi5_forbidden_dlopen']",
        'profile=profile.PROFILE':'profile=\'pi-libinfo600-static-files-stat-validation-no-native-dlopen-v2\'',
        'native_stdout=EXPECTED,native_asan_ubsan_pass=True,':
            'native_stdout=EXPECTED,native_asan_ubsan_pass=True,native_dynamic_loading_forbidden=True,native_named_host_flags="AI_PASSIVE",',
    }
    for old,new in changes.items():
        if body.count(old)!=1:raise ValueError('Frozen builder derivation boundary changed')
        body=body.replace(old,new)
    namespace={'__name__':'rpi5_private_checked_files_builder','__file__':__file__}
    exec(compile(body,str(source),'exec'),namespace)
    return namespace['build']()


if __name__=='__main__':build()
