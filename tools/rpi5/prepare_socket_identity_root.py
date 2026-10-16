#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct socket v2 root, with fixed read-only runtime identity diagnosis.

No changes to the frozen v1 diagnostic, accepted kernel, init or Apple commands.
No media, serial, firmware or reboot actions. This is build evidence only.
"""
import argparse
import json
from pathlib import Path

try:
    from . import prepare_socketprobe_root as old
    from .ramroot import inspect
except ImportError:
    import prepare_socketprobe_root as old
    from ramroot import inspect

BEARSSL = old.ROOT/'build/rpi5/bearssl-candidate'
BEARSSL_COMMIT = '7bea48e5e850ab4cafbe68d3765cdaba13a86d6f'
CALLS = {**old.CALLS, 5: '_open', 339: '_sys_fstat64', 340: '_lstat64', 345: '_statfs64'}


def catalog(baseline):
    """Derive all 32 paths; self length/hash must be compared from outside."""
    # A placeholder only computes the final path tree; it is not published.
    placeholder = old.files_from(baseline)['/sbin/launchd'][0]
    image, _ = old.prepare(baseline, placeholder, old.ROOT_PIN)
    files = old.files_from(baseline)
    rows = []
    for entry in inspect(image)['entries']:
        path = entry['path']
        directory = entry['type'] == 'directory'
        rows.append(dict(path=path, mode=entry['mode'] | (0o40000 if directory else 0o100000),
                         bytes=0 if directory or path == old.INSTALL_PATH else len(files[path][0]),
                         sha256='' if directory else None if path == old.INSTALL_PATH else old.sha(files[path][0])))
    return rows


def header(rows):
    return ('/* Generated fixed catalog; self digest is externally verified. */\n'
            'static const struct identity_entry identity_catalog[] = {\n' + ''.join(
                '    {'+json.dumps(row['path'])+','+str(row['mode'])+','+str(row['bytes'])+', '+
                ('0' if row['sha256'] is None else json.dumps(row['sha256']))+'},\n' for row in rows) + '};\n')


def kernel_calls():
    # Reuse the reviewed actual-sysent decoder without changing v1's globals.
    raw = old.metadata.KERNEL.read_bytes()
    receipt = old.metadata.BUILD.read_bytes()
    if old.sha(raw) != old.metadata.KERNEL_SHA or old.sha(receipt) != old.metadata.BUILD_SHA:
        raise ValueError('Accepted kernel/build changed')
    wiring = old.linked_calls(raw, old.inspect_kernel(raw)['segments'],
                            old.run(['xcrun', 'nm', '-nm', str(old.metadata.KERNEL)]), CALLS)
    for row in wiring['calls']:
        if CALLS[row['number']] not in row['handler_symbols']:
            raise ValueError('Unexpected identity/socket sysent handler')
    return wiring, {old.metadata.KERNEL: raw, old.metadata.BUILD: receipt}


def build(output):
    baseline = old.ACCEPTED_ROOT.read_bytes()
    if old.sha(baseline) != old.ROOT_PIN:
        raise ValueError('Accepted root changed')
    if (old.run(['git', '-C', str(BEARSSL), 'rev-parse', 'HEAD']) != BEARSSL_COMMIT or
            old.run(['git', '-C', str(BEARSSL), 'status', '--porcelain', '--untracked-files=all'])):
        raise ValueError('Pinned pristine BearSSL checkout required')
    wiring, kernel = kernel_calls()
    sdk = Path(old.run(['xcrun', '--sdk', 'macosx', '--show-sdk-path']))
    clang, ld = old.run(['xcrun', '--find', 'clang']), old.run(['xcrun', '--find', 'ld'])
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows = catalog(baseline)
    generated = output/'rootidentity_catalog.h'
    with generated.open('x') as stream:
        stream.write(header(rows))
    sources = [old.SOURCE/name for name in ('start.S', 'runtime.c', 'socketprobe_identity.c',
                                           'rootidentity.c', 'identity_memory.c')]
    crypto = [BEARSSL/'src'/name for name in ('hash/sha2small.c', 'codec/dec32be.c', 'codec/enc32be.c')]
    common = [clang, '-isysroot', str(sdk), '-target', 'arm64-apple-darwin',
              '-mcpu=cortex-a76', '-Os', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
              '-D_FORTIFY_SOURCE=0',
              '-I'+str(output), '-I'+str(BEARSSL/'inc'), '-I'+str(BEARSSL/'src')]
    strict = ['-Wall', '-Wextra', '-Werror']
    helpers = [Path(old.__file__).with_name(name) for name in (
        'prepare_pid1.py', 'prepare_zsh_trial_root.py', 'ramroot.py',
        'audit_apple_network_kernel.py', 'audit_macho.py', 'check_zsh_metadata_package.py')]
    captured = {p: p.read_bytes() for p in [*sources, *crypto, *helpers, generated, Path(__file__),
                Path(old.__file__), old.SOURCE/'socketprobe.c', old.SOURCE/'runtime.h', BEARSSL/'LICENSE.txt']}
    dependencies = {}
    for source in [*sources, *crypto]:
        for p in old.dependencies(old.run([*common, '-M', str(source)])):
            if p not in captured:
                dependencies[p] = p.read_bytes()
    commands, objects = [], []
    for index, source in enumerate([*sources, *crypto]):
        obj = output/(str(index)+'-'+source.stem+'.o')
        command = [*common, *(strict if source in sources else []), '-c', str(source), '-o', str(obj)]
        old.run(command); commands.append(command); objects.append(str(obj))
    executable = output/'socketprobe'
    command = [ld, '-arch', 'arm64', '-static', '-e', '_start', '-no_adhoc_codesign',
               '-o', str(executable), *objects]
    old.run(command); commands.append(command)
    if old.run(['xcrun', 'nm', '-u', str(executable)]):
        raise ValueError('Unresolved identity diagnostic symbols')
    diagnostic = executable.read_bytes()
    image, report = old.prepare(baseline, diagnostic, old.ROOT_PIN)
    for path, data in {**captured, **dependencies, **kernel, old.ACCEPTED_ROOT: baseline}.items():
        if path.read_bytes() != data:
            raise ValueError('Build input changed: '+str(path))
    expected = []
    files = old.files_from(image)
    for row in rows:
        actual = dict(row)
        if row['path'] == old.INSTALL_PATH:
            actual.update(bytes=len(diagnostic), sha256=old.sha(diagnostic))
        expected.append(actual)
    report.update(schema_version=2, modes=['identity', 'unix', 'inet'],
                  scope='Unstaged v2: fixed mounted-root identity followed by separately admitted sockets',
                  commands=commands, sdk=str(sdk), compiler_version=old.run([clang, '--version']).splitlines()[0],
                  source_inputs_sha256={str(p): old.sha(data) for p, data in captured.items()},
                  sdk_headers_sha256={str(p): old.sha(data) for p, data in dependencies.items()},
                  kernel_sha256=old.metadata.KERNEL_SHA, kernel_build_sha256=old.metadata.BUILD_SHA,
                  linked_sysent=wiring, identity_catalog=expected,
                  identity_max_calls=2048, identity_max_file_bytes=2097152,
                  identity_max_read_steps_per_file=1024, self_digest_compared_externally=True,
                  kernel_syscall_hang_contained=False, external_traffic=False,
                  interface_or_route_mutations=False, bearssl_source_commit=BEARSSL_COMMIT)
    if files[old.INSTALL_PATH] != (diagnostic, 0o555):
        raise ValueError('Installed helper bytes mismatch')
    for name, data in (('ramdisk.bin', image), ('manifest.json',
                       (json.dumps(report, indent=2, sort_keys=True)+'\n').encode())):
        with (output/name).open('xb') as stream:
            stream.write(data)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    report = build(args.output_dir)
    print(json.dumps({key: report[key] for key in ('output_sha256', 'output_bytes', 'output_nodes', 'pi_executed')}))


if __name__ == '__main__':
    main()
