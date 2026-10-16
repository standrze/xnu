#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Whole original Apple interface/Ethernet helpers, real local-only host tests."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_libc_prereqs as previous
from tools.rpi5 import audit_apple_libinfo_current as libinfo

ROOT, sha, SOURCE = libinfo.ROOT, libinfo.sha, libinfo.SOURCE
BASE = ROOT / 'build/rpi5/apple-ssh-libc-prereqs-crebas6n'
BASE_SHA = 'e50d8616f35c33e88beebab3d6e75ccfe008598669534c1ec4c06f7f9de809dd'
INVENTORY = ROOT / 'build/rpi5/apple-libinfo-current-kdmwyk4q'
HOST = ROOT / 'tools/rpi5/tests/apple_interface_ether_host.c'
UNITS = ('if_indextoname.c', 'if_nametoindex.c', 'ether_addr.c')
NATIVE_UNITS = UNITS + ('getifaddrs.c',)
NATIVE_RENAMES = ('if_indextoname', 'if_nametoindex', 'ether_aton', 'ether_ntoa',
                  'ether_line', 'getifaddrs', 'freeifaddrs')
EXPECTED = r'APPLE_INTERFACES_ETHER PASS MAC_CASES=1536 REJECTED=10 LOCAL_AF_LINK=([1-9][0-9]*) ORIGINAL_GETIFADDRS=1\n'


def build():
    if sha(BASE / 'manifest.json') != BASE_SHA: raise ValueError('Frozen full-client predecessor changed')
    base = json.loads((BASE / 'manifest.json').read_text())
    pins = {str(BASE / 'manifest.json'): BASE_SHA}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
        for name, digest in base[key].items():
            if name in pins and pins[name] != digest: raise ValueError('Inherited pin conflict')
            pins[name] = digest
    if subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() != libinfo.COMMIT:
        raise ValueError('Official Apple Libinfo commit changed')
    sources = {name: SOURCE / 'gen.subproj' / name for name in NATIVE_UNITS}
    for name, path in sources.items():
        if subprocess.check_output(['git', '-C', str(SOURCE), 'show', 'HEAD:gen.subproj/' + name]) != path.read_bytes():
            raise ValueError('Original complete translation unit changed: ' + name)
    for path in (Path(__file__).resolve(), HOST, *sources.values(), INVENTORY / 'manifest.json'):
        if str(path) in pins and pins[str(path)] != sha(path): raise ValueError('Pinned original changed')
        pins[str(path)] = sha(path)
    def verify():
        for name, digest in pins.items():
            if sha(name) != digest: raise ValueError('Pinned input drift: ' + name)
    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-ssh-interface-helpers-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers, records = [], {}, {}
    def run(args, label, allowed=False):
        args = list(map(str, args)); result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=90)
        for name in ('stdout', 'stderr'): (out / (label + '.' + name)).write_text(getattr(result, name))
        commands.append(dict(command=args, cwd=str(ROOT), returncode=result.returncode,
            stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if result.returncode and not allowed: raise ValueError(label + ': ' + result.stderr[-6000:])
        return result
    def deps(raw):
        return {str(Path(n).resolve()): sha(Path(n).resolve()) for n in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}
    def compile_(flags, source, label):
        before = deps(run(flags + ['-M', source], label + '-scan').stdout)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        run(flags + ['-MD', '-MF', dep, '-c', source, '-o', obj], label + '-compile')
        actual = deps(dep.read_text())
        if actual != before: raise ValueError('Actual consumed dependency closure differs')
        records[label] = dict(scanned_sha256=before, consumed_sha256=actual); headers.update(actual)
        return obj
    original = json.loads((INVENTORY / 'manifest.json').read_text())
    old = next(c['command'] for c in original['commands'] if c['stdout'].endswith('/13-getifaddrs-compile.stdout'))
    target = old[:old.index('-MD')]
    native = [x for x in target if x not in ('-ffreestanding', '-mcpu=cortex-a76')]
    at = native.index('-target'); del native[at:at + 2]
    renames = ['-D' + n + '=fixture_' + n for n in NATIVE_RENAMES]
    native += ['-O1', '-g', '-fsanitize=address,undefined'] + renames
    objects = {name: compile_(target, sources[name], 'target-' + Path(name).stem) for name in UNITS}
    compile_(target + renames, HOST, 'target-caller-abi')
    host = [compile_(native, sources[name], 'native-' + Path(name).stem) for name in NATIVE_UNITS]
    caller = compile_(native, HOST, 'native-caller'); executable = out / 'host-interface-ether'
    run(native + [caller, *host, '-Wl,-map,' + str(out / 'native.map'), '-o', executable], 'native-link')
    result = run([executable], 'native-run')
    match = re.fullmatch(EXPECTED, result.stdout)
    if not match or result.stderr: raise ValueError('Original native interface/parser oracle failed')
    archive = out / 'libapple-ssh-interface-helpers.a'
    run(['xcrun', 'ar', 'rcs', archive, *objects.values()], 'archive')
    run(['xcrun', 'nm', '-g', archive], 'symbols')
    run(['xcrun', 'llvm-objdump', '-d', '-r', *objects.values()], 'disassembly')
    link = list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o') + 1] = str(out / 'NOT_RUN_ssh'); link[link.index('-map') + 1] = str(out / 'target.map')
    link.append(str(archive)); result = run(link, 'target-link', True)
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', result.stderr, re.M)))
    duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", result.stderr)))
    closed, added = set(base['target_missing_symbols']) - set(missing), set(missing) - set(base['target_missing_symbols'])
    if not result.returncode or duplicates or closed != {'_if_indextoname', '_if_nametoindex', '_ether_aton'}:
        raise ValueError('Unexpected original-provider link closure')
    verify()
    for name, digest in headers.items():
        if sha(name) != digest: raise ValueError('Consumed header drift')
    report = dict(profile='apple-original-full-ssh-interface-ethernet-helpers-v1', source_inputs_sha256=pins,
        headers_sha256=headers, dependency_records=records, commands=commands, original_libinfo_commit=libinfo.COMMIT,
        whole_original_translation_units_compiled=list(UNITS), whole_original_native_translation_units=list(NATIVE_UNITS),
        original_sources_unchanged=True, original_libinfo_macros=list(libinfo.MACROS), target_archive=str(archive),
        objects={name: str(path) for name, path in objects.items()}, native_asan_ubsan_pass=True,
        native_stdout=(out / 'native-run.stdout').read_text(), native_af_link_count=int(match[1]),
        native_runtime_boundary=['original getifaddrs/freeifaddrs using actual host local route sysctl',
            'host sscanf/snprintf, allocator and errno'], native_external_network_services=False,
        actual_target_and_native_darwin_layout_assertions_compiled=True,
        original_ether_line_unbounded_hostname_scan_retained=True, arbitrary_oversized_ether_line_input_qualified=False,
        original_parser_octet_narrowing_and_trailing_input_retained=True,
        original_getifaddrs_already_owned=True, previous_missing_count=len(base['target_missing_symbols']),
        closed_symbols=sorted(closed), newly_reachable_symbols=sorted(added), target_missing_symbols=missing,
        target_duplicate_symbols=duplicates, original_openssh_config_unchanged=True, provider_stubs=False,
        target_link_complete=False, target_executed=False, target_network_runtime_qualified=False,
        accepted_runtime_modified=False, generated_sha256={str(p): sha(p) for p in out.rglob('*') if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), manifest_sha256=sha(out / 'manifest.json'),
        closed=sorted(closed), new=sorted(added), remaining=len(missing)), indent=2))
    return out, report


if __name__ == '__main__': build()
