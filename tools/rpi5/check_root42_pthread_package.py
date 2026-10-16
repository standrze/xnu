#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Independent complete loader/link/handoff audit for the 42-node pthread root."""
import argparse
import json
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.rpi5 import build_root42_pthread_package as builder

_source = builder.derived_source('check_root96_batch_package.py', (
    ('build_root96_batch_package as builder', 'build_root42_pthread_package as builder', 2),
    ("package.name.startswith('root96-batch-')", "package.name.startswith('root42-pthread-')", 1),
    ('Distinct root96-batch package required', 'Distinct root42-pthread package required', 1),
    ('root_nodes=41,root_files=29', 'root_nodes=42,root_files=30', 1),
))
_module = types.ModuleType('tools.rpi5._root42_retained_loader_check')
_module.__file__ = str(Path(__file__).resolve())
_module.__package__ = 'tools.rpi5'
exec(compile(_source, _module.__file__, 'exec'), _module.__dict__)
inspect_record = _module.inspect_record
inspect = _module.inspect


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    print(json.dumps(inspect(parser.parse_args().package), indent=2, sort_keys=True))
