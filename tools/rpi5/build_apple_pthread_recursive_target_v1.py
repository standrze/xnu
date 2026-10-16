#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build a default-off target candidate for Apple recursive mutex semantics."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'build/rpi5/apple-pthread-static-complete-gm82fjkz'
BASE_MANIFEST_SHA256 = '4a22b183000378e842d59c643ed1f8a80a520e1e77d62370880a7c095adfc35a'
PRIOR_GATE = ROOT / 'build/rpi5/apple-pthread-filex-gate-gj99o8li'
PRIOR_GATE_SHA256 = '9c0d30fe853dd864e78035293b74880b2fb1a2b63f60cdba551a9f5c1706bca3'
SOURCE = ROOT / 'tools/rpi5/user/pthread_recursive_mutex_target_v1.c'
TEST_SOURCE = ROOT / 'tools/rpi5/tests/test_apple_pthread_recursive_target_v1.py'
PROFILE = 'apple-pthread-recursive-target-candidate-default-off-v1'
HOST_LINE = 'PTHREAD:RECURSIVE PASS DEPTH=3 FOREIGN_EPERM=2 BUSY=2 RELEASED=1\n'
API_OWNERS = {
    '_pthread_mutexattr_settype': 'pthread-pthread_mutex.o',
    '_pthread_mutex_init': 'pthread-pthread_mutex.o',
    '_pthread_mutex_lock': 'pthread-pthread_mutex.o',
    '_pthread_mutex_trylock': 'pthread-pthread_mutex.o',
    '_pthread_mutex_unlock': 'pthread-pthread_mutex.o',
    '_pthread_mutex_destroy': 'pthread-pthread_mutex.o',
    '_pthread_create': 'pthread-private.o',
    '_pthread_join': 'original-cancelable.o',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_frozen_inputs():
    if sha(BASE / 'manifest.json') != BASE_MANIFEST_SHA256:
        raise ValueError('frozen complete pthread target manifest drift')
    if sha(PRIOR_GATE / 'manifest.json') != PRIOR_GATE_SHA256:
        raise ValueError('frozen FILEX prerequisite gate manifest drift')
    base = json.loads((BASE / 'manifest.json').read_text())
    prior = json.loads((PRIOR_GATE / 'manifest.json').read_text())
    if prior.get('gate_open') is not False or prior.get('filex_popen_admission_allowed') is not False:
        raise ValueError('prior FILEX prerequisite gate is not closed')
    if not base.get('target_link_complete') or base.get('pi_executed') is not False:
        raise ValueError('frozen target startup package scope changed')
    pins = {
        str(BASE / 'manifest.json'): BASE_MANIFEST_SHA256,
        str(PRIOR_GATE / 'manifest.json'): PRIOR_GATE_SHA256,
        str(SOURCE): sha(SOURCE),
        str(TEST_SOURCE): sha(TEST_SOURCE),
        str(Path(__file__).resolve()): sha(Path(__file__).resolve()),
    }
    for field in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
        for path, digest in base[field].items():
            if sha(path) != digest:
                raise ValueError(f'frozen complete target closure drift: {path}')
            pins[path] = digest
    return base, prior, pins


def run(command, output, label, commands, cwd=None):
    command = list(map(str, command))
    result = subprocess.run(command, cwd=cwd or ROOT, text=True, capture_output=True, timeout=90)
    stdout = output / f'{label}.stdout'
    stderr = output / f'{label}.stderr'
    stdout.write_text(result.stdout)
    stderr.write_text(result.stderr)
    commands.append(dict(command=command, cwd=str(cwd or ROOT), returncode=result.returncode,
                         stdout=stdout.name, stderr=stderr.name))
    if result.returncode:
        raise ValueError(f'{label} failed: {result.stderr[-6000:]}')
    return result


def dependencies(raw):
    return {str(Path(path).resolve()): sha(Path(path).resolve())
            for path in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}


def owner_map(map_text):
    owners = {int(number): path for number, path in
              re.findall(r'^\[\s*(\d+)\]\s+(.+)$', map_text, re.M)}
    result = {}
    for symbol, expected_member in API_OWNERS.items():
        match = re.search(r'^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+' +
                          re.escape(symbol) + r'$', map_text, re.M)
        if not match:
            raise ValueError(f'live target symbol missing from map: {symbol}')
        path = owners[int(match.group(1))]
        if not path.endswith(f'({expected_member})'):
            raise ValueError(f'wrong target owner for {symbol}: {path}')
        result[symbol] = path
    return result


def source_contract():
    text = SOURCE.read_text()
    ordered = [
        'pthread_mutexattr_settype(&attributes, PTHREAD_MUTEX_RECURSIVE)',
        'pthread_mutex_lock(&recursive_mutex)',
        'pthread_mutex_lock(&recursive_mutex)',
        'pthread_mutex_trylock(&recursive_mutex)',
        'run_worker(probe_owned_mutex, 0)',
        'pthread_mutex_unlock(&recursive_mutex)',
        'run_worker(probe_owned_mutex, 1)',
        'pthread_mutex_unlock(&recursive_mutex)',
        'pthread_mutex_unlock(&recursive_mutex)',
        'run_worker(probe_released_mutex, 2)',
    ]
    positions = []
    start = text.index('int rpi5_pthread_smoke_main(')
    for fragment in ordered:
        position = text.find(fragment, start)
        if position < 0:
            raise ValueError(f'recursive target behavior fragment missing: {fragment}')
        positions.append(position)
        start = position + len(fragment)
    if positions != sorted(positions):
        raise ValueError('recursive target behavior order changed')
    for fragment in ('foreign_unlock[0] != EPERM', 'foreign_unlock[1] != EPERM',
                     'foreign_trylock[0] != EBUSY', 'foreign_trylock[1] != EBUSY',
                     HOST_LINE.strip()):
        if fragment not in text:
            raise ValueError(f'recursive target acceptance fragment missing: {fragment}')
    return dict(source=str(SOURCE), source_sha256=sha(SOURCE), ordered_steps=ordered,
                checks_foreign_owner=True, checks_depth_three=True,
                checks_partial_release_still_busy=True, checks_final_release=True)


def build():
    base, prior, pins = load_frozen_inputs()
    contract = source_contract()
    output = Path(tempfile.mkdtemp(prefix='apple-pthread-recursive-target-v1-',
                                  dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(output), flush=True)
    commands = []

    compile_template = next(list(entry['command']) for entry in base['commands']
                            if entry['stdout'].endswith('/smoke-compile.stdout'))
    dep_template = list(compile_template)
    dep_template[dep_template.index('-MD')] = '-M'
    del dep_template[dep_template.index('-MF'):dep_template.index('-MF') + 2]
    del dep_template[dep_template.index('-c')]
    del dep_template[dep_template.index('-o'):dep_template.index('-o') + 2]
    old_source = str(ROOT / 'tools/rpi5/user/pthread_smoke.c')
    dep_template[dep_template.index(old_source)] = str(SOURCE)
    before = dependencies(run(dep_template, output, 'target-deps', commands).stdout)

    target_object = output / 'pthread-recursive-target-v1.o'
    target_dep = output / 'pthread-recursive-target-v1.d'
    compile_command = list(compile_template)
    compile_command[compile_command.index(old_source)] = str(SOURCE)
    compile_command[compile_command.index('-MF') + 1] = str(target_dep)
    compile_command[compile_command.index('-o') + 1] = str(target_object)
    run(compile_command, output, 'target-compile', commands)
    after = dependencies(target_dep.read_text())
    if after != before:
        raise ValueError('recursive target consumed dependency set changed')
    pins.update(before)

    target = output / 'NOT_RUN_recursive_mutex_target'
    target_map = output / 'target.map'
    link = next(list(entry['command']) for entry in base['commands']
                if entry['stdout'].endswith('/target-link.stdout'))
    link[link.index('-o') + 1] = str(target)
    link[link.index('-map') + 1] = str(target_map)
    old_object = str(BASE / 'smoke.o')
    if link.count(old_object) != 1:
        raise ValueError('frozen workload object membership changed')
    link[link.index(old_object)] = str(target_object)
    run(link, output, 'target-link', commands)
    undefined = run(['xcrun', 'nm', '-u', target], output, 'target-undefined', commands)
    if undefined.stdout.strip():
        raise ValueError('recursive target retains undefined symbols')
    run(['xcrun', 'nm', '-g', target], output, 'target-symbols', commands)
    disassembly = run(['xcrun', 'llvm-objdump', '--disassemble-symbols=_rpi5_pthread_smoke_main,'
                       '_run_worker,_probe_owned_mutex,_probe_released_mutex', target],
                      output, 'target-disassembly', commands)
    for symbol in API_OWNERS:
        if f'<{symbol}>' not in disassembly.stdout:
            raise ValueError(f'target call edge missing from disassembly: {symbol}')
    ownership = owner_map(target_map.read_text())

    compiler = subprocess.check_output(['xcrun', '--find', 'clang'], text=True).strip()
    sdk = subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip()
    host = output / 'pthread-recursive-host-oracle'
    host_flags = [compiler, '-isysroot', sdk, '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                  '-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                  '-pthread', '-DRPI5_PTHREAD_RECURSIVE_HOST=1']
    run([*host_flags, SOURCE, '-o', host], output, 'host-compile', commands)
    host_result = run([host], output, 'host-run', commands)
    if host_result.stdout != HOST_LINE or host_result.stderr:
        raise ValueError('recursive host oracle result changed')

    for path, digest in pins.items():
        if sha(path) != digest:
            raise ValueError(f'pinned recursive target input drift: {path}')

    report = dict(
        profile=PROFILE,
        default_off=True,
        admitted=False,
        gate_open=False,
        filex_popen_admission_allowed=False,
        accepted_runtime_modified=False,
        target_image_installed=False,
        pi_executed=False,
        source_inputs_sha256=pins,
        source_contract=contract,
        prior_gate=dict(manifest=str(PRIOR_GATE / 'manifest.json'),
                        manifest_sha256=PRIOR_GATE_SHA256,
                        gate_open=prior['gate_open'],
                        filex_popen_admission_allowed=prior['filex_popen_admission_allowed']),
        recursive_mutex_stage=dict(implementation_linked=True,
                                   genuine_current_apple_owners=True,
                                   behavior_spec_host_oracle=True,
                                   target_execution=False,
                                   target_behavior_qualified=False,
                                   remaining_requirement='execute this exact candidate on the Pi and bind its serial receipt'),
        target=str(target),
        target_sha256=sha(target),
        target_link_complete=True,
        target_undefined_symbols=[],
        target_api_owners=ownership,
        host_oracle=dict(stdout=host_result.stdout, asan_ubsan=True,
                         host_pthread_only=True, target_evidence=False),
        remaining_blockers=[
            'target-recursive-mutex-execution',
            'target-atfork-fork-composition',
            'target-cancelable-variant',
            'target-filex-locking',
        ],
        commands=commands,
    )
    report['generated_sha256'] = {
        str(path.relative_to(output)): sha(path)
        for path in sorted(output.rglob('*')) if path.is_file()
    }
    (output / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(output), target_sha256=report['target_sha256'],
                          recursive_mutex=report['recursive_mutex_stage'],
                          gate_open=report['gate_open']), indent=2))
    return output, report


def check(package):
    package = Path(package).resolve()
    report = json.loads((package / 'manifest.json').read_text())
    _, prior, expected_pins = load_frozen_inputs()
    contract = source_contract()
    if report.get('profile') != PROFILE or report.get('default_off') is not True:
        raise ValueError('not the versioned default-off recursive target package')
    for field in ('admitted', 'gate_open', 'filex_popen_admission_allowed',
                  'accepted_runtime_modified', 'target_image_installed', 'pi_executed'):
        if report.get(field) is not False:
            raise ValueError(f'closed recursive prerequisite changed: {field}')
    stage = report.get('recursive_mutex_stage') or {}
    expected_stage = dict(implementation_linked=True, genuine_current_apple_owners=True,
                          behavior_spec_host_oracle=True, target_execution=False,
                          target_behavior_qualified=False,
                          remaining_requirement='execute this exact candidate on the Pi and bind its serial receipt')
    if stage != expected_stage:
        raise ValueError('recursive target readiness/qualification boundary changed')
    if report.get('source_inputs_sha256') != expected_pins:
        raise ValueError('recursive target source receipts changed')
    if report.get('source_contract') != contract:
        raise ValueError('recursive target behavior contract changed')
    if report.get('prior_gate', {}).get('gate_open') is not False or prior['gate_open'] is not False:
        raise ValueError('recursive candidate may not open prior FILEX gate')
    if report.get('host_oracle') != dict(stdout=HOST_LINE, asan_ubsan=True,
                                         host_pthread_only=True, target_evidence=False):
        raise ValueError('host behavior oracle was promoted or changed')
    if report.get('remaining_blockers') != [
            'target-recursive-mutex-execution', 'target-atfork-fork-composition',
            'target-cancelable-variant', 'target-filex-locking']:
        raise ValueError('recursive prerequisite remaining blocker set changed')
    if report.get('target_link_complete') is not True or report.get('target_undefined_symbols') != []:
        raise ValueError('recursive target is not closed-linked')
    if set(report.get('target_api_owners', {})) != set(API_OWNERS):
        raise ValueError('recursive target owner coverage changed')
    for symbol, member in API_OWNERS.items():
        if not report['target_api_owners'][symbol].endswith(f'({member})'):
            raise ValueError(f'recursive target API owner changed: {symbol}')
    for relative, digest in report.get('generated_sha256', {}).items():
        path = package / relative
        if relative == 'manifest.json' or not path.is_file() or sha(path) != digest:
            raise ValueError(f'generated recursive target evidence drift: {relative}')
    target = package / 'NOT_RUN_recursive_mutex_target'
    if report.get('target_sha256') != sha(target):
        raise ValueError('recursive target binary receipt changed')
    for command in report.get('commands', []):
        if command.get('returncode') != 0:
            raise ValueError('recursive target command failed')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', type=Path)
    args = parser.parse_args()
    if args.check:
        checked = check(args.check)
        print(json.dumps(dict(package=str(args.check.resolve()), profile=checked['profile'],
                              gate_open=checked['gate_open'],
                              target_sha256=checked['target_sha256']), indent=2))
    else:
        build()
