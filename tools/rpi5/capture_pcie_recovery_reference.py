#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Plan by default; inspect the exact installed socket/zsh boot media read-only."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

try:
    from . import pcie_recovery_reference_core as core
    from . import hfs_persistence_capture_core as original
    from . import stage_socket_identity_trial as installed
except ImportError:
    import pcie_recovery_reference_core as core
    import hfs_persistence_capture_core as original
    import stage_socket_identity_trial as installed

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT / 'build/rpi5/socket-identity-installed-20261012'
HISTORY_SHA = {'plan.json': 'c9c519d8a24659ba2c185ab967c8f5c10c2ab8a8c3580b49874b17f7f8294edf',
               'result.json': '4d189669fa7c4604d7b27f3f97c0081ea98a6ac55be233c0bb4eab2545b80282'}
SOURCES = (Path(__file__), Path(core.__file__), Path(original.__file__), Path(installed.__file__))


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def hashes(): return {str(path.relative_to(ROOT)): sha(path) for path in SOURCES}


def load_plan(boot_id):
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id):
        raise ValueError('Fresh verified SSD Linux boot UUID required')
    if any(sha(HISTORY / name) != digest for name, digest in HISTORY_SHA.items()):
        raise ValueError('Accepted installed socket/zsh history changed')
    plan = json.loads((HISTORY / 'plan.json').read_text())
    result = json.loads((HISTORY / 'result.json').read_text())
    installed.validate_result(result, plan)
    if result['image_sha256'] != installed.NEW_SHA:
        raise ValueError('Not the physically tested socket/zsh baseline')
    binding = copy.deepcopy(plan['identity_binding'])
    binding['linux_boot_id_before_write'] = result['identity']['boot_id']
    binding['linux_boot_id_after_write'] = boot_id
    if boot_id == binding['linux_boot_id_before_write']: raise ValueError('Distinct intervening SSD boot required')
    return dict(host=installed.HOST, identity_binding=binding, history_sha256=HISTORY_SHA,
                protected_extents_sha256={name: result['protected_after'][name]['sha256'] for name in core.EXTENTS},
                protected_files_sha256=result['protected_files_sha256'], source_sha256=hashes(),
                operations=core.OPERATIONS, limitations=core.LIMITATIONS)


def remote_source(plan):
    return ('import json,types\noriginal=types.ModuleType("protected_capture")\nexec(' +
            repr(Path(original.__file__).read_text()) + ',original.__dict__)\n' +
            Path(core.__file__).read_text() + '\nPLAN=json.loads(' + repr(json.dumps(plan)) +
            ')\nprint(json.dumps(capture_recovery(PLAN,original),sort_keys=True))\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--linux-boot-id', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    plan = load_plan(args.linux_boot_id)
    source = remote_source(plan)
    out = args.output_dir.resolve()
    if not (out.parent == ROOT / 'build/rpi5' or out.is_relative_to(Path('/private/tmp')) or
            out.is_relative_to(Path('/private/var/folders'))):
        raise ValueError('Separate fresh evidence/temporary output required')
    out.mkdir(parents=True, exist_ok=False)
    # Archive the exact programs as well as their hashes. Later source work
    # must not make historical raw observations unreproducible.
    snapshots = out / 'source-snapshots'; snapshots.mkdir()
    archived = {}
    for path in SOURCES:
        target = snapshots / path.name
        shutil.copyfile(path, target)
        name = str(path.relative_to(ROOT))
        if sha(target) != plan['source_sha256'][name]: raise ValueError('Source changed during snapshot')
        archived[name] = dict(file=str(target.relative_to(out)), sha256=sha(target))
    (out / 'source-snapshots.json').write_text(json.dumps(archived, indent=2, sort_keys=True) + '\n')
    plan.update(execute=args.execute, remote_program_sha256=hashlib.sha256(source.encode()).hexdigest())
    (out / 'plan.json').write_text(json.dumps(plan, indent=2, sort_keys=True) + '\n')
    if not args.execute:
        print(json.dumps(dict(plan_only=True, output=str(out)))); return 0
    result = dict(passed=False, ssh_attempted=False, remote_outcome='not-started')
    try:
        if hashes() != plan['source_sha256'] or remote_source({k: v for k, v in plan.items()
            if k not in ('execute', 'remote_program_sha256')}) != source:
            raise ValueError('Source changed before SSH')
        result.update(ssh_attempted=True, remote_outcome='unknown')
        response = subprocess.run(['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ConnectTimeout=8', plan['host'], 'sudo -n python3 -'],
            input=source, text=True, capture_output=True, timeout=180)
        (out / 'remote.stdout').write_text(response.stdout); (out / 'remote.stderr').write_text(response.stderr)
        result.update(remote_outcome='exited', remote_exit_code=response.returncode)
        response.check_returncode()
        report = json.loads(response.stdout); core.validate_recovery(report, plan)
        if hashes() != plan['source_sha256']: raise ValueError('Source changed during capture')
        result.update(passed=True, reference_sha256=hashlib.sha256(response.stdout.encode()).hexdigest(),
                      report=report, source_sha256=plan['source_sha256'])
    except subprocess.TimeoutExpired as error:
        for name, value in (('partial.stdout', error.stdout), ('partial.stderr', error.stderr)):
            if value is not None: (out / name).write_bytes(value.encode() if isinstance(value, str) else value)
        result['error'] = str(error); raise
    except Exception as error:
        result['error'] = str(error); raise
    finally:
        (out / 'result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(passed=True, output=str(out),
        configured_one_shot_nvme_return=report['configured_one_shot_nvme_return'],
        requested_watchdog_seconds=report['requested_watchdog_seconds'],
        physical_reset_return_proven=False, config=report['boot_files']['config_profile'])))
    return 0


if __name__ == '__main__': raise SystemExit(main())
