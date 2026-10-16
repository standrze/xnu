#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Offline boot-video ELF + one-object XNU console mirror, always inactive.

No loader, card, device tree, boot argument, VM mapping, or hardware changes.
The resulting kernel is NOT a bootable display package and has no mirror
publisher call site. Native proofs use exact Apple bodies with explicit host
transport/lock scaffolding; they do not emulate a Pi or prove scanout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile
from . import apple_console_native as native
from . import console_mirror_overlay as overlay

ROOT=native.ROOT
BASE=ROOT/'build/rpi5/root42-confirmed-kernel-20261013-final'
BASE_SHA='a51d2a68adb182b2980c67da3288f562d90727ef2a677fb8aa27890a6aca4539'
OBJ=ROOT/'build/rpi5-xcode27/fresh-435uage7/obj/DEVELOPMENT_ARM64_BCM2712'
DATABASE=OBJ/'compile_commands.json'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def deps(path,cwd):
    tokens=shlex.split(Path(path).read_text().replace('\\\n',' '))
    if not tokens or not tokens[0].endswith(':'):raise ValueError('Malformed actual compiler dependencies')
    return {str((Path(cwd)/name).resolve()) for name in tokens[1:]}


def elf_symbols(data):
    if data[:7]!=b'\x7fELF\x02\x01\x01' or struct.unpack_from('<HH',data,16)!=(2,183):
        raise ValueError('Not a static AArch64 ELF executable')
    phoff,shoff=struct.unpack_from('<QQ',data,32)
    phsize,phnum,shsize,shnum=struct.unpack_from('<HHHH',data,54)
    if (phsize,shsize)!=(56,64):raise ValueError('Unexpected ELF tables')
    for i in range(phnum):
        if struct.unpack_from('<I',data,phoff+i*phsize)[0] in (2,3):raise ValueError('Dynamic ELF forbidden')
    sections=[struct.unpack_from('<IIQQQQIIQQ',data,shoff+i*shsize) for i in range(shnum)]
    result=[]
    for section in sections:
        if section[1]!=2:continue
        strings=sections[section[6]];table=data[strings[4]:strings[4]+strings[5]]
        if section[9]!=24 or section[5]%24:raise ValueError('Invalid ELF symbol table')
        for i in range(section[4]+24,section[4]+section[5],24):
            name,info,other,index,value,size=struct.unpack_from('<IBBHQQ',data,i)
            del other,value,size
            label=table[name:table.index(b'\0',name)].decode()
            if index==0 and info>>4:raise ValueError('Unresolved target helper '+label)
            if info>>4:result.append(label)
    if 'rpi5_boot_video_encode' not in result:raise ValueError('Actual helper not linked')
    return sorted(result)


def build(output=None):
    basepath=BASE/'manifest.json'
    if sha(basepath)!=BASE_SHA:raise ValueError('Frozen kernel parent differs')
    base=json.loads(basepath.read_text());pins={str(basepath):BASE_SHA}
    for key in ('inputs_sha256','generated_sha256'):
        for name,digest in base[key].items():
            if name in pins and pins[name]!=digest:raise ValueError('Conflicting inherited closure')
            pins[name]=digest
    local=[Path(__file__).resolve(),Path(native.__file__).resolve(),Path(overlay.__file__).resolve(),
        overlay.SOURCE,overlay.HEADER,native.VIDEO,native.BOOT,native.LAYOUT,native.FONT,DATABASE,
        ROOT/'tools/rpi5/tests/test_boot_video_console.py',
        ROOT/'tools/rpi5/check_boot_video_console.py',ROOT/'tools/rpi5/tests/test_boot_video_console_artifact.py',
        *[native.HARNESS/name for name in ('boot_video_host.c','console_mirror_host.c','apple_video_glyph_host.c')],
        *[ROOT/'loader/rpi5'/name for name in ('boot_video.c','boot_video.h','boot_args.c','boot_args.h',
            'framebuffer_descriptor.c','framebuffer_descriptor.h','fdt.c','fdt.h','ranges.c','ranges.h','memory.S')]]
    def pin(path):
        name=str(Path(path).resolve());digest=sha(name)
        if name in pins and pins[name]!=digest:raise ValueError('Source changed within build '+name)
        pins[name]=digest
    for path in local:pin(path)
    def verify():
        for name,digest in pins.items():
            if sha(name)!=digest:raise ValueError('Closure changed: '+name)
    verify()
    if output is None:output=Path(tempfile.mkdtemp(prefix='boot-video-console-',dir=ROOT/'build/rpi5'))
    else:
        output=Path(output).resolve()
        if output.parent!=ROOT/'build/rpi5':raise ValueError('Exact fresh build child required')
        output.mkdir(exist_ok=False)
    commands=[];headers={};source_scan={}
    def run(args,label,cwd=ROOT,expected=0,allow_warnings=False):
        args=list(map(str,args));result=subprocess.run(args,cwd=cwd,capture_output=True,timeout=60)
        log=output/(label+'.log');log.write_bytes(result.stdout+result.stderr)
        row=dict(command=args,cwd=str(cwd),returncode=result.returncode,log=str(log),log_sha256=sha(log))
        commands.append(row)
        if result.returncode!=expected:raise ValueError('Build step failed: '+str(log))
        if not allow_warnings and b'warning:' in result.stderr:raise ValueError('Unexpected warning: '+str(log))
        return result.stdout.decode(errors='replace')
    def compile_unit(args,source,label,cwd=ROOT,extra=()):
        before=output/(label+'.scan.d');after=output/(label+'.actual.d');obj=output/(label+'.o')
        run([*args,'-M','-MF',before,source],label+'-scan',cwd)
        found=deps(before,cwd);source_scan[label]=sorted(found)
        for name in found:pin(name);headers[name]=pins[name]
        run([*args,'-c','-MD','-MF',after,source,'-o',obj,*extra],label+'-compile',cwd)
        if deps(after,cwd)!=found:raise ValueError('Compiler actual dependency set changed')
        for name in found:
            if sha(name)!=headers[name]:raise ValueError('Consumed header changed '+name)
        return obj
    clang=Path(subprocess.check_output(['xcrun','--find','clang'],text=True).strip())
    linker=Path(subprocess.check_output(['xcrun','--find','ld'],text=True).strip())
    sdk=subprocess.check_output(['xcrun','--show-sdk-path'],text=True).strip()
    for tool in (clang,linker):pin(tool)
    native.prepare(output)
    for name in ('boot_abi_original.inc','video_layout_original.inc','console_dispatch_original.inc','video_glyph_original.inc'):pin(output/name)
    # Compile each native source separately, admitting its real full header set
    # before compiler invocation; a final ordinary native link adds sanitizers.
    for name,command in native.commands(output).items():
        source_start=next(i for i,a in enumerate(command) if a.endswith('.c'))
        flags=[str(clang),'-isysroot',sdk,*command[2:source_start]]
        sources=command[source_start:command.index('-o')];objects=[]
        for i,source in enumerate(sources):objects.append(compile_unit(flags,source,name+'-'+str(i)))
        run([clang,'-isysroot',sdk,'-fsanitize=address,undefined',*objects,'-o',output/name],name+'-link')
        run([output/name],name+'-run')
    run([output/'console-mirror','invalid-index'],'native-invalid-index',expected=91)
    run([output/'apple-glyph','bad-expectation'],'native-bad-expectation',expected=74)
    freestanding=[str(clang),'--target=aarch64-none-elf','-mcpu=cortex-a76','-mstrict-align',
        '-ffreestanding','-fno-builtin','-fno-stack-protector','-mgeneral-regs-only','-O2',
        '-Wall','-Wextra','-Werror','-I',str(ROOT/'loader/rpi5')]
    objects=[compile_unit(freestanding,ROOT/'loader/rpi5'/name,'elf-'+Path(name).stem)
             for name in ('boot_video.c','boot_args.c','framebuffer_descriptor.c','fdt.c','ranges.c','memory.S')]
    lld=ROOT/'build/rpi5/zig-aarch64-macos-0.16.0/zig';pin(lld)
    elf=output/'NOT_RUN_boot_video.elf'
    run([lld,'ld.lld','--no-undefined','--image-base=0x70000','-e','rpi5_boot_video_encode',
         '-Ttext=0x80000',*objects,'-o',elf],'elf-link')
    symbols=elf_symbols(elf.read_bytes())
    # Whole original kernel TU, exact actual A76 flags/headers, only putc overlay.
    source=output/'serial_console.c';source.write_text(overlay.overlay(overlay.SOURCE.read_text()));pin(source)
    templates=json.loads(DATABASE.read_text())
    template=next(t for t in templates if t['file']==str(overlay.SOURCE))
    args=[];original=template['arguments'];i=0
    while i<len(original):
        a=original[i]
        if a in ('-o','-MF','-MT','-MQ','-MJ'):i+=2;continue
        if a in ('-c','-MD','-MMD','-MP') or a==template['file']:i+=1;continue
        args.append(a);i+=1
    if '-mcpu=cortex-a76' not in args:raise ValueError('Actual target CPU changed')
    obj=compile_unit(args,source,'serial-console-target',Path(template['directory']))
    run([*args,'-S',source,'-o',output/'serial_console.s'],'target-assembly',template['directory'])
    old=OBJ/'osfmk/DEVELOPMENT/serial_console.o'
    filelist=BASE/'kernel.root-confirmed.filelist';pin(filelist)
    kernel_objects=[Path(s) for s in filelist.read_text().splitlines()]
    if kernel_objects.count(old)!=1 or len(kernel_objects)!=len(set(kernel_objects)):raise ValueError('Exact one-object replacement failed')
    unchanged=[str(p) for p in kernel_objects if p!=old]
    newlist=output/'kernel.mirror.filelist';newlist.write_text(''.join(str(obj if p==old else p)+'\n' for p in kernel_objects))
    link=next(row['command'] for row in base['commands'] if row['log'].endswith('/link.log'))
    unstripped=output/'kernel.unstripped';kernel=output/'NOT_RUN_kernel.console-mirror';linkmap=output/'kernel.map'
    changes={str(filelist):str(newlist),str(BASE/'kernel.unstripped'):str(unstripped),
             '-Wl,-map,'+str(BASE/'kernel.map'):'-Wl,-map,'+str(linkmap)}
    if any(link.count(name)!=1 for name in changes):raise ValueError('Frozen complete link command changed')
    run([changes.get(a,a) for a in link],'kernel-link',allow_warnings=True)
    warnings=[s for s in (output/'kernel-link.log').read_text().splitlines() if 'warning:' in s]
    if warnings!=base['baseline_linker_warnings']:raise ValueError('New kernel link warning')
    run(['xcrun','strip','-S',unstripped,'-o',kernel],'kernel-strip')
    if run(['xcrun','nm','-ju',kernel],'kernel-undefined').strip():raise ValueError('Unresolved kernel symbol')
    mapped=linkmap.read_text(errors='surrogateescape')
    if str(old) in mapped or str(obj) not in mapped or any(name not in mapped for name in unchanged):
        raise ValueError('Actual kernel link composition differs')
    for symbol in ('_rpi5_console_mirror_publish','_rpi5_console_mirror_revoke','_rpi5_console_mirror_putc','_vcputc_options'):
        if symbol not in mapped:raise ValueError('Required linked symbol missing '+symbol)
    verify()
    report=dict(profile='rpi5-boot-video-uart-mirror-offline-v1',parent_manifest_sha256=BASE_SHA,
        kernel=str(kernel),kernel_sha256=sha(kernel),boot_video_elf=str(elf),elf_defined_symbols=symbols,
        inputs_sha256=pins,actual_headers_sha256=headers,compiler_scans=source_scan,commands=commands,
        replaced_objects={str(old):str(obj)},unchanged_link_objects=unchanged,
        original_video_console_object_unchanged=True,original_kprintf_object_unchanged=True,
        uart_first_once=True,original_newline_normalization=True,serial_input_unchanged=True,
        mirror_default_off=True,mirror_has_enable_callsite=False,poll_debugger_uart_only=True,
        native_renderer_cases=12288,native_guarded_ram=True,native_actual_dispatch=True,
        native_full_vt100_parser=False,boot_video_six_fields_only=True,
        framebuffer_mapping_created=False,scanout_proven=False,loader_integrated=False,
        pi_executed=False,installed=False,tool_identity_scope='compiler, Mach-O linker and ELF linker binaries pinned; not entire SDK/toolchain installation',
        generated_sha256={str(p):sha(p) for p in output.iterdir() if p.is_file()})
    (output/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return output,report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path)
    directory,report=build(parser.parse_args().output_dir)
    print(json.dumps(dict(directory=str(directory),kernel_sha256=report['kernel_sha256'],
        manifest_sha256=sha(directory/'manifest.json'),input_count=len(report['inputs_sha256']))))
