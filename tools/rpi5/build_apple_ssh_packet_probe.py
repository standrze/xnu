#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Test original Apple SSH packet cipher on host; expose target crypto gap."""
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
try:
    from . import build_apple_ssh_crypto_probe as primitive
except ImportError:
    import build_apple_ssh_crypto_probe as primitive

ROOT, sha = primitive.ROOT, primitive.sha
BASE = ROOT / 'build/rpi5/apple-ssh-crypto-_qsv492k'
BASE_SHA = '4a2e8e7303fe1d0f28c5a634ca04d8e132fb50350734b8a113f7180d7d2176ee'
SOURCE = ROOT / 'tools/rpi5/user/sshpacketprobe.c'
CRYPTO = Path('/opt/homebrew/opt/openssl@3/lib/libcrypto.3.dylib').resolve()


def build():
    if sha(BASE / 'manifest.json') != BASE_SHA:
        raise ValueError('Primitive manifest changed')
    prior = json.loads((BASE / 'manifest.json').read_text())
    pins = prior['source_inputs_sha256'] | prior['headers_sha256'] | prior['generated_sha256']
    for p in (BASE / 'manifest.json', SOURCE, Path(__file__).resolve(), CRYPTO): pins[str(p)] = sha(p)
    for p, digest in pins.items():
        if sha(Path(p)) != digest: raise ValueError('Packet dependency changed: ' + p)
    out = Path(tempfile.mkdtemp(prefix='apple-ssh-packet-', dir=ROOT / 'build/rpi5'))
    commands, headers = [], {}
    def run(args, label, allowed_failure=False):
        args = list(map(str, args)); result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=60)
        (out / (label + '.stdout')).write_text(result.stdout); (out / (label + '.stderr')).write_text(result.stderr)
        commands.append(dict(command=args, returncode=result.returncode, stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if not allowed_failure and (result.returncode or result.stderr): raise ValueError('Packet step failed: ' + str(out / (label + '.stderr')))
        return result
    def deps(raw):
        return {str(Path(p).resolve()): sha(Path(p).resolve()) for p in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}
    def compile_unit(flags, source, name):
        before = deps(run(flags + ['-M', source], name + '-dependencies').stdout)
        obj = out / (name + '.o'); dep = out / (name + '.d')
        run(flags + ['-MD', '-MF', dep, '-c', source, '-o', obj], name)
        if deps(dep.read_text()) != before: raise ValueError('Actual packet compile dependencies differ')
        headers.update(before); return obj
    native_command = next(r['command'] for r in prior['commands'] if r['stdout'].endswith('/probe-native.stdout'))
    native = native_command[:native_command.index('-MD')]
    target_command = next(r['command'] for r in prior['commands'] if r['stdout'].endswith('/probe-target.stdout'))
    target = [v for v in target_command[:target_command.index('-MD')] if v != '-Dmain=darwin_network_command_main']
    original = primitive.runtime.previous.SOURCE
    sources = (original / 'cipher-chachapoly-libcrypto.c', original / 'openbsd-compat/timingsafe_bcmp.c',
               original / 'openbsd-compat/freezero.c', original / 'openbsd-compat/explicit_bzero.c')
    host_objects, target_objects = [], []
    for source in sources:
        if str(source) not in pins: raise ValueError('Unpinned original cipher provider')
        host_objects.append(compile_unit(native, source, source.stem + '-native'))
        target_objects.append(compile_unit(target, source, source.stem + '-target'))
    host_probe = compile_unit(native, SOURCE, 'probe-native')
    target_probe = compile_unit(target + ['-Dmain=darwin_network_command_main'], SOURCE, 'probe-target')
    host = out / 'sshpacketprobe-host'
    run(native + [host_probe, *host_objects, BASE / 'poly1305.c.native.o', CRYPTO, '-o', host], 'host-link')
    result = run([host], 'host-run')
    if result.stdout != 'RPI5XNU:SSHPACKET:PASS CASES=48 REJECTED=5036 NO_TRANSPORT_OR_ENTROPY_PROOF\n':
        raise ValueError('Incomplete native packet tests: ' + result.stdout)
    archive = out / 'libapple-ssh-packet-cipher.a'
    run(['xcrun', 'ar', 'rcs', archive, *target_objects, BASE / 'poly1305.c.o'], 'target-archive')
    attempted = run(['xcrun', 'ld', '-arch', 'arm64', '-platform_version', 'macos', '26.0', '27.0',
        '-static', '-e', '_start', '-dead_strip', '-no_adhoc_codesign', '-no_uuid', '-o', out / 'sshpacketprobe',
        target_probe, primitive.BASE / 'argv-entry.o', archive, primitive.runtime.ABI,
        *primitive.runtime.previous.ARCHIVES], 'target-link', allowed_failure=True)
    if attempted.returncode == 0: raise ValueError('Unexpected target closure; independently audit before use')
    if 'Undefined symbols for architecture arm64:' not in attempted.stderr or '_EVP_' not in attempted.stderr:
        raise ValueError('Unexpected target link failure: ' + attempted.stderr)
    for p, digest in (pins | headers).items():
        if sha(Path(p)) != digest: raise ValueError('Packet input drift: ' + p)
    report = dict(profile='original-apple-ssh-packet-cipher-host-v1', source_inputs_sha256=pins, headers_sha256=headers,
        commands=commands, host_crypto_library=str(CRYPTO), host_crypto_sha256=sha(CRYPTO),
        original_feature_config_unchanged=True, original_libcrypto_cipher_source_unchanged=True,
        native_asan_ubsan_pass=True, valid_cases=48, rejected_tamper_or_sequence_cases=5036,
        host_stdout=result.stdout, target_archive=str(archive), target_link_complete=False,
        target_link_error=attempted.stderr, entropy_qualified=False, live_keys=False,
        ssh_transport=False, pi_execution=False, scope='Original packet-cipher host semantics; target still needs real EVP/libcrypto runtime',
        generated_sha256={str(p): sha(p) for p in out.iterdir() if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return out, report


if __name__ == '__main__':
    out, report = build()
    print(json.dumps(dict(package=str(out), native_asan_ubsan_pass=True, target_link_complete=False)))
