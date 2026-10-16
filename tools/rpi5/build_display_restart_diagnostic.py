#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct instrumented restart image; unchanged userland, SMC and fallback."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid
from . import build_display_restart as original
from . import check_display_restart as oldcheck
from . import psci_restart_diagnostic_profile as policy
from . import restart_diag_access_profile as access

ROOT=original.ROOT
BASE=ROOT/'build/rpi5/display-restart-lw62p0x8'
BASE_SHA='58679b8dec4bbb9f785faed702dc48511d80615a8d7061aeb9eb63a7d8126c5d'
MARKER='RPI5XNU:DISPLAYRESTART_DIAG:ENTRY TAG='
PROFILE='rpi5-display-restart-diagnostic-full-composition-v1'
sha=original.sha
document=original.document

def sources():
    names=('build_display_restart_diagnostic.py','check_display_restart_diagnostic.py',
        'psci_restart_diagnostic_profile.py','restart_diagnostic_serial.py',
        'tests/test_display_restart_diagnostic.py','tests/test_psci_restart_diagnostic.py',
        'tests/psci_restart_diagnostic_host.c','tests/test_restart_diagnostic_serial.py')
    return [*(ROOT/'tools/rpi5'/name for name in names),*access.sources(),
        ROOT/'loader/rpi5/psci_restart_diagnostic.c',ROOT/'loader/rpi5/psci_restart_diagnostic.h',
        ROOT/'iokit/Kernel/rpi5_psci_restart_diagnostic.inc',Path(oldcheck.__file__),Path(original.__file__)]

def units(output,tag):
    base=document(BASE/'manifest.json');database=document(original.display.DATABASE)
    old={row['label']:row for row in base['commands']}
    flags=original.display.compiler_flags
    serial=next(row for row in database if row['file']==str(access.SERIAL))
    wm=document(original.display.KERNEL/'manifest.json')
    watchdog=next(row['command'] for row in wm['commands'] if row['log'].endswith('/pe_fiq-compile.log'))
    lf=flags(old['loader-main-compile']['command'],BASE/'probe_main.c')
    lf=[a if not a.startswith('-DRPI5_DISPLAY_XNU_TAG=') else '-DRPI5_DISPLAY_XNU_TAG="'+tag+'"' for a in lf]
    return {
        'platform':(flags(old['platform-compile']['command'],BASE/'IOPlatformExpert.restart.cpp'),output/'platform.cpp',Path(old['platform-compile']['cwd'])),
        'policy':(flags(old['policy-compile']['command'],ROOT/'loader/rpi5/psci_restart_candidate.c')+['-I',str(ROOT)],ROOT/'loader/rpi5/psci_restart_diagnostic.c',Path(old['policy-compile']['cwd'])),
        'serial':(flags(serial['arguments'],access.SERIAL)+['-I',str(ROOT),'-iquote',str(access.SERIAL.parent)],output/'pe_serial.c',Path(serial['directory'])),
        'watchdog':(flags(watchdog,access.FIQ)+['-I',str(ROOT)],output/'pe_fiq.c',original.display.OBJ/'pexpert/DEVELOPMENT'),
        'loader-main':(lf,output/'probe_main.c',ROOT),
        'loader-payload':(lf,output/'payload.S',ROOT)}

def generated_sources(output):
    return {'platform.cpp':policy.platform(policy.original.ORIGINAL.read_text()),
        'pe_serial.c':access.serial_source(access.SERIAL.read_text()),'pe_fiq.c':access.fiq_source(access.FIQ.read_text()),
        'probe_main.c':policy.main((BASE/'probe_main.c').read_text()),
        'payload.S':'.section .payload,"a"\n.balign 64\n.incbin "'+str(output/'payload.bin')+'"\n'}

def command_plan(output,tag):
    base=document(BASE/'manifest.json');old={row['label']:row for row in base['commands']}
    rows=[]
    def row(label,args,cwd=ROOT):rows.append(dict(label=label,command=list(map(str,args)),cwd=str(cwd)))
    all_units=units(output,tag)
    for label in ('platform','policy','serial','watchdog'):
        flags,source,cwd=all_units[label]
        if label=='serial':row('serial-original-compile',[*flags,'-c',access.SERIAL,'-o',output/'serial-original.o'],cwd)
        row(label+'-scan',[*flags,'-M','-MF',output/(label+'.scan.d'),source],cwd)
        row(label+'-compile',[*flags,'-c','-MD','-MF',output/(label+'.actual.d'),source,'-o',output/(label+'.o')],cwd)
    changes={str(BASE/'kernel.restart.filelist'):str(output/'kernel.filelist'),str(BASE/'kernel.unstripped'):str(output/'kernel.unstripped'),
        '-Wl,-map,'+str(BASE/'kernel.map'):'-Wl,-map,'+str(output/'kernel.map')}
    row('kernel-link',[changes.get(a,a) for a in old['kernel-link']['command']])
    row('kernel-strip',['xcrun','strip','-S',output/'kernel.unstripped','-o',output/'kernel.display-restart'])
    row('kernel-undefined',['xcrun','nm','-ju',output/'kernel.display-restart'])
    for label in ('loader-main','loader-payload'):
        flags,source,cwd=all_units[label]
        row(label+'-scan',[*flags,'-M','-MF',output/(label+'.scan.d'),source],cwd)
        row(label+'-compile',[*flags,'-c','-MD','-MF',output/(label+'.actual.d'),source,'-o',output/(label+'.o')],cwd)
    changes={str(BASE/'loader-main.o'):str(output/'loader-main.o'),str(BASE/'loader-payload.o'):str(output/'loader-payload.o'),
        str(BASE/'display_restart.elf'):str(output/'display_restart.elf')}
    row('loader-link',[changes.get(a,a) for a in old['loader-link']['command']])
    row('loader-objcopy',[ROOT/'tools/rpi5/tfa-objcopy','-O','binary',output/'display_restart.elf',output/'probe.bin'])
    row('loader-undefined',['xcrun','llvm-nm','--undefined-only',output/'display_restart.elf'])
    return rows

def replacements(output):
    return {str(BASE/'platform.o'):str(output/'platform.o'),str(BASE/'policy.o'):str(output/'policy.o'),
        str(original.display.OBJ/'pexpert/DEVELOPMENT/pe_serial.o'):str(output/'serial.o'),
        str(original.display.KERNEL/'pe_fiq.o'):str(output/'watchdog.o')}

def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen accepted restart parent required')
    base=document(BASE/'manifest.json');pins={str(BASE/'manifest.json'):BASE_SHA}
    def pin(path,expected=None):
        path=str(Path(path).absolute());actual=sha(path)
        if expected is not None and expected!=actual:raise ValueError('Input changed '+path)
        if path in pins and pins[path]!=actual:raise ValueError('Conflicting input '+path)
        pins[path]=actual
    for key in ('inputs_sha256','headers_sha256','generated_sha256'):
        for name,value in base[key].items():pin(name,value)
    for path in sources():pin(path)
    output=Path(tempfile.mkdtemp(prefix='display-restart-diagnostic-',dir=ROOT/'build/rpi5'));tag=uuid.uuid4().hex
    print('OUTPUT='+str(output),flush=True)
    for name,text in generated_sources(output).items():(output/name).write_text(text)
    original_list=(BASE/'kernel.restart.filelist').read_text().splitlines();changes=replacements(output)
    if any(original_list.count(name)!=1 for name in changes):raise ValueError('Unique actual kernel replacement boundary')
    (output/'kernel.filelist').write_text(''.join(changes.get(name,name)+'\n' for name in original_list))
    headers={};scans={};commands=[];plan=command_plan(output,tag)
    for row in plan:
        label=row['label']
        if label=='platform-scan':print('PHASE=actual-kernel-owner-compilation',flush=True)
        if label=='kernel-link':print('PHASE=full-kernel-link',flush=True)
        if label=='loader-main-scan':
            print('PHASE=unchanged-root33-tagged-loader',flush=True)
            for name in ('ramdisk.bin','root-catalog.json'):(output/name).write_bytes((BASE/name).read_bytes())
            (output/'payload.bin').write_bytes(original.payload_container.encode((output/'kernel.display-restart').read_bytes(),(output/'ramdisk.bin').read_bytes()))
        result=subprocess.run(row['command'],cwd=row['cwd'],capture_output=True,text=True,timeout=180)
        log=output/(label+'.log');log.write_text(result.stdout+result.stderr)
        commands.append(dict(row,returncode=result.returncode,log=str(log),log_sha256=sha(log)))
        if result.returncode:raise ValueError(label+': '+result.stderr[-4000:])
        warnings=[line for line in result.stderr.splitlines() if 'warning:' in line]
        accepted=[line for line in (BASE/(label+'.log')).read_text().splitlines() if 'warning:' in line] if label=='kernel-link' else []
        if label in ('serial-original-compile','serial-compile'):
            if len(warnings)!=1 or 'warning: variable length array folded to constant array as an extension [-Wgnu-folding-constant]' not in warnings[0]:raise ValueError('Unexpected original serial diagnostic')
        elif label=='platform-compile':
            if len(warnings)!=1 or "warning: variable 'i' set but not used" not in warnings[0]:raise ValueError('Unexpected platform diagnostics')
        elif warnings!=accepted:raise ValueError('Unexpected diagnostics '+label)
        if label.endswith('-scan'):
            unit=label[:-5];names=original.display.dependencies(output/(unit+'.scan.d'),Path(row['cwd']))
            for path in names:pin(path);headers[path]=pins[path]
            scans[unit]=sorted(names)
        if label.endswith('-compile') and label!='serial-original-compile':
            unit=label[:-8];names=original.display.dependencies(output/(unit+'.actual.d'),Path(row['cwd']))
            if sorted(names)!=scans[unit]:raise ValueError('Actual header closure differs '+unit)
            for path in names:pin(path,headers[path])
        if label.endswith('-undefined') and result.stdout.strip():raise ValueError('Linked undefined symbols '+label)
    for path,value in pins.items():
        if sha(path)!=value:raise ValueError('Inputs changed during composition '+path)
    raw=(output/'probe.bin').read_bytes();payload=(output/'payload.bin').read_bytes();offset=raw.find(payload)
    if offset<0 or offset%64 or raw.find(payload,offset+1)>=0:raise ValueError('Unique aligned embedded payload')
    m=dict(profile=PROFILE,parent=str(BASE),parent_manifest_sha256=BASE_SHA,tag=tag,image=str(output/'probe.bin'),image_bytes=len(raw),image_sha256=sha(output/'probe.bin'),
        kernel_sha256=sha(output/'kernel.display-restart'),root_sha256=base['root_sha256'],root_bytes=base['root_bytes'],root_nodes=33,
        kernel_replaced=changes,payload_offset=offset,terminal_seconds=180,hardware_watchdog_seconds=15,
        watchdog_reloaded_by_diagnostic=False,watchdog_deadline_changed=False,watchdog_rate_bound_proven=False,
        physical_psci_causality_proven=False,target_executed=False,poweroff_supported=False,
        commands=commands,inputs_sha256=pins,headers_sha256=headers,compiler_scans=scans,
        generated_sha256={str(path):sha(path) for path in output.rglob('*') if path.is_file()})
    (output/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(directory=str(output),manifest_sha256=sha(output/'manifest.json'),image_sha256=m['image_sha256']),indent=2),flush=True)
    return output

if __name__=='__main__':build()
