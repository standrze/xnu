#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preserve v1's failed audit and compile with original non-Werror policy.

Original configure.ac makes -Werror opt-in for program code. All warnings are
still recorded. Explicit original SDK limits.h inclusion compensates for Clang
freestanding limits.h omitting include_next; no API/feature macro is changed.
"""
import hashlib
from pathlib import Path

SOURCE = Path(__file__).with_name('audit_apple_ssh_full_client.py')
EXPECTED = '13537a0f3d5ec19d283635ebb27f87de6ccb239716ff8dc0ecf40ec35ddf386e'


def implementation():
    raw = SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED:
        raise ValueError('Frozen failed full-client audit changed')
    text = raw.decode()
    old = "flags += ['-I', str(LIBINFO)]"
    new = """flags += ['-I', str(LIBINFO)]
    flags.remove('-Werror')
    sdk = Path(flags[flags.index('-isysroot') + 1])
    flags += ['-include', str(sdk / 'usr/include/limits.h')]
    pins[str(SOURCE_BUILDER)] = sha(SOURCE_BUILDER)"""
    if text.count(old) != 1:
        raise ValueError('Exact compile policy site changed')
    text = text.replace(old, new)
    text = text.replace("profile='original-apple-openssh-full-client-static-closure-v1',",
        "profile='original-apple-openssh-full-client-static-closure-v2',\n"
        "        warnings_recorded_not_promoted=True, sdk_limits_included_explicitly=True,")
    scope = dict(__name__=__name__ + '.private', __file__=str(Path(__file__).resolve()),
                 SOURCE_BUILDER=SOURCE.resolve())
    exec(compile(text, str(SOURCE), 'exec'), scope)
    return scope


if __name__ == '__main__':
    implementation()['build']()
