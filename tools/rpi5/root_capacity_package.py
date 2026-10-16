#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Extend the accepted Pi root and rebuild its real mounted-file catalogue."""
import argparse
import json
from pathlib import Path
import subprocess

try:
    from . import root_capacity_profile as profile
    from . import prepare_socket_identity_root as identity
    from .prepare_pid1 import inspect as inspect_macho
except ImportError:
    import root_capacity_profile as profile
    import prepare_socket_identity_root as identity
    from prepare_pid1 import inspect as inspect_macho

ROOT = profile.ROOT
BASE = ROOT / 'build/rpi5/socket-identity-root-20261012-devfs'
BASE_SHA = 'ea24195e8e816583654006856285812b133464f32e02bc6d2208497336ae4abe'
ROOT_SHA = '3fa5ed9f501cedd744b0d6d75cc0886837db562f3bd42282284d82e2798d9a27'
PROBE_PATH = '/usr/local/libexec/xnu/sshbufferprobe'
IDENTITY_PATH = '/usr/local/libexec/xnu/socketprobe'


def build(output, probe, probe_sha, kernel_manifest, probe_manifest):
    manifest = BASE / 'manifest.json'
    if profile.sha(manifest.read_bytes()) != BASE_SHA:
        raise ValueError('Accepted Pi root manifest changed')
    prior = json.loads(manifest.read_text())
    original_raw = (BASE / 'ramdisk.bin').read_bytes()
    if profile.sha(original_raw) != ROOT_SHA:
        raise ValueError('Accepted Pi root image changed')
    raw = probe.read_bytes()
    if profile.sha(raw) != probe_sha:
        raise ValueError('SSH probe hash mismatch')
    executable = inspect_macho(raw)
    probe_record = json.loads(probe_manifest.read_text())
    if probe_record.get('actual_static_executable') != str(probe):
        raise ValueError('SSH probe manifest names a different executable')
    probe_pins = {**probe_record['source_inputs_sha256'], **probe_record['headers_sha256'], **probe_record['generated_sha256']}
    if probe_pins.get(str(probe)) != probe_sha:
        raise ValueError('SSH probe manifest does not pin the requested binary')
    for name, digest in probe_pins.items():
        if profile.sha(Path(name).read_bytes()) != digest:
            raise ValueError('SSH probe source/output changed: ' + name)
    kernel_raw = kernel_manifest.read_bytes()
    kernel = json.loads(kernel_raw)
    if kernel.get('profile') != 'rpi5-ramroot-96-v1' or kernel.get('node_capacity') != 96:
        raise ValueError('A matching complete 96-node Pi kernel is required')
    if profile.sha(Path(kernel['kernel']).read_bytes()) != kernel['kernel_sha256']:
        raise ValueError('Expanded Pi kernel bytes changed')
    captured = {**prior['source_inputs_sha256'], **prior['sdk_headers_sha256'], **probe_pins}
    for name, digest in captured.items():
        if profile.sha(Path(name).read_bytes()) != digest:
            raise ValueError('Preserved identity source changed: ' + name)
    for path in (manifest, BASE / 'ramdisk.bin', probe, probe_manifest, kernel_manifest, Path(kernel['kernel']),
                 Path(__file__).resolve(), Path(profile.__file__).resolve(), Path(identity.__file__).resolve(),
                 profile.PACKER, Path(inspect_macho.__code__.co_filename)):
        captured[str(path)] = profile.sha(path.read_bytes())
    original = profile.files_from(original_raw)
    if PROBE_PATH in original or IDENTITY_PATH not in original:
        raise ValueError('Unexpected baseline utility paths')
    expanded = {**original, PROBE_PATH: (raw, 0o555)}
    provisional, layout = profile.build(expanded)
    rows = []
    for entry in layout['entries']:
        path = entry['path']
        directory = entry['type'] == 'directory'
        rows.append(dict(path=path, mode=entry['mode'] | (0o40000 if directory else 0o100000),
                         bytes=0 if directory or path == IDENTITY_PATH else len(expanded[path][0]),
                         sha256='' if directory else None if path == IDENTITY_PATH else profile.sha(expanded[path][0])))
    output = output.resolve()
    if output.parent != ROOT / 'build/rpi5':
        raise ValueError('A fresh directory directly under build/rpi5 is required')
    output.mkdir(exist_ok=False)
    generated = output / 'rootidentity_catalog.h'
    generated.write_text(identity.header(rows))
    source = ROOT / 'tools/rpi5/user/rootidentity.c'
    matches = [cmd for cmd in prior['commands'] if str(source) in cmd]
    if len(matches) != 1:
        raise ValueError('Missing real identity compile command')
    old_compile = matches[0]
    old_object = Path(old_compile[-1])
    new_object = output / 'rootidentity.o'
    if old_compile[-2] != '-o' or old_compile.count('-I' + str(BASE)) != 1:
        raise ValueError('Unexpected identity build invocation')
    args = [('-I' + str(output)) if a == '-I' + str(BASE) else a for a in old_compile[:-2]]
    dependencies = identity.old.dependencies(identity.old.run([a for a in args if a != '-c'] + ['-M']))
    if generated not in dependencies:
        raise ValueError('Compiler missed the expanded identity catalogue')
    for path in dependencies:
        digest = profile.sha(path.read_bytes())
        if str(path) in captured and captured[str(path)] != digest:
            raise ValueError('Conflicting root identity dependency')
        captured[str(path)] = digest
    command = args + ['-o', str(new_object)]
    identity.old.run(command)
    old_link = prior['commands'][-1]
    if old_link.count(str(old_object)) != 1 or old_link.count(str(BASE / 'socketprobe')) != 1:
        raise ValueError('Unexpected real identity link invocation')
    diagnostic = output / 'socketprobe'
    link = [str(new_object) if a == str(old_object) else str(diagnostic) if a == str(BASE / 'socketprobe') else a
            for a in old_link]
    for token in old_link:
        if token.endswith('.o'):
            captured[token] = profile.sha(Path(token).read_bytes())
    identity.old.run(link)
    if identity.old.run(['xcrun', 'nm', '-u', str(diagnostic)]):
        raise ValueError('Expanded identity tool has unresolved symbols')
    diagnostic_raw = diagnostic.read_bytes()
    inspect_macho(diagnostic_raw)
    expanded[IDENTITY_PATH] = (diagnostic_raw, 0o555)
    image, layout = profile.build(expanded)
    if profile.inspect(image) != layout or profile.files_from(image) != expanded:
        raise ValueError('Expanded Pi root failed complete round-trip')
    for path, value in original.items():
        if path != IDENTITY_PATH and expanded[path] != value:
            raise ValueError('Unrelated accepted root file changed')
    for name, digest in captured.items():
        if profile.sha(Path(name).read_bytes()) != digest:
            raise ValueError('Capacity root input changed during build: ' + name)
    for row in rows:
        if row['path'] == IDENTITY_PATH:
            row.update(bytes=len(diagnostic_raw), sha256=profile.sha(diagnostic_raw))
    (output / 'ramdisk.bin').write_bytes(image)
    report = dict(profile='rpi5-ramroot-96-sshbuffer-v1', input_root_sha256=ROOT_SHA,
                  output_sha256=profile.sha(image), output_bytes=len(image), output_nodes=len(layout['entries']),
                  node_capacity=96, install_path=PROBE_PATH, executable=executable,
                  added_files_sha256={PROBE_PATH: probe_sha},
                  probe_manifest=str(probe_manifest), probe_manifest_sha256=profile.sha(probe_manifest.read_bytes()),
                  regenerated_identity_sha256=profile.sha(diagnostic_raw), identity_catalog=rows,
                  identity_self_digest_compared_externally=True,
                  preserved_files_sha256={path: profile.sha(data) for path, (data, _) in original.items() if path != IDENTITY_PATH},
                  inputs_sha256=captured, commands=[command, link], kernel=str(kernel['kernel']),
                  kernel_sha256=kernel['kernel_sha256'], kernel_manifest=str(kernel_manifest),
                  kernel_manifest_sha256=profile.sha(kernel_raw), default_init_and_shell_unchanged=True,
                  installed=False, pi_executed=False, ssh_proven=False, nic_ready=False, durability=False,
                  sd_actions=0, serial_actions=0, reboots=0)
    report['generated_sha256'] = {str(p): profile.sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}
    (output / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--probe-sha256', required=True)
    parser.add_argument('--probe-manifest', type=Path, required=True)
    parser.add_argument('--kernel-manifest', type=Path, required=True)
    args = parser.parse_args()
    report = build(args.output_dir, args.probe.resolve(), args.probe_sha256, args.kernel_manifest.resolve(), args.probe_manifest.resolve())
    print(json.dumps({k: report[k] for k in ('output_sha256', 'output_bytes', 'output_nodes', 'kernel_sha256', 'pi_executed')}))
