#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct retained-FDT loader for the state-confirmed 42-node root.

Only the checked kernel payload and fresh loader tag change. The failed
pthread package, complete root, four-CPU entry and recovery deadline survive.
"""
import argparse
import json
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rpi5 import build_root42_pthread_package as preceding

PRECEDING_SHA = '3db7ec22f22369590776a6c00a01246971482a6e6935369fc9de5ab4db5ef5da'
if preceding.sha(Path(preceding.__file__)) != PRECEDING_SHA:
    raise ValueError('Frozen root42 builder changed')

KERNEL_DIGEST = 'a1c5bc529cbbd25a40adc25a4a8da2c6a4545f366e767929ac00b5ef73c8fc56'
KERNEL_MANIFEST_DIGEST = 'a51d2a68adb182b2980c67da3288f562d90727ef2a677fb8aa27890a6aca4539'
source = preceding._source
for before, after in (
    ("PROFILE='root42-pthread-ready-retained-fdt-v1'", "PROFILE='root42-mounted-ready-retained-fdt-v1'"),
    ('build/rpi5/root96-ready-delay-kernel-20261013-final', 'build/rpi5/root42-confirmed-kernel-20261013-final'),
    ("KERNEL_DIR/'kernel.ready'", "KERNEL_DIR/'kernel.root-confirmed'"),
    (preceding.KERNEL_SHA, KERNEL_DIGEST),
    (preceding.KERNEL_MANIFEST_SHA, KERNEL_MANIFEST_DIGEST),
    ("WATCHDOG_PROFILE='root96-terminal-ready-delay-kernel-v2'", "WATCHDOG_PROFILE='root42-state-confirmed-watchdog-kernel-v1'"),
    ("KERNEL_DIR/'kernel.ready.filelist'", "KERNEL_DIR/'kernel.root-confirmed.filelist'"),
    ("km['terminal_deadline_seconds']", "km['watchdog_deadline_seconds']"),
    ("km['first_notice_minimum_post_enable_seconds']", "km['root_ready_first_minimum_post_enable_seconds']"),
    ("km['boot_caller_added'] or km['controller_initialized']", "km['deadline_extended'] or not km['actual_validated_mount_state_required']"),
    ('check_root42_pthread_package.py', 'check_root42_ready_package.py'),
    ('tests/test_root42_pthread_package.py', 'tests/test_root42_ready_package.py'),
    ('ROOT42_PTHREAD_TRIAL TAG=', 'ROOT42_READY_TRIAL TAG='),
    ("prefix='root42-pthread-'", "prefix='root42-ready-'"),
):
    if source.count(before) != 1:
        raise ValueError('Exact mounted-root loader adaptation boundary changed: ' + before)
    source = source.replace(before, after)

_module = types.ModuleType('tools.rpi5._root42_state_confirmed_loader')
_module.__file__ = str(Path(__file__).resolve())
_module.__package__ = 'tools.rpi5'
exec(compile(source, _module.__file__, 'exec'), _module.__dict__)
_original_inputs = _module.inputs
_original_build = _module.build


def root_ready_contract():
    extent = (preceding.ROOT_DIR / 'ramdisk.bin').stat().st_size
    return dict(root_ready_marker=f'RPI5XNU:TERMINAL:ROOT_READY SECONDS=180 NODES=42 BYTES={extent} READONLY',
        root_ready_max_reports=3, root_ready_requires_mounted_readonly=True,
        root_ready_requires_successful_reload=True)


def inputs():
    pins, old, root, kernel = _original_inputs()
    for name, digest in preceding.FROZEN.items():
        _module.merge(pins, {str(ROOT / 'tools/rpi5' / name): digest})
    _module.merge(pins, {str(Path(preceding.__file__).resolve()): PRECEDING_SHA})
    if (root['root_nodes'], root['root_files']) != (42, 30):
        raise ValueError('Exact unchanged pthread root required')
    if (kernel['root_ready_max_reports'] != 3 or kernel['watchdog_hardware_timeout_seconds'] != 15 or
        any(kernel[k] is not True for k in ('root_ready_successful_reload_only',
            'actual_validated_mount_state_required', 'root_teardown_revokes_before_free',
            'readers_take_no_vfs_locks', 'original_mount_and_watchdog_ready_markers_retained')) or
        kernel['arbitrary_console_serialization'] is not False or
        sorted(Path(p).name for p in kernel['replaced_objects'].values()) != ['mockfs_vfsops.o', 'pe_fiq.o']):
        raise ValueError('Exact two-object state publication and recovery bounds required')
    raw = _module.KERNEL.read_bytes()
    for marker in (b'RPI5XNU:TERMINAL:ROOT_READY SECONDS=%u NODES=%u BYTES=%llu READONLY\n',
                   b'RPI5XNU:TERMINAL:WATCHDOG_READY SECONDS=%u\n'):
        if raw.count(marker) != 1:
            raise ValueError('Exact linked root/watchdog confirmation format required')
    _module.base.verify(pins)
    return pins, old, root, kernel


_module.inputs = inputs
for _name, _value in vars(_module).items():
    if not _name.startswith('_'):
        globals()[_name] = _value


def build():
    directory, report = _original_build()
    report.update(root_ready_contract())
    (directory / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return directory, report


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    directory, report = build()
    print(json.dumps({k: report[k] for k in ('image', 'image_sha256', 'image_bytes', 'trial_marker', 'geometry')}, indent=2))
