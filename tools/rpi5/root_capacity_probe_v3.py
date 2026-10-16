#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the ordinary serial XNU loader with the isolated 96-node root parser."""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import shlex
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parent))
import root_capacity_profile as profile

ROOT = profile.ROOT
BUILDER = ROOT / 'tools/rpi5/build_probe.py'
BUILDER_SHA = 'e8f96974a5c161bbf8d0fb3eb67af272f00268de374980f08d72a1b3c02d019e'


def build(root_manifest, kernel_manifest):
    root_raw, kernel_raw = root_manifest.read_bytes(), kernel_manifest.read_bytes()
    root, kernel = json.loads(root_raw), json.loads(kernel_raw)
    if (root.get('profile') != 'rpi5-ramroot-96-sshbuffer-v1' or
            kernel.get('profile') != 'rpi5-ramroot-96-v1' or
            root['kernel_manifest_sha256'] != profile.sha(kernel_raw) or
            root['kernel_sha256'] != kernel['kernel_sha256']):
        raise ValueError('Expanded root/kernel profiles do not match')
    captured = {str(root_manifest): profile.sha(root_raw), str(kernel_manifest): profile.sha(kernel_raw),
                str(BUILDER): BUILDER_SHA, str(Path(__file__).resolve()): profile.sha(Path(__file__).read_bytes()),
                str(Path(profile.__file__).resolve()): profile.sha(Path(profile.__file__).read_bytes())}
    for report in (root, kernel):
        for name, digest in {**report['inputs_sha256'], **report['generated_sha256']}.items():
            if name in captured and captured[name] != digest:
                raise ValueError('Conflicting root/kernel build dependency')
            captured[name] = digest
    for name, digest in captured.items():
        if profile.sha(Path(name).read_bytes()) != digest:
            raise ValueError('Expanded package dependency changed: ' + name)
    image = root_manifest.parent / 'ramdisk.bin'
    if (profile.sha(image.read_bytes()) != root['output_sha256'] or
            profile.sha(Path(kernel['kernel']).read_bytes()) != kernel['kernel_sha256']):
        raise ValueError('Expanded image bytes differ from receipt')
    profile.inspect(image.read_bytes())
    # The original builder remains unchanged. Only this private module instance
    # uses the matching expanded root validator; all loader/runtime code is reused.
    spec = importlib.util.spec_from_file_location('_root_capacity_loader', BUILDER)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.inspect_pid1 = profile.inspect
    actual_compiles = []
    class CompilerCapture:
        check_output = staticmethod(subprocess.check_output)
        def run(self, command, **kwargs):
            command = list(map(str, command))
            if command[:2] != ['xcrun', 'clang'] or '-c' not in command:
                return subprocess.run(command, **kwargs)
            if command.count('-o') != 1 or command.count('-c') != 1:
                raise ValueError('Ambiguous actual loader compile')
            index = command.index('-o')
            destination = Path(command[index + 1])
            scan = command[:index] + command[index + 2:]
            scan = [arg for arg in scan if arg not in ('-c', '-fstack-usage')]
            before = subprocess.run(scan + ['-M'], cwd=ROOT, capture_output=True, text=True, check=True)
            if before.stderr:
                raise ValueError('Loader dependency scan produced diagnostics')
            def paths(text):
                tokens = shlex.split(text.replace(chr(92) + chr(10), ' '))
                if not tokens or not tokens[0].endswith(':'):
                    raise ValueError('Malformed actual compiler dependency output')
                return {Path(token).resolve() for token in tokens[1:]}
            dependencies = paths(before.stdout)
            pins = {str(path): profile.sha(path.read_bytes()) for path in dependencies}
            for name, digest in pins.items():
                if name in captured and captured[name] != digest:
                    raise ValueError('Actual loader dependency conflicts with captured input: ' + name)
                captured[name] = digest
            dependency_file = destination.with_suffix('.d')
            actual = command + ['-MD', '-MF', str(dependency_file)]
            result = subprocess.run(actual, **kwargs)
            if paths(dependency_file.read_text()) != dependencies:
                raise ValueError('Loader headers changed between scan and actual compile')
            for name, digest in pins.items():
                if profile.sha(Path(name).read_bytes()) != digest:
                    raise ValueError('Loader input changed during compile: ' + name)
            actual_compiles.append(dict(command=actual, dependencies_sha256=pins,
                                        dependency_file=str(dependency_file),
                                        dependency_sha256=profile.sha(dependency_file.read_bytes())))
            return result
    builder.subprocess = CompilerCapture()
    argv = [str(BUILDER), '--load-address', '0x9000000', '--kernel', kernel['kernel'],
            '--init', str(image), '--transfer', '--serial-terminal', '--gate3-cpu-on-all', '--gate5-pcie-topology']
    saved, printed = sys.argv, io.StringIO()
    try:
        sys.argv = argv
        with contextlib.redirect_stdout(printed):
            builder.main()
    finally:
        sys.argv = saved
    output = Path(printed.getvalue().strip())
    if output.parent != ROOT / 'build/rpi5' or not output.name.startswith('bl33-probe-'):
        raise ValueError('Unexpected loader build output directory')
    loader = json.loads((output / 'manifest.json').read_text())
    if (loader['embedded_init']['sha256'] != root['output_sha256'] or
            len(loader['embedded_init']['entries']) != root['output_nodes'] or
            not loader['serial_terminal'] or not loader['gate3_cpu_on_all']):
        raise ValueError('Actual loader embedded the wrong root or profile')
    for name, digest in captured.items():
        if profile.sha(Path(name).read_bytes()) != digest:
            raise ValueError('Expanded package input changed during loader build: ' + name)
    for relative, digest in loader['sha256'].items():
        path = ROOT / relative
        if profile.sha(path.read_bytes()) != digest:
            raise ValueError('Loader generated/source bytes changed: ' + relative)
        captured[str(path)] = digest
    report = dict(profile='rpi5-serial-root96-sshbuffer-v1', image=str(output / 'probe.bin'),
                  image_sha256=profile.sha((output / 'probe.bin').read_bytes()),
                  kernel_sha256=kernel['kernel_sha256'], root_sha256=root['output_sha256'],
                  output_nodes=root['output_nodes'], node_capacity=96, command=argv,
                  inputs_sha256=captured, loader_manifest_sha256=profile.sha((output / 'manifest.json').read_bytes()),
                  root_manifest=str(root_manifest), kernel_manifest=str(kernel_manifest),
                  actual_compiles=actual_compiles, actual_compiler_dependencies_verified=True,
                  installed=False, pi_executed=False, networking_proven=False, ssh_proven=False,
                  sd_actions=0, serial_actions=0, reboots=0)
    (output / 'capacity.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root-manifest', type=Path, required=True)
    parser.add_argument('--kernel-manifest', type=Path, required=True)
    args = parser.parse_args()
    report = build(args.root_manifest.resolve(), args.kernel_manifest.resolve())
    print(json.dumps({k: report[k] for k in ('image', 'image_sha256', 'output_nodes', 'node_capacity', 'pi_executed')}))
