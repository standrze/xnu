#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Close two genuine Apple leaf providers; retain the real six-EVP target gap."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
try:
    from . import build_apple_ssh_packet_probe as packet
except ImportError:
    import build_apple_ssh_packet_probe as packet

ROOT, sha = packet.ROOT, packet.sha
BASE = ROOT / 'build/rpi5/apple-ssh-packet-v9xoz8gd'
BASE_SHA = '725eede29cd6412f4fefb8b8f3f742999f20e8bc3b30ff3c1b5316dbae8544f4'
LIBC = ROOT / 'build/rpi5/apple-libc-main-candidate-20261013'
LIBC_COMMIT = '71bbe350ab79eef58113991d817ccc6165061a64'
MEMSET_PACKAGE = ROOT / 'build/rpi5/apple-ssh-probe-v2-1tmwow6z'
MEMSET_RECEIPT = '623944b390cb778643ad9c8e8939e285a2ebb11eabee5a1d23896a103878d038'
GAPS = ['_EVP_CIPHER_CTX_free', '_EVP_CIPHER_CTX_get_iv_length', '_EVP_CIPHER_CTX_new',
        '_EVP_Cipher', '_EVP_CipherInit', '_EVP_chacha20']


def build():
    if sha(BASE / 'manifest.json') != BASE_SHA or sha(MEMSET_PACKAGE / 'manifest.json') != MEMSET_RECEIPT:
        raise ValueError('Frozen SSH packet/runtime prerequisite changed')
    old = json.loads((BASE / 'manifest.json').read_text())
    runtime = json.loads((MEMSET_PACKAGE / 'manifest.json').read_text())
    pins = {}
    for report in (old, runtime):
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, value in report[key].items():
                if name in pins and pins[name] != value: raise ValueError('Conflicting leaf input')
                pins[name] = value
    source = LIBC / 'string/FreeBSD/timingsafe_bcmp.c'
    memset = LIBC / 'string/NetBSD/memset_s.c'
    adornments = ROOT / 'tools/rpi5/user/ssh_runtime_build.h'
    test = ROOT / 'tools/rpi5/tests/ssh_leaf_host.c'
    for p in (BASE / 'manifest.json', MEMSET_PACKAGE / 'manifest.json', Path(__file__).resolve(),
              source, memset, test, adornments): pins[str(p)] = sha(p)
    if subprocess.check_output(['git', '-C', str(LIBC), 'rev-parse', 'HEAD'], text=True).strip() != LIBC_COMMIT:
        raise ValueError('Unexpected current Apple Libc checkout')
    for p in (source, memset):
        if subprocess.check_output(['git', '-C', str(LIBC), 'show', 'HEAD:' + str(p.relative_to(LIBC))]) != p.read_bytes():
            raise ValueError('Apple leaf source modified')
    legacy = packet.primitive.runtime.USERLAND / 'upstream/apple-Libc-1752.120.2/string/NetBSD/memset_s.c'
    if legacy.read_bytes() != memset.read_bytes(): raise ValueError('Reused memset_s differs from current original source')
    def verify():
        for name, value in pins.items():
            if sha(Path(name)) != value: raise ValueError('SSH leaf input drift: ' + name)
    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-ssh-packet-leaves-', dir=ROOT / 'build/rpi5'))
    commands, headers = [], {}
    def run(command, label, allowed=False):
        args = list(map(str, command))
        result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=60)
        (out / (label + '.stdout')).write_text(result.stdout)
        (out / (label + '.stderr')).write_text(result.stderr)
        commands.append(dict(command=args, returncode=result.returncode,
            stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if not allowed and (result.returncode or result.stderr): raise ValueError('Leaf step failed: ' + label + ': ' + result.stderr)
        return result
    def compile(flags, source, label):
        def deps(raw):
            return {str(Path(p).resolve()): sha(Path(p).resolve())
                for p in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}
        before = deps(run(flags + ['-M', source], label + '-dependencies').stdout)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        run(flags + ['-MD', '-MF', dep, '-c', source, '-o', obj], label)
        if deps(dep.read_text()) != before: raise ValueError('Leaf compile dependency drift')
        headers.update(before); return obj
    native_cmd = next(r['command'] for r in old['commands'] if r['stdout'].endswith('/probe-native.stdout'))
    target_cmd = next(r['command'] for r in old['commands'] if r['stdout'].endswith('/probe-target.stdout'))
    native = native_cmd[:native_cmd.index('-MD')] + ['-include', str(adornments)]
    target = [x for x in target_cmd[:target_cmd.index('-MD')] if x != '-Dmain=darwin_network_command_main']
    target += ['-include', str(adornments)]
    apple_native = compile(native, source, 'apple-timingsafe-native')
    apple_target = compile(target, source, 'apple-timingsafe-target')
    memset_native = compile(native, memset, 'apple-memset-native')
    native_test = compile(native, test, 'leaf-test-native')
    native_exe = out / 'ssh-leaves-host'
    run(native + [native_test, apple_native, memset_native, '-o', native_exe], 'leaves-host-link')
    leaf = run([native_exe], 'leaves-host-run')
    if leaf.stdout != 'RPI5XNU:SSHLEAF:PASS COMPARES=131842 MEMSET_CASES=6 NO_TIMING_OR_TRANSPORT_PROOF\n':
        raise ValueError('Incomplete Apple leaf tests: ' + leaf.stdout)
    # Execute the original complete packet test with both actual Apple leaves,
    # not the host LibSystem providers it happened to resolve in the baseline.
    host_link = next(r['command'] for r in old['commands'] if r['stdout'].endswith('/host-link.stdout'))
    host = out / 'sshpacketprobe-apple-leaves-host'
    updated_host = list(host_link)
    updated_host[updated_host.index('-o') + 1] = str(host)
    updated_host += list(map(str, (apple_native, memset_native)))
    run(updated_host, 'packet-host-link')
    result = run([host], 'packet-host-run')
    if result.stdout != old['host_stdout']: raise ValueError('Packet tests regressed with Apple leaves')
    archive = out / 'libapple-ssh-packet-cipher-leaves.a'
    archive_cmd = next(r['command'] for r in old['commands'] if r['stdout'].endswith('/target-archive.stdout'))
    members = archive_cmd[4:] + [str(apple_target), str(MEMSET_PACKAGE / '5-memset_s.o')]
    run(['xcrun', 'ar', 'rcs', archive, *members], 'target-archive')
    target_link = next(list(r['command']) for r in old['commands'] if r['stdout'].endswith('/target-link.stdout'))
    target_link[target_link.index(str(BASE / 'libapple-ssh-packet-cipher.a'))] = str(archive)
    target_link[target_link.index('-o') + 1] = str(out / 'sshpacketprobe')
    target_link += ['-map', str(out / 'link.map')]
    attempt = run(target_link, 'target-link', True)
    missing = sorted(re.findall(r'^\s+"([^"]+)", referenced from:', attempt.stderr, re.M))
    if not attempt.returncode or missing != GAPS: raise ValueError('Unexpected actual target closure: ' + attempt.stderr)
    symbols = run(['xcrun', 'nm', '-g', archive], 'target-symbols').stdout
    for symbol in ('_timingsafe_bcmp', '_memset_s'):
        if len(re.findall(r'^[0-9a-f]+ T ' + symbol + '$', symbols, re.M)) != 1:
            raise ValueError('Not exactly one actual Apple executable leaf definition: ' + symbol)
    verify()
    for name, value in headers.items():
        if sha(Path(name)) != value: raise ValueError('Actual leaf header changed')
    report = dict(profile='original-apple-ssh-packet-two-leaves-v1', source_inputs_sha256=pins,
        headers_sha256=headers, commands=commands, current_libc_commit=LIBC_COMMIT,
        reused_memset_object=str(MEMSET_PACKAGE / '5-memset_s.o'),
        reused_memset_source_identical_to_current=True, original_feature_config_unchanged=True,
        original_packet_cipher_unchanged=True, native_asan_ubsan_pass=True,
        leaf_stdout=leaf.stdout, packet_stdout=result.stdout, compare_cases=131842,
        memset_cases=6, valid_packet_cases=48, rejected_packet_cases=5036,
        target_archive=str(archive), target_link_complete=False, target_missing_symbols=missing,
        target_link_error=attempt.stderr, host_crypto_library=old['host_crypto_library'],
        target_crypto_provider_implemented=False, entropy_qualified=False,
        timing_measurement=False, ssh_transport=False, pi_executed=False, installed=False,
        generated_sha256={str(p): sha(p) for p in out.iterdir() if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return out, report


if __name__ == '__main__':
    output, report = build()
    print(json.dumps(dict(package=str(output), native_asan_ubsan_pass=True,
        target_missing_symbols=report['target_missing_symbols']), indent=2))
