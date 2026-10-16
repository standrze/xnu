#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Sealed 42-node pthread recorder; original bounded serial engine, no rebuild."""
import argparse
import json
from pathlib import Path
import sys
import types
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_root42_pthread_trial as staging
import stage_pcie_trial_v3 as helpers
import serial_root41_trial as original
import root42_pthread_trial_core as core
import root_capacity_profile as root_profile

t, lease = core.t, original.lease


def clean_return(raw):
    if any(v in raw for v in (*t.FORBIDDEN, b'Debugger message: panic', b'panic(', b'panic:')):
        raise ValueError('Post-command runtime fault; recovery is not clean trial acceptance')
    return core.returned(raw)


checked_core = types.SimpleNamespace(**{**vars(core), 'returned': clean_return})


def bound_sources(context):
    current = staging.source_pins() | {str(Path(m.__file__).resolve()): staging.sha(m.__file__) for m in
        (sys.modules[__name__], original, core, root_profile)}
    if any(context['evidence'].get(n) != h for n, h in current.items()):
        raise ValueError('Recorder/source bytes absent from original root42 seal')
    return {n: context['evidence'][n] for n in current}


def revalidate(context):
    staging.seals.check_pins(context['evidence'])
    bound_sources(context)


def package_pins(context):
    report = context['installed']['preflight']
    manifest = Path(report['image']).parent/'manifest.json'
    record = json.loads(manifest.read_text())
    pins = {str(manifest): staging.sha(manifest)}
    for key in ('inputs_sha256', 'headers_sha256', 'generated_sha256'):
        for name, pin in record[key].items():
            if name in pins and pins[name] != pin:
                raise ValueError('Conflicting package input pins')
            pins[name] = pin
    if any(context['evidence'].get(n) != h for n, h in pins.items()):
        raise ValueError('Complete root42 package must belong to sealed evidence')
    return pins


def armed_line(report):
    return 'ROOT42_PTHREAD_CAPTURE_ARMED ZERO_TX_UNTIL_EXACT_FRESH_BOOT WATCHDOG_180_SECONDS IMAGE_SHA=' + report['image_sha256']


def bindings(context):
    installed = context['installed']; report = installed['preflight']
    expected_package = Path(report['image']).parent.resolve()
    checked_package_pins = package_pins(context)
    def validate_package(path):
        if Path(path).resolve() != expected_package:
            raise ValueError('Exact once-audited sealed package required')
        revalidate(context)
        return report
    def installation(path, candidate):
        if str(staging.local(path)) != installed['directory'] or candidate != report:
            raise ValueError('Exact installed root42 candidate required')
        revalidate(context)
        return installed
    def receipts(path):
        installation(path, report)
        return context['evidence']
    def packages(path):
        validate_package(path)
        return checked_package_pins
    # No checker subprocess is run here: the package was audited before the
    # installer sealed it; current exact bytes are still checked before TX.
    scope = dict(original.__dict__, staging=staging, core=checked_core, t=t,
        package=types.SimpleNamespace(inspect=validate_package), root_profile=root_profile,
        installation=installation, receipt_evidence_pins=receipts,
        package_evidence_pins=packages, source_pins=lambda: bound_sources(context),
        armed_line=armed_line, __file__=__file__, __doc__=__doc__)
    scope['trial'] = helpers.private(original.trial, **scope)
    return helpers.private(original.main, **scope)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('device'); p.add_argument('output', type=Path)
    p.add_argument('--installation', type=Path, required=True)
    p.add_argument('--seal-sha256', required=True); p.add_argument('--plan-sha256', required=True)
    p.add_argument('--boot-wait-seconds', type=int, default=600)
    a = p.parse_args(argv)
    context = staging.load_installation(a.installation, a.seal_sha256, a.plan_sha256)
    package = str(Path(context['installed']['preflight']['image']).parent)
    return bindings(context)([a.device, str(a.output), '--installation', str(a.installation),
        '--package', package, '--boot-wait-seconds', str(a.boot_wait_seconds)])


if __name__ == '__main__':
    raise SystemExit(main())
