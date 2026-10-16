#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Compile/partial-link the distinct write provider; no kernel build or staging.

Requires the actual successful real-header write-foundations bundle, unchanged
hashed inputs, and its original Cortex-A76 IOKit compile context. This is not
IOKit runtime, worker/concurrency, physical cache, SD-write or durability proof.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'iokit/Kernel/BCM2712SDWriteStorage.cpp'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--foundations',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    args.output=args.output.resolve()
    if not args.output.is_relative_to(ROOT/'build/rpi5'):
        parser.error('Use a fresh build/rpi5 output directory')
    manifest=json.loads(args.foundations.read_text())
    link=manifest.get('partial_link',{})
    if (manifest.get('returncode')!=0 or manifest.get('source_unchanged') is not True or
        manifest.get('bundle_pass') is not True or link.get('returncode')!=0 or
        link.get('missing_required_definitions')!=[] or link.get('unresolved_sd_dependencies')!=[]):
        raise ValueError('Require the actual successful complete real-header foundations bundle')
    inputs=manifest['input_sha256'].copy()
    for name,expected in inputs.items():
        path=Path(name)
        if path.is_symlink() or not path.is_file() or digest(path)!=expected:
            raise ValueError('Changed foundations input: '+name)
    bundle=args.foundations.resolve().parent/'sd-write-foundations.o'
    if bundle.is_symlink() or digest(bundle)!=link['object_sha256']:
        raise ValueError('Changed isolated foundations object')
    inputs.update({str(SOURCE):digest(SOURCE),str(bundle):digest(bundle),
                   str(args.foundations.resolve()):digest(args.foundations),str(Path(__file__).resolve()):digest(Path(__file__))})
    command=manifest['command'].copy()
    original=str(ROOT/'iokit/Kernel/rpi5_sd_memory.cpp')
    if (command.count(original)!=1 or command.count('-o')!=1 or '-mkernel' not in command or
        '-mcpu=cortex-a76' not in command or '-Werror' not in command or
        '--target=arm64-apple-macosx27.0.0' not in command or
        any('doubles' in flag for flag in command)):
        raise ValueError('Not the actual real-header IOKit context')
    directory=Path(manifest['directory']).resolve()
    if not directory.is_relative_to(ROOT/'build/rpi5-xcode27'):
        raise ValueError('Unexpected kernel working directory')
    args.output.mkdir(parents=True,exist_ok=False)
    obj=args.output/'sd-write-provider.o'
    command[command.index(original)]=str(SOURCE)
    command[command.index('-o')+1]=str(obj)
    command.append('-DRPI5_STORAGE_WRITE_PROVIDER=1')
    compiled=subprocess.run(command,cwd=directory,capture_output=True,timeout=60)
    (args.output/'compile.log').write_bytes(compiled.stdout+compiled.stderr)
    report=dict(compile_returncode=compiled.returncode,command=command,directory=str(directory),
                input_sha256=inputs,linked_into_kernel=False,hardware_accesses=0,
                scope='Real-header compile and isolated relocatable link only; not worker runtime or SD acceptance')
    if compiled.returncode==0:
        combined=args.output/'sd-write-provider-foundations.o'
        command=['xcrun','ld','-r','-arch','arm64','-o',str(combined),str(obj),str(bundle)]
        linked=subprocess.run(command,capture_output=True,timeout=60)
        (args.output/'link.log').write_bytes(linked.stdout+linked.stderr)
        report.update(link_command=command,link_returncode=linked.returncode,
                      object_sha256=digest(combined) if combined.exists() else None)
        if linked.returncode==0:
            defined=set(subprocess.check_output(['xcrun','nm','-jU',str(combined)],text=True).splitlines())
            undefined=set(subprocess.check_output(['xcrun','nm','-ju',str(combined)],text=True).splitlines())
            report['write_provider_metaclass_present']='__ZN21BCM2712SDWriteStorage10gMetaClassE' in defined
            report['unresolved_sd_dependencies']=sorted(name for name in undefined if name.startswith('_rpi5_sd_') or 'rpi5_sd_memory_execute' in name)
            report['undefined_symbols']=sorted(undefined)
    report['source_unchanged']=all(digest(Path(name))==expected for name,expected in inputs.items())
    report['passed']=(report['compile_returncode']==0 and report.get('link_returncode')==0 and
                      report.get('write_provider_metaclass_present') is True and
                      report.get('unresolved_sd_dependencies')==[] and report['source_unchanged'])
    (args.output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    if compiled.returncode:
        print((compiled.stdout+compiled.stderr).decode(errors='replace'))
    print(args.output)
    return 0 if report['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
