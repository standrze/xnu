#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build pristine current Apple commands against the existing real Pi runtime.

Each invocation creates a separate candidate and records an honest failed link
when a current command needs runtime facilities that are not yet implemented.
No root image, accepted runtime, hardware, or system clock is changed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

try:
    from .prepare_pid1 import inspect as inspect_macho
except ImportError:
    from prepare_pid1 import inspect as inspect_macho

ROOT = Path(__file__).resolve().parents[2]
SHELL = ROOT / 'build/rpi5/apple-shell-cmds-main-20261013'
SHELL_COMMIT = '298787009e5432c5e4c378a077f98267077e3495'
LIBC = ROOT / 'build/rpi5/apple-libc-main-candidate-20261013'
LIBC_COMMIT = '71bbe350ab79eef58113991d817ccc6165061a64'
OPENSSH = ROOT / 'build/rpi5/apple-openssh-candidate-20261013'
OPENSSH_COMMIT = 'f386b2e948280f6ecac875329c0b56020821d558'
BASE = ROOT / 'build/rpi5/apple-ssh-probe-v2-1tmwow6z'
BASE_SHA = '623944b390cb778643ad9c8e8939e285a2ebb11eabee5a1d23896a103878d038'
ANNOTATIONS = ROOT / 'tools/rpi5/user/apple_current_command_build.h'
CRT = ROOT / 'tools/rpi5/user/apple_current_command_crt.c'
NATIVE_ENTRY = ROOT / 'tools/rpi5/tests/current_command_native_start.c'
PROJECT = SHELL / 'shell_cmds.xcodeproj/project.pbxproj'
SOURCES = {'pwd': ('pwd/pwd.c',), 'date': ('date/date.c', 'date/vary.c')}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args, **kwargs):
    return subprocess.run(list(map(str, args)), text=True, capture_output=True,
                          timeout=60, check=False, **kwargs)


def verify(pins):
    for name, digest in pins.items():
        if sha(Path(name)) != digest:
            raise ValueError('Pinned command dependency changed: ' + name)


def pristine(directory, commit, relative):
    if command(['git', '-C', directory, 'rev-parse', 'HEAD']).stdout.strip() != commit:
        raise ValueError('Unexpected Apple source commit: ' + str(directory))
    r = command(['git', '-C', directory, 'show', commit + ':' + relative])
    path = directory / relative
    if r.returncode or path.read_bytes() != r.stdout.encode():
        raise ValueError('Selected Apple source changed from commit: ' + str(path))
    return path


def build(selected):
    if sha(BASE / 'manifest.json') != BASE_SHA:
        raise ValueError('Preserved runtime provider manifest changed')
    base = json.loads((BASE / 'manifest.json').read_text())
    pins = base['source_inputs_sha256'] | base['headers_sha256'] | base['generated_sha256']
    pins.update({str(BASE / 'manifest.json'): BASE_SHA,
                 str(Path(__file__).resolve()): sha(Path(__file__).resolve()),
                 str(ANNOTATIONS): sha(ANNOTATIONS),
                 str(Path(inspect_macho.__code__.co_filename)): sha(Path(inspect_macho.__code__.co_filename))})
    project = pristine(SHELL, SHELL_COMMIT, 'shell_cmds.xcodeproj/project.pbxproj')
    pins[str(project)] = sha(project)
    sources = {}
    libc_sources = [pristine(LIBC, LIBC_COMMIT, relative) for relative in
                    ('stdlib/FreeBSD/getopt.c', 'gen/FreeBSD/err.c', 'gen/FreeBSD/getprogname.c')]
    for path in libc_sources + [CRT, NATIVE_ENTRY]:
        pins[str(path)] = sha(path)
    asprintf = pristine(OPENSSH, OPENSSH_COMMIT, 'openssh/openbsd-compat/bsd-asprintf.c')
    pins[str(asprintf)] = sha(asprintf)
    for name in selected:
        paths = [pristine(SHELL, SHELL_COMMIT, relative) for relative in SOURCES[name]]
        for path in paths:
            pins[str(path)] = sha(path)
        sources[name] = paths
    if 'date' in selected:
        for directory, commit, relative in ((SHELL, SHELL_COMMIT, 'date/vary.h'),
                                           (LIBC, LIBC_COMMIT, 'gen/get_compat.h')):
            path = pristine(directory, commit, relative)
            pins[str(path)] = sha(path)
    verify(pins)
    output = Path(tempfile.mkdtemp(prefix='apple-current-commands-', dir=ROOT / 'build/rpi5'))
    commands, headers = [], {}

    def run(args, label, **kwargs):
        args = list(map(str, args))
        r = command(args, cwd=ROOT, **kwargs)
        stdout, stderr = output / (label + '.stdout'), output / (label + '.stderr')
        stdout.write_text(r.stdout)
        stderr.write_text(r.stderr)
        commands.append(dict(command=args, returncode=r.returncode, stdout=str(stdout), stderr=str(stderr)))
        return r

    def compile_unit(args, label):
        args = list(map(str, args))
        scan, skip = [], False
        for token in args:
            if skip:
                skip = False
                continue
            if token == '-o':
                skip = True
            elif token != '-c':
                scan.append(token)
        before = run(scan + ['-M'], label + '-dependencies')
        if before.returncode:
            return before

        def dependencies(text):
            return {str(Path(v).resolve()): sha(Path(v).resolve())
                    for v in shlex.split(text.replace('\\\n', ' ').partition(':')[2])}

        before = dependencies(before.stdout)
        for path, digest in before.items():
            if path in headers and headers[path] != digest:
                raise ValueError('Dependency changed between command units: ' + path)
        depfile = output / (label + '.d')
        r = run(args + ['-MD', '-MF', depfile], label)
        if r.returncode:
            return r
        after = dependencies(depfile.read_text())
        if before != after:
            raise ValueError('Actual compiler dependencies changed: ' + label)
        headers.update(after)
        return r

    sdk = run(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], 'sdk').stdout.strip()
    clang = run(['xcrun', '--find', 'clang'], 'clang').stdout.strip()
    target = [clang, '-isysroot', sdk, '-target', 'arm64-apple-darwin', '-mcpu=cortex-a76',
              '-ffreestanding', '-O2', '-D_FORTIFY_SOURCE=0', '-fno-builtin',
              '-fno-stack-protector', '-Wall', '-Wextra', '-Werror',
              '-include', ANNOTATIONS, '-I', LIBC / 'gen', '-Dmain=darwin_network_command_main']
    native = [clang, '-isysroot', sdk, '-O1', '-g', '-fsanitize=address,undefined',
              '-fno-omit-frame-pointer', '-include', ANNOTATIONS, '-I', LIBC / 'gen']
    old_link = [entry['command'] for entry in base['commands']
                if entry['command'][:2] == ['xcrun', 'ld']]
    if len(old_link) != 1:
        raise ValueError('Expected one fully audited runtime link')
    # The exact preserved runtime objects/archives are reused. OpenSSH's buffer
    # library is not linked: neither command depends on the SSH implementation.
    runtime = [a for a in old_link[0] if a.endswith(('.a', '.o'))
               and Path(a).name != 'sshbufferprobe.o'
               and Path(a).name != 'libapple-openssh-buffers-reset.a']
    if any(a not in pins for a in runtime):
        raise ValueError('A reused runtime link dependency is not pinned')
    libc_flags = target[:-1] + ['-include', LIBC / 'fbsdcompat/_fbsd_compat_.h',
                               '-I', LIBC / 'fbsdcompat', '-I', LIBC / 'darwin',
                               '-idirafter', LIBC / 'include']
    libc_objects, libc_failures = [], []
    for source in libc_sources + [CRT]:
        obj = output / ('current-libc-' + source.stem + '.o')
        # Keep the current original err.c body: its byte-to-four-character
        # escape is already bounded by the four-times-length allocation. Retain
        # the SDK deprecation diagnostic without promoting only this warning.
        warnings = ['-Wno-error=deprecated-declarations'] if source.name == 'err.c' else []
        r = compile_unit(libc_flags + warnings + ['-c', source, '-o', obj], 'current-libc-' + source.stem)
        if r.returncode:
            libc_failures.append(str(output / ('current-libc-' + source.stem + '.stderr')))
        else:
            libc_objects.append(obj)
    asprintf_obj = output / 'current-openssh-asprintf.o'
    r = compile_unit(target[:-1] + ['-DRPI5_APPLE_ASPRINTF=1',
                     '-I', OPENSSH / 'openssh',
                     '-I', '/opt/homebrew/Cellar/openssl@3/3.6.5/include',
                     '-c', asprintf, '-o', asprintf_obj], 'current-openssh-asprintf')
    if r.returncode:
        libc_failures.append(str(output / 'current-openssh-asprintf.stderr'))
    else:
        libc_objects.append(asprintf_obj)
    # Exercise the same current Apple option parser/error formatter/asprintf
    # bodies in native tests. Native filesystem/allocator/syscalls remain host
    # LibSystem and are explicitly not Pi execution evidence.
    native_helpers = []
    for source in libc_sources + [CRT, NATIVE_ENTRY, asprintf]:
        obj = output / ('native-helper-' + source.stem + '.o')
        flags = native + ['-include', LIBC / 'fbsdcompat/_fbsd_compat_.h',
                          '-I', LIBC / 'fbsdcompat', '-I', LIBC / 'darwin',
                          '-idirafter', LIBC / 'include']
        if source == asprintf:
            flags += ['-DRPI5_APPLE_ASPRINTF=1', '-I', OPENSSH / 'openssh',
                      '-I', '/opt/homebrew/Cellar/openssl@3/3.6.5/include']
        r = compile_unit(flags + ['-c', source, '-o', obj], 'native-helper-' + source.stem)
        if r.returncode:
            raise ValueError('Native current-provider harness failed to compile: ' + str(source))
        native_helpers.append(obj)
    entries = {}
    for name, paths in sources.items():
        objects, failures = [], list(libc_failures)
        for source in paths:
            obj = output / (name + '-' + source.stem + '.o')
            flags = ['-DRPI5_APPLE_DATE=1'] if name == 'date' and source.stem == 'date' else []
            r = compile_unit(target + flags + ['-c', source, '-o', obj], name + '-' + source.stem)
            if r.returncode:
                failures.append(str(output / (name + '-' + source.stem + '.stderr')))
            else:
                objects.append(obj)
        program, native_program = output / name, output / (name + '-native')
        link = None
        if not failures:
            link = run(['xcrun', 'ld', '-arch', 'arm64', '-platform_version', 'macos', '26.0', '27.0',
                        '-static', '-e', '_start', '-dead_strip', '-no_adhoc_codesign', '-no_uuid',
                        '-alias', '_fopen', '_fopen$DARWIN_EXTSN', '-map', output / (name + '.map'),
                        '-o', program, *objects, *libc_objects, *runtime], name + '-link')
        native_objects = []
        for source in paths:
            obj = output / (name + '-native-' + source.stem + '.o')
            flags = ['-DRPI5_APPLE_DATE=1'] if name == 'date' and source.stem == 'date' else []
            r = compile_unit(native + flags + ['-Dmain=darwin_network_command_main',
                             '-c', source, '-o', obj], name + '-native-' + source.stem)
            if r.returncode:
                break
            native_objects.append(obj)
        if len(native_objects) == len(paths):
            native_result = run(native + [*native_objects, *native_helpers, '-o', native_program], name + '-native-link')
        else:
            native_result = r
        complete = link is not None and link.returncode == 0
        audit = inspect_macho(program.read_bytes()) if complete else None
        if complete:
            undefined = run(['xcrun', 'nm', '-u', program], name + '-undefined')
            if undefined.returncode or undefined.stdout.strip():
                raise ValueError('New static command has undefined symbols')
        entries[name] = dict(install_path='/bin/' + name,
                             pristine_sources={str(p): sha(p) for p in paths},
                             compile_failures=failures, static_link_complete=complete,
                             static_executable=str(program) if complete else None,
                             static_executable_sha256=sha(program) if complete else None,
                             missing_symbols=[] if link is None else re.findall(
                                 r'^\s+"([^"]+)", referenced from:', link.stderr, re.MULTILINE),
                             macho_audit=audit,
                             native_executable=str(native_program) if native_result.returncode == 0 else None,
                             native_executed=False, pi_executed=False)
    verify(pins)
    verify(headers)
    for directory, commit in ((SHELL, SHELL_COMMIT), (LIBC, LIBC_COMMIT)):
        for path in map(Path, headers):
            if path.is_relative_to(directory):
                pristine(directory, commit, str(path.relative_to(directory)))
    report = dict(profile='apple-current-commands-static-v1', apple_source_commit=SHELL_COMMIT,
                  apple_release='shell_cmds-329', apple_source_url='https://github.com/apple-oss-distributions/shell_cmds',
                  source_inputs_sha256=pins, headers_sha256=headers, commands=commands, programs=entries,
                  current_command_source_pristine=True, existing_bootstrap_runtime_reused=True,
                  current_libc_sources={str(p): sha(p) for p in libc_sources},
                  current_libc_commit=LIBC_COMMIT,
                  asprintf_provider=dict(source=str(asprintf), sha256=sha(asprintf),
                                         apple_openssh_commit=OPENSSH_COMMIT,
                                         original_missing_provider_body=True),
                  declaration_only_adaptation='date printdate noreturn declaration; original exit body unchanged',
                  modern_full_libsystem=False, native_host_executed=False, pi_executed=False,
                  installed=False, root_changed=False, clock_changed=False,
                  scope='Current original Apple command sources with real existing static runtime; no target execution proof',
                  generated_sha256={str(p): sha(p) for p in output.iterdir() if p.is_file()})
    (output / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return output, report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('commands', nargs='*', choices=tuple(SOURCES), default=list(SOURCES))
    args = parser.parse_args()
    output, report = build(args.commands)
    print(json.dumps(dict(output=str(output), programs=report['programs']), indent=2))
