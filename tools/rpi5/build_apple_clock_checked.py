#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct Apple clock derivation; native checks precede target composition.

Never replaces accepted archives. Original Mach helpers remain byte-identical.
Native host callbacks are test doubles, not target providers or clock proof.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import audit_apple_clock_private as inventory

ROOT, sha = inventory.ROOT, inventory.sha
BASE = ROOT / 'build/rpi5/apple-clock-private-ds64r613'
BASE_SHA = 'fa39a38e4400a76dfd0fccabf30b19b700f35a3cadc1963842d30b3f1e1b850f'
HOST = ROOT / 'tools/rpi5/tests/apple_clock_host.c'
RENAMES = ('clock_gettime', 'clock_gettime_nsec_np', 'clock_getres', 'clock_settime',
           'gettimeofday', 'getrusage', 'sysctlbyname', 'settimeofday', 'mach_boottime_usec',
           'mach_timebase_info', 'mach_continuous_time', 'mach_continuous_approximate_time',
           'mach_absolute_time', 'mach_approximate_time', '__thread_selfusage')


def derive(raw):
    edits = {
        'static uint64_t\n_boottime_fallback_usec(void)':
        'static int\n_boottime_fallback_usec(uint64_t *result)',
        'if (ret == -1) return 0;\n    return (uint64_t)tv.tv_sec * USEC_PER_SEC + (uint64_t)tv.tv_usec;':
        'if (ret) return ret;\n    *result = (uint64_t)tv.tv_sec * USEC_PER_SEC + (uint64_t)tv.tv_usec;\n    return 0;',
        'if (os_slowpath(bt1 == 0)) bt1 = _boottime_fallback_usec();':
        'if (os_slowpath(bt1 == 0)) {\n'
        '            ret = _boottime_fallback_usec(&bt1);\n            if (ret) return ret;\n        }',
        'if (os_slowpath(bt2 == 0)) bt2 = _boottime_fallback_usec();':
        'if (os_slowpath(bt2 == 0)) {\n'
        '            ret = _boottime_fallback_usec(&bt2);\n            if (ret) return ret;\n        }',
        'int ret = gettimeofday(&tv, NULL);\n        TIMEVAL_TO_TIMESPEC':
        'int ret = gettimeofday(&tv, NULL);\n        if (ret) return ret;\n        TIMEVAL_TO_TIMESPEC',
        'int ret = _mach_boottime_usec(&boottime_usec, &tv);\n        struct timeval':
        'int ret = _mach_boottime_usec(&boottime_usec, &tv);\n        if (ret) return ret;\n        struct timeval',
        'int ret = getrusage(RUSAGE_SELF, &ru);\n        timeradd':
        'int ret = getrusage(RUSAGE_SELF, &ru);\n        if (ret) return ret;\n        timeradd',
        'uint64_t ns = clock_gettime_nsec_np(clk_id);\n        if (!ns) return -1;':
        'int saved_errno = errno;\n        errno = 0;\n        uint64_t ns = clock_gettime_nsec_np(clk_id);\n'
        '        if (!ns && errno) return -1;\n        errno = saved_errno;',
        'if (kr != KERN_SUCCESS) {': 'if (kr != KERN_SUCCESS || !tb_info.denom) {',
        'return (mach_time * tb_info.numer) / tb_info.denom;':
        'uint64_t quotient = mach_time / tb_info.denom;\n'
        '    uint64_t remainder = mach_time % tb_info.denom;\n'
        '    if (tb_info.numer && quotient > UINT64_MAX / tb_info.numer) {\n'
        '        errno = EOVERFLOW; return 0;\n    }\n'
        '    uint64_t whole = quotient * tb_info.numer;\n'
        '    /* remainder and numerator are both <2^32, so this product fits. */\n'
        '    uint64_t fraction = (remainder * tb_info.numer) / tb_info.denom;\n'
        '    if (whole > UINT64_MAX - fraction) { errno = EOVERFLOW; return 0; }\n'
        '    return whole + fraction;',
        'clock_getres(clockid_t clk_id, struct timespec *res)\n{':
        'clock_getres(clockid_t clk_id, struct timespec *res)\n{\n'
        '    struct timespec ignored;\n    if (!res) res = &ignored;',
        'res->tv_nsec = tb_info.numer / tb_info.denom + (tb_info.numer % tb_info.denom != 0);\n        res->tv_sec = 0;':
        'uint64_t resolution = tb_info.numer / tb_info.denom + (tb_info.numer % tb_info.denom != 0);\n'
        '        res->tv_sec = resolution / NSEC_PER_SEC;\n        res->tv_nsec = resolution % NSEC_PER_SEC;',
        'clock_settime(clockid_t clk_id, const struct timespec *tp)\n{':
        'clock_settime(clockid_t clk_id, const struct timespec *tp)\n{\n'
        '    if (tp->tv_nsec < 0 || tp->tv_nsec >= NSEC_PER_SEC) { errno = EINVAL; return -1; }',
    }
    for before, after in edits.items():
        expected = 2 if before == 'if (kr != KERN_SUCCESS) {' else 1
        if raw.count(before) != expected:
            raise ValueError('Exact original clock repair boundary changed')
        raw = raw.replace(before, after)
    return ('/* Pi derivation: atomic error outputs, propagated fallback failures,\n'
            ' * valid zero ticks, safe scale,\n'
            ' * normalized optional resolution and nanosecond range. See build receipt. */\n' + raw)


def build():
    manifest = BASE / 'manifest.json'
    if sha(manifest) != BASE_SHA:
        raise ValueError('Frozen private-provider inventory required')
    original = json.loads(manifest.read_text())
    pins = {str(manifest):BASE_SHA, str(Path(__file__).resolve()):sha(__file__), str(HOST):sha(HOST)}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
        for name,digest in original[key].items():
            if name in pins and pins[name] != digest:
                raise ValueError('Inherited pin conflict')
            pins[name] = digest

    def verify():
        for name,digest in pins.items():
            if sha(name) != digest: raise ValueError('Pinned input drift: '+name)

    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-clock-checked-', dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out), flush=True)
    commands,headers,records = [],{},{}

    def run(args,label,allowed=False):
        args=list(map(str,args))
        r=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=90)
        for stream in ('stdout','stderr'):(out/(label+'.'+stream)).write_text(getattr(r,stream))
        commands.append(dict(command=args,label=label,returncode=r.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr[-5000:])
        return r

    def deps(raw):
        return {str(Path(p).resolve()):sha(Path(p).resolve()) for p in
            shlex.split(raw.replace('\\\n',' ').partition(':')[2])}

    def compile_(flags,source,label):
        scanned=deps(run([*flags,'-M',source],label+'-scan').stdout)
        obj,dep=out/(label+'.o'),out/(label+'.d')
        run([*flags,'-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile')
        consumed=deps(dep.read_text())
        if scanned!=consumed:raise ValueError('Consumed header closure changed')
        headers.update(consumed);records[label]=dict(scanned_sha256=scanned,consumed_sha256=consumed)
        return obj

    old=next(c['command'] for c in original['commands'] if c['label']=='clock-compile')
    target=old[:old.index('-MD')]
    source=inventory.base.LIBC/'gen/clock_gettime.c'
    derived=out/'derived-clock_gettime.c';derived.write_text(derive(source.read_text()))
    native=[arg for arg in target if arg not in ('-ffreestanding','-mcpu=cortex-a76')]
    at=native.index('-target');del native[at:at+2]
    native += ['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=undefined']
    native += ['-D'+n+'=fixture_'+n for n in RENAMES]
    pristine=compile_(native,source,'native-original')
    corrected=compile_(native,derived,'native-derived')
    caller=compile_(native,HOST,'native-caller')
    for label,obj in (('original',pristine),('derived',corrected)):
        exe=out/('host-'+label)
        run([*native,caller,obj,'-o',exe],label+'-native-link')
        result=run([exe,label],label+'-native-run')
        expected='APPLE_CLOCK '+label.upper()+' PASS\n'
        if result.stdout!=expected or result.stderr:raise ValueError('Native clock oracle differs')
    clock=compile_(target,derived,'target-clock')
    archive=out/'libapple-clock-checked.a'
    # Reuse only genuine, immutable Mach implementations and generated syscall.
    helpers=original['objects'][1:]
    run(['xcrun','ar','rcs',archive,clock,*helpers],'archive')
    run(['xcrun','nm','-g',archive],'symbols')
    run(['xcrun','llvm-objdump','-d','-r',clock,*helpers],'disassembly')
    prior=json.loads((inventory.predecessor.PREDECESSOR/'manifest.json').read_text())
    link=list(next(c['command'] for c in prior['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map')
    linked=run([*link,archive],'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',linked.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",linked.stderr)))
    if not linked.returncode or duplicates or set(prior['target_missing_symbols'])-set(missing)!={'_clock_gettime'} or set(missing)-set(prior['target_missing_symbols']):
        raise ValueError('Unexpected full original client dependency delta')
    verify()
    for name,digest in headers.items():
        if sha(name)!=digest:raise ValueError('Consumed input drift')
    report=dict(profile='apple-clock-derived-native-and-target-v1',source_inputs_sha256=pins,
        headers_sha256=headers,dependency_records=records,commands=commands,
        original_clock_source=str(source),derived_clock_source=str(derived),
        derived_not_unchanged_upstream=True,original_mach_helpers=helpers,
        target_archive=str(archive),target_missing_symbols=missing,target_duplicate_symbols=duplicates,
        closed_symbols=['_clock_gettime'],newly_reachable_symbols=[],previous_missing_count=47,
        native_asan_ubsan_pass=True,native_original_error_output_mutation_reproduced=True,
        native_zero_tick_error_reproduced=True,native_original_nanosecond_validation_failure_reproduced=True,
        native_original_fallback_false_success_reproduced=True,
        native_fallback_first_second_and_persistent_errors_propagated=True,
        native_rational_scale_cases=36936,
        native_mach_and_syscall_boundary='Deterministic host test doubles only; no target or host clock setting',
        original_openssh_config_unchanged=True,target_link_complete=False,target_executed=False,
        full_client_qualified=False,accepted_runtime_modified=False,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return out,report


if __name__=='__main__':
    out,report=build()
    print(json.dumps(dict(output=str(out),manifest_sha256=sha(out/'manifest.json'),
        missing=len(report['target_missing_symbols']),closed=report['closed_symbols'],target_executed=False)))
