#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Use Apple's original provider-only fortify policy; consumers stay unchanged.

The preserved SDK-default predecessor exposed real checked-provider recursion.
This is a distinct derivation, not an edit of its source, archive or receipt.
"""
import json
from pathlib import Path
import subprocess
from tools.rpi5 import build_apple_fortify_runtime as original

ROOT,sha=original.ROOT,original.sha
PREVIOUS=ROOT/'build/rpi5/apple-fortify-runtime-5zejwq5n'
PREVIOUS_SHA='907aa5ceded4ab8e343a3df3aa5d511fa7b0f841af5659df8195091d53256b32'
BUILDER_SHA='aeca4d2da46bee83901702e6c8af5967e588f83008c154c4d041c6ea40be3be4'
CONFIG=original.LIBC/'xcodescripts/libc.xcconfig'
CONFIG_SHA='eddf64eace5e2d6c84fd10bdb87bf23eb97bd809cde6212b6f729fbe489f2200'
POLICY='BASE_PREPROCESSOR_MACROS = __LIBC__ __DARWIN_UNIX03=1 __DARWIN_64_BIT_INO_T=1 __DARWIN_NON_CANCELABLE=1 __DARWIN_VERS_1050=1 _FORTIFY_SOURCE=0'


def derivation():
    source=Path(original.__file__).resolve()
    if sha(source)!=BUILDER_SHA or sha(CONFIG)!=CONFIG_SHA or sha(PREVIOUS/'manifest.json')!=PREVIOUS_SHA:
        raise ValueError('Preserved fortify/configuration boundary changed')
    if CONFIG.read_text().splitlines().count(POLICY)!=1:
        raise ValueError('Original Libc provider-only policy changed')
    if subprocess.check_output(['git','-C',str(original.LIBC),'show','HEAD:xcodescripts/libc.xcconfig'])!=CONFIG.read_bytes():
        raise ValueError('Provider policy is not original Apple source')
    prior=json.loads((PREVIOUS/'manifest.json').read_text())
    pins={str(source):BUILDER_SHA,str(CONFIG):CONFIG_SHA,str(PREVIOUS/'manifest.json'):PREVIOUS_SHA}
    for k in ('source_inputs_sha256','headers_sha256','generated_sha256'):
        pins.update(prior[k])
    for n,h in pins.items():
        if sha(n)!=h:raise ValueError('Preserved prototype input changed: '+n)
    body=source.read_text()
    edits={
        'pins={};reports={}':'pins='+repr(pins)+';reports={}',
        "'-std=gnu99','-Wall','-Wextra','-Wno-unused-parameter','-DPR_13085474_CHECK=0',":
            "'-std=gnu99','-Wall','-Wextra','-Wno-unused-parameter','-D_FORTIFY_SOURCE=0','-DPR_13085474_CHECK=0',",
        "profile='pi-current-apple-fortify-prewrite-strcpy-v1'":"profile='pi-current-apple-fortify-provider-policy-prewrite-strcpy-v2'",
        'original_memcpy_overlap_policy_retained=True,':
            'original_memcpy_overlap_policy_retained=True,provider_only_fortify_source=0,consumer_flags_unchanged=True,'
            'preserved_prototype_target_recursion_not_admitted=True,original_provider_policy='+repr(POLICY)+',',
    }
    for old,new in edits.items():
        if body.count(old)!=1:raise ValueError('Frozen builder derivation boundary changed')
        body=body.replace(old,new)
    return body


def build():
    namespace={'__name__':'rpi5_private_provider_policy_fortify','__file__':__file__}
    exec(compile(derivation(),str(Path(original.__file__).resolve()),'exec'),namespace)
    return namespace['build']()


if __name__=='__main__':build()
