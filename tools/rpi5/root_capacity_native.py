#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Run the existing actual-loader audit using the expanded RAM-root validator."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import root_capacity_profile as profile

SOURCE = Path(__file__).with_name('compare_native_macho.py')
SOURCE_SHA = 'ee7cc87f15f913065ba8cfab1450bb832d6123fa4fd7f1f7a9eb0208dd46f31d'


def compare(kernel, package):
    source = SOURCE.read_bytes()
    if profile.sha(source) != SOURCE_SHA:
        raise ValueError('Preserved native loader validator changed')
    old = '            from prepare_pid1 import inspect as inspect_pid1\n'
    new = '            from root_capacity_profile import inspect as inspect_pid1\n'
    text = source.decode()
    if text.count(old) != 1:
        raise ValueError('Expected exactly one raw-init parser import')
    # Keep the original validator and all native loader C code unchanged on disk.
    # This private instance substitutes only the matching RAM-root parser.
    adapted = text.replace(old, new)
    namespace = dict(__name__='_root_capacity_native', __file__=str(SOURCE.resolve()))
    exec(compile(adapted, str(SOURCE), 'exec'), namespace)
    result = namespace['compare'](kernel, package, True)
    result.update(adapter_sha256=profile.sha(Path(__file__).read_bytes()),
                  original_validator_sha256=SOURCE_SHA,
                  adapted_validator_sha256=profile.sha(adapted.encode()),
                  adaptation='Only raw-init parser import uses the matching 96-node RAM-root profile',
                  original_validator_unchanged=profile.sha(SOURCE.read_bytes()) == SOURCE_SHA,
                  pi_executed=False)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.kernel.resolve(), args.package.resolve())
    with args.report.open('x') as output:
        output.write(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, indent=2, sort_keys=True))
