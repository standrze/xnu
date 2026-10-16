#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Separately approved launcher-only fix for the frozen diagnostic ARMED line.

The receiver, installed image, original installation seal and evidence/restore
code are unchanged.  This supplemental source is NOT in that earlier seal.
Only the inherited arm_once recognition literal is derived.  Exact-line,
live-child, timeout, receipt, same-process Linux checks and no-retry behavior
are the original implementation, not a replacement launch algorithm.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arm_pcie_trace_reboot as original_arm
import arm_restart_diagnostic_trial as original_launcher

stage = original_launcher.stage
recorder = original_launcher.recorder
SELF = Path(__file__).resolve()
TEST = SELF.parent/'tests/test_arm_restart_diagnostic_compat_v2.py'
FORMAT = 'rpi5-restart-diagnostic-armed-launcher-supplement-v2'
FROZEN = {
    str(SELF.parent/'arm_pcie_trace_reboot.py'):
        '7a4f7fe864bf11f600ac93d2c3eaa594d0bced05cddb1dd114094219733136f5',
    str(SELF.parent/'arm_display_xnu_reboot.py'):
        '4797df9d6bb41fe6e68e5c36ff34df226efc7b1503096e9471c808aa88735af9',
    str(SELF.parent/'arm_restart_diagnostic_trial.py'):
        'ab67b2fdd6f84da5502762eda5eb9e823b7420e5d702f52f7e58fd528a4e13c4',
    str(SELF.parent/'serial_restart_diagnostic_trial.py'):
        'e8c57a6a673c06c0e664de9d138635eb5c4aa98a912d30554b1a873fadfaf03a',
    str(SELF.parent/'stage_restart_diagnostic_trial.py'):
        '5760b23008dada58e9d0ab153a1dfdbc93e9fbf7cf17c76f74662ad9f02c4b34',
}


def derive_arm_once():
    stage.seals.check_pins(FROZEN)
    source = Path(original_arm.__file__).read_text()
    before = "armed=[line for line in lines if 'CAPTURE_ARMED' in line]"
    after = "armed=[line for line in lines if 'RESTART_DIAGNOSTIC_ARMED' in line]"
    if source.count(before) != 1:
        raise ValueError('Exact original recognition boundary required')
    code = compile(source.replace(before, after), str(SELF), 'exec')
    functions = [c for c in code.co_consts if isinstance(c, types.CodeType) and c.co_name == 'arm_once']
    if len(functions) != 1:
        raise ValueError('One actual original arming implementation required')
    return types.FunctionType(functions[0], vars(original_arm),
        argdefs=original_arm.arm_once.__defaults__)


arm_once = derive_arm_once()


def approved_sources(adapter_sha, tests_sha):
    # Both digests are separately retained by the caller, never self-asserted
    # from a new JSON document.  They are not merged into the old evidence map.
    pins = {str(SELF): adapter_sha, str(TEST): tests_sha}
    stage.seals.check_pins(pins)
    stage.seals.check_pins(FROZEN)
    return pins


def load_context(installation, seal_sha, plan_sha, result_sha, adapter_sha, tests_sha):
    approved_sources(adapter_sha, tests_sha)
    installation = stage.local(installation)
    if stage.sha(installation/'result.json') != result_sha:
        raise ValueError('Separately retained installed result differs')
    context = stage.load_installation(installation, seal_sha, plan_sha)
    if context['installed']['result_sha256'] != result_sha:
        raise ValueError('Installed result changed during validation')
    if any(context['evidence'].get(n) != h for n, h in FROZEN.items()):
        raise ValueError('Original launcher and receiver must be in the installation seal')
    return context


def launch(context, device, capture, output, boot, adapter_sha, tests_sha):
    supplemental = approved_sources(adapter_sha, tests_sha)
    installed = context['installed']
    capture, output = stage.local(capture), stage.local(output)
    if any(context['evidence'].get(n) != h for n, h in FROZEN.items()):
        raise ValueError('Original source membership required')
    record = dict(format=FORMAT, installation=installed,
        installed_receipts_sha256={n: stage.sha(Path(installed['directory'])/n)
            for n in ('checkpoint.json', 'plan.json', 'result.json')},
        supplemental_source_sha256=supplemental, frozen_source_sha256=FROZEN,
        supplemental_was_in_original_installation_seal=False,
        changed_recognition_literal=dict(before='CAPTURE_ARMED', after='RESTART_DIAGNOSTIC_ARMED'),
        receiver_source_unchanged=True, receiver_expected_armed=recorder.armed_line(installed['preflight']),
        capture=str(capture), launch=str(output), device=device, linux_boot_id=boot,
        exact_line_alive_deadline_receipt_linux_guards_unchanged=True,
        installation_and_runtime_evidence_unchanged=True, no_sd_write=True, no_retry=True)
    record_path = output/'launcher-supplement.json'

    def check_record(required=False):
        approved_sources(adapter_sha, tests_sha)
        if any(stage.sha(Path(installed['directory'])/n) != h
                for n, h in record['installed_receipts_sha256'].items()):
            raise ValueError('Exact installed receipts changed')
        if required and (not record_path.is_file() or
                not stage.engine.same(json.loads(record_path.read_text()), record)):
            raise ValueError('Supplemental launch provenance changed')

    def supplemented_arm(out, command, expected, validate_armed, reboot):
        check_record()
        if out != output or expected != record['receiver_expected_armed']:
            raise ValueError('Exact original launch binding required')

        def spawn(*args, **kwargs):
            check_record()
            stage.save(record_path, record)
            # Exact Popen arguments originate in unchanged arm_once.  The
            # supplemental provenance is durable before the child is started.
            return subprocess.Popen(*args, **kwargs)

        def validate(pid):
            check_record(required=True)
            witness = validate_armed(pid)
            check_record(required=True)
            return dict(witness, launcher_supplement_sha256=stage.sha(record_path),
                launcher_supplement=str(record_path))

        def reboot_once():
            check_record(required=True)
            return reboot()

        return arm_once(out, command, expected, validate, reboot_once, popen=spawn)

    # No changes to command construction, exact armed.json validation, SSH
    # boot/root script, receipt checks, output paths or recorder namespace.
    scoped = dict(original_launcher.launch.__globals__, arm_once=supplemented_arm)
    bound = types.FunctionType(original_launcher.launch.__code__, scoped,
        argdefs=original_launcher.launch.__defaults__)
    return bound(context, device, capture, output, boot)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('installation', 'capture', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    for name in ('seal-sha256', 'plan-sha256', 'result-sha256', 'adapter-sha256',
                 'tests-sha256', 'device', 'linux-boot-id'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args(argv)
    context = load_context(args.installation, args.seal_sha256, args.plan_sha256,
        args.result_sha256, args.adapter_sha256, args.tests_sha256)
    value = launch(context, args.device, args.capture, args.output,
        args.linux_boot_id, args.adapter_sha256, args.tests_sha256)
    print(json.dumps(value, sort_keys=True))
    return 0 if value['result']['verification_marker_observed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
