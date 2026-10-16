#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Offline next root: real Apple pwd, crypto KAT, Darwin command paths and PATH."""
import argparse
import difflib
import json
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile
try:
    from . import root_capacity_profile as profile
    from . import prepare_socket_identity_root as identity
    from .prepare_pid1 import inspect as inspect_macho
except ImportError:
    import root_capacity_profile as profile
    import prepare_socket_identity_root as identity
    from prepare_pid1 import inspect as inspect_macho

ROOT = profile.ROOT
BASE = ROOT / 'build/rpi5/root-capacity-rp1-ssh-20261013-bounded'
BASE_MANIFEST = '7d3c5240cd9b57b9634e2a9e86183a899b7c45823cce26bd12af3ec457f2d9f4'
BASE_IMAGE = '18b2213c02353ea6f41baad9af6e5be0df7eadf31b61a19620c023b96f375340'
PWD = ROOT / 'build/rpi5/apple-current-commands-qg7qd51g'
PWD_MANIFEST = '58f43461d7f9768400afe01972ad409e9c88845655e1eaeddd378c75f109a1c1'
CRYPTO = ROOT / 'build/rpi5/apple-ssh-crypto-_qsv492k'
CRYPTO_MANIFEST = '4a2e8e7303fe1d0f28c5a634ca04d8e132fb50350734b8a113f7180d7d2176ee'
RECOVERY = ROOT / 'build/rpi5/userland-shell-appendfix-20261011'
RECOVERY_MANIFEST = 'd662b4a43c6e4cd791afb538583f6c374845f4570f138cf191c2a9eb0760c803'
IDENTITY = '/usr/local/libexec/xnu/socketprobe'
CANONICAL_PATH = '/usr/bin:/bin:/usr/sbin:/sbin'
ALIASES = {'/usr/bin/uname': '/bin/uname', '/usr/bin/hexdump': '/bin/hexdump',
    '/usr/bin/wc': '/bin/wc', '/usr/local/libexec/xnu/statprobe': '/bin/statprobe'}
SOURCE = ROOT / 'tools/rpi5/user'


def sha(path): return profile.sha(path.read_bytes())


def verify(pins):
    for name, value in pins.items():
        if sha(Path(name)) != value: raise ValueError('Next-root input changed: ' + name)


def receipt(path, digest):
    if sha(path) != digest: raise ValueError('Frozen next-root receipt changed: ' + str(path))
    return json.loads(path.read_text())


def replay_equal(a, b):
    """ld derives LC_UUID from the output path; compare every other actual byte."""
    def normalized(raw):
        result = bytearray(raw); offset = 32; count = 0
        for _ in range(struct.unpack_from('<I', raw, 16)[0]):
            cmd, size = struct.unpack_from('<II', raw, offset)
            if size < 8 or offset + size > len(raw): raise ValueError('Invalid replay Mach-O')
            if cmd == 0x1b:
                if size != 24: raise ValueError('Invalid UUID command')
                result[offset + 8:offset + 24] = bytes(16); count += 1
            offset += size
        if count != 1: raise ValueError('Expected exactly one replay UUID')
        return result
    return normalized(a) == normalized(b)


def derive_recovery(name):
    original = (SOURCE / name).read_text()
    if original.count('"PATH=/bin"') != 1: raise ValueError('Recovery PATH source changed')
    result = original.replace('"PATH=/bin"', '"PATH=' + CANONICAL_PATH + '"')
    if name == 'shell.c':
        start = result.index('    if (slash) {', result.index('static _Noreturn void execute('))
        end = result.index('    rt_error(name, error);', start)
        result = result[:start] + '''    rt_copy(pwd_env, sizeof(pwd_env), "PWD=");
    rt_copy(pwd_env + 4, sizeof(pwd_env) - 4, cwd);
    char *env[] = {pwd_env, "PATH=''' + CANONICAL_PATH + '''", "HOME=/", "TERM=dumb", 0};
    long error = -2;
    if (slash) {
        if (sh_path(path, sizeof(path), cwd, name)) rt_exit(126);
        error = rt_call(59, (long)path, (long)c->argv, (long)env, 0, 0, 0);
    } else {
        const char *directories[] = {"/usr/bin/", "/bin/", "/usr/sbin/", "/sbin/"};
        for (unsigned i = 0; i < sizeof(directories) / sizeof(directories[0]); i++) {
            size_t prefix = rt_len(directories[i]);
            if (rt_len(name) + prefix + 1 > sizeof(path)) rt_exit(126);
            rt_copy(path, sizeof(path), directories[i]);
            rt_copy(path + prefix, sizeof(path) - prefix, name);
            error = rt_call(59, (long)path, (long)c->argv, (long)env, 0, 0, 0);
            /* Only absent path components permit another bounded lookup. */
            if (error != -2 && error != -20) break;
        }
    }
''' + result[end:]
    return original, result


def run(command, output, label, records):
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=60)
    (output / (label + '.stdout')).write_text(result.stdout)
    (output / (label + '.stderr')).write_text(result.stderr)
    records.append(dict(command=command, returncode=result.returncode))
    if result.returncode: raise ValueError('Next-root command failed: ' + label + ': ' + result.stderr)
    return result.stdout


def dependency_command(args):
    result, skip = [], False
    for token in args:
        if skip: skip = False
        elif token == '-o': skip = True
        elif token != '-c': result.append(token)
    return result


def compile_actual(args, output, label, records, pins):
    def decode(text):
        return {str(Path(p).resolve()): sha(Path(p).resolve())
            for p in shlex.split(text.replace('\\\n', ' ').partition(':')[2])}
    before = decode(run(dependency_command(args) + ['-M'], output, label + '-dependencies', records))
    depfile = output / (label + '.d')
    run(args + ['-MD', '-MF', str(depfile)], output, label, records)
    if before != decode(depfile.read_text()): raise ValueError('Actual compiler dependency drift')
    for name, digest in before.items():
        if name in pins and pins[name] != digest: raise ValueError('Conflicting build input')
        pins[name] = digest


def build():
    prior = receipt(BASE / 'manifest.json', BASE_MANIFEST)
    pwd = receipt(PWD / 'manifest.json', PWD_MANIFEST)
    crypto = receipt(CRYPTO / 'manifest.json', CRYPTO_MANIFEST)
    recovery = receipt(RECOVERY / 'manifest.json', RECOVERY_MANIFEST)
    original_raw = (BASE / 'ramdisk.bin').read_bytes()
    if profile.sha(original_raw) != BASE_IMAGE: raise ValueError('Baseline root changed')
    original = profile.files_from(original_raw)
    pins = dict(prior['inputs_sha256'])
    for m in (pwd, crypto):
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, digest in m[key].items():
                if name in pins and pins[name] != digest: raise ValueError('Conflicting utility pin')
                pins[name] = digest
    for directory in (BASE, PWD, CRYPTO, RECOVERY):
        pins[str(directory / 'manifest.json')] = sha(directory / 'manifest.json')
    for path in (BASE / 'ramdisk.bin', Path(__file__).resolve(), Path(profile.__file__).resolve(),
        Path(identity.__file__).resolve(), Path(identity.old.__file__).resolve(),
        Path(inspect_macho.__code__.co_filename), profile.PACKER):
        pins[str(path)] = sha(path)
    for name in ('init.c', 'shell.c', 'runtime.h', 'parser.h'):
        path = SOURCE / name
        if recovery['source_inputs_sha256'][str(path)] != sha(path):
            raise ValueError('Accepted recovery source changed: ' + name)
        pins[str(path)] = sha(path)
    old_link = recovery['commands'][-1]
    for token in old_link:
        if token.endswith('.o'): pins[token] = sha(Path(token))
    verify(pins)
    output = Path(tempfile.mkdtemp(prefix='root96-command-batch-', dir=ROOT / 'build/rpi5'))
    commands = []
    replay = [str(output / 'recovery-baseline') if p == str(RECOVERY / 'userland') else p for p in old_link]
    run(replay, output, 'baseline-relink', commands)
    if not replay_equal((output / 'recovery-baseline').read_bytes(), original['/sbin/launchd'][0]) or \
        original['/bin/sh'] != original['/sbin/launchd']:
        raise ValueError('Existing object set does not replay the actual accepted recovery binary')
    replacements = {str(RECOVERY / 'userland'): str(output / 'recovery')}
    for name in ('init.c', 'shell.c'):
        before, after = derive_recovery(name)
        copied = output / name; copied.write_text(after)
        (output / (name + '.diff')).write_text(''.join(difflib.unified_diff(
            before.splitlines(True), after.splitlines(True), fromfile='accepted/' + name, tofile=name)))
        args = next(list(c) for c in recovery['commands'] if str(SOURCE / name) in c)
        new_object = output / (Path(name).stem + '.o')
        replacements[args[-1]] = str(new_object)
        args[args.index(str(SOURCE / name))] = str(copied)
        args[-1] = str(new_object)
        args[1:1] = ['-iquote', str(SOURCE), '-mcpu=cortex-a76']
        compile_actual(args, output, Path(name).stem, commands, pins)
    run([replacements.get(x, x) for x in old_link], output, 'recovery-link', commands)
    if run(['xcrun', 'nm', '-u', str(output / 'recovery')], output, 'recovery-undefined', commands).strip():
        raise ValueError('Unresolved recovery symbols')
    recovery_raw = (output / 'recovery').read_bytes(); inspect_macho(recovery_raw)
    if ('PATH=' + CANONICAL_PATH).encode() + b'\0' not in recovery_raw:
        raise ValueError('Actual child PATH absent')
    expanded = dict(original)
    for canonical, alias in ALIASES.items(): expanded[canonical] = original[alias]
    additions = {'/bin/pwd': (PWD / 'pwd').read_bytes(),
        '/usr/local/libexec/xnu/sshcryptoprobe': (CRYPTO / 'sshcryptoprobe').read_bytes()}
    for path, raw in additions.items():
        if path in expanded: raise ValueError('New utility path collides')
        inspect_macho(raw); expanded[path] = (raw, 0o555)
    expanded['/etc/paths'] = (('\n'.join(CANONICAL_PATH.split(':')) + '\n').encode(), 0o444)
    expanded['/sbin/launchd'] = expanded['/bin/sh'] = (recovery_raw, 0o555)
    provisional, layout = profile.build(expanded)
    del provisional
    rows = []
    for entry in layout['entries']:
        path, directory = entry['path'], entry['type'] == 'directory'
        rows.append(dict(path=path, mode=entry['mode'] | (0o40000 if directory else 0o100000),
            bytes=0 if directory or path == IDENTITY else len(expanded[path][0]),
            sha256='' if directory else None if path == IDENTITY else profile.sha(expanded[path][0])))
    (output / 'rootidentity_catalog.h').write_text(identity.header(rows))
    args = list(prior['commands'][0])
    old_object = args[-1]; new_object = output / 'rootidentity.o'
    args = ['-I' + str(output) if x == '-I' + str(BASE) else x for x in args]
    if '-I' + str(output) not in args: raise ValueError('Actual identity include directory changed')
    args[-1] = str(new_object)
    compile_actual(args, output, 'identity', commands, pins)
    old_identity_link = prior['commands'][-1]
    diagnostic = output / 'socketprobe'
    link = [str(new_object) if x == old_object else str(diagnostic) if x == str(BASE / 'socketprobe') else x
        for x in old_identity_link]
    for token in old_identity_link:
        if token.endswith('.o'): pins[token] = sha(Path(token))
    run(link, output, 'identity-link', commands)
    if run(['xcrun', 'nm', '-u', str(diagnostic)], output, 'identity-undefined', commands).strip():
        raise ValueError('Unresolved identity symbols')
    diagnostic_raw = diagnostic.read_bytes(); inspect_macho(diagnostic_raw)
    expanded[IDENTITY] = (diagnostic_raw, 0o555)
    raw, layout = profile.build(expanded)
    if profile.files_from(raw) != expanded or profile.inspect(raw) != layout:
        raise ValueError('Next-root round trip mismatch')
    changed = {IDENTITY, '/bin/sh', '/sbin/launchd'}
    for path, value in original.items():
        if path not in changed and expanded[path] != value: raise ValueError('Unrelated baseline file changed')
    for row in rows:
        if row['path'] == IDENTITY: row.update(bytes=len(diagnostic_raw), sha256=profile.sha(diagnostic_raw))
    verify(pins)
    (output / 'ramdisk.bin').write_bytes(raw)
    report = dict(profile='rpi5-root96-current-command-batch-v1', node_capacity=96,
        baseline=str(BASE), input_root_sha256=BASE_IMAGE, output_sha256=profile.sha(raw),
        output_bytes=len(raw), output_nodes=len(layout['entries']), identity_catalog=rows,
        identity_self_digest_compared_externally=True, commands=commands, inputs_sha256=pins,
        canonical_path=CANONICAL_PATH, compatibility_regular_files=ALIASES,
        added_files_sha256={p: profile.sha(v[0]) for p, v in expanded.items() if p not in original},
        changed_files_sha256={p: profile.sha(expanded[p][0]) for p in changed},
        unchanged_files_sha256={p: profile.sha(v[0]) for p, v in original.items() if p not in changed},
        kernel=prior['kernel'], kernel_sha256=prior['kernel_sha256'],
        kernel_manifest=prior['kernel_manifest'], kernel_manifest_sha256=prior['kernel_manifest_sha256'],
        apple_pwd_manifest_sha256=PWD_MANIFEST, crypto_manifest_sha256=CRYPTO_MANIFEST,
        crypto_vectors=crypto['vectors'], crypto_transport=False, date_included=False,
        source_baseline_recovery_replay_except_uuid=True, frozen_zsh_unchanged=True,
        default_init_and_shell_unchanged=False, recovery_change='Only canonical PATH and bounded command lookup',
        installed=False, pi_executed=False, ssh_proven=False, networking_proven=False,
        sd_actions=0, serial_actions=0, reboots=0,
        generated_sha256={str(p): sha(p) for p in output.iterdir() if p.is_file()})
    (output / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return output, report


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    output, result = build()
    print(json.dumps(dict(package=str(output), **{k: result[k] for k in
        ('output_sha256', 'output_bytes', 'output_nodes', 'canonical_path')}), indent=2))
