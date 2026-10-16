#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original case-search/signal providers with explicit minimal signal repairs.

Preserve upstream and accepted runtime archives. A distinct runtime derivation
removes only the legacy ASCII comparison owner so the whole genuine current
locale-aware comparison TU can own all four public comparison symbols.
"""
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_libc_prereqs as libc

ROOT, sha, LIBC = libc.ROOT, libc.sha, libc.LIBC
BASE = ROOT / 'build/rpi5/apple-ssh-strncpy-chk-uhooi_u9'
BASE_SHA = 'cb674efb3ebad4d28e68f519557f199bd748d57c599ead438b616dcdcc29acf9'
GROUP = ROOT / 'build/rpi5/apple-ssh-locale-slice-p7_8ertv'
GROUP_SHA = 'a6411a2990ba6abea004cd17363bb57a7d89559c4703a00d6d923d5facc43fc6'
NATIVE = ROOT / 'build/rpi5/apple-ssh-current-locale-contract-ni1pfpjw'
NATIVE_SHA = 'c45e4a7c3f672003dfa1b6afdb97b6c370153902a487ac0230457251b5da5c6b'
RUNTIME = ROOT / 'build/rpi5/apple-ssh-current-locale-ebd652yw/private-apple-runtime-current-locale.a'
REMOVE = 'string.subproj-strcasecmp.o'
UNITS = {'strcasestr': 'string/FreeBSD/strcasestr.c', 'strcasecmp': 'string/FreeBSD/strcasecmp.c',
         'strsignal': 'string/FreeBSD/strsignal.c', 'siglist': 'gen/FreeBSD/siglist.c'}
HOST = ROOT / 'tools/rpi5/tests/apple_case_signal_host.c'
RENAMES = ('strcasestr', 'strcasestr_l', 'strcasecmp', 'strcasecmp_l', 'strncasecmp',
           'strncasecmp_l', 'strsignal', 'strsignal_r', 'sys_siglist', 'sys_signame')
EXPECTED = ('APPLE_LOCALE PASS VECTORS=23 MODES=3 THREADS=4 ITERATIONS=2048 DESTRUCTORS=4 HOST_KEY_MAPPING_ONLY\n'
    'APPLE_CASE_SIGNAL PASS SEARCH_CASES=174880 MODES=3 HIGH_BYTES=255 CASE_THREADS=4 SIGNAL_BUFFERS=648 SIGNALS=31 SIGNAL_THREADS=4 INT_MIN=1 ORIGINAL_NEGATIVES_SEPARATE\n')


def signal_derivation(text):
    edits = {
        '\tint signum;': '\tunsigned int signum;',
        '\t\tsignum = -signum;': '\t\tsignum = 0U - signum;',
        '\t\tif (n >= (buflen - suffixlen)) {':
            '\t\tif (buflen <= (size_t)suffixlen || n >= (buflen - (size_t)suffixlen)) {',
        '\tif (n < (buflen - suffixlen)) {':
            '\tif (buflen > (size_t)suffixlen && n < (buflen - (size_t)suffixlen)) {'}
    for before, after in edits.items():
        if text.count(before) != 1: raise ValueError('Exact original signal repair boundary changed')
        text = text.replace(before, after)
    return ('/* Pi derived correction: unsigned INT_MIN magnitude and guarded suffix capacity.\n'
            ' * Original signal table, TLS lifecycle, return codes and formatting retained. */\n' + text)


def build():
    pins, reports = {}, {}
    for package, digest in ((BASE, BASE_SHA), (GROUP, GROUP_SHA), (NATIVE, NATIVE_SHA)):
        manifest = package / 'manifest.json'
        if sha(manifest) != digest: raise ValueError('Frozen predecessor/locale receipt changed')
        pins[str(manifest)] = digest; reports[package] = json.loads(manifest.read_text())
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, value in reports[package][key].items():
                if name in pins and pins[name] != value: raise ValueError('Inherited pin conflict')
                pins[name] = value
    base, group, native_group = reports[BASE], reports[GROUP], reports[NATIVE]
    if subprocess.check_output(['git', '-C', str(LIBC), 'rev-parse', 'HEAD'], text=True).strip() != libc.COMMIT:
        raise ValueError('Original Apple Libc commit changed')
    sources = {name: LIBC / path for name, path in UNITS.items()}
    for path in sources.values():
        if subprocess.check_output(['git', '-C', str(LIBC), 'show', 'HEAD:' + str(path.relative_to(LIBC))]) != path.read_bytes():
            raise ValueError('Whole original translation unit changed')
    for path in (Path(__file__).resolve(), HOST, *sources.values(), RUNTIME):
        if str(path) in pins and pins[str(path)] != sha(path): raise ValueError('Pinned original input changed')
        pins[str(path)] = sha(path)
    def verify():
        for name, digest in pins.items():
            if sha(name) != digest: raise ValueError('Pinned input drift: ' + name)
    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-ssh-case-signal-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers, records = [], {}, {}
    def run(args, label, allowed=False, cwd=ROOT):
        args = list(map(str, args)); result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=90)
        for name in ('stdout', 'stderr'): (out / (label + '.' + name)).write_text(getattr(result, name))
        commands.append(dict(command=args, cwd=str(cwd), returncode=result.returncode,
            stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if result.returncode and not allowed: raise ValueError(label + ': ' + result.stderr[-7000:])
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
    old = next(c['command'] for c in group['commands'] if c['stdout'].endswith('/target-tolower-compile.stdout'))
    target = old[:old.index('-MD')]
    old_native = next(c['command'] for c in native_group['commands'] if c['stdout'].endswith('/native-tolower-compile.stdout'))
    native_flags = old_native[:old_native.index('-MD')] + ['-fno-sanitize-recover=undefined']
    native = native_flags + ['-D' + name + '=fixture_' + name for name in RENAMES]
    pristine_flags = native_flags + ['-D' + name + '=fixture_' + name for name in ('sys_siglist', 'sys_signame')]
    pristine_flags += ['-Dstrsignal=fixture_original_strsignal', '-Dstrsignal_r=fixture_original_strsignal_r']
    derived = out / 'derived-strsignal.c'; derived.write_text(signal_derivation(sources['strsignal'].read_text()))
    pristine_target = compile_(target, sources['strsignal'], 'target-original-strsignal')
    pristine = compile_(pristine_flags, sources['strsignal'], 'native-original-strsignal')
    objects = {name: compile_(target, derived if name == 'strsignal' else path, 'target-' + name) for name, path in sources.items()}
    host = [compile_(native, derived if name == 'strsignal' else path, 'native-' + name) for name, path in sources.items()]
    caller = compile_(native, HOST, 'native-caller')
    old_native_link = next(c['command'] for c in native_group['commands'] if c['stdout'].endswith('/native-link.stdout'))
    original_host_objects = [arg for arg in old_native_link if arg.endswith('.o') and arg != str(NATIVE / 'native-harness.o')]
    if len(original_host_objects) != 38: raise ValueError('Exact original locale provider set changed')
    visibility = [arg for arg in old_native_link if arg.startswith('-Wl,-unexported_symbol,')]
    executable = out / 'host-case-signal'
    run(native + [caller, *host, pristine, *original_host_objects, '-Wl,-dead_strip', *visibility,
                  '-Wl,-map,' + str(out / 'native.map'), '-o', executable], 'native-link')
    small = run([executable, 'original-small-buffer'], 'original-small-buffer-negative', True)
    minimum = run([executable, 'original-int-min'], 'original-int-min-negative', True)
    if not small.returncode or 'AddressSanitizer: heap-buffer-overflow' not in small.stderr:
        raise ValueError('Original small-capacity signal overflow not reproduced')
    if not minimum.returncode or "negation of -2147483648 cannot be represented in type 'int'" not in minimum.stderr:
        raise ValueError('Original INT_MIN signal overflow not reproduced')
    failure = dict(profile='unchanged-apple-strsignal-original-failures-v1', original_libc_commit=libc.COMMIT,
        original_source=str(sources['strsignal']), original_source_sha256=sha(sources['strsignal']),
        original_target_object=str(pristine_target), original_native_object=str(pristine),
        executable=str(executable), executable_sha256=sha(executable),
        source_inputs_sha256=pins, commands=[c for c in commands if '-negative.' in c['stdout']],
        small_capacity_heap_overflow_observed=True, int_min_signed_negation_undefined_behavior_observed=True,
        derived_source_used_by_negative_calls=False, target_executed=False,
        generated_sha256={str(out / name): sha(out / name) for name in
            ('native-original-strsignal.o', 'target-original-strsignal.o', 'original-small-buffer-negative.stderr',
             'original-small-buffer-negative.stdout', 'original-int-min-negative.stderr', 'original-int-min-negative.stdout')})
    failure_path = out / 'original-failure-manifest.json'
    failure_path.write_text(json.dumps(failure, indent=2, sort_keys=True) + '\n')
    result = run([executable], 'native-run')
    if (result.stdout, result.stderr) != (EXPECTED, ''): raise ValueError('Corrected native case/signal oracle failed')
    archive = out / 'libapple-ssh-case-signal.a'
    run(['xcrun', 'ar', 'rcs', archive, *objects.values()], 'archive')
    run(['xcrun', 'nm', '-g', archive], 'symbols')
    run(['xcrun', 'llvm-objdump', '-d', '-r', *objects.values()], 'disassembly')
    link = list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o') + 1] = str(out / 'NOT_RUN_ssh'); link[link.index('-map') + 1] = str(out / 'target.map')
    unchanged = run(link + [str(archive)], 'target-link-original-ownership', True)
    incomplete_original_duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", unchanged.stderr)))
    contract = list(next(c['command'] for c in native_group['commands'] if c['stdout'].endswith('/target-link.stdout')))
    contract[contract.index('-o') + 1] = str(out / 'NOT_RUN_case_signal_contract')
    contract[contract.index('-map') + 1] = str(out / 'contract.map')
    contract.append(str(archive))
    for name in ('strcasestr', 'strsignal', 'strcasecmp', 'strncasecmp'): contract += ['-u', '_' + name]
    original_contract = run(contract, 'contract-original-ownership', True)
    original_duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", original_contract.stderr)))
    if original_duplicates != ['_strcasecmp', '_strncasecmp']:
        raise ValueError('Complete forced comparison ownership boundary differs: ' + original_contract.stderr[-3000:])
    listed = run(['xcrun', 'ar', 't', RUNTIME], 'original-runtime-members').stdout.splitlines()
    if listed.count('__.SYMDEF SORTED') != 1: raise ValueError('Unexpected archive index')
    members = [name for name in listed if name != '__.SYMDEF SORTED']
    if len(members) != len(set(members)) or any(Path(name).name != name for name in members) or members.count(REMOVE) != 1:
        raise ValueError('Unsafe/ambiguous legacy runtime owner set')
    directory = out / 'runtime'; directory.mkdir()
    run(['xcrun', 'ar', 'x', RUNTIME], 'extract-runtime', cwd=directory)
    before = {name: sha(directory / name) for name in members}
    kept = [name for name in members if name != REMOVE]
    runtime = out / 'private-apple-runtime-current-comparisons.a'
    run(['xcrun', 'ar', 'rcs', runtime, *[directory / name for name in kept]], 'runtime-archive')
    final = run(['xcrun', 'ar', 't', runtime], 'derived-runtime-members').stdout.splitlines()
    if final.count('__.SYMDEF SORTED') != 1 or [name for name in final if name != '__.SYMDEF SORTED'] != kept:
        raise ValueError('Exact runtime ownership derivation failed')
    for name in kept:
        if hashlib.sha256(subprocess.check_output(['xcrun', 'ar', 'p', runtime, name])).hexdigest() != before[name]:
            raise ValueError('Retained unrelated runtime object changed')
    if link.count(str(RUNTIME)) != 1: raise ValueError('Ambiguous original runtime owner')
    link[link.index(str(RUNTIME))] = str(runtime); link.append(str(archive))
    result = run(link, 'target-link', True)
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', result.stderr, re.M)))
    duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", result.stderr)))
    closed, added = set(base['target_missing_symbols']) - set(missing), set(missing) - set(base['target_missing_symbols'])
    if not result.returncode or duplicates or closed != {'_strcasestr', '_strsignal'}:
        raise ValueError('Unexpected actual full-client provider closure')
    if contract.count(str(RUNTIME)) != 1: raise ValueError('Ambiguous forced-contract runtime owner')
    contract[contract.index(str(RUNTIME))] = str(runtime)
    run(contract, 'contract-link')
    target_contract = out / 'NOT_RUN_case_signal_contract'
    if run(['xcrun', 'nm', '-ju', target_contract], 'contract-undefined').stdout:
        raise ValueError('Forced target contract has unresolved providers')
    run(['xcrun', 'llvm-objdump', '-d', '--disassemble-symbols=_strcasestr,_strcasestr_l,_strsignal,_strsignal_r', target_contract],
        'contract-disassembly')
    verify()
    for name, digest in headers.items():
        if sha(name) != digest: raise ValueError('Consumed source/header drift')
    report = dict(profile='apple-full-ssh-case-search-and-derived-bounded-signal-v1', source_inputs_sha256=pins,
        headers_sha256=headers, dependency_records=records, commands=commands, original_libc_commit=libc.COMMIT,
        whole_original_units_compiled=['string/FreeBSD/strcasestr.c', 'string/FreeBSD/strcasecmp.c', 'gen/FreeBSD/siglist.c'],
        derived_original_units={'string/FreeBSD/strsignal.c': str(derived)},
        whole_original_strsignal_unchanged=False, upstream_files_unchanged=True,
        original_failure_receipt=str(failure_path), original_failure_receipt_sha256=sha(failure_path),
        signal_corrections=['unsigned magnitude for INT_MIN', 'guard suffix capacity before size_t subtraction and append'],
        original_signal_tls_data_return_codes_and_format_retained=True, native_asan_ubsan_pass=True,
        native_stdout=EXPECTED, native_original_locale_provider_count=38,
        native_runtime_boundary=['accepted fresh host locale TSD key mapping', 'real host pthread TLS/once/allocator',
            'original current locale/rune objects and custom in-memory ctype fixtures', 'host string/format and scheduler calls'],
        non_c_locale_files_qualified=False, target_archive=str(archive), objects={name: str(path) for name, path in objects.items()},
        original_runtime_archive=str(RUNTIME), runtime_archive=str(runtime), removed_legacy_members=[REMOVE],
        before_members_sha256=before, after_members_sha256={name: before[name] for name in kept},
        original_duplicate_symbols_before_owner_derivation=original_duplicates, archive_index_regenerated=True,
        incomplete_full_client_original_duplicate_diagnostics=incomplete_original_duplicates,
        forced_target_contract=str(target_contract), forced_target_contract_sha256=sha(target_contract),
        forced_target_contract_link_complete=True, forced_contract_not_full_client=True,
        previous_missing_count=len(base['target_missing_symbols']), closed_symbols=sorted(closed),
        newly_reachable_symbols=sorted(added), target_missing_symbols=missing, target_duplicate_symbols=duplicates,
        original_openssh_config_unchanged=True, provider_stubs=False, target_link_complete=False,
        target_executed=False, target_locale_or_signal_runtime_qualified=False, accepted_runtime_modified=False,
        network_services_executed=False, generated_sha256={str(p): sha(p) for p in out.rglob('*') if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), manifest_sha256=sha(out / 'manifest.json'),
        closed=sorted(closed), new=sorted(added), remaining=len(missing),
        original_failure_receipt_sha256=sha(failure_path)), indent=2))
    return out, report


if __name__ == '__main__': build()
