#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Add release comparison and exact native caller headers to the first audit."""
import hashlib
from pathlib import Path

SOURCE = Path(__file__).with_name('build_kernel_entropy_word_api.py')
EXPECTED = 'ba17b0883beed00a0663bc0a502501d5ac99373de57d022e1c69a0fef0c1cb24'


def implementation():
    raw = SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED:
        raise ValueError('Frozen initial API builder changed')
    text = raw.decode()
    replacements = (
        ('import tempfile\n', 'import tempfile\nimport tarfile\n'),
        ("    for path in (Path(__file__).resolve(), WORD, HOST):", """    release = LIBRESSL.parent / 'libressl-4.3.3.tar.gz'
    digest = 'ff97c432457f349e6ba3d416ab903bc7468f1436f0f32efe5fff808de292c7b8'
    if sha(release) != digest:
        raise ValueError('Accepted original LibreSSL archive changed')
    with tarfile.open(release, 'r:gz') as original:
        if original.extractfile('libressl-4.3.3/crypto/compat/arc4random_uniform.c').read() != UNIFORM.read_bytes():
            raise ValueError('Original rejection sampler changed')
    pins[str(release)] = digest
    for path in (Path(__file__).resolve(), SOURCE_BUILDER, WORD, HOST):"""),
        ("    run(native + [HOST, *hosts, '-o', native_target], 'native-link')",
         "    caller = compile_(native, HOST, 'native-caller')\n"
         "    run(native + [caller, *hosts, '-o', native_target], 'native-link')"),
        ("profile='project-kernel-random-word-original-libressl-uniform-v1'",
         "profile='project-kernel-random-word-original-libressl-uniform-v2'"),
    )
    for old, new in replacements:
        if text.count(old) != 1:
            raise ValueError('Exact initial audit site changed')
        text = text.replace(old, new)
    scope = dict(__name__=__name__ + '.private', __file__=str(Path(__file__).resolve()),
        SOURCE_BUILDER=SOURCE.resolve())
    exec(compile(text, str(SOURCE), 'exec'), scope)
    return scope


if __name__ == '__main__':
    implementation()['build']()
