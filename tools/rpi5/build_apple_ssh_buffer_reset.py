#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct one-function OpenSSH correction; preserve original/failing baseline."""
import argparse
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
try:
    from . import build_apple_ssh_buffers as previous
except ImportError:
    import build_apple_ssh_buffers as previous

ROOT=previous.ROOT
BASE=ROOT/'build/rpi5/apple-ssh-buffers-_2f0fe7x'
BASE_SHA='6c0cf849532749ea53ca6c7363ff6c779aef6fb31671a630228d5c4426157cca'
PATCH=ROOT/'tools/rpi5/patches/sshbuf-reset-max.patch'
HARNESS=ROOT/'tools/rpi5/tests/apple_ssh_reset_host.c'
sha=previous.sha


def inputs():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Accepted original OpenSSH dependency manifest changed')
    base=json.loads((BASE/'manifest.json').read_text())
    pins=base['source_inputs_sha256']|base['headers_sha256']|base['generated_sha256']
    pins[str(BASE/'manifest.json')]=BASE_SHA
    for p in (PATCH,HARNESS,Path(__file__).resolve(),ROOT/'tools/rpi5/tests/test_apple_ssh_reset.py'):
        pins[str(p)]=sha(p)
    for name,pin in pins.items():
        if sha(Path(name))!=pin:raise ValueError('Preserved original/reset input changed: '+name)
    if previous.source_pins()!=base['source_inputs_sha256']:raise ValueError('Original vendor/runtime inputs changed')
    return pins,base


def build():
    captured,base=inputs();out=Path(tempfile.mkdtemp(prefix='apple-ssh-reset-',dir=ROOT/'build/rpi5'))
    commands=[]
    def execute(args,label,expected=(0,),cwd=ROOT):
        args=list(map(str,args));r=subprocess.run(args,cwd=cwd,text=True,capture_output=True,timeout=60)
        (out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr)
        commands.append(dict(command=args,returncode=r.returncode,stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode not in expected:raise ValueError('Reset correction build/test failed: '+str(out/(label+'.stderr')))
        return r.stdout.strip()
    overlay=out/'overlay';overlay.mkdir();source=overlay/'sshbuf.c'
    shutil.copyfile(previous.SOURCE/'sshbuf.c',source)
    execute(['patch','--batch','--fuzz=0','-p1','-i',PATCH],'patch',cwd=overlay)
    original=(previous.SOURCE/'sshbuf.c').read_text();corrected=source.read_text()
    begin='void\nsshbuf_reset(struct sshbuf *buf)\n';end='\nsize_t\nsshbuf_max_size('
    if original.count(begin)!=1 or corrected.count(begin)!=1:raise ValueError('Reset function boundary ambiguous')
    old_prefix,old_tail=original.split(begin);new_prefix,new_tail=corrected.split(begin)
    if old_tail.count(end)!=1 or new_tail.count(end)!=1:raise ValueError('Reset end boundary ambiguous')
    old_body,old_suffix=old_tail.split(end);new_body,new_suffix=new_tail.split(end)
    if old_prefix!=new_prefix or old_suffix!=new_suffix or old_body==new_body:
        raise ValueError('Only the actual reset body may change')
    diff=subprocess.run(['diff','-u',previous.SOURCE/'sshbuf.c',source],text=True,capture_output=True,timeout=30)
    if diff.returncode!=1:raise ValueError('Expected one actual modified source file')
    (out/'actual-source.diff').write_text(diff.stdout)
    reference=base['commands'][0]['command'];common=reference[:reference.index('-target')]
    tools=base['tool_identity']
    for row in tools.values():
        if sha(Path(row['path']))!=row['sha256']:raise ValueError('Compiler/archive/nm identity changed')
    objects=[];native=[];headers={}
    for index,name in enumerate(previous.UNITS):
        selected=source if name=='sshbuf.c' else previous.SOURCE/name
        obj=out/(str(index)+'-'+selected.stem+'.o');dep=out/(str(index)+'.d')
        execute(common+['-target','arm64-apple-darwin','-mcpu=cortex-a76','-ffreestanding','-O2',
            '-MD','-MF',dep,'-c',selected,'-o',obj],str(index)+'-target');objects.append(obj)
        data=obj.read_bytes()
        if data[:4]!=b'\xcf\xfa\xed\xfe' or int.from_bytes(data[4:8],'little')!=0x100000c or int.from_bytes(data[12:16],'little')!=1:
            raise ValueError('Actual ARM64 Mach-O object required')
        for name in shlex.split(dep.read_text().replace('\\\n',' ').partition(':')[2]):
            p=Path(name).resolve();headers[str(p)]=sha(p)
        host=out/(str(index)+'-native.o')
        execute(common+['-O1','-g','-fsanitize=address,undefined','-c',selected,'-o',host],str(index)+'-native');native.append(host)
    archive=out/'libapple-openssh-buffers-reset.a';execute(['xcrun','ar','rcs',archive,*objects],'archive')
    definitions=previous.symbols(archive,True)
    external=previous.symbols(archive,False)-definitions
    if definitions!=previous.symbols(Path(base['archive']),True):raise ValueError('Production archive definition set changed')
    if external!=set(base['selected_archive_dependency_inventory']['external_symbols']):
        raise ValueError('Reset correction added/changed production dependencies')
    original_program=out/'original-buffer-host-test'
    execute(common+['-O1','-g','-fsanitize=address,undefined',ROOT/'tools/rpi5/tests/apple_ssh_buffers_host.c',
        *native,'-Wl,-dead_strip','-o',original_program],'original-native-link')
    normal=execute([original_program],'original-normal')
    if normal!=base['host_test_stdout']:raise ValueError('Original ordinary buffer checks changed')
    execute([original_program,'--low-max-reset'],'original-reproducer-corrected',expected=(7,))
    program=out/'reset-host-test'
    execute(common+['-O1','-g','-fsanitize=address,undefined',HARNESS,*native,'-Wl,-dead_strip','-o',program],'reset-native-link')
    success=execute([program],'reset-native-run')
    if success!='APPLE_SSH_RESET_HOST_PASS CAPACITIES=514 ZEROIZATION=1 READONLY_PARENT=1 ALLOC_FAILURE=0':
        raise ValueError('Reset capacity/zeroization/read-only regression failed')
    # Only this additional HOST test interposes one allocation attempt. The
    # actual original recallocarray implementation still handles all others;
    # the production ARM64 archive has no symbol rename or failure wrapper.
    injected=out/'recallocarray-fault-native.o'
    execute(common+['-O1','-g','-fsanitize=address,undefined','-Drecallocarray=probe_recallocarray_real',
        '-c',previous.SOURCE/'openbsd-compat/recallocarray.c','-o',injected],'fault-allocator-native')
    test_objects=[injected if previous.UNITS[i]=='openbsd-compat/recallocarray.c' else p for i,p in enumerate(native)]
    fault_program=out/'reset-fault-host-test'
    execute(common+['-O1','-g','-fsanitize=address,undefined','-DSSH_RESET_ALLOC_FAULT=1',HARNESS,
        *test_objects,'-Wl,-dead_strip','-o',fault_program],'fault-native-link')
    fault=execute([fault_program],'fault-native-run')
    if fault!='APPLE_SSH_RESET_HOST_PASS CAPACITIES=514 ZEROIZATION=1 READONLY_PARENT=1 ALLOC_FAILURE=1':
        raise ValueError('Reset allocation-failure regression failed')
    if inputs()[0]!=captured or any(sha(Path(n))!=v for n,v in headers.items()):raise ValueError('Reset build inputs changed')
    generated={str(p):sha(p) for p in out.rglob('*') if p.is_file()}
    report=dict(profile='apple-openssh-buffer-reset-correction-v1',baseline=str(BASE),baseline_manifest_sha256=BASE_SHA,
        source_inputs_sha256=captured,headers_sha256=headers,generated_sha256=generated,commands=commands,
        source_commit=previous.COMMIT,source_units=list(previous.UNITS),patched_unit='sshbuf.c',
        patch_sha256=sha(PATCH),archive=str(archive),archive_sha256=sha(archive),tool_identity=tools,
        corrected_target_objects=True,upstream_checkout_unchanged=True,original_archive_and_failure_preserved=True,
        only_reset_body_changed=True,production_definition_set_unchanged=True,production_external_symbol_set_unchanged=True,
        apple_config_unchanged=True,crypto_pam_sandbox_declarations_unchanged=True,
        normal_host_test=normal,reset_host_test=success,allocation_fault_host_test=fault,
        reset_capacities=514,rounds_per_capacity=3,zeroization_checked=True,readonly_parent_behavior_checked=True,
        original_reproducer_before=-11,same_original_reproducer_after=7,
        reproducer_return_scope='Original harness intentional sentinel 7 is reached after len/free instead of SIGSEGV; new 514-capacity harness returns 0',
        allocation_failure_injection_scope='Extra native test only; production archive uses unchanged original recallocarray',
        host_native_libsystem_and_sanitizers=True,production_stub_functions_added=False,
        crypto_runtime_linked=False,pi_static_runtime_closed=False,pi_executed=False,installed=False,
        full_ssh_or_sshd_built=False,ethernet_or_ssh_proven=False,vm_or_pi_images_changed=False,
        scope='One documented source overlay and actual target archive; original/native reset regression fixed, not full SSH runtime/crypto or Pi acceptance')
    with (out/'manifest.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
    return report


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args();r=build()
    print(json.dumps({k:r[k] for k in ('archive','archive_sha256','reset_host_test','allocation_fault_host_test','pi_static_runtime_closed')},indent=2))
