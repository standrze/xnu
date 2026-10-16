#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Fixed root-bridge routing case on the unchanged sealed v3 trial controller.

No publisher, hardware guard, deadline or retry policy is copied or relaxed.
Only one explicitly named checker/protocol adapter and its transport bindings
are added. Prior restoration evidence retains its supplemental replay pins.
"""
import builtins
from pathlib import Path
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_pcie_trial_v3 as prior

ROOT, HOST, SSH, GOOD, engine, seals, lease, sha, save, save_bytes, local, private = (
    getattr(prior, k) for k in ('ROOT', 'HOST', 'SSH', 'GOOD', 'engine', 'seals',
        'lease', 'sha', 'save', 'save_bytes', 'local', 'private'))
ADAPTER = ('tools.rpi5.check_pcie_root_route_package',
           'tools.rpi5.pcie_root_route_serial_core',
           'RPI5XNU:BL33:PCIE_ROOT_ROUTE_TRIAL TAG=', True)
get_descriptor = private(prior.descriptors.get,
    ADAPTERS={'root-bridge-route': ADAPTER})
descriptors = types.SimpleNamespace(get=get_descriptor)


def source_pins():
    names = ('root_route_trial_v1.py', 'serial_root_route_trial_v1.py',
             'root_route_evidence_v1.py', 'tests/test_root_route_trial_v1.py')
    return prior.source_pins() | {str(ROOT/'tools/rpi5'/n): sha(ROOT/'tools/rpi5'/n) for n in names}


def load_descriptor(reference):
    import serial_root_route_trial_v1
    import root_route_evidence_v1
    # These modules load before the once-audit source closure is captured.
    selected = get_descriptor(reference)
    protocol = selected['protocol']
    required = ('inspect', 'inventory', 'return_positions', 'PREFIX', 'BEGIN',
                'TRANSFER', 'ENTRY', 'COMMIT', 'PREPARED', 'PREPARED_PREFIX')
    if any(not hasattr(protocol, name) for name in required):
        raise ValueError('Complete recorder and full evidence replay protocol API required')
    if protocol.PREPARED_PREFIX != protocol.PREFIX + b'PREPARED ':
        raise ValueError('Exact unchanged PCIEID preparation prefix required')
    return selected


sealed_operation = prior.sealed_operation
baseline = prior.baseline
merge_pins = prior.merge_pins
package_graph = prior.package_graph
prepare_install = private(prior.prepare_install,
    load_descriptor=load_descriptor, source_pins=source_pins)
load_installation = private(prior.load_installation,
    load_descriptor=load_descriptor, source_pins=source_pins)
dispatch = private(prior.dispatch, descriptors=descriptors)


def import_(name, *args, **kwargs):
    if name == 'pcie_trial_evidence_v3':
        return builtins.__import__('root_route_evidence_v1', *args, **kwargs)
    if name == 'serial_pcie_trial_v3':
        return builtins.__import__('serial_root_route_trial_v1', *args, **kwargs)
    return builtins.__import__(name, *args, **kwargs)


scoped = dict(vars(builtins), __import__=import_)
prepare_restore = private(prior.prepare_restore,
    load_installation=load_installation, __builtins__=scoped)
launch = private(prior.launch, load_installation=load_installation, __builtins__=scoped)
replay = private(prior.replay, load_installation=load_installation,
    prepare_restore=prepare_restore, __builtins__=scoped)
main = private(prior.main, prepare_install=prepare_install, dispatch=dispatch,
    launch=launch, load_installation=load_installation, prepare_restore=prepare_restore,
    replay=replay, __builtins__=scoped, __doc__=__doc__)


if __name__ == '__main__':
    main()
