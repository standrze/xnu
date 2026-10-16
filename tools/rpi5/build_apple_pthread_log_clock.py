#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Close real absolute-clock import with original feature-gated assembly."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / 'tools/rpi5/build_apple_pthread_log_providers.py'


def build():
    raw = PARENT.read_text()
    replacements = {
        "prefix='apple-pthread-log-'": "prefix='apple-pthread-log-clock-'",
        "*generated_sources,": "(ROOT / 'libsyscall/wrappers/mach_absolute_time.s', 'absolute-time', assembly_flags), *generated_sources,",
        "if label == 'log-traps':": "if label in ('log-traps', 'absolute-time'):",
        "commands, headers, units, installations, migrations = [], {}, [], {}, []": """commands, headers, units, installations, migrations = [], {}, [], {}, []
    pins[str(ROOT / 'tools/rpi5/build_apple_pthread_log_providers.py')] = sha(ROOT / 'tools/rpi5/build_apple_pthread_log_providers.py')""",
        "profile='original-apple-pthread-log-provider-inventory-v1'": "profile='original-apple-pthread-log-clock-provider-v2'",
    }
    for old, new in replacements.items():
        if raw.count(old) != 1: raise ValueError('Exact frozen provider derivation changed')
        raw = raw.replace(old, new)
    scope = {'__name__': 'private_log_clock_builder', '__file__': str(Path(__file__).resolve())}
    exec(compile(raw, str(PARENT), 'exec'), scope)
    return scope['build']()


if __name__ == '__main__': build()
