#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Reuse pinned source-built Apple commands in a NEW Pi root; never install."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

try:
    from .prepare_pid1 import inspect as inspect_macho
    from .prepare_zsh_trial_root import files_from
    from .check_zsh_ramroot import checked_hash, read_bounded
    from .ramroot import build, inspect
    from .audit_zsh_pi_binary import audit as audit_instructions
except ImportError:
    from prepare_pid1 import inspect as inspect_macho
    from prepare_zsh_trial_root import files_from
    from check_zsh_ramroot import checked_hash, read_bounded
    from ramroot import build, inspect
    from audit_zsh_pi_binary import audit as audit_instructions

ROOT = Path(__file__).resolve().parents[2]
USERLAND = ROOT / 'experiments/darwin-container/userland'
CAPSULE = USERLAND / 'build/apple-ifconfig-working-2026-10-12'
EVIDENCE = ROOT / 'experiments/darwin-container/results/2026-10-12-apple-ifconfig'
PI_ROOT = ROOT / 'build/rpi5/statprobe-root-20261012-v2/ramdisk.bin'
ROOT_PIN = '5644490c8969d930ad706101ab0656dcfafac78846aca51933f2eb3ec128cc23'
PINS = {
    'ifconfig': ('73bb8b54bd73e1239a6a6e609f02e7df13c271c23db3570202c70bb1b82a202b',
                 '7b592a806c856a9472bba801aade048f05d6a2a03364bedb59861ed6954ddb1b'),
    'route': ('c7baaf0b511ed4519aa48493626472136db10487989d740b3475500bbe2b5c6a',
              '94bd7a04840839ae693530d166e423651d5d85663a7e4020b8f3bbb2cf5e033a'),
}
SOURCE_PIN = 'f8c87f3c5eccdeb95e414c6b1b0c3b9dca4233ca'
INSTALL_PATHS = {'ifconfig': '/sbin/ifconfig', 'route': '/sbin/route'}


def prepare(image, commands, root_pin, command_pins):
    """Pure additive packaging. Synthetic tests are not provenance evidence."""
    checked_hash(image, root_pin, 'accepted Pi root')
    if set(commands) != {'ifconfig', 'route'} or set(command_pins) != set(commands):
        raise ValueError('Only the two explicit Apple command additions are allowed')
    original = files_from(image)
    for path in ('/sbin/launchd', '/bin/sh', '/bin/zsh', '/bin/statprobe'):
        if original.get(path, (None, None))[1] != 0o555:
            raise ValueError('Missing accepted executable: ' + path)
    additions, executables = {}, {}
    for name, data in commands.items():
        checked_hash(data, command_pins[name], name)
        executables[name] = inspect_macho(data)
        additions[INSTALL_PATHS[name]] = (data, 0o555)
    if original.keys() & additions.keys():
        raise ValueError('Apple command addition would replace an existing file')
    result, layout = build({**original, **additions})
    actual = files_from(result)
    if any(actual[path] != record for path, record in original.items()) or inspect(result) != layout:
        raise ValueError('Pi root reconstruction or recovery preservation failed')
    return result, dict(
        schema_version=1, scope='Unstaged original Apple command reuse, not Pi execution',
        input_root_sha256=root_pin, output_sha256=layout['sha256'], output_bytes=len(result),
        output_nodes=len(layout['entries']), executables=executables,
        preserved_files_sha256={path: hashlib.sha256(data).hexdigest()
                                for path, (data, _) in original.items()},
        added_files_sha256={INSTALL_PATHS[name]: command_pins[name] for name in commands},
        command_install_paths=dict(INSTALL_PATHS), complete_darwin_layout=False,
        default_init_and_shell_unchanged=True, frozen_zsh_unchanged=True,
        vm_init_or_poweroff_imported=False, pi_executed=False, networking_proven=False,
        isa_and_abi_compatibility_proven=False, boot_package_preflight_passed=False,
        sd_actions=0, serial_actions=0, reboots=0)


def load_inputs():
    """Bind actual binaries to pinned source/build receipts, not VM status alone."""
    snapshots = {}

    def capture(path, pin=None):
        path = path.resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError('Non-workspace source receipt path refused: ' + str(path))
        data = read_bounded(path)
        if pin is not None:
            checked_hash(data, pin, str(path))
        if path in snapshots and snapshots[path] != data:
            raise ValueError('Input changed during capture: ' + str(path))
        snapshots[path] = data
        return data

    manifests, commands, heads = {}, {}, {}
    for helper in ('prepare_apple_network_root.py', 'prepare_pid1.py', 'prepare_zsh_trial_root.py',
                   'check_zsh_ramroot.py', 'ramroot.py', 'audit_zsh_pi_binary.py'):
        capture(ROOT / 'tools/rpi5' / helper)
    for name, (binary_pin, receipt_pin) in PINS.items():
        commands[name] = capture(CAPSULE / name, binary_pin)
        m = json.loads(capture(EVIDENCE / (name + '-manifest.json'), receipt_pin))
        if (type(m.get('exit')) is not int or m['exit'] != 0 or
                m.get('host_runtime_linked') is not False or m.get('apple_' + name) is not True or
                m.get('apple_libinfo') is not True or m.get('sha256') != binary_pin or
                m['pins'].get('apple-network_cmds-396.6') != SOURCE_PIN):
            raise ValueError('Original Apple command build/profile refused: ' + name)
        capture(USERLAND / 'build_apple_resolver.py', m['builder_sha256'])
        for group in ('sources', 'private_header_sha256', 'runtime_archives'):
            if not m.get(group):
                raise ValueError('Missing source/archive evidence: ' + name)
            for filename, pin in m[group].items():
                capture(Path(filename), pin)
        for checkout, commit in m['pins'].items():
            if '/' in checkout or checkout.startswith('.'):
                raise ValueError('Invalid checkout receipt name')
            path = USERLAND / 'upstream' / checkout
            head = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'],
                                           text=True, timeout=30).strip()
            dirty = subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain',
                                             '--untracked-files=no'], text=True, timeout=30)
            if head != commit or dirty or (checkout in heads and heads[checkout] != head):
                raise ValueError('Original Apple checkout changed: ' + checkout)
            heads[checkout] = head
        manifests[name] = m
    # Reuse the existing linked-constructor inspection; do not reimplement it.
    helper = USERLAND / 'inspect_initializers.py'
    capture(helper)
    sys.path.insert(0, str(ROOT / 'tools/rpi5'))
    spec = importlib.util.spec_from_file_location('apple_command_initializers', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    constructors = tuple('_' + name + '_ctor' for name in
                         ('inet', 'inet6', 'link', 'bond', 'bridge', 'clone', 'ifconfig', 'ifmedia', 'vlan'))
    initializers = module.inspect_initializers(commands['ifconfig'], constructors)
    upstream = USERLAND / 'upstream/apple-network_cmds-396.6'
    required = [*sorted((upstream / 'ifconfig.tproj').glob('*.c')), upstream / 'route.tproj/route.c']
    selected = set(manifests['ifconfig']['sources']) | set(manifests['route']['sources'])
    if len(required) != 10 or not all(str(path) in selected for path in required):
        raise ValueError('Complete original command/modules missing from build receipts')
    capture(upstream / 'APPLE_LICENSE')
    capture(upstream / 'network_cmds.xcodeproj/project.pbxproj')
    return commands, snapshots, dict(
        repository='https://github.com/apple-oss-distributions/network_cmds',
        tag='network_cmds-396.6', commit=SOURCE_PIN, original_checkouts=heads,
        receipt_sha256={name: pin[1] for name, pin in PINS.items()},
        verified_input_sha256={str(path.relative_to(ROOT)): hashlib.sha256(data).hexdigest()
                               for path, data in snapshots.items()},
        original_ifconfig_constructors=initializers,
        capability_limits={name: m['capability_limits'] for name, m in manifests.items()},
        license_scope='Notices and original source retained in existing source capsules; private experiment, not redistribution clearance')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True, help='New build/rpi5 directory only')
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if not output.is_relative_to(ROOT / 'build/rpi5') or output.exists():
        raise ValueError('Distinct, nonexistent local build/rpi5 output required')
    commands, snapshots, provenance = load_inputs()
    baseline = read_bounded(PI_ROOT)
    image, report = prepare(baseline, commands, ROOT_PIN, {name: pin[0] for name, pin in PINS.items()})
    inventories = {}
    for name, pins in PINS.items():
        inventory = audit_instructions(CAPSULE / name, pins[0])
        inventory['binary_sha256'] = inventory.pop('zsh_sha256')
        inventory['command'] = name
        inventories[name] = inventory
    for path, before in snapshots.items():
        if read_bounded(path) != before:
            raise ValueError('Source/build input changed during preparation: ' + str(path))
    if read_bounded(PI_ROOT) != baseline:
        raise ValueError('Accepted Pi root changed')
    report.update(provenance=provenance, instruction_inventories=inventories,
                  input_root=str(PI_ROOT), original_commands_unchanged=True,
                  next='Review actual Pi startup/socket/ioctl contracts; separate boot package and read-only trial before configuration')
    output.mkdir(parents=True, exist_ok=False)
    with (output / 'ramdisk.bin').open('xb') as stream:
        stream.write(image)
    with (output / 'manifest.json').open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({key: report[key] for key in
                      ('output_sha256', 'output_bytes', 'output_nodes', 'pi_executed', 'networking_proven')}, sort_keys=True))


if __name__ == '__main__':
    main()
