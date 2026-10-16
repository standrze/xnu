#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build an isolated diagnostic; preserve every byte/mode of the accepted zsh root."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

try:
    from .prepare_pid1 import inspect as inspect_macho
    from .prepare_zsh_trial_root import files_from
    from .ramroot import build, inspect
except ImportError:
    from prepare_pid1 import inspect as inspect_macho
    from prepare_zsh_trial_root import files_from
    from ramroot import build, inspect

ROOT = Path(__file__).resolve().parents[2]
ACCEPTED_ROOT = ROOT / 'build/rpi5/zsh-pi-trial-root-20261012/ramdisk.bin'
ROOT_PIN = 'ddbdffe24f4441985cadf5aa1556d2b409e0c8a39d6d86dd5352d49814712e08'
SOURCE = Path(__file__).with_name('user')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare(image, diagnostic, root_pin):
    if sha(image) != root_pin:
        raise ValueError('Recovery/zsh root hash mismatch')
    original = files_from(image)
    if not all(original.get(path, (None, None))[1] == 0o555
               for path in ('/sbin/launchd', '/bin/sh', '/bin/zsh')):
        raise ValueError('Missing preserved recovery/zsh executable')
    if '/bin/statprobe' in original or '/etc/statprobe-missing' in original:
        raise ValueError('Diagnostic path collision or negative control exists')
    executable = inspect_macho(diagnostic)
    result, layout = build({**original, '/bin/statprobe': (diagnostic, 0o555)})
    actual = files_from(result)
    if any(actual[path] != record for path, record in original.items()):
        raise ValueError('Existing recovery/zsh file or mode changed')
    if inspect(result) != layout:
        raise ValueError('Root reconstruction mismatch')
    return result, {
        'schema_version': 1, 'scope': 'Unstaged read-only raw stat/open/fcntl diagnostic',
        'input_root_sha256': root_pin, 'output_sha256': layout['sha256'],
        'output_bytes': len(result), 'output_nodes': len(layout['entries']),
        'executable': executable,
        'preserved_files_sha256': {path: sha(data) for path, (data, _) in original.items()},
        'default_init_and_shell_unchanged': True,
        'frozen_zsh_unchanged': True, 'pi_executed': False,
        'script_file_acceptance': False, 'abi_root_cause_proven': False,
        'sd_actions': 0, 'serial_actions': 0, 'reboots': 0,
    }


def run(command):
    value = subprocess.run(command, capture_output=True, text=True, check=True)
    return (value.stdout or value.stderr).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True, help='Must not exist')
    args = parser.parse_args()
    baseline = ACCEPTED_ROOT.read_bytes()
    if sha(baseline) != ROOT_PIN:
        raise ValueError('Pinned physical-trial root has changed')
    sources = [SOURCE / name for name in ('start.S', 'runtime.c', 'statprobe.c')]
    inputs = sources + [SOURCE / 'runtime.h', Path(__file__),
                        Path(__file__).with_name('prepare_pid1.py'),
                        Path(__file__).with_name('prepare_zsh_trial_root.py'),
                        Path(__file__).with_name('ramroot.py')]
    captured = {str(path): path.read_bytes() for path in inputs}
    sdk = Path(run(['xcrun', '--sdk', 'macosx', '--show-sdk-path']))
    headers = {str(sdk / 'usr/include' / name): (sdk / 'usr/include' / name).read_bytes()
               for name in ('sys/stat.h', 'sys/fcntl.h')}
    compiler, linker = run(['xcrun', '--find', 'clang']), run(['xcrun', '--find', 'ld'])
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    commands, objects = [], []
    for source in sources:
        obj = out / (source.stem + '.o')
        command = [compiler, '-isysroot', str(sdk), '-target', 'arm64-apple-darwin',
                   '-mcpu=cortex-a76', '-c', '-Os', '-ffreestanding', '-fno-builtin',
                   '-fno-stack-protector', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(obj)]
        run(command); commands.append(command); objects.append(str(obj))
    executable = out / 'statprobe'
    command = [linker, '-arch', 'arm64', '-static', '-e', '_start', '-no_adhoc_codesign',
               '-o', str(executable), *objects]
    run(command); commands.append(command)
    image, report = prepare(baseline, executable.read_bytes(), ROOT_PIN)
    for name, data in {**captured, **headers}.items():
        if Path(name).read_bytes() != data:
            raise ValueError('Build input changed: ' + name)
    if ACCEPTED_ROOT.read_bytes() != baseline:
        raise ValueError('Baseline changed during build')
    report.update(commands=commands, compiler_version=run([compiler, '--version']).splitlines()[0],
                  sdk=str(sdk), input_root=str(ACCEPTED_ROOT),
                  source_inputs_sha256={name: sha(data) for name, data in captured.items()},
                  sdk_headers_sha256={name: sha(data) for name, data in headers.items()})
    with (out / 'ramdisk.bin').open('xb') as output:
        output.write(image)
    with (out / 'manifest.json').open('x') as output:
        json.dump(report, output, sort_keys=True, indent=2); output.write('\n')
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
