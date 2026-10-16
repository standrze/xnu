#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build a separate read-only raw socket diagnostic root; never install/reboot."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

try:
    from .prepare_pid1 import inspect as inspect_macho
    from .prepare_zsh_trial_root import files_from
    from .ramroot import build, inspect
    from .audit_apple_network_kernel import linked_calls
    from .audit_macho import inspect as inspect_kernel
    from . import check_zsh_metadata_package as metadata
except ImportError:
    from prepare_pid1 import inspect as inspect_macho
    from prepare_zsh_trial_root import files_from
    from ramroot import build, inspect
    from audit_apple_network_kernel import linked_calls
    from audit_macho import inspect as inspect_kernel
    import check_zsh_metadata_package as metadata

ROOT = Path(__file__).resolve().parents[2]
ACCEPTED_ROOT = ROOT / 'build/rpi5/apple-network-root-darwin-20261012/ramdisk.bin'
ROOT_PIN = '0fdb95400e7a6421602a39851eaaa6f20e43836e33c390740774165053548b7e'
INSTALL_PATH = '/usr/local/libexec/xnu/socketprobe'
SOURCE = Path(__file__).with_name('user')
CALLS = {3: '_read', 4: '_write', 6: '_sys_close', 29: '_recvfrom', 30: '_accept',
         32: '_getsockname', 92: '_sys_fcntl', 97: '_socket', 98: '_connect',
         104: '_bind', 105: '_setsockopt', 106: '_listen', 118: '_getsockopt',
         133: '_sendto', 134: '_shutdown', 135: '_socketpair', 230: '_poll'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare(image, diagnostic, root_pin):
    if sha(image) != root_pin:
        raise ValueError('Accepted root hash mismatch')
    original = files_from(image)
    for path in ('/sbin/launchd', '/bin/sh', '/bin/zsh', '/sbin/ifconfig', '/sbin/route'):
        if original.get(path, (None, None))[1] != 0o555:
            raise ValueError('Missing preserved executable: ' + path)
    if INSTALL_PATH in original:
        raise ValueError('Socket diagnostic path collision')
    executable = inspect_macho(diagnostic)
    result, layout = build({**original, INSTALL_PATH: (diagnostic, 0o555)})
    actual = files_from(result)
    if ({k: v for k, v in actual.items() if k != INSTALL_PATH} != original or
            inspect(result) != layout):
        raise ValueError('Existing recovery/zsh/Apple command bytes or modes changed')
    return result, dict(
        schema_version=1, scope='Unstaged raw socket ABI diagnostic; loopback only',
        input_root_sha256=root_pin, output_sha256=layout['sha256'],
        output_bytes=len(result), output_nodes=len(layout['entries']),
        executable=executable, install_path=INSTALL_PATH,
        added_files_sha256={INSTALL_PATH: sha(diagnostic)},
        preserved_files_sha256={p: sha(data) for p, (data, _) in original.items()},
        default_init_and_shell_unchanged=True, frozen_zsh_unchanged=True,
        original_apple_network_tools_unchanged=True, complete_darwin_layout=False,
        pi_executed=False, socket_semantics_proven=False, nic_ready=False,
        networking_proven=False, ssh_proven=False, durability=False,
        sd_actions=0, serial_actions=0, reboots=0)


def run(command):
    value = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
    return (value.stdout or value.stderr).strip()


def dependencies(output):
    """clang Make dependencies, including SDK headers, with escaped spaces."""
    tokens = shlex.split(output.replace('\\\n', ' '))
    if not tokens or not tokens[0].endswith(':'):
        raise ValueError('Invalid compiler dependency list')
    return {Path(name).resolve() for name in tokens[1:]}


def kernel_calls():
    raw = metadata.KERNEL.read_bytes()
    receipt = metadata.BUILD.read_bytes()
    if sha(raw) != metadata.KERNEL_SHA or sha(receipt) != metadata.BUILD_SHA:
        raise ValueError('Accepted kernel or build receipt hash mismatch')
    listing = run(['xcrun', 'nm', '-nm', str(metadata.KERNEL)])
    wiring = linked_calls(raw, inspect_kernel(raw)['segments'], listing, CALLS)
    for row in wiring['calls']:
        if CALLS[row['number']] not in row['handler_symbols']:
            raise ValueError('Unexpected linked syscall handler')
    return wiring, {metadata.KERNEL: raw, metadata.BUILD: receipt}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True, help='Must not exist')
    args = parser.parse_args()
    baseline = ACCEPTED_ROOT.read_bytes()
    if sha(baseline) != ROOT_PIN:
        raise ValueError('Accepted Apple-command root changed')
    wiring, kernel_inputs = kernel_calls()
    sdk = Path(run(['xcrun', '--sdk', 'macosx', '--show-sdk-path']))
    compiler, linker = run(['xcrun', '--find', 'clang']), run(['xcrun', '--find', 'ld'])
    sources = [SOURCE / name for name in ('start.S', 'runtime.c', 'socketprobe.c')]
    flags = [compiler, '-isysroot', str(sdk), '-target', 'arm64-apple-darwin',
             '-mcpu=cortex-a76', '-Os', '-ffreestanding', '-fno-builtin',
             '-fno-stack-protector', '-Wall', '-Wextra', '-Werror']
    helpers = [Path(__file__).with_name(name) for name in (
        'prepare_socketprobe_root.py', 'prepare_pid1.py', 'prepare_zsh_trial_root.py',
        'ramroot.py', 'audit_apple_network_kernel.py', 'audit_macho.py',
        'check_zsh_metadata_package.py')]
    captured = {p: p.read_bytes() for p in [*sources, SOURCE/'runtime.h', *helpers]}
    sdk_inputs = {}
    for source in sources:
        for p in dependencies(run([*flags, '-M', str(source)])):
            if p not in captured:
                sdk_inputs[p] = p.read_bytes()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    commands, objects = [], []
    for source in sources:
        obj = out / (source.stem + '.o')
        command = [*flags, '-c', str(source), '-o', str(obj)]
        run(command); commands.append(command); objects.append(str(obj))
    executable = out / 'socketprobe'
    command = [linker, '-arch', 'arm64', '-static', '-e', '_start', '-no_adhoc_codesign',
               '-o', str(executable), *objects]
    run(command); commands.append(command)
    image, report = prepare(baseline, executable.read_bytes(), ROOT_PIN)
    for path, data in {**captured, **sdk_inputs, **kernel_inputs, ACCEPTED_ROOT: baseline}.items():
        if path.read_bytes() != data:
            raise ValueError('Build input changed: ' + str(path))
    report.update(commands=commands, sdk=str(sdk), input_root=str(ACCEPTED_ROOT),
                  compiler_version=run([compiler, '--version']).splitlines()[0],
                  source_inputs_sha256={str(p): sha(data) for p, data in captured.items()},
                  sdk_headers_sha256={str(p): sha(data) for p, data in sdk_inputs.items()},
                  kernel_sha256=metadata.KERNEL_SHA, kernel_build_sha256=metadata.BUILD_SHA,
                  linked_sysent=wiring, syscall_inventory_basis='Reviewed fixed raw-call IDs; not an immediate-X16 binary closure audit',
                  max_data_path_calls=256, max_io_steps_per_direction=16,
                  max_poll_timeout_ms=200, nonblocking_socket_io=True,
                  kernel_syscall_hang_contained=False,
                  modes=['unix', 'inet'], ipv4_scope='127.0.0.1 ephemeral ports only',
                  external_traffic=False, interface_or_route_mutations=False)
    with (out/'ramdisk.bin').open('xb') as output:
        output.write(image)
    with (out/'manifest.json').open('x') as output:
        json.dump(report, output, indent=2, sort_keys=True); output.write('\n')
    print(json.dumps({key: report[key] for key in ('output_sha256', 'output_bytes',
        'output_nodes', 'install_path', 'pi_executed', 'socket_semantics_proven')}))


if __name__ == '__main__':
    main()
