#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Host-window successor only: immutable image, config, publication and rollback."""
from pathlib import Path
import sys
import types
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import stage_display_xnu_trial as original
from tools.rpi5 import prepare_display_xnu_trial_v2 as graph

for _name, _value in vars(original).items():
    if not _name.startswith('__'):
        globals()[_name] = _value
CONTROLLER = 'display-xnu-config-loader-controller-v2'


def source_pins():
    names = ('stage_display_xnu_trial_v2.py', 'serial_display_xnu_trial_v2.py',
             'display_xnu_evidence_v2.py', 'arm_display_xnu_reboot_v2.py',
             'tests/test_display_xnu_window_v2.py')
    return graph.source_pins() | {str(ROOT/'tools/rpi5'/n): sha(ROOT/'tools/rpi5'/n) for n in names}


def transport():
    import serial_display_xnu_trial_v2
    import display_xnu_evidence_v2
    import arm_display_xnu_reboot_v2
    return display_xnu_evidence_v2


def baseline(directory, seal_sha, plan_sha):
    # Only completed original DISPLAYXNU restoration; no failed capture is
    # promoted to success, and current original config/firmware/loader persist.
    return original.restoration(directory, seal_sha, plan_sha)


def admit(checkpoint):
    import serial_display_xnu_trial_v2 as recorder
    media = checkpoint['payload']['media_plan']
    valid_report(media['preflight'])
    engine.bound_core('0'*32).validate_files(media)
    context = {'installed': {'preflight': media['preflight']}, 'evidence': checkpoint['evidence_sha256']}
    sources = recorder.bound_sources(context)
    package = recorder.package_pins(context)
    if (Path(recorder.capture.__globals__['__file__']).resolve() != ROOT/'tools/rpi5/serial_display_xnu_trial_v2.py'
            or Path(recorder.stage.__file__).resolve() != ROOT/'tools/rpi5/stage_display_xnu_trial_v2.py'
            or recorder.HOST_RETURN_SECONDS != 300):
        raise ValueError('Exact separate 300s host receiver required')
    return dict(actual_report_bound=True, actual_recorder_source_members=len(sources),
                actual_recorder_package_members=len(package), host_sd_to_nvme_seconds=300,
                terminal_service_seconds=180, hardware_countdown_seconds=15,
                tx_seconds=120, tx_command_reserve_seconds=45,
                serial_input_guarded_by_fresh_mirror_root_prompt=True, hardware_executed=False)


def launch(directory, seal_sha, plan_sha, device, capture, output, boot):
    import arm_display_xnu_reboot_v2 as launcher
    return launcher.launch(load_installation(directory, seal_sha, plan_sha), device, capture, output, boot)


_preceding = types.SimpleNamespace(**{**vars(original.preceding), 'package_graph': graph.package_graph})
_scope = dict(vars(original), CONTROLLER=CONTROLLER, source_pins=source_pins, transport=transport,
              baseline=baseline, admit=admit, launch=launch, preceding=_preceding,
              __file__=__file__, __doc__=__doc__)
for _name in ('prepare_install', 'sealed_operation', 'load_installation', 'prepare_restore',
              'restoration', 'dispatch', 'replay', 'main'):
    _fn = getattr(original, _name)
    _scope[_name] = types.FunctionType(_fn.__code__, _scope, argdefs=_fn.__defaults__)
    globals()[_name] = _scope[_name]

if __name__ == '__main__':
    raise SystemExit(main())
