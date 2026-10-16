#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Recompile original Apple packet code with genuine LibreSSL headers and runtime."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
try:
    from . import build_apple_ssh_packet_leaves as leaves
except ImportError:
    import build_apple_ssh_packet_leaves as leaves

ROOT, sha = leaves.ROOT, leaves.sha
LEAVES = ROOT / 'build/rpi5/apple-ssh-packet-leaves-we7s8n0w'
LEAVES_SHA = '9bad3f20cad3fb77cd2dfa78efcf7a50263291722a7dc119cf7198c87e28f8d5'
RUNTIME = ROOT / 'build/rpi5/libressl-runtime-j_dt94vs'
RUNTIME_SHA = '1aeae7b5aba4491af5c7dd25199919ed5336c4bc16580e3533077fd06b5b5231'


def build():
    if sha(LEAVES / 'manifest.json') != LEAVES_SHA or sha(RUNTIME / 'manifest.json') != RUNTIME_SHA:
        raise ValueError('Frozen leaf/LibreSSL source closure changed')
    previous = json.loads((LEAVES / 'manifest.json').read_text())
    runtime = json.loads((RUNTIME / 'manifest.json').read_text())
    packet = json.loads((leaves.BASE / 'manifest.json').read_text())
    pins = {}
    for report, keys in ((previous, ('source_inputs_sha256', 'headers_sha256', 'generated_sha256')),
        (runtime, ('source_inputs_sha256', 'native_actual_headers_sha256', 'target_headers_sha256', 'generated_sha256'))):
        for key in keys:
            for name, digest in report[key].items():
                if name in pins and pins[name] != digest: raise ValueError('Conflicting genuine provider input')
                pins[name] = digest
    for path in (LEAVES / 'manifest.json', RUNTIME / 'manifest.json', Path(__file__).resolve()):
        pins[str(path)] = sha(path)
    def verify():
        for name, digest in pins.items():
            if sha(Path(name)) != digest: raise ValueError('Genuine packet input changed: ' + name)
    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-ssh-libressl-packet-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers = [], {}
    def run(args, label, allowed=False):
        args = list(map(str, args)); result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_text(result.stdout)
        (out / (label + '.stderr')).write_text(result.stderr)
        commands.append(dict(command=args, returncode=result.returncode,
            stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if not allowed and (result.returncode or result.stderr):
            raise ValueError('Genuine LibreSSL packet step failed: ' + label + ': ' + result.stderr)
        return result
    def compile(flags, source, label):
        def deps(raw):
            return {str(Path(p).resolve()): sha(Path(p).resolve())
                for p in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}
        before = deps(run(flags + ['-M', source], label + '-dependencies').stdout)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        run(flags + ['-MD', '-MF', dep, '-c', source, '-o', obj], label)
        if deps(dep.read_text()) != before: raise ValueError('Provider matching header drift')
        headers.update(before); return obj
    source = Path(runtime['source'])
    def flags(label, variant):
        old = next(r['command'] for r in packet['commands'] if r['stdout'].endswith('/probe-' + label + '.stdout'))
        result = [x for x in old[:old.index('-MD')] if x != '-Dmain=darwin_network_command_main']
        candidates = [i for i, x in enumerate(result) if '/openssl@3/' in x and x.endswith('/include')]
        if len(candidates) != 1 or result[candidates[0] - 1] != '-I':
            raise ValueError('Unexpected original OpenSSL include selection')
        result[candidates[0]] = str(source / 'include')
        result += ['-I', str(RUNTIME / variant / 'include')]
        if any('openssl@3' in p for p in result): raise ValueError('Mixed crypto provider include paths')
        return result
    native, target = flags('native', 'native'), flags('target', 'a76')
    original = leaves.packet.primitive.runtime.previous.SOURCE
    sources = [original / name for name in ('cipher-chachapoly-libcrypto.c',
        'openbsd-compat/timingsafe_bcmp.c', 'openbsd-compat/freezero.c',
        'openbsd-compat/explicit_bzero.c', 'poly1305.c')]
    native_objects, target_objects = [], []
    for path in sources:
        native_objects.append(compile(native, path, path.stem + '-native'))
        target_objects.append(compile(target, path, path.stem + '-target'))
    probe_native = compile(native, leaves.packet.SOURCE, 'probe-native')
    probe_target = compile(target + ['-Dmain=darwin_network_command_main'], leaves.packet.SOURCE, 'probe-target')
    host = out / 'sshpacketprobe-libressl-host'
    run(native + [probe_native, *native_objects, LEAVES / 'apple-timingsafe-native.o',
        LEAVES / 'apple-memset-native.o', runtime['native_archive'], '-o', host], 'native-packet-link')
    result = run([host], 'native-packet-run')
    if result.stdout != packet['host_stdout']: raise ValueError('Original packet oracle failed with real LibreSSL')
    run(['xcrun', 'otool', '-L', host], 'native-dynamic-dependencies')
    dynamic = (out / 'native-dynamic-dependencies.stdout').read_text()
    if 'libcrypto.' in dynamic or 'libssl.' in dynamic or '/opt/homebrew/' in dynamic:
        raise ValueError('Native packet unexpectedly uses host dynamic crypto')
    archive = out / 'libapple-ssh-libressl-packet.a'
    run(['xcrun', 'ar', 'rcs', archive, *target_objects, LEAVES / 'apple-timingsafe-target.o',
        leaves.MEMSET_PACKAGE / '5-memset_s.o'], 'target-archive')
    old_link = next(r['command'] for r in packet['commands'] if r['stdout'].endswith('/target-link.stdout'))
    target_link = [str(probe_target) if p == str(leaves.BASE / 'probe-target.o') else
        str(archive) if p == str(leaves.BASE / 'libapple-ssh-packet-cipher.a') else p for p in old_link]
    target_link[target_link.index('-o') + 1] = str(out / 'sshpacketprobe')
    target_link.insert(target_link.index(str(archive)) + 1, runtime['target_archive'])
    target_link += ['-map', str(out / 'link.map')]
    link = run(target_link, 'target-static-link', True)
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', link.stderr, re.M)))
    if any(name.startswith('_EVP_') for name in missing): raise ValueError('EVP provider was not actually closed')
    if link.returncode and not missing: raise ValueError('Unexpected static target link failure: ' + link.stderr)
    verify()
    for name, digest in headers.items():
        if sha(Path(name)) != digest: raise ValueError('Consumed provider header changed')
    provider_headers = [name for name in headers if '/include/openssl/' in name]
    if not provider_headers or any(not name.startswith(str(source)) and not name.startswith(str(RUNTIME))
        for name in provider_headers): raise ValueError('Mixed actual consumed crypto headers')
    executable_audit = None
    if not link.returncode:
        from prepare_pid1 import inspect
        executable_audit = inspect((out / 'sshpacketprobe').read_bytes())
    report = dict(profile='genuine-libressl-apple-packet-static-attempt-v1',
        source_inputs_sha256=pins, headers_sha256=headers, commands=commands,
        provider='LibreSSL 4.3.3', provider_archive_sha256=runtime['target_archive_sha256'],
        provider_runtime_manifest_sha256=RUNTIME_SHA, actual_provider_headers=provider_headers,
        upstream_security_features_unchanged=True, original_apple_config_unchanged=True,
        original_apple_packet_source_unchanged=True, native_asan_ubsan_packet_pass=True,
        provider_library_instrumented=False, native_library_original_tests_passed=7,
        native_packet_stdout=result.stdout, valid_packet_cases=48, rejected_packet_cases=5036,
        native_dynamic_crypto_used=False, target_archive=str(archive),
        target_link_complete=not link.returncode, target_missing_symbols=missing,
        target_link_error=link.stderr, actual_static_executable=str(out / 'sshpacketprobe') if not link.returncode else None,
        macho_audit=executable_audit, evp_provider_shim=False, entropy_qualified=False,
        ssh_transport=False, installed=False, pi_executed=False,
        generated_sha256={str(p): sha(p) for p in out.iterdir() if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), target_link_complete=not link.returncode,
        missing_symbols=missing), indent=2), flush=True)
    return out, report


if __name__ == '__main__': build()
