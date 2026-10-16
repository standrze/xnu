#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Compile original full Apple OpenSSH client and attempt its honest static link.

No target execution, keys, network, feature reconfiguration, fake providers or
installation. Failed compilation and unresolved linkage remain first-class
saved results. All upstream object membership is parsed from its Makefile.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_kernel_entropy_rand_probe as previous

ROOT, sha = previous.ROOT, previous.sha
UPSTREAM = ROOT / 'build/rpi5/apple-openssh-candidate-20261013'
SOURCE = UPSTREAM / 'openssh'
COMMIT = 'f386b2e948280f6ecac875329c0b56020821d558'
RUNTIME = ROOT / 'build/rpi5/kernel-entropy-rand-hfrb7y67'
RUNTIME_SHA = 'f46bd17a8171c4272985875cfbb6a49d7305a49e26d2ee716facbe6aaac924f8'
PACKET = ROOT / 'build/rpi5/apple-ssh-libressl-packet-9ws4lrfd'
PACKET_SHA = '5b801203eb3cc0033961a2a28e6f1b8353c7cad451daf676cfb579a2b1dc232a'
LIBINFO = ROOT / 'experiments/darwin-container/userland/upstream/apple-Libinfo-542.40.3/lookup.subproj'


def object_lists(text, names):
    """Only expand explicit simple Makefile object lists; reject guessed inputs."""
    joined = text.replace('\\\n', ' ')
    variables = dict(re.findall(r'^([A-Z][A-Z0-9_]*)\s*=\s*(.*)$', joined, re.M))
    def expand(name, seen=()):
        if name in seen or name not in variables:
            raise ValueError('Unresolved/cyclic upstream object variable: ' + name)
        value = re.sub(r'\$[({]([A-Z][A-Z0-9_]*)[)}]',
                       lambda m: expand(m[1], seen + (name,)), variables[name])
        if any(not re.fullmatch(r'[a-zA-Z0-9_-]+\.o', s) for s in value.split()):
            raise ValueError('Not an exact upstream object list: ' + name)
        return value
    return {name: expand(name).split() for name in names}


def build():
    pins = {}; inherited = []
    for directory, digest in ((RUNTIME, RUNTIME_SHA), (PACKET, PACKET_SHA)):
        path = directory / 'manifest.json'
        if sha(path) != digest:
            raise ValueError('Frozen runtime manifest changed')
        report = json.loads(path.read_text()); inherited.append(report)
        pins[str(path)] = digest
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, value in report[key].items():
                if name in pins and pins[name] != value:
                    raise ValueError('Conflicting inherited dependency')
                pins[name] = value
    actual_commit = subprocess.check_output(['git', '-C', str(UPSTREAM), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(UPSTREAM), 'status', '--porcelain', '--untracked-files=all'], text=True)
    if actual_commit != COMMIT or dirty:
        raise ValueError('Exact pristine upstream required')
    tracked = subprocess.check_output(['git', '-C', str(UPSTREAM), 'ls-files'], text=True).splitlines()
    for p in [UPSTREAM / n for n in tracked] + [Path(__file__).resolve(),
              LIBINFO / 'si_compare.h', ROOT / 'tools/rpi5/user/ssh_full_client_entry.c']:
        pins[str(p)] = sha(p)
    def verify():
        for name, digest in pins.items():
            if sha(name) != digest:
                raise ValueError('Input changed: ' + name)
    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-ssh-full-client-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers, scans, failures, objects = [], {}, {}, [], {}
    runtime, packet = inherited
    cmd = next(c['command'] for c in packet['commands'] if c['stdout'].endswith('/probe-target.stdout'))
    flags = [s for s in cmd[:cmd.index('-MD')] if s != '-Dmain=darwin_network_command_main']
    # Declaration only: no Libinfo provider is fabricated by supplying its
    # original public/private source header. The full call remains unresolved.
    flags += ['-I', str(LIBINFO)]
    def run(args, label):
        args = list(map(str, args))
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=90)
        for kind in ('stdout', 'stderr'):
            (out / (label + '.' + kind)).write_text(getattr(result, kind))
        commands.append(dict(command=args, cwd=str(ROOT), returncode=result.returncode,
            stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        return result
    def deps(raw):
        return {str(Path(p).resolve()): sha(Path(p).resolve())
            for p in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}
    def compile(source, label, extra=()):
        scan = run(flags + list(extra) + ['-M', source], label + '-scan')
        dep = out / (label + '.d'); obj = out / (label + '.o')
        result = run(flags + list(extra) + ['-MD', '-MF', dep, '-c', source, '-o', obj], label + '-compile')
        scanned = deps(scan.stdout) if not scan.returncode else {}
        consumed = deps(dep.read_text()) if dep.exists() else {}
        scans[label] = dict(scan_complete=not scan.returncode,
            consumed_dependencies_emitted=dep.exists(), scanned_sha256=scanned,
            consumed_sha256=consumed)
        if not result.returncode and (scan.returncode or scanned != consumed):
            raise ValueError('Actual consumed dependencies differ: ' + label)
        for name, digest in (scanned | consumed).items():
            if name in headers and headers[name] != digest:
                raise ValueError('Header drift')
            headers[name] = digest
        if result.returncode:
            failures.append(dict(source=str(source), label=label, diagnostics=result.stderr))
            return None
        objects[str(source)] = str(obj)
        return obj
    groups = object_lists((SOURCE / 'Makefile.in').read_text(), ('LIBSSH_OBJS', 'SSHOBJS'))
    compat = object_lists((SOURCE / 'openbsd-compat/Makefile.in').read_text(), ('COMPAT', 'OPENBSD', 'PORTS'))
    requested = []
    for names in groups.values():
        requested += [SOURCE / (n[:-2] + '.c') for n in names]
    for names in compat.values():
        requested += [SOURCE / 'openbsd-compat' / (n[:-2] + '.c') for n in names]
    requested = list(dict.fromkeys(requested))
    for index, source in enumerate(requested):
        extra = ('-Dmain=rpi5_original_ssh_main',) if source.name == 'ssh.c' else ()
        compile(source, f'{index:03d}-{source.stem}', extra)
    entry = compile(ROOT / 'tools/rpi5/user/ssh_full_client_entry.c', 'entry')
    archive = out / 'libapple-openssh-full.a'
    library_sources = [SOURCE / (n[:-2] + '.c') for n in groups['LIBSSH_OBJS']]
    library_sources += [SOURCE / 'openbsd-compat' / (n[:-2] + '.c') for v in compat.values() for n in v]
    members = list(dict.fromkeys(objects[str(p)] for p in library_sources if str(p) in objects))
    if run(['xcrun', 'ar', 'rcs', archive, *members], 'archive').returncode:
        raise ValueError('Archive failure')
    # A partial compile still gets a clearly labelled partial link diagnostic,
    # never an assertion that omitted original functions were supplied.
    link = list(next(c['command'] for c in runtime['commands'] if c['stdout'].endswith('/target-link.stdout')))
    old_workload = str(RUNTIME / 'randprobe.o')
    if link.count(old_workload) != 1 or entry is None:
        raise ValueError('Exact genuine startup workload replacement required')
    link[link.index(old_workload)] = str(entry)
    link[link.index('-o') + 1] = str(out / 'NOT_RUN_ssh')
    link[link.index('-map') + 1] = str(out / 'target.map')
    link += [objects[str(SOURCE / (n[:-2] + '.c'))] for n in groups['SSHOBJS']
             if str(SOURCE / (n[:-2] + '.c')) in objects] + [str(archive)]
    result = run(link, 'target-link')
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', result.stderr, re.M)))
    duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", result.stderr)))
    verify()
    for name, digest in headers.items():
        if sha(name) != digest:
            raise ValueError('Consumed header changed')
    report = dict(profile='original-apple-openssh-full-client-static-closure-v1',
        upstream_commit=COMMIT, original_config_sha256=sha(SOURCE / 'config.h'),
        original_apple_config_unchanged=True, security_features_disabled=False,
        apple_xcode_extra_integration_macros_enabled=False,
        apple_xcode_extras_scope='Same explicit config.h-only profile as previous buffer/packet builds; not Apple shipping framework-integrated build',
        source_inputs_sha256=pins, headers_sha256=headers, dependency_records=scans,
        commands=commands, requested_groups=groups, requested_compat_groups=compat,
        requested_translation_units=[str(p) for p in requested], compiled_objects=objects,
        compile_failures=failures, all_original_client_units_compiled=not failures,
        full_client_link_attempted=not failures, partial_client_link_attempted=bool(failures),
        target_link_complete=not failures and not result.returncode,
        target_missing_symbols=missing, target_duplicate_symbols=duplicates,
        target_link_returncode=result.returncode, archive=str(archive),
        actual_target_executed=False, host_client_executed=False,
        intended_first_execution='Only original ssh -V, after separate target runtime/entropy approval',
        original_main_renamed_only=True, genuine_pthread_prerequisite_retained=True,
        project_random_adapter=str(RUNTIME / 'kernel-entropy-adapter.o'),
        crypto_provider='LibreSSL 4.3.3', entropy_qualified=False,
        provider_stubs=False, live_keys=False, network_access=False, installed=False,
        accepted_runtime_modified=False, source_header_only_libinfo=str(LIBINFO / 'si_compare.h'),
        generated_sha256={str(p): sha(p) for p in out.iterdir() if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), units=len(requested), failures=len(failures),
        missing=missing, duplicates=duplicates), indent=2), flush=True)
    return out, report


if __name__ == '__main__':
    build()
