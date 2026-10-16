#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact new kernel/tag, unchanged root, and actual loader/FDT audit."""
import argparse
import json
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rpi5 import build_root42_ready_package as builder

source = builder.preceding.derived_source('check_root96_batch_package.py', (
    ('build_root96_batch_package as builder', 'build_root42_ready_package as builder', 2),
    ("package.name.startswith('root96-batch-')", "package.name.startswith('root42-ready-')", 1),
    ('Distinct root96-batch package required', 'Distinct root42-ready package required', 1),
    ('root_nodes=41,root_files=29', 'root_nodes=42,root_files=30', 1),
))
_module = types.ModuleType('tools.rpi5._root42_state_confirmed_loader_check')
_module.__file__ = str(Path(__file__).resolve())
_module.__package__ = 'tools.rpi5'
exec(compile(source, _module.__file__, 'exec'), _module.__dict__)


def inspect_record(package, record):
    expected = builder.root_ready_contract()
    if any(record.get(k) != v or type(record.get(k)) is not type(v) for k, v in expected.items()):
        raise ValueError('Exact mounted-root readiness contract required')
    result = _module.inspect_record(package, record)
    result.update(expected)
    return result


def inspect(package):
    package = package.resolve()
    return inspect_record(package, json.loads((package / 'manifest.json').read_text()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    print(json.dumps(inspect(parser.parse_args().package), indent=2, sort_keys=True))
