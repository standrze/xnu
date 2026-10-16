#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Compile the unlinked memory adapter with the pinned real kernel headers.

Reuses the accepted storage screen's Cortex-A76/kernel command, replacing only
its source/output. No provider link, kernel build, serial/SD access or staging.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-screen',required=True,type=Path)
    parser.add_argument('--kernel-commands',type=Path,default=ROOT/
                        'build/rpi5-xcode27/obj/DEVELOPMENT_ARM64_BCM2712/compile_commands.json')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--bundle',action='store_true',help='Also compile/link the isolated, uninstalled write foundations')
    args=parser.parse_args()
    screen=json.loads(args.storage_screen.read_text())
    if digest(args.kernel_commands)!=screen['kernel_commands_sha256']:
        raise ValueError('Compile database changed from the accepted storage screen')
    templates=[row for row in json.loads(args.kernel_commands.read_text())
               if row['file'].endswith('/iokit/Kernel/IOCPU.cpp')]
    if len(templates)!=1:
        raise ValueError('Missing unique original IOKit compilation working directory')
    directory=Path(templates[0]['directory'])
    if not directory.resolve().is_relative_to((ROOT/'build/rpi5-xcode27').resolve()):
        raise ValueError('Unexpected generated-header working directory')
    original=ROOT/'iokit/Kernel/BCM2712SDStorage.cpp'
    rows=[row for row in screen['results'] if row['unit']==original.name and row['family']=='rpi5-storage']
    if len(rows)!=1 or rows[0].get('source_sha256')!=digest(original):
        raise ValueError('Changed/missing accepted read-only adapter command')
    command=rows[0]['command'].copy()
    if (command.count(str(original))!=1 or command.count('-o')!=1 or '-mkernel' not in command
            or '-mcpu=cortex-a76' not in command or '-Werror' not in command
            or '--target=arm64-apple-macosx27.0.0' not in command
            or any('sd_memory_doubles' in flag for flag in command)):
        raise ValueError('Not the pinned real kernel compilation context')
    if not args.output.resolve().is_relative_to((ROOT/'build/rpi5').resolve()):
        parser.error('Use a fresh build/rpi5 output directory')
    args.output=args.output.resolve()
    source=ROOT/'iokit/Kernel/rpi5_sd_memory.cpp'
    inputs=[source,ROOT/'iokit/Kernel/rpi5_sd_memory.h',ROOT/'iokit/Kernel/rpi5_sd_transfer.h',
            ROOT/'iokit/Kernel/rpi5_sd_contract.h',ROOT/'iokit/Kernel/rpi5_sdhci_write.h',
            ROOT/'iokit/Kernel/rpi5_sd_write_policy.h',ROOT/'iokit/Kernel/rpi5_sdhci_core.h',
            ROOT/'iokit/Kernel/rpi5_sd_cache.h',ROOT/'iokit/Kernel/rpi5_sd_handoff.h',
            ROOT/'iokit/IOKit/IOMemoryDescriptor.h',ROOT/'iokit/IOKit/IOLib.h',
            ROOT/'osfmk/machine/machine_routines.h',directory/'meta_features.h']
    c_units=('rpi5_sd_write_policy.c','rpi5_sdhci_write.c','rpi5_sd_transfer.c',
             'rpi5_sd_contract.c','rpi5_sdhci_core.c','rpi5_sd_cache.c','rpi5_sd_handoff.c')
    if args.bundle:
        inputs.extend(ROOT/'iokit/Kernel'/name for name in c_units)
    before={str(path):digest(path) for path in inputs}
    args.output.mkdir(parents=True,exist_ok=False)
    obj=args.output/'rpi5_sd_memory.o'
    command[command.index(str(original))]=str(source)
    command[command.index('-o')+1]=str(obj)
    result=subprocess.run(command,cwd=directory,capture_output=True,timeout=60)
    (args.output/'compile.log').write_bytes(result.stdout+result.stderr)
    after={str(path):digest(path) for path in inputs}
    symbols=[]
    if result.returncode==0:
        symbols=subprocess.check_output(['xcrun','nm','-ju',str(obj)],text=True).splitlines()
    report=dict(returncode=result.returncode,command=command,directory=str(directory),source_unchanged=before==after,
                input_sha256=before,storage_screen_sha256=digest(args.storage_screen),
                object_sha256=digest(obj) if obj.exists() else None,undefined_symbols=symbols,
                linked_into_provider=False,linked_into_kernel=False,hardware_accesses=0,
                scope='Real Apple-header Cortex-A76 kernel compile only; not linking, descriptor runtime or writes')
    if args.bundle and result.returncode==0:
        c_rows=[row for row in screen['results'] if row['unit']=='rpi5_sd_contract.c' and row['family']=='rpi5-storage']
        c_templates=[row for row in json.loads(args.kernel_commands.read_text()) if row['file'].endswith('/bsd/dev/memdev.c')]
        c_source=str(ROOT/'iokit/Kernel/rpi5_sd_contract.c')
        if len(c_rows)!=1 or len(c_templates)!=1 or c_rows[0]['source_sha256']!=digest(Path(c_source)):
            raise ValueError('Missing or changed original C kernel context')
        c_directory=Path(c_templates[0]['directory'])
        objects=[obj]; reports=[]
        for name in c_units:
            cc=c_rows[0]['command'].copy()
            if cc.count(c_source)!=1 or cc.count('-o')!=1:
                raise ValueError('Unexpected C compilation command')
            target=args.output/(name+'.o')
            cc[cc.index(c_source)]=str(ROOT/'iokit/Kernel'/name)
            cc[cc.index('-o')+1]=str(target)
            compiled=subprocess.run(cc,cwd=c_directory,capture_output=True,timeout=60)
            (args.output/(name+'.log')).write_bytes(compiled.stdout+compiled.stderr)
            reports.append(dict(unit=name,command=cc,directory=str(c_directory),returncode=compiled.returncode,
                                object_sha256=digest(target) if target.exists() else None))
            if compiled.returncode:
                print((compiled.stdout+compiled.stderr).decode(errors='replace'))
                break
            objects.append(target)
        report['bundle_compiles']=reports
        if len(reports)==len(c_units) and all(row['returncode']==0 for row in reports):
            bundle=args.output/'sd-write-foundations.o'
            link=['xcrun','ld','-r','-arch','arm64','-o',str(bundle),*map(str,objects)]
            linked=subprocess.run(link,capture_output=True,timeout=60)
            (args.output/'bundle-link.log').write_bytes(linked.stdout+linked.stderr)
            defined=set(); undefined=set()
            if linked.returncode==0:
                defined=set(subprocess.check_output(['xcrun','nm','-jU',str(bundle)],text=True).splitlines())
                undefined=set(subprocess.check_output(['xcrun','nm','-ju',str(bundle)],text=True).splitlines())
            required={'_rpi5_sd_transfer','_rpi5_sd_write_authorize','_rpi5_sd_write_request_valid',
                      '_rpi5_sd_write_quarantine','_rpi5_sd_write_sector','_rpi5_sd_write_wait_ready',
                      '_rpi5_sd_start','_rpi5_sd_start_identified','_rpi5_sd_read_sector',
                      '_rpi5_sd_cache_probe','_rpi5_sd_cache_scr','_rpi5_sd_cache_location',
                      '_rpi5_sd_cache_performance','_rpi5_sd_handoff'}
            adapter=[name for name in defined if 'rpi5_sd_memory_execute' in name]
            report['partial_link']=dict(command=link,returncode=linked.returncode,
                missing_required_definitions=sorted(required-defined),adapter_definition=adapter,
                unresolved_sd_dependencies=sorted(name for name in undefined if name.startswith('_rpi5_sd_')),
                undefined_symbols=sorted(undefined),object_sha256=digest(bundle) if bundle.exists() else None,
                scope='Isolated relocatable ABI/link screen, not a provider/kernel or hardware trial')
        report['bundle_pass']=(len(reports)==len(c_units) and all(row['returncode']==0 for row in reports)
            and report.get('partial_link',{}).get('returncode')==0
            and report['partial_link']['missing_required_definitions']==[]
            and report['partial_link']['unresolved_sd_dependencies']==[]
            and len(report['partial_link']['adapter_definition'])==1)
        report['source_unchanged']=before=={str(path):digest(path) for path in inputs}
    (args.output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(args.output)
    if result.returncode or not report['source_unchanged'] or (args.bundle and not report.get('bundle_pass')):
        print((result.stdout+result.stderr).decode(errors='replace'))
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
