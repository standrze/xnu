#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct same-boot allocation/Normal-NC Apple console candidate; offline only."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile
import uuid
from . import display_xnu_overlays as overlay
from . import payload_container
from . import ramroot

ROOT=overlay.ROOT
KERNEL=ROOT/'build/rpi5/root42-confirmed-kernel-20261013-final'
KERNEL_SHA='a51d2a68adb182b2980c67da3288f562d90727ef2a677fb8aa27890a6aca4539'
LOADER=overlay.ARM.parent
LOADER_SHA='eed613aaa91207b3c6db298fe811e4400bb4dca2d1a7ec8858243f817561b301'
WORKING=ROOT/'build/rpi5/bl33-probe-vszhh6o4'
ROOT_SHA='3fa5ed9f501cedd744b0d6d75cc0886837db562f3bd42282284d82e2798d9a27'
OBJ=ROOT/'build/rpi5-xcode27/fresh-435uage7/obj/DEVELOPMENT_ARM64_BCM2712'
DATABASE=OBJ/'compile_commands.json'
EXTRA_LOADER=('display_xnu_handoff.c','display_allocation_retained.c','display_allocate_wire.c','display_allocate_transaction.c','display_mailbox_fdt.c','display_query_arch.S')
def kernel_units():
    return (
        ('serial_console',ROOT/'osfmk/console/serial_console.c',overlay.serial,OBJ/'osfmk/DEVELOPMENT/serial_console.o'),
        ('video_console',ROOT/'osfmk/console/video_console.c',overlay.video,OBJ/'osfmk/DEVELOPMENT/video_console.o'),
        ('pmap',ROOT/'osfmk/arm/pmap/pmap.c',overlay.pmap,OBJ/'osfmk/DEVELOPMENT/pmap.o'),
        ('arm_init',overlay.ARM,overlay.arm,LOADER/'arm_init.c.o'))
def compiler_flags(record,oldsource):
    args=[];i=0
    while i<len(record):
        a=record[i]
        if a in ('-o','-MF','-MT','-MQ','-MJ'):i+=2;continue
        if a in ('-c','-MD','-MMD','-MP') or a==str(oldsource):i+=1;continue
        args.append(a);i+=1
    return args
def command_plan(output,tag):
    """Pure reconstruction, not executable authority or historical replay."""
    parents={p:json.loads((p/'manifest.json').read_text()) for p in (KERNEL,LOADER)}
    templates=json.loads(DATABASE.read_text());rows=[];scans={};replacement={}
    def row(label,args,cwd=ROOT):rows.append((label,list(map(str,args)),str(cwd)))
    def unit(args,source,label,cwd=ROOT):
        row(label+'-scan',[*args,'-M','-MF',output/(label+'.scan.d'),source],cwd)
        row(label+'-compile',[*args,'-c','-MD','-MF',output/(label+'.actual.d'),source,'-o',output/(label+'.o')],cwd)
        scans[label]=str(cwd)
    for name,source,transform,old in kernel_units():
        if name=='arm_init':
            record=next(r['command'] for r in parents[LOADER]['commands'] if r['log'].endswith('/arm_init.c-compile.log'))
            args=compiler_flags(record,source);cwd=OBJ/'osfmk/DEVELOPMENT'
        else:
            template=next(t for t in templates if t['file']==str(source));cwd=Path(template['directory']);args=compiler_flags(template['arguments'],source)
            args[1:1]=['-I',str(ROOT),'-iquote',str(source.parent)]
        if name in ('arm_init','video_console'):row(name+'-original-compile',[*args,'-c',source,'-o',output/(name+'-original.o')],cwd)
        generated=output/(name+'.c');unit(args,generated,name,cwd)
        row(name+'-assembly',[*args,'-S',generated,'-o',output/(name+'.s')],cwd)
        replacement[str(old)]=str(output/(name+'.o'))
    filelist=KERNEL/'kernel.root-confirmed.filelist'
    link=next(r['command'] for r in parents[KERNEL]['commands'] if r['log'].endswith('/link.log'))
    changes={str(filelist):str(output/'kernel.display.filelist'),str(KERNEL/'kernel.unstripped'):str(output/'kernel.unstripped'),
        '-Wl,-map,'+str(KERNEL/'kernel.map'):'-Wl,-map,'+str(output/'kernel.map')}
    row('kernel-link',[changes.get(a,a) for a in link]);row('kernel-strip',['xcrun','strip','-S',output/'kernel.unstripped','-o',output/'kernel.display-console'])
    row('kernel-undefined',['xcrun','nm','-ju',output/'kernel.display-console'])
    main_record=next(r['command'] for r in parents[LOADER]['commands'] if r['log'].endswith('/loader-main.log'))
    flags=compiler_flags(main_record,overlay.LOADER)+['-DRPI5_DISPLAY_XNU_TAG="'+tag+'"']
    for name in ('probe_main','firmware_seed_tree','display_xnu_allocate'):unit(flags,output/(name+'.c'),'loader-'+name)
    for name in EXTRA_LOADER:unit(flags,ROOT/'loader/rpi5'/name,'loader-'+Path(name).stem)
    unit(flags,output/'payload.S','loader-payload')
    link=next(r['command'] for r in parents[LOADER]['commands'] if r['log'].endswith('/firmware-fdt-link.log'))
    changes={str(LOADER/'probe_main.o'):str(output/'loader-probe_main.o'),str(LOADER/'firmware_seed_tree.o'):str(output/'loader-firmware_seed_tree.o'),
        str(WORKING/'payload.o'):str(output/'loader-payload.o'),str(ROOT/'loader/rpi5/probe.ld'):str(output/'display_xnu.ld')}
    args=[changes.get(a,a) for a in link];args[args.index('-o')+1]=str(output/'display_xnu.elf')
    args[args.index('-o'):args.index('-o')]=[str(output/'loader-display_xnu_allocate.o'),*[str(output/('loader-'+Path(n).stem+'.o')) for n in EXTRA_LOADER]]
    row('loader-link',args);row('loader-objcopy',[ROOT/'tools/rpi5/tfa-objcopy','-O','binary',output/'display_xnu.elf',output/'probe.bin'])
    row('loader-undefined',['xcrun','llvm-nm','--undefined-only',output/'display_xnu.elf']);row('loader-symbols',['xcrun','llvm-nm','-n',output/'display_xnu.elf'])
    return rows,scans,replacement
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dependencies(p,cwd):
    tokens=shlex.split(Path(p).read_text().replace('\\\n',' '))
    if not tokens or not tokens[0].endswith(':'):raise ValueError('Bad compiler dependency output')
    return {str((Path(cwd)/s).resolve()) for s in tokens[1:]}
def stack_budget(output,parent):
    # The new pre-CPU_ON chain is nonrecursive. Deliberately sum every reused
    # FDT/range frame and every new helper frame, even mutually exclusive
    # branches. Original recursive ADT/planner chains retain their separately
    # reviewed depth bounds, with all new helper frames added as an overcount.
    reused=[row for row in parent['stack_frames'] if row['location'].split(':')[0] in
        ('loader/rpi5/fdt.c','loader/rpi5/fdt_reg.c','loader/rpi5/ranges.c')]
    fresh=[];caller=[]
    for path in sorted(output.glob('loader-*.su')):
        for line in path.read_text().splitlines():
            location,size,kind=line.split('\t');size=int(size)
            if kind!='static' or size<0:raise ValueError('Unbounded display stack frame')
            row=dict(location=location,bytes=size,kind=kind)
            if path.name=='loader-probe_main.su':
                if location.rsplit(':',1)[-1] in ('probe_el1_main','runtime_cpus','display_allocate','board_tree_diagnostic'):caller.append(row)
            elif path.name!='loader-firmware_seed_tree.su':fresh.append(row)
    if len(caller)!=4 or not fresh or not reused:raise ValueError('Missing actual stack inputs')
    allocation=sum(r['bytes'] for r in reused+fresh+caller)
    original=max(parent['stack_budgets']['firmware_fdt']['conservative_bytes'],
        *parent['stack_budgets']['runtime_plan']['paths_bytes'].values(),*parent['stack_budgets']['tree']['paths_bytes'].values())
    old_chosen=next(row['bytes'] for row in parent['stack_frames'] if row['location'].endswith(':board_tree_diagnostic'))
    new_chosen=next(row['bytes'] for row in caller if row['location'].endswith(':board_tree_diagnostic'))
    seed=next(int(line.split('\t')[1]) for line in (output/'loader-firmware_seed_tree.su').read_text().splitlines() if ':rpi5_firmware_seed_tree\t' in line)
    original_seed=next(row['bytes'] for row in parent['stack_frames'] if row['location'].endswith(':rpi5_firmware_seed_tree'))
    retained=original+sum(r['bytes'] for r in fresh)+max(0,new_chosen-old_chosen)+max(0,seed-original_seed)
    maximum=max(allocation,retained)
    if maximum+512>=32768:raise ValueError('Display stack exceeds exact 32KiB primary bound')
    return dict(allocation_chain_conservative=allocation,retained_original_paths_conservative=retained,
        conservative_bytes=maximum,stack_bytes=32768,required_margin=512,minimum_remaining_bytes=32768-maximum,
        scope='Overcounted actual nonrecursive allocation frames plus reviewed original recursive ADT bounds; masked IRQ and separate fault stack required',
        fresh_frames=fresh,caller_frames=caller,reused_frames=reused)
def build(output=None,kernel_only=False):
    pins={};parents={}
    def pin(p,digest=None):
        # Retain exact inherited names (including clang++ symlink identity),
        # not only their resolved target; closure membership is authoritative.
        p=str(Path(p).absolute());actual=sha(p)
        if digest is not None and actual!=digest:raise ValueError('Pinned bytes changed: '+p)
        if p in pins and pins[p]!=actual:raise ValueError('Conflicting closure: '+p)
        pins[p]=actual
    for directory,digest in ((KERNEL,KERNEL_SHA),(LOADER,LOADER_SHA)):
        path=directory/'manifest.json';pin(path,digest);report=json.loads(path.read_text());parents[directory]=report
        for key in ('inputs_sha256','generated_sha256'):
            for name,value in report[key].items():pin(name,value)
    for p in (Path(__file__),Path(overlay.__file__),Path(payload_container.__file__),Path(ramroot.__file__),DATABASE,
              ROOT/'loader/rpi5/console_mirror.h',ROOT/'loader/rpi5/display_xnu_record.h',
              ROOT/'loader/rpi5/display_xnu_handoff.h',ROOT/'loader/rpi5/display_xnu_handoff.c',
              ROOT/'loader/rpi5/display_xnu_allocate.h',ROOT/'osfmk/arm64/rpi5_display_xnu.inc',
              ROOT/'osfmk/arm64/rpi5_display_xnu_api.h',ROOT/'tools/rpi5/tests/test_display_xnu_handoff.py',
              ROOT/'tools/rpi5/tests/display_xnu_handoff_host.c',ROOT/'tools/rpi5/tests/test_display_xnu_allocator.py',
              ROOT/'tools/rpi5/tests/test_display_xnu_mapping.py',ROOT/'tools/rpi5/tests/test_display_xnu_console_package.py',
              ROOT/'tools/rpi5/check_display_xnu_console.py',Path(overlay.mirror.__file__),overlay.ALLOCATOR,
              ROOT/'tools/rpi5/tests/test_display_allocate_zero_adapter.py',ROOT/'tools/rpi5/tests/display_allocate_zero_adapter_host.c',
              ROOT/'tools/rpi5/tests/test_display_mailbox_fdt.py',ROOT/'tools/rpi5/tests/test_pcie_fdt.py') :pin(p)
    for name in ('clang','ld','llvm-nm','strip'):
        pin(subprocess.check_output(['xcrun','--find',name],text=True).strip())
    for path in (ROOT/'tools/rpi5/tfa-lld',ROOT/'tools/rpi5/tfa-objcopy',ROOT/'build/rpi5/zig-aarch64-macos-0.16.0/zig'):pin(path)
    output=Path(tempfile.mkdtemp(prefix='display-xnu-console-',dir=ROOT/'build/rpi5')) if output is None else Path(output).resolve()
    if not output.is_dir():
        if output.parent!=ROOT/'build/rpi5':raise ValueError('Fresh build child required')
        output.mkdir(exist_ok=False)
    elif output.name.startswith('display-xnu-console-') and not any(output.iterdir()):pass
    else:raise ValueError('Refuse existing output')
    commands=[];headers={};scans={};tag=uuid.uuid4().hex
    def run(args,label,cwd=ROOT,warning=None):
        args=list(map(str,args));result=subprocess.run(args,cwd=cwd,capture_output=True,timeout=120)
        log=output/(label+'.log');log.write_bytes(result.stdout+result.stderr)
        row=dict(command=args,cwd=str(cwd),returncode=result.returncode,log=str(log),log_sha256=sha(log));commands.append(row)
        if result.returncode:raise ValueError('Build failed: '+str(log))
        warnings=[s for s in result.stderr.decode(errors='replace').splitlines() if 'warning:' in s]
        if warning=='arm':
            if len(warnings)!=1 or "dyld_kernel_fixups.h:367:12: warning: variable 'cnt' set but not used" not in warnings[0]:raise ValueError('Unexpected arm warning: '+str(log))
        elif warning=='video':
            if len(warnings)!=1 or "video_console.c:1771:52: warning: variable 'rowscanline' set but not used" not in warnings[0]:raise ValueError('Unexpected original renderer warning: '+str(log))
        elif warning=='link':
            if warnings!=parents[KERNEL]['baseline_linker_warnings']:raise ValueError('Unexpected link warning: '+str(log))
        elif warnings:raise ValueError('Unexpected warning: '+str(log))
        return result.stdout.decode(errors='replace')
    flags=compiler_flags
    def compile(args,source,label,cwd=ROOT,warning=None):
        pin(source);before=output/(label+'.scan.d');after=output/(label+'.actual.d');obj=output/(label+'.o')
        run([*args,'-M','-MF',before,source],label+'-scan',cwd)
        found=dependencies(before,cwd);scans[label]=sorted(found)
        for path in found:pin(path);headers[path]=pins[path]
        run([*args,'-c','-MD','-MF',after,source,'-o',obj],label+'-compile',cwd,warning)
        if dependencies(after,cwd)!=found:raise ValueError('Actual dependency set changed')
        for path in found:pin(path,headers[path])
        return obj
    templates=json.loads(DATABASE.read_text());replacement={}
    for name,source,transform,old in kernel_units():
        pin(source);generated=output/(name+'.c');generated.write_text(transform(source.read_text()))
        if name=='arm_init':
            record=next(r for r in parents[LOADER]['commands'] if r['log'].endswith('/arm_init.c-compile.log'))
            args=flags(record['command'],source);cwd=OBJ/'osfmk/DEVELOPMENT'
        else:
            template=next(t for t in templates if t['file']==str(source));cwd=Path(template['directory']);args=flags(template['arguments'],source)
            args[1:1]=['-I',str(ROOT),'-iquote',str(source.parent)]
        if '-mcpu=cortex-a76' not in args:raise ValueError('Actual target CPU changed')
        warning='arm' if name=='arm_init' else 'video' if name=='video_console' else None
        if warning:
            run([*args,'-c',source,'-o',output/(name+'-original.o')],name+'-original-compile',cwd,warning)
        replacement[str(old)]=compile(args,generated,name,cwd,warning)
        run([*args,'-S',generated,'-o',output/(name+'.s')],name+'-assembly',cwd,warning)
    filelist=KERNEL/'kernel.root-confirmed.filelist';pin(filelist)
    oldobjects=filelist.read_text().splitlines()
    if len(oldobjects)!=len(set(oldobjects)) or any(oldobjects.count(name)!=1 for name in replacement):raise ValueError('Four-object composition differs')
    newlist=output/'kernel.display.filelist';newlist.write_text(''.join(str(replacement.get(p,p))+'\n' for p in oldobjects))
    link=next(r['command'] for r in parents[KERNEL]['commands'] if r['log'].endswith('/link.log'))
    kernel=output/'kernel.display-console';unstripped=output/'kernel.unstripped';linkmap=output/'kernel.map'
    changes={str(filelist):str(newlist),str(KERNEL/'kernel.unstripped'):str(unstripped),'-Wl,-map,'+str(KERNEL/'kernel.map'):'-Wl,-map,'+str(linkmap)}
    if any(link.count(k)!=1 for k in changes):raise ValueError('Original kernel link changed')
    run([changes.get(a,a) for a in link],'kernel-link',warning='link')
    run(['xcrun','strip','-S',unstripped,'-o',kernel],'kernel-strip')
    if run(['xcrun','nm','-ju',kernel],'kernel-undefined').strip():raise ValueError('Undefined kernel symbols')
    mapped=linkmap.read_text(errors='surrogateescape')
    for old,new in replacement.items():
        if old in mapped or str(new) not in mapped:raise ValueError('Wrong linked console object')
    for symbol in ('_rpi5_display_xnu_mapping_verify','_rpi5_display_xnu_video_admit','_rpi5_console_mirror_publish','_initialize_screen'):
        if symbol not in mapped:raise ValueError('Required kernel symbol missing '+symbol)
    report=dict(profile='pi5-display-xnu-sameboot-console-v1',kernel=str(kernel),kernel_sha256=sha(kernel),
        replaced_objects={k:str(v) for k,v in replacement.items()},commands=commands,physical_execution=False,installed=False,
        scanout_proven=False,managed_span=[0x6000000,0x10000000],framebuffer_policy='exact retained allocation only; Normal-NC index1=0x44, kernel RW NX/PNX',
        uart_first=True,uart_input_unchanged=True,apple_renderer_unchanged=True,mirror_enable_after_initialize_screen=True,
        global_feature_macro_changed=False,loader_integrated=False,tag=tag,
        terminal_watchdog_seconds=180,watchdog_countdown_seconds=15,watchdog_deadline_extended=False,
        automatic_return_contract='unchanged terminal deadline; cease reload by180s, active hardware timeout15s; fresh NVMe return separately required',
        original_watchdog_object_unchanged=True)
    if not kernel_only:
        # Preserve the exact already operational root, rather than substituting
        # a new userland as part of display integration.
        payload=WORKING/'payload.bin';pin(payload)
        raw=payload.read_bytes()
        if raw[:8]!=b'RPI5XNU\0' or struct.unpack_from('<II',raw,8)!=(1,64) or struct.unpack_from('<I',raw,24)[0]!=2:raise ValueError('Working payload shape changed')
        root_offset,root_bytes=struct.unpack_from('<QQ',raw,128+8)
        root=raw[root_offset:root_offset+root_bytes]
        if len(root)!=1916928 or hashlib.sha256(root).hexdigest()!=ROOT_SHA:raise ValueError('Working zsh root changed')
        root_catalog=ramroot.inspect(root)
        if len(root_catalog['entries'])!=32 or not any(r['path']=='/bin/zsh' for r in root_catalog['entries']):raise ValueError('Exact operating root32 zsh absent')
        (output/'root-catalog.json').write_text(json.dumps(root_catalog,indent=2,sort_keys=True)+'\n')
        packed=output/'payload.bin';packed.write_bytes(payload_container.encode(kernel.read_bytes(),root))
        assembly=output/'payload.S';assembly.write_text('.section .payload,"a"\n.balign 64\n.incbin "'+str(packed)+'"\n')
        main_record=next(r['command'] for r in parents[LOADER]['commands'] if r['log'].endswith('/loader-main.log'))
        loaderflags=flags(main_record,overlay.LOADER)
        loaderflags+=['-DRPI5_DISPLAY_XNU_TAG="'+tag+'"']
        units={}
        for name,source,transform in (
            ('probe_main',overlay.LOADER,overlay.loader),('firmware_seed_tree',overlay.SEED,overlay.seed),
            ('display_xnu_allocate',overlay.ALLOCATOR,overlay.allocator)):
            pin(source);generated=output/(name+'.c');generated.write_text(transform(source.read_text()));units[name]=compile(loaderflags,generated,'loader-'+name)
        for name in EXTRA_LOADER:
            units[Path(name).stem]=compile(loaderflags,ROOT/'loader/rpi5'/name,'loader-'+Path(name).stem)
        units['payload']=compile(loaderflags,assembly,'loader-payload')
        ld=output/'display_xnu.ld';original_ld=ROOT/'loader/rpi5/probe.ld';pin(original_ld)
        ld.write_text(overlay.once(original_ld.read_text(),'.stack (NOLOAD) : { . += 0x4000; }','.stack (NOLOAD) : { . += 0x8000; }')+
            '\nASSERT(__probe_end < 0xb000000, "Display loader overlaps original firmware FDT load window")\n')
        link=next(r['command'] for r in parents[LOADER]['commands'] if r['log'].endswith('/firmware-fdt-link.log'))
        replace={str(LOADER/'probe_main.o'):str(units.pop('probe_main')),str(LOADER/'firmware_seed_tree.o'):str(units.pop('firmware_seed_tree')),
                 str(WORKING/'payload.o'):str(units.pop('payload')),str(original_ld):str(ld)}
        if any(link.count(k)!=1 for k in replace):raise ValueError('Original loader object boundary changed')
        elf=output/'display_xnu.elf';image=output/'probe.bin';args=[replace.get(a,a) for a in link]
        args[args.index('-o')+1]=str(elf);args[args.index('-o'):args.index('-o')]=list(map(str,units.values()))
        run(args,'loader-link');run([ROOT/'tools/rpi5/tfa-objcopy','-O','binary',elf,image],'loader-objcopy')
        if run(['xcrun','llvm-nm','--undefined-only',elf],'loader-undefined').strip():raise ValueError('Undefined loader symbols')
        symbols=run(['xcrun','llvm-nm','-n',elf],'loader-symbols');parsed={line.split()[2]:int(line.split()[0],16) for line in symbols.splitlines() if len(line.split())==3}
        if parsed['__probe_end']>=0xb000000 or parsed['__stack_top']-parsed['__bss_end']!=32768:raise ValueError('Actual loader placement/stack differs')
        body=image.read_bytes();encoded=packed.read_bytes();offset=body.find(encoded)
        if offset<0 or offset&63 or body.find(encoded,offset+1)>=0:raise ValueError('Actual embedded payload differs')
        report.update(loader_integrated=True,image=str(image),image_sha256=sha(image),image_bytes=len(body),
            root_sha256=ROOT_SHA,root_bytes=len(root),loader_symbols=parsed,payload_offset=offset,primary_stack_bytes=32768,
            matched_allocation_required=True,allocation_requests_max=4,release=False,loader_framebuffer_access=False,
            stack_budget=stack_budget(output,parents[LOADER]),published_mapping_retained_until_reset=True,
            late_descriptor_or_mapping_replacement_prohibited=True)
    for name,digest in pins.items():
        if sha(name)!=digest:raise ValueError('Consumed source changed '+name)
    if not kernel_only:
        plan,expected_scans,expected_replacement=command_plan(output,tag)
        actual=[(Path(r['log']).stem,r['command'],r['cwd']) for r in commands]
        if actual!=plan or set(scans)!=set(expected_scans) or report['replaced_objects']!=expected_replacement:raise ValueError('Actual build differs from exact reconstructed plan')
    report.update(inputs_sha256=pins,actual_headers_sha256=headers,compiler_scans=scans,
        generated_sha256={str(p):sha(p) for p in output.iterdir() if p.is_file()})
    (output/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return output,report
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path);parser.add_argument('--kernel-only',action='store_true')
    options=parser.parse_args();directory,report=build(options.output_dir,options.kernel_only)
    print(json.dumps(dict(directory=str(directory),manifest_sha256=sha(directory/'manifest.json'),kernel_sha256=report['kernel_sha256'],loader_integrated=report['loader_integrated'])))
