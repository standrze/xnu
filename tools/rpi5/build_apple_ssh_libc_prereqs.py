#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Whole Apple strnstr and original generated private initgroups syscall.

No group-changing syscall is executed. The syscall evidence is the actual
A76 object/alias/error-path audit, separately from native string sanitizer tests.
"""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_stpcpy as strings
from tools.rpi5 import build_apple_ssh_socket_syscalls as syscalls

ROOT, sha, LIBC = strings.ROOT, strings.sha, strings.LIBC
BASE = ROOT / 'build/rpi5/apple-dispatch-once-gr21uo30'
BASE_SHA = 'd7f02eb05b151d5dd1ca609c8dd2bd0106d02ea756c7a72eaeb680819611cbd3'
COMMIT = '71bbe350ab79eef58113991d817ccc6165061a64'
SOURCE = LIBC / 'string/FreeBSD/strnstr.c'
HOST = ROOT / 'tools/rpi5/tests/apple_strnstr_host.c'
EXPECTED = 'APPLE_STRNSTR PASS CASES=465920 ALIGNMENTS=4 LIMITS=8 HEAP_GUARD_BOUNDARIES=129\n'


def build():
    if sha(BASE / 'manifest.json') != BASE_SHA: raise ValueError('Frozen full-client composition changed')
    base = json.loads((BASE / 'manifest.json').read_text())
    pins = {str(BASE / 'manifest.json'): BASE_SHA}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
        for name, digest in base[key].items():
            if name in pins and pins[name] != digest: raise ValueError('Inherited pin conflict')
            pins[name] = digest
    if subprocess.check_output(['git', '-C', str(LIBC), 'rev-parse', 'HEAD'], text=True).strip() != COMMIT:
        raise ValueError('Original Apple Libc commit changed')
    if subprocess.check_output(['git', '-C', str(LIBC), 'show', 'HEAD:string/FreeBSD/strnstr.c']) != SOURCE.read_bytes():
        raise ValueError('Original whole string translation unit changed')
    policy = LIBC / 'xcodescripts/libc.xcconfig'
    if '_FORTIFY_SOURCE=0' not in policy.read_text(): raise ValueError('Original provider build policy changed')
    generator, master = ROOT / 'libsyscall/xcodescripts/create-syscalls.pl', ROOT / 'bsd/kern/syscalls.master'
    custom, platforms = ROOT / 'libsyscall/custom', ROOT / 'libsyscall/Platforms'
    for path in (Path(__file__).resolve(), SOURCE, HOST, policy, generator, master,
                 syscalls.JOIN / 'manifest.json', *custom.iterdir(), platforms / 'syscall.map',
                 platforms / 'MacOSX/arm64/syscall.map'):
        if not path.is_file(): continue
        if str(path) in pins and pins[str(path)] != sha(path): raise ValueError('Original pinned input changed')
        pins[str(path)] = sha(path)
    def verify():
        for name, digest in pins.items():
            if sha(name) != digest: raise ValueError('Pinned input drift: ' + name)
    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-ssh-libc-prereqs-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers, records = [], {}, {}
    def run(args, label, allowed=False, env=None):
        args = list(map(str, args)); result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=90, env=env)
        for name in ('stdout', 'stderr'): (out / (label + '.' + name)).write_text(getattr(result, name))
        commands.append(dict(command=args, cwd=str(ROOT), returncode=result.returncode,
            stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if result.returncode and not allowed: raise ValueError(label + ': ' + result.stderr[-6000:])
        return result
    def deps(raw):
        return {str(Path(n).resolve()): sha(Path(n).resolve()) for n in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}
    def consumed(label, before, dep):
        actual = deps(dep.read_text())
        if actual != before: raise ValueError('Actual consumed header closure differs')
        records[label] = dict(scanned_sha256=before, consumed_sha256=actual); headers.update(actual)
    def compile_(flags, source, label):
        before = deps(run(flags + ['-M', source], label + '-scan').stdout)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        run(flags + ['-MD', '-MF', dep, '-c', source, '-o', obj], label + '-compile')
        consumed(label, before, dep)
        return obj
    prior = json.loads((ROOT / 'build/rpi5/apple-stpcpy-i77u3elg/manifest.json').read_text())
    old = next(c['command'] for c in prior['commands'] if c['stdout'].endswith('/target-stpcpy-compile.stdout'))
    target = old[:old.index('-MD')]
    if '-D_FORTIFY_SOURCE=0' not in target: raise ValueError('Provider-only original policy missing')
    native = [x for x in target if x not in ('-ffreestanding', '-mcpu=cortex-a76')]
    at = native.index('-target'); del native[at:at + 2]
    native += ['-O1', '-g', '-fsanitize=address,undefined', '-Dstrnstr=fixture_strnstr']
    string = compile_(target, SOURCE, 'target-strnstr')
    host_string = compile_(native, SOURCE, 'native-strnstr'); caller = compile_(native, HOST, 'native-caller')
    executable = out / 'host-strnstr'
    run(native + [caller, host_string, '-o', executable], 'native-link')
    result = run([executable], 'native-run')
    if (result.stdout, result.stderr) != (EXPECTED, ''): raise ValueError('Native strnstr oracle failed')
    generated = out / 'generated'; generated.mkdir()
    run(['/usr/bin/perl', generator, master, custom, platforms, 'MacOSX', generated],
        'original-generator', env=dict(os.environ, ARCHS='arm64'))
    syscall_source = generated / '___initgroups.s'
    raw = syscall_source.read_text()
    if 'MI_ENTRY_POINT(___initgroups)' not in raw or 'SYSCALL_NONAME(initgroups, 3, cerror_nocancel)' not in raw:
        raise ValueError('Original private syscall alias or error policy differs')
    number = int(re.search(r'^(\d+)\s+[^\n]*\bint initgroups\(u_int gidsetsize, gid_t \*gidset, int gmuid\) NO_SYSCALL_STUB;', master.read_text(), re.M)[1])
    original = json.loads((syscalls.JOIN / 'manifest.json').read_text())
    template = next(c['command'] for c in original['commands'] if c['stdout'].endswith('/create-trap-preprocess.stdout'))
    assembly = template[:template.index('-E')]
    before = deps(run(assembly + ['-M', syscall_source], 'target-initgroups-scan').stdout)
    dep, asm, syscall = out / 'target-initgroups.d', out / 'target-initgroups.s', out / 'target-initgroups.o'
    text = run(assembly + ['-E', '-P', '-MD', '-MF', dep, syscall_source], 'target-initgroups-preprocess').stdout
    consumed('target-initgroups', before, dep)
    asm.write_text(text.replace('%%', '\n').replace(';', '\n'))
    run([assembly[0], '-target', 'arm64-apple-darwin', '-mcpu=cortex-a76', '-x', 'assembler', '-c', asm, '-o', syscall],
        'target-initgroups-assemble')
    undefined = run(['xcrun', 'nm', '-ju', syscall], 'initgroups-undefined').stdout.splitlines()
    if undefined != ['_cerror_nocancel']: raise ValueError('Unexpected syscall error provider')
    archive = out / 'libapple-ssh-libc-prereqs.a'
    run(['xcrun', 'ar', 'rcs', archive, string, syscall], 'archive')
    run(['xcrun', 'nm', '-g', archive], 'symbols')
    run(['xcrun', 'llvm-objdump', '-d', '-r', string, syscall], 'disassembly')
    link = list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o') + 1] = str(out / 'NOT_RUN_ssh'); link[link.index('-map') + 1] = str(out / 'target.map')
    link.append(str(archive)); result = run(link, 'target-link', True)
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', result.stderr, re.M)))
    duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", result.stderr)))
    closed, added = set(base['target_missing_symbols']) - set(missing), set(missing) - set(base['target_missing_symbols'])
    if not result.returncode or duplicates or closed != {'_strnstr', '___initgroups'} or added:
        raise ValueError('Unexpected original-provider full-client delta')
    verify()
    for name, digest in headers.items():
        if sha(name) != digest: raise ValueError('Consumed input drift')
    report = dict(profile='current-apple-full-ssh-strnstr-private-initgroups-v1', source_inputs_sha256=pins,
        headers_sha256=headers, dependency_records=records, commands=commands, original_libc_commit=COMMIT,
        original_source_unchanged=True, whole_original_translation_unit_compiled=True, provider_only_fortify_source=0,
        original_generator=str(generator), generator_environment={'ARCHS': 'arm64'}, generated_directory=str(generated),
        original_arm64_private_alias_preserved=True, original_syscall_emitter_unchanged=True,
        syscall_name='initgroups', syscall_number=number, syscall_error_handler='_cerror_nocancel',
        objects={'strnstr': str(string), '__initgroups': str(syscall)}, target_archive=str(archive), native_stdout=EXPECTED,
        native_asan_ubsan_pass=True, native_runtime_boundary=['host strlen/strncmp, allocator and page protection'],
        previous_missing_count=len(base['target_missing_symbols']), closed_symbols=sorted(closed),
        newly_reachable_symbols=sorted(added), target_missing_symbols=missing, target_duplicate_symbols=duplicates,
        original_openssh_config_unchanged=True, target_link_complete=False, target_executed=False,
        native_privileged_syscall_executed=False, syscall_runtime_qualified=False, provider_stubs=False,
        accepted_runtime_modified=False, generated_sha256={str(p): sha(p) for p in out.rglob('*') if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), manifest_sha256=sha(out / 'manifest.json'),
        closed=sorted(closed), new=sorted(added), remaining=len(missing)), indent=2))
    return out, report


if __name__ == '__main__': build()
