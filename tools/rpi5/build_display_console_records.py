#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Opt-in complete console-record image; no accepted source/file is modified."""
import json
from pathlib import Path
import subprocess
import tempfile
import uuid
from . import console_record_profile as profile
from . import build_display_restart_late_framed as late
from . import build_display_restart_diagnostic as diagnostic
from . import build_display_xnu_console as compiler
from . import root_capacity_profile as rootfs, payload_container, prepare_pid1

ROOT=profile.ROOT
BASE=ROOT/'build/rpi5/display-restart-late-framed-tquvyn12'
BASE_SHA='80fb3f47301a1d7be2ccc9834706f47feb635b98690e4c9404e383c196b77c2e'
KERNEL=profile.SERIAL.parent
KERNEL_SHA='fb09729396cf9bbec7ced1b50b7846c8fa23e4b9b03c51e2dd0304725257f5ae'
MARKER='RPI5XNU:DISPLAY_CONSOLE_RECORDS:ENTRY TAG='
PROFILE='rpi5-safe-thread-console-records-v1'
sha=diagnostic.sha
document=diagnostic.document
CONTRACT=dict(opt_in_pi5_only=True,normal_thread_kprintf_before_irq_mask=True,
    original_apple_printbuf_and_ring=True,maximum_normal_record_bytes=255,
    long_lines_split_without_truncation=True,all_output_atomicity_claimed=False,
    panic_irq_debugger_raw_escape_retained=True,restart_presmc_raw_unchanged=True,
    pl011_check_dr_nonblocking_single_cas=True,irq_lock_across_sleep_video=False,
    terminal_thread_callout_only=True,terminal_callout_armed_before_enqueue=True,
    terminal_callout_armed_before_ready=True,
    enabled_unarmed_gap_no_service=True,terminal_deadline_epoch_unchanged=True,
    terminal_seconds=180,hardware_watchdog_seconds=15,terminal_reload_seconds=5,
    old_copy_phase_limits_unchanged=True,short_pid1_state_label_only=True,
    unbounded_or_backlogged_tty_atomicity_claimed=False,target_executed=False)

def sources():
    return [Path(__file__).resolve(),ROOT/'tools/rpi5/check_display_console_records.py',
        ROOT/'tools/rpi5/tests/test_display_console_records.py',*profile.sources(),
        Path(compiler.__file__),Path(prepare_pid1.__file__),ROOT/'tools/rpi5/tests/test_root42_confirmation_service.py']

def generated(out):
    result={name+'.c':transform(source.read_text()) for name,source,transform,flags,cwd in profile.compiler_units()}
    result['probe_main.c']=profile.once((BASE/'probe_main.c').read_text(),late.MARKER,MARKER)
    result['payload.S']='.section .payload,"a"\n.balign 64\n.incbin "'+str(out/'payload.bin')+'"\n'
    result['init.c']=profile.init_source()
    result['init-host.c']=profile.once((ROOT/'tools/rpi5/tests/init_shutdown_late_framed_host.c').read_text(),profile.OLD_READY,profile.READY)
    return result

def replacements(out):
    return {str(compiler.OBJ/'pexpert/DEVELOPMENT/pe_kprintf.o'):str(out/'kprintf.o'),
        str(profile.CONSOLE.parent/'serial_console.o'):str(out/'console.o'),
        str(KERNEL/'serial.o'):str(out/'serial.o'),str(KERNEL/'watchdog.o'):str(out/'watchdog.o'),
        str(compiler.OBJ/'osfmk/DEVELOPMENT/sleh.o'):str(out/'sleh.o'),str(KERNEL/'policy.o'):str(out/'policy.o')}

def command_plan(out,tag):
    rows=[]
    def row(label,args,cwd=ROOT):rows.append(dict(label=label,command=list(map(str,args)),cwd=str(cwd)))
    for name,source,transform,flags,cwd in profile.compiler_units():
        del source,transform
        flags=[*flags,'-fstack-usage']
        row(name+'-scan',[*flags,'-M','-MF',out/(name+'.scan.d'),out/(name+'.c')],cwd)
        row(name+'-compile',[*flags,'-c','-MD','-MF',out/(name+'.actual.d'),out/(name+'.c'),'-o',out/(name+'.o')],cwd)
        row(name+'-assembly',[*flags,'-S',out/(name+'.c'),'-o',out/(name+'.s')],cwd)
    kernel_commands={r['label']:r for r in document(KERNEL/'manifest.json')['commands']}
    changes={str(KERNEL/'kernel.filelist'):str(out/'kernel.filelist'),str(KERNEL/'kernel.unstripped'):str(out/'kernel.unstripped'),
        '-Wl,-map,'+str(KERNEL/'kernel.map'):'-Wl,-map,'+str(out/'kernel.map')}
    row('kernel-link',[changes.get(a,a) for a in kernel_commands['kernel-link']['command']])
    row('kernel-strip',['xcrun','strip','-S',out/'kernel.unstripped','-o',out/'kernel.display-restart'])
    row('kernel-undefined',['xcrun','nm','-ju',out/'kernel.display-restart'])
    # Preserve genuine entry/runtime/utility objects; only the actual init TU
    # string changes. Native process doubles are in a separate executable.
    init_commands={r['label']:r for r in document(profile.INIT/'manifest.json')['commands']}
    for name,old_source in [('shutdown-init',profile.INIT/'init.c'),('host-init',profile.INIT/'init.c'),
                            ('host-harness',ROOT/'tools/rpi5/tests/init_shutdown_late_framed_host.c')]:
        old=init_commands[name+'-compile'];flags=compiler.compiler_flags(old['command'],old_source)
        source=out/('init-host.c' if name=='host-harness' else 'init.c')
        row(name+'-scan',[*flags,'-M','-MF',out/(name+'.scan.d'),source])
        row(name+'-compile',[*flags,'-c','-MD','-MF',out/(name+'.actual.d'),source,'-o',out/(name+'.o')])
    changes={str(profile.INIT/n):str(out/n) for n in ('shutdown-init.o','NOT_RUN_launchd','target.map','host-init.o','host-harness.o','init-host')}
    for label in ('target-link','host-link'):
        row(label,[changes.get(a,a) for a in init_commands[label]['command']])
    row('target-undefined',['xcrun','nm','-ju',out/'NOT_RUN_launchd'])
    row('target-disassembly',['xcrun','llvm-objdump','-d','-r',out/'shutdown-init.o'])
    row('host-run',[out/'init-host']);row('host-negative',[out/'init-host','bad-expectation'])
    loader={r['label']:r for r in document(BASE/'manifest.json')['commands']}
    flags=compiler.compiler_flags(loader['loader-main-compile']['command'],BASE/'probe_main.c')
    flags=[('-DRPI5_DISPLAY_XNU_TAG="'+tag+'"') if a.startswith('-DRPI5_DISPLAY_XNU_TAG=') else a for a in flags]
    for name,source in [('loader-main',out/'probe_main.c'),('loader-payload',out/'payload.S')]:
        row(name+'-scan',[*flags,'-M','-MF',out/(name+'.scan.d'),source])
        row(name+'-compile',[*flags,'-c','-MD','-MF',out/(name+'.actual.d'),source,'-o',out/(name+'.o')])
    changes={str(BASE/n):str(out/n) for n in ('loader-main.o','loader-payload.o','display_restart.elf')}
    if any(loader['loader-link']['command'].count(n)!=1 for n in changes):raise ValueError('Exact loader replacements')
    row('loader-link',[changes.get(a,a) for a in loader['loader-link']['command']])
    row('loader-objcopy',[ROOT/'tools/rpi5/tfa-objcopy','-O','binary',out/'display_restart.elf',out/'probe.bin'])
    row('loader-undefined',['xcrun','llvm-nm','--undefined-only',out/'display_restart.elf'])
    return rows

def build():
    pins={}
    def pin(path,expected=None):
        n=str(Path(path).absolute());h=sha(n)
        if (expected is not None and h!=expected) or (n in pins and pins[n]!=h):raise ValueError('Exact input changed '+n)
        pins[n]=h
    for directory,digest in [(BASE,BASE_SHA),(KERNEL,KERNEL_SHA),(profile.INIT,profile.INIT_SHA)]:
        pin(directory/'manifest.json',digest)
        for key in ('inputs_sha256','source_inputs_sha256','headers_sha256','generated_sha256'):
            for n,h in document(directory/'manifest.json').get(key,{}).items():pin(n,h)
    for path in sources():pin(path)
    for path in profile.PINS:pin(path,profile.PINS[path])
    pin('/usr/bin/xcrun')
    for tool in ('clang','clang++','ld','strip','nm','llvm-objdump'):
        pin(subprocess.check_output(['xcrun','--find',tool],text=True).strip())
    out=Path(tempfile.mkdtemp(prefix='display-console-records-',dir=ROOT/'build/rpi5'));tag=uuid.uuid4().hex
    print('OUTPUT='+str(out),flush=True)
    for n,raw in generated(out).items():(out/n).write_text(raw)
    original=(KERNEL/'kernel.filelist').read_text().splitlines();changes=replacements(out)
    if any(original.count(n)!=1 for n in changes):raise ValueError('Exact six kernel owners')
    (out/'kernel.filelist').write_text(''.join(changes.get(n,n)+'\n' for n in original))
    commands=[];headers={};scans={}
    for row in command_plan(out,tag):
        label=row['label']
        if label in ('kprintf-scan','kernel-link','shutdown-init-scan','host-run','loader-main-scan'):
            print('PHASE='+label,flush=True)
        if label=='loader-main-scan':
            kernel=(out/'kernel.display-restart').read_bytes();files=rootfs.files_from((BASE/'ramdisk.bin').read_bytes())
            files['/sbin/launchd']=((out/'NOT_RUN_launchd').read_bytes(),files['/sbin/launchd'][1])
            root,catalog=rootfs.build(files)
            if len(catalog['entries'])!=33 or rootfs.inspect(root)!=catalog:raise ValueError('Root33 catalog')
            (out/'ramdisk.bin').write_bytes(root);(out/'root-catalog.json').write_text(json.dumps(catalog,sort_keys=True,indent=2)+'\n')
            (out/'payload.bin').write_bytes(payload_container.encode(kernel,root))
        r=subprocess.run(row['command'],cwd=row['cwd'],capture_output=True,text=True,timeout=180)
        log=out/(label+'.log');log.write_text(r.stdout+r.stderr)
        commands.append(dict(row,returncode=r.returncode,log=str(log),log_sha256=sha(log)))
        if r.returncode!=(37 if label=='host-negative' else 0):raise ValueError(label+': '+r.stderr[-5000:])
        warnings=[s for s in r.stderr.splitlines() if 'warning:' in s]
        if label in ('serial-compile','serial-assembly'):
            if len(warnings)!=1 or 'variable length array folded to constant array' not in warnings[0]:raise ValueError('Unexpected serial warning')
        elif label=='kernel-link':
            old=[s for s in (KERNEL/'kernel-link.log').read_text().splitlines() if 'warning:' in s]
            if warnings!=old:raise ValueError('Unexpected kernel link warnings')
        elif warnings:raise ValueError('Unexpected diagnostics '+label)
        if label.endswith('-scan'):
            name=label[:-5];scans[name]=sorted(compiler.dependencies(out/(name+'.scan.d'),Path(row['cwd'])))
            for n in scans[name]:pin(n);headers[n]=pins[n]
        if label.endswith('-compile'):
            name=label[:-8]
            if sorted(compiler.dependencies(out/(name+'.actual.d'),Path(row['cwd'])))!=scans[name]:raise ValueError('Actual header disagreement')
        if label.endswith('-undefined') and r.stdout.strip():raise ValueError('Linked undefined symbols '+label)
        if label=='host-run' and (r.stderr or 'INIT_SHUTDOWN_LATE PASS CASES=205 ' not in r.stdout):raise ValueError('Actual PID1 native cases')
    for n,h in pins.items():
        if sha(n)!=h:raise ValueError('Input changed during composition '+n)
    raw=(out/'probe.bin').read_bytes();payload=(out/'payload.bin').read_bytes();offset=raw.find(payload)
    if offset<0 or offset%64 or raw.find(payload,offset+1)>=0:raise ValueError('Unique actual embedded payload')
    m=dict(profile=PROFILE,parent=str(BASE),parent_manifest_sha256=BASE_SHA,kernel_parent=str(KERNEL),kernel_parent_manifest_sha256=KERNEL_SHA,
        init_parent=str(profile.INIT),init_parent_manifest_sha256=profile.INIT_SHA,tag=tag,
        image=str(out/'probe.bin'),image_sha256=sha(out/'probe.bin'),image_bytes=len(raw),payload_offset=offset,
        kernel_sha256=sha(out/'kernel.display-restart'),root_sha256=sha(out/'ramdisk.bin'),root_bytes=(out/'ramdisk.bin').stat().st_size,
        root_nodes=33,launchd_sha256=sha(out/'NOT_RUN_launchd'),init_shutdown_ready_marker=profile.READY,init_shutdown_ready_max_reports=3,
        target_inspection=prepare_pid1.inspect((out/'NOT_RUN_launchd').read_bytes()),console_record_contract=CONTRACT,
        kernel_replacements=changes,commands=commands,inputs_sha256=pins,headers_sha256=headers,compiler_scans=scans,
        generated_sha256={str(f):sha(f) for f in out.iterdir() if f.is_file()})
    (out/'manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(package=str(out),manifest_sha256=sha(out/'manifest.json'),image_sha256=m['image_sha256']),indent=2),flush=True)
    return out

if __name__=='__main__':build()
