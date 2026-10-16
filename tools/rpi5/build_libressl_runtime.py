#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Out-of-tree real LibreSSL native tests and independent A76 static library."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / 'build/rpi5/libressl-4.3.3-input-X8xG1B'
INPUT_SHA = 'b353e87612288271f4db13317bfe189c135296524f806327175f7570ee32fad5'
SOURCE = INPUT / 'libressl-4.3.3'
CMAKE = Path('/opt/homebrew/bin/cmake').resolve()
TESTS = ('chachatest', 'poly1305test', 'evptest', 'evp_test', 'crypto_test',
         'evp_ecx_test', 'evp_pkey_cleanup')


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    manifest = INPUT / 'source-manifest.json'
    if sha(manifest) != INPUT_SHA: raise ValueError('Verified LibreSSL input receipt changed')
    source = json.loads(manifest.read_text())
    pins = source['source_files_sha256'] | source['generated_sha256']
    pins.update({str(manifest): INPUT_SHA, str(Path(__file__).resolve()): sha(Path(__file__)), str(CMAKE): sha(CMAKE)})
    def verify():
        for name, digest in pins.items():
            if sha(Path(name)) != digest: raise ValueError('Pristine LibreSSL input changed: ' + name)
    verify()
    out = Path(tempfile.mkdtemp(prefix='libressl-runtime-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    records, headers = [], {}
    def run(args, name):
        args = list(map(str, args)); print(name, flush=True)
        result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=900)
        (out / (name + '.stdout')).write_text(result.stdout)
        (out / (name + '.stderr')).write_text(result.stderr)
        records.append(dict(command=args, returncode=result.returncode, log=str(out / (name + '.stdout'))))
        if result.returncode: raise ValueError('LibreSSL real build/test failed: ' + name + ': ' + result.stderr[-2000:])
        return result.stdout
    compiler = subprocess.check_output(['xcrun', '--find', 'clang'], text=True).strip()
    sdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()
    common = [CMAKE, '-S', SOURCE, '-DBUILD_SHARED_LIBS=OFF', '-DLIBRESSL_SKIP_INSTALL=ON',
        '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '-DCMAKE_BUILD_TYPE=RelWithDebInfo',
        '-DCMAKE_C_COMPILER=' + compiler, '-DCMAKE_OSX_SYSROOT=' + sdk]
    native, target = out / 'native', out / 'a76'
    run(common + ['-B', native], 'native-configure')
    run([CMAKE, '--build', native, '--parallel', '4', '--target', *TESTS], 'native-build')
    ctest = CMAKE.with_name('ctest')
    test_output = run([ctest, '--test-dir', native, '--output-on-failure', '--parallel', '4',
        '-R', '^(' + '|'.join(TESTS) + ')$'], 'native-original-tests')
    if '100% tests passed, 0 tests failed out of 7' not in test_output and \
       '100% tests passed out of 7' not in test_output:
        raise ValueError('Original test set was not completely executed')
    target_flags = '-target arm64-apple-darwin -mcpu=cortex-a76 -ffreestanding -fno-stack-protector -fno-builtin -D_FORTIFY_SOURCE=0'
    # Configure using the real Darwin SDK. Host capability checks are not proof
    # that the bootstrap target implements those services; the static link below
    # must expose that remaining platform closure rather than altering results.
    run(common + ['-B', target, '-DCMAKE_C_FLAGS=' + target_flags,
        '-DCMAKE_ASM_FLAGS=-target arm64-apple-darwin -mcpu=cortex-a76'], 'target-configure')
    commands = json.loads((target / 'compile_commands.json').read_text())
    target_crypto = [c for c in commands if Path(c['directory']) == target / 'crypto']
    if not target_crypto: raise ValueError('No actual target crypto compile commands')
    before = {}
    print('target-actual-header-scan units=' + str(len(target_crypto)), flush=True)
    for index, command in enumerate(target_crypto):
        args = shlex.split(command['command']); scan = []; skip = False
        for arg in args:
            if skip: skip = False
            elif arg == '-o': skip = True
            elif arg != '-c': scan.append(arg)
        result = subprocess.run(scan + ['-M'], cwd=command['directory'], text=True, capture_output=True, timeout=30)
        if result.returncode: raise ValueError('Actual A76 source dependency scan failed: ' + result.stderr)
        paths = shlex.split(result.stdout.replace('\\\n', ' ').partition(':')[2])
        before[command['output']] = {str(Path(command['directory'], p).resolve()):
            sha(Path(command['directory'], p).resolve()) for p in paths}
        (out / ('target-scan-' + str(index) + '.d')).write_text(result.stdout)
    run([CMAKE, '--build', target, '--parallel', '4', '--target', 'crypto'], 'target-build')
    for command in target_crypto:
        args = shlex.split(command['command'])
        dep = Path(command['directory']) / (args[args.index('-o') + 1] + '.d')
        paths = shlex.split(dep.read_text().replace('\\\n', ' ').partition(':')[2])
        after = {str(Path(command['directory'], p).resolve()): sha(Path(command['directory'], p).resolve()) for p in paths}
        if after != before[command['output']]: raise ValueError('Actual A76 include closure changed: ' + command['file'])
        headers.update(after)
    native_headers = {}
    for command in json.loads((native / 'compile_commands.json').read_text()):
        args = shlex.split(command['command'])
        dep = Path(command['directory']) / (args[args.index('-o') + 1] + '.d')
        if not dep.exists(): continue  # Not one of the actual requested native targets.
        for p in shlex.split(dep.read_text().replace('\\\n', ' ').partition(':')[2]):
            path = Path(command['directory'], p).resolve(); native_headers[str(path)] = sha(path)
    verify()
    for name, digest in headers.items():
        if sha(Path(name)) != digest: raise ValueError('A76 dependency changed before receipt')
    archive = target / 'crypto/libcrypto.a'
    if not archive.exists(): raise ValueError('Genuine target libcrypto archive missing')
    report = dict(profile='real-libressl-4.3.3-native-and-a76-v1', version='4.3.3',
        source=str(SOURCE), source_receipt_sha256=INPUT_SHA, signature_verified=True,
        source_inputs_sha256=pins, target_headers_sha256=headers,
        native_actual_headers_sha256=native_headers, commands=records,
        target_compile_commands=target_crypto, target_compile_units=len(target_crypto),
        target_archive=str(archive), target_archive_sha256=sha(archive),
        native_archive=str(native / 'crypto/libcrypto.a'), original_native_tests=list(TESTS),
        native_tests_passed=True, native_tests_count=len(TESTS),
        target_flags=target_flags, target_platform_capability_checks='Darwin host/SDK, not Pi runtime proof',
        source_unchanged=True, upstream_security_feature_options_changed=False,
        target_runtime_linked=False, installed=False, pi_executed=False, entropy_qualified=False,
        generated_sha256={str(p): sha(p) for p in out.rglob('*') if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), target_archive_sha256=sha(archive),
        target_compile_units=len(target_crypto), native_tests=len(TESTS)), indent=2), flush=True)
    return out, report


if __name__ == '__main__': build()
