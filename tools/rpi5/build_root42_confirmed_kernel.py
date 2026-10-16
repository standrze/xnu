#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct two-object kernel: state-backed bounded late RAM-root admission."""
import argparse
import json
from pathlib import Path
import re
try:
    from . import build_root96_ready_delay_kernel as prior
except ImportError:
    import build_root96_ready_delay_kernel as prior
ROOT,audit=prior.ROOT,prior.audit
BASE=ROOT/'build/rpi5/root96-ready-delay-kernel-20261013-final'
BASE_SHA='73d44400c8b473d92fc186a199cce0fda908027248f1d2287a9888f62d08c23c'
MOUNT=ROOT/'build/rpi5/root-capacity-kernel-20261013-b'
MOUNT_SHA='cfeb6b6295f7d2e5efac8c33d3b5cd1783d4460e231ba3e995467c63a942a48a'
HEADER=ROOT/'loader/rpi5/ramroot_confirmation.h'
MARKER='RPI5XNU:TERMINAL:ROOT_READY SECONDS=%u NODES=%u BYTES=%llu READONLY\n'


def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Exact root confirmation boundary changed: '+old)
    return text.replace(old,new)


def mount_source(text):
    declaration='''#if MOCKFS_RPI5_RAMROOT
#include "HEADER_PATH"
_Static_assert(RPI5_RFS_NODES == 96 && RPI5_RFS_PAGE == 16384 &&
    RPI5_RFS_MAX == 67108864, "root confirmation geometry differs");
static uint64_t mockfs_rpi5_confirmed_root;
bool mockfs_rpi5_root_snapshot(uint32_t *nodes, uint64_t *bytes);
bool
mockfs_rpi5_root_snapshot(uint32_t *nodes, uint64_t *bytes)
{
    return rpi5_root_confirmation_snapshot(&mockfs_rpi5_confirmed_root, nodes, bytes);
}
static void
mockfs_ramroot_destroy'''.replace('HEADER_PATH',str(HEADER))
    text=once(text,'#if MOCKFS_RPI5_RAMROOT\nstatic void\nmockfs_ramroot_destroy',declaration)
    text=once(text,'\tmp->mnt_flag |= MNT_RDONLY;\n',
        '\tmp->mnt_flag |= MNT_RDONLY;\n'
        '\t/* Publish only the fully installed validated, read-only root. */\n'
        '\t(void)rpi5_root_confirmation_publish(&mockfs_rpi5_confirmed_root,\n'
        '\t    data->ramroot_count, data->ramroot_bytes, (mp->mnt_flag & MNT_RDONLY) != 0);\n')
    return once(text,'\tif (mockfs_mnt->ramroot_count) {\n\t\tmockfs_ramroot_destroy(mockfs_mnt);',
        '\tif (mockfs_mnt->ramroot_count) {\n'
        '\t\t/* vflush succeeded; revoke the snapshot before freeing its mount. */\n'
        '\t\trpi5_root_confirmation_clear(&mockfs_rpi5_confirmed_root);\n'
        '\t\tmockfs_ramroot_destroy(mockfs_mnt);')


def pe_source(text):
    text=once(text,'static uint64_t rpi5_wdog_terminal_report_after;\n',
        'static uint64_t rpi5_wdog_terminal_report_after;\n'
        'static unsigned rpi5_wdog_root_reports;\n'
        'extern bool mockfs_rpi5_root_snapshot(uint32_t *nodes, uint64_t *bytes);\n')
    return once(text,prior.ANNOUNCE,prior.ANNOUNCE+'''
    /* Existing service gate owns this counter. No VFS lock or mount pointer
     * is accessed from the timer/callout; a zero snapshot never consumes a try.
     * Repetition bounds noise, not console atomicity. Keep the original deadline.
     */
    if (rpi5_wdog_terminal_enabled && report_after != 0 && now >= report_after &&
        rpi5_wdog_root_reports < 3) {
        uint32_t nodes;
        uint64_t bytes;
        if (mockfs_rpi5_root_snapshot(&nodes, &bytes)) {
            rpi5_wdog_root_reports++;
            kprintf("\\nRPI5XNU:TERMINAL:ROOT_READY SECONDS=%u NODES=%u BYTES=%llu READONLY\\n",
                RPI5_TERMINAL_WDOG_SECONDS, nodes, bytes);
        }
    }
''')


def build(output):
    pins={};parents=[]
    for directory,expected in ((BASE,BASE_SHA),(MOUNT,MOUNT_SHA)):
        manifest=directory/'manifest.json'
        if audit.sha(manifest)!=expected:raise ValueError('Frozen kernel parent changed')
        report=json.loads(manifest.read_text());parents.append(report)
        for key in ('inputs_sha256','generated_sha256'):
            for name,digest in report[key].items():
                if name in pins and pins[name]!=digest:raise ValueError('Conflicting kernel ancestry')
                pins[name]=digest
        pins[str(manifest)]=expected
    base,mount=parents
    for path in (Path(__file__).resolve(),HEADER,ROOT/'tools/rpi5/tests/root_confirmation_native.c',
                 ROOT/'tools/rpi5/tests/test_root42_confirmed_kernel.py'):pins[str(path)]=audit.sha(path)
    def verify():
        for name,digest in pins.items():
            if audit.sha(Path(name))!=digest:raise ValueError('Frozen kernel closure changed: '+name)
    verify();output=output.resolve()
    if output.parent!=ROOT/'build/rpi5':raise ValueError('Fresh exact output child required')
    output.mkdir(exist_ok=False);commands=[];headers={}
    def execute(args,label,cwd=ROOT,warnings=False):
        row=audit.execute(list(map(str,args)),cwd,output/(label+'.log'));row['cwd']=str(cwd);commands.append(row)
        if row['returncode'] or (row['warning_count'] and not warnings):raise ValueError('Confirmation kernel step failed: '+row['log'])
        return row
    replacements={}
    for name,original,old_obj,template,cwd,transform in (
        ('pe_fiq',BASE/'pe_fiq.c',BASE/'pe_fiq.c.o',next(r['command'] for r in base['commands'] if r['log'].endswith('/compile.log')),
            audit.OBJ/'pexpert/DEVELOPMENT',pe_source),
        ('mockfs_vfsops',ROOT/'bsd/miscfs/mockfs/mockfs_vfsops.c',MOUNT/'mockfs_vfsops.o',
            next(r['command'] for r in mount['commands'] if r['log'].endswith('/mockfs_vfsops-compile.log')),
            audit.OBJ/'bsd/DEVELOPMENT',mount_source)):
        source=output/(name+'.c');source.write_text(transform(original.read_text()));pins[str(source)]=audit.sha(source)
        args=list(template[:template.index('-MD')]) if '-MD' in template else list(template[:template.index('-o')])
        args=[str(source) if a==str(original) else a for a in args]
        if args.count(str(source))!=1:raise ValueError('Exact source replacement missing')
        dep=output/(name+'.d');actual=output/(name+'.actual.d');obj=output/(name+'.o')
        execute([a for a in args if a!='-c']+['-M','-MF',dep],name+'-deps',cwd)
        before=audit.dependency_paths(dep,cwd)
        for path in before:headers[str(path)]=audit.sha(path)
        execute(args+['-MD','-MF',actual,'-o',obj],name+'-compile',cwd)
        if audit.dependency_paths(actual,cwd)!=before:raise ValueError('Actual consumed confirmation header set changed')
        execute([a for a in args if a!='-c']+['-S','-o',output/(name+'.s')],name+'-assembly',cwd)
        replacements[old_obj]=obj
    for name,digest in headers.items():
        if name in pins and pins[name]!=digest:raise ValueError('Actual consumed header drift')
        pins[name]=digest
    objects=[Path(s) for s in (BASE/'kernel.ready.filelist').read_text().splitlines()]
    if len(objects)!=len(set(objects)) or any(objects.count(p)!=1 for p in replacements):raise ValueError('Exact two-object replacement required')
    objects=[replacements.get(p,p) for p in objects];filelist=output/'kernel.root-confirmed.filelist'
    filelist.write_text(''.join(str(p)+'\n' for p in objects))
    kernel=output/'kernel.root-confirmed';unstripped=output/'kernel.unstripped';linkmap=output/'kernel.map'
    link=next(r['command'] for r in base['commands'] if r['log'].endswith('/link.log'))
    changes={str(BASE/'kernel.ready.filelist'):str(filelist),str(BASE/'kernel.unstripped'):str(unstripped),
        '-Wl,-map,'+str(BASE/'kernel.map'):'-Wl,-map,'+str(linkmap)}
    if any(link.count(p)!=1 for p in changes):raise ValueError('Exact complete kernel link changed')
    row=execute([changes.get(a,a) for a in link],'link',warnings=True)
    warnings=[s for s in Path(row['log']).read_text().splitlines() if 'warning:' in s]
    if warnings!=base['baseline_linker_warnings']:raise ValueError('New kernel link diagnostics')
    execute(['xcrun','strip','-S',unstripped,'-o',kernel],'strip')
    symbols=audit.read_command(['xcrun','nm','-nm',kernel]);(output/'kernel.symbols').write_text(symbols+'\n')
    if audit.read_command(['xcrun','nm','-ju',kernel]):raise ValueError('Undefined confirmation kernel symbol')
    mapped=linkmap.read_text(errors='surrogateescape')
    if any(str(p) not in mapped for p in objects) or any(str(p) in mapped for p in replacements):raise ValueError('Wrong actual kernel objects')
    linked=prior.prior.prior.capacity.previous.full.linked_audit(kernel.read_bytes(),symbols,mapped)
    if MARKER.encode() not in kernel.read_bytes():raise ValueError('Linked confirmation marker missing')
    native=output/'native-confirmation'
    execute(['xcrun','clang','-std=c11','-O1','-g','-fsanitize=address,undefined','-Wall','-Wextra','-Werror',
        ROOT/'tools/rpi5/tests/root_confirmation_native.c','-o',native],'native-build')
    execute([native],'native-run')
    verify()
    result=dict(profile='root42-state-confirmed-watchdog-kernel-v1',kernel=str(kernel),kernel_sha256=audit.sha(kernel),
        kernel_bytes=kernel.stat().st_size,parent_manifest_sha256=BASE_SHA,node_capacity=96,
        inputs_sha256=pins,actual_headers_sha256=headers,commands=commands,replaced_objects={str(k):str(v) for k,v in replacements.items()},
        link=linked,baseline_linker_warnings=warnings,root_ready_marker=MARKER,root_ready_max_reports=3,
        root_ready_first_minimum_post_enable_seconds=5,root_ready_successful_reload_only=True,
        actual_validated_mount_state_required=True,publication='single uint64 release store/acquire load; zero suppresses output',
        root_teardown_revokes_before_free=True,readers_take_no_vfs_locks=True,watchdog_deadline_seconds=180,
        watchdog_hardware_timeout_seconds=15,watchdog_service_interval_seconds=5,deadline_extended=False,
        original_mount_and_watchdog_ready_markers_retained=True,arbitrary_console_serialization=False,
        installed=False,pi_executed=False,generated_sha256={str(p):audit.sha(p) for p in output.iterdir() if p.is_file()})
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True)
    r=build(p.parse_args().output_dir);print(json.dumps({k:r[k] for k in ('kernel','kernel_sha256','kernel_bytes','profile')}))
