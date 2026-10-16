#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct 42-node pthread payload using the frozen retained-FDT loader build.

Only the root selection, unique tag and derived package names change. The
four-CPU entry, exact kernel, normal firmware and 180-second deadline do not.
The original builder/checker remain byte-identical and explicitly pinned.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
FROZEN = {
    'build_root96_batch_package.py': 'bc7e7b81d9f96c8f619ee00ab275366fdf24021520d17ae33ae768bf7adcec0e',
    'check_root96_batch_package.py': '5dc056e158021771c930747bd9e7a7b3821802046457e450f36cb535a4b71472',
}


def derived_source(name, replacements):
    path = ROOT / 'tools/rpi5' / name
    source = path.read_text()
    if hashlib.sha256(source.encode()).hexdigest() != FROZEN[name]:
        raise ValueError('Frozen retained-FDT source changed: ' + name)
    for before, after, count in replacements:
        if source.count(before) != count:
            raise ValueError('Exact retained-FDT adaptation boundary changed: ' + before)
        source = source.replace(before, after)
    return source


_source = derived_source('build_root96_batch_package.py', (
    ('check_root96_command_package as root_check', 'check_root42_pthread_root as root_check', 2),
    ("PROFILE='root96-ready41-retained-fdt-v1'", "PROFILE='root42-pthread-ready-retained-fdt-v1'", 1),
    ('check_root96_batch_package.py', 'check_root42_pthread_package.py', 1),
    ('tests/test_root96_batch_package.py', 'tests/test_root42_pthread_package.py', 1),
    ('ROOT96_BATCH_TRIAL TAG=', 'ROOT42_PTHREAD_TRIAL TAG=', 1),
    ('CPUS=4 ROOT_NODES=41 WATCHDOG_READY_V2', 'CPUS=4 ROOT_NODES=42 WATCHDOG_READY_V2', 1),
    ('RAMROOT:MOUNT NODES=41 BYTES=', 'RAMROOT:MOUNT NODES=42 BYTES=', 1),
    ("prefix='root96-batch-'", "prefix='root42-pthread-'", 1),
))
_module = types.ModuleType('tools.rpi5._root42_retained_loader')
_module.__file__ = str(Path(__file__).resolve())
_module.__package__ = 'tools.rpi5'
exec(compile(_source, _module.__file__, 'exec'), _module.__dict__)
_original_inputs = _module.inputs


def inputs():
    pins, old, root, kernel = _original_inputs()
    for name, digest in FROZEN.items():
        _module.merge(pins, {str(ROOT / 'tools/rpi5' / name): digest})
    _module.base.verify(pins)
    if (root.get('root_nodes'), root.get('root_files')) != (42, 30):
        raise ValueError('Exact reviewed pthread root geometry required')
    return pins, old, root, kernel


_module.inputs = inputs
for _name, _value in vars(_module).items():
    if not _name.startswith('_'):
        globals()[_name] = _value


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    directory, report = build()
    print(json.dumps({k: report[k] for k in
        ('image', 'image_sha256', 'image_bytes', 'trial_marker', 'geometry')}, indent=2))
