#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original Apple-distributed OpenSSH primitive KAT; build-only, no Pi I/O."""
import json
from pathlib import Path
import shlex
import subprocess
import tempfile

try:
    from . import build_apple_ssh_buffer_probe_v2 as runtime
    from .prepare_pid1 import inspect as inspect_macho
except ImportError:
    import build_apple_ssh_buffer_probe_v2 as runtime
    from prepare_pid1 import inspect as inspect_macho

ROOT = runtime.ROOT
BASE = ROOT / 'build/rpi5/apple-ssh-probe-v2-1tmwow6z'
BASE_SHA = '623944b390cb778643ad9c8e8939e285a2ebb11eabee5a1d23896a103878d038'
SOURCE = ROOT / 'tools/rpi5/user/sshcryptoprobe.c'
sha = runtime.previous.sha


def build():
    manifest = BASE / 'manifest.json'
    if sha(manifest) != BASE_SHA:
        raise ValueError('Preserved real static-runtime receipt changed')
    parent = json.loads(manifest.read_text())
    pins = parent['source_inputs_sha256'] | parent['headers_sha256'] | parent['generated_sha256']
    pins.update({str(manifest): BASE_SHA, str(SOURCE): sha(SOURCE),
                 str(Path(__file__).resolve()): sha(Path(__file__))})
    for path, digest in pins.items():
        if sha(Path(path)) != digest:
            raise ValueError('Preserved primitive input changed: ' + path)
    out = Path(tempfile.mkdtemp(prefix='apple-ssh-crypto-', dir=ROOT / 'build/rpi5'))
    commands, headers = [], {}

    def execute(args, label):
        args = list(map(str, args))
        result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=60)
        (out / (label + '.stdout')).write_text(result.stdout)
        (out / (label + '.stderr')).write_text(result.stderr)
        commands.append(dict(command=args, returncode=result.returncode,
                             stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if result.returncode:
            raise ValueError('Primitive build/test failed: ' + str(out / (label + '.stderr')))
        return result.stdout

    def dependencies(raw):
        names = shlex.split(raw.replace('\\\n', ' ').partition(':')[2])
        return {str(Path(p).resolve()): sha(Path(p).resolve()) for p in names}

    def compile_unit(flags, source, obj, label):
        before = dependencies(execute(flags + ['-M', source], label + '-dependencies'))
        dep = out / (label + '.d')
        execute(flags + ['-MD', '-MF', dep, '-c', source, '-o', obj], label)
        after = dependencies(dep.read_text())
        if before != after or any(p in headers and headers[p] != h for p, h in after.items()):
            raise ValueError('Actual primitive compiler dependency drift')
        headers.update(after)

    compile_rows = [r['command'] for r in parent['commands'] if '-c' in r['command'] and str(runtime.SOURCE) in r['command']]
    if len(compile_rows) != 1:
        raise ValueError('Ambiguous original target compiler command')
    reference = compile_rows[0]
    common = reference[:reference.index('-target')]
    target = common + ['-target', 'arm64-apple-darwin', '-mcpu=cortex-a76', '-ffreestanding', '-O2']
    native = common + ['-O1', '-g', '-fsanitize=address,undefined']
    target_objects, native_objects = [], []
    for name in ('chacha.c', 'poly1305.c'):
        source = runtime.previous.SOURCE / name
        if str(source) not in pins:
            raise ValueError('Original source absent from accepted pristine checkout')
        obj, host = out / (name + '.o'), out / (name + '.native.o')
        # ChaCha's two 16-byte constants intentionally omit a string terminator;
        # every access is fixed-width. Preserve the upstream bytes, not a NUL.
        flags = ['-Wno-unterminated-string-initialization'] if name == 'chacha.c' else []
        compile_unit(target + flags, source, obj, name + '-target')
        compile_unit(native + flags, source, host, name + '-native')
        target_objects.append(obj)
        native_objects.append(host)
    probe, host_probe = out / 'probe.o', out / 'probe.native.o'
    compile_unit(target + ['-Dmain=darwin_network_command_main'], SOURCE, probe, 'probe-target')
    compile_unit(native, SOURCE, host_probe, 'probe-native')
    host = out / 'sshcryptoprobe-host'
    execute(native + [host_probe, *native_objects, '-o', host], 'native-link')
    stdout = execute([host], 'native-run')
    expected = ('RPI5XNU:SSHCRYPTO:BEGIN ORIGINAL_CHACHA_POLY1305 PUBLIC_VECTORS NO_KEYS\n'
                'RPI5XNU:SSHCRYPTO:PASS TWO_KATS BOUNDARIES IN_PLACE NOT_SSH_ENTROPY_OR_AEAD_PROOF\n')
    if stdout != expected:
        raise ValueError('Primitive host checks did not complete exactly')
    archive = out / 'libapple-openssh-chacha-poly1305.a'
    execute(['xcrun', 'ar', 'rcs', archive, *target_objects], 'archive')
    program, linkmap = out / 'sshcryptoprobe', out / 'link.map'
    execute(['xcrun', 'ld', '-arch', 'arm64', '-platform_version', 'macos', '26.0', '27.0',
             '-static', '-e', '_start', '-dead_strip', '-no_adhoc_codesign', '-no_uuid',
             '-map', linkmap, '-o', program, probe, BASE / 'argv-entry.o', archive,
             runtime.ABI, *runtime.previous.ARCHIVES], 'target-link')
    undefined = execute(['xcrun', 'nm', '-ju', program], 'undefined-symbols')
    if undefined.strip():
        raise ValueError('Target primitive executable contains undefined symbols')
    symbols = execute(['xcrun', 'nm', '-nm', program], 'symbols')
    for symbol in ('_chacha_keysetup', '_chacha_ivsetup', '_chacha_encrypt_bytes', '_poly1305_auth',
                   '_darwin_network_command_main', '_darwin_static_start', '_start'):
        if not any(line.endswith(' ' + symbol) for line in symbols.splitlines()):
            raise ValueError('Required real linked symbol absent: ' + symbol)
    macho = inspect_macho(program.read_bytes())
    for path, digest in (pins | headers).items():
        if sha(Path(path)) != digest:
            raise ValueError('Primitive input drift after link: ' + path)
    report = dict(profile='apple-openssh-primitive-probe-v1',
                  source_commit=runtime.previous.COMMIT, source_inputs_sha256=pins,
                  headers_sha256=headers, commands=commands, macho_audit=macho,
                  archive=str(archive), actual_static_executable=str(program),
                  static_link_complete=True, undefined_symbols=[],
                  native_host_asan_ubsan_pass=True, native_stdout=stdout,
                  vectors='https://www.rfc-editor.org/rfc/rfc8439#appendix-A.1 and #section-2.5.2',
                  chacha_scope='Original 64-bit nonce variant; all-zero state overlaps RFC test vector only',
                  upstream_sources_and_config_unchanged=True,
                  chacha_fixed_width_constant_warning_suppressed=True,
                  pi_executed=False, installed=False, crypto_in_ssh_transport=False,
                  entropy_qualified=False, aead_qualified=False,
                  scope='Two primitive KATs and 12 boundary/in-place round trips; not general crypto security, SSH or board proof')
    report['generated_sha256'] = {str(p): sha(p) for p in out.iterdir() if p.is_file()}
    with (out / 'manifest.json').open('x') as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write('\n')
    return report


if __name__ == '__main__':
    result = build()
    print(json.dumps({k: result[k] for k in ('actual_static_executable', 'static_link_complete',
                                          'native_host_asan_ubsan_pass', 'pi_executed')}))
