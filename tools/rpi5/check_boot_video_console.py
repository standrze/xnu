#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Byte/source closure check for inactive display artifacts; no semantic rebuild."""
import argparse
import json
from pathlib import Path
from . import build_boot_video_console as build
from . import console_mirror_overlay as overlay


def validate(report,directory):
    directory=Path(directory).resolve()
    if report['profile']!='rpi5-boot-video-uart-mirror-offline-v1':raise ValueError('Wrong display artifact profile')
    for name,expected in {'mirror_default_off':True,'mirror_has_enable_callsite':False,
        'original_video_console_object_unchanged':True,'original_kprintf_object_unchanged':True,
        'uart_first_once':True,'original_newline_normalization':True,'serial_input_unchanged':True,
        'poll_debugger_uart_only':True,'native_full_vt100_parser':False,
        'framebuffer_mapping_created':False,'scanout_proven':False,'loader_integrated':False,
        'pi_executed':False,'installed':False}.items():
        if report.get(name) is not expected:raise ValueError('Display scope changed '+name)
    pins=report['inputs_sha256'];generated=report['generated_sha256']
    if set(generated)!={str(p) for p in directory.iterdir() if p.is_file() and p.name!='manifest.json'}:
        raise ValueError('Generated closure omitted/added actual member')
    for table in (pins,generated):
        for name,digest in table.items():
            if build.sha(name)!=digest:raise ValueError('Artifact/source changed '+name)
    required=[Path(__file__).resolve(),Path(build.__file__).resolve(),Path(overlay.__file__).resolve(),
        build.native.VIDEO,build.native.BOOT,build.native.FONT,overlay.SOURCE,overlay.HEADER,build.DATABASE,
        build.ROOT/'loader/rpi5/boot_video.c',build.ROOT/'loader/rpi5/boot_video.h',
        build.ROOT/'tools/rpi5/tests/test_boot_video_console.py',
        build.ROOT/'tools/rpi5/tests/test_boot_video_console_artifact.py']
    if any(str(p) not in pins for p in required):raise ValueError('Required original/project source omitted')
    parent=build.BASE/'manifest.json'
    if pins.get(str(parent))!=build.BASE_SHA or report['parent_manifest_sha256']!=build.BASE_SHA:
        raise ValueError('Frozen original kernel parent changed')
    baseline=json.loads(parent.read_text())
    for key in ('inputs_sha256','generated_sha256'):
        if any(pins.get(name)!=digest for name,digest in baseline[key].items()):
            raise ValueError('Inherited kernel input omitted')
    consumed=set()
    for label,names in report['compiler_scans'].items():
        rows=[r for r in report['commands'] if r['log']==str(directory/(label+'-compile.log'))]
        if len(rows)!=1:raise ValueError('Actual compiler command missing')
        row=rows[0];before=build.deps(directory/(label+'.scan.d'),row['cwd'])
        after=build.deps(directory/(label+'.actual.d'),row['cwd'])
        if before!=after or after!=set(names):raise ValueError('Actual before/after compiler closure differs')
        command=row['command']
        if not all(flag in command for flag in ('-MD','-MF','-c','-o')):raise ValueError('Compiler closure flags missing')
        if command[command.index('-MF')+1]!=str(directory/(label+'.actual.d')):
            raise ValueError('Compiler actual dependency output differs')
        for name in after:
            if name not in pins or report['actual_headers_sha256'].get(name)!=pins[name]:
                raise ValueError('Consumed source/header omitted '+name)
        consumed.update(after)
    if set(report['actual_headers_sha256'])!=consumed:raise ValueError('Header union differs from actual scans')
    source=directory/'serial_console.c'
    if source.read_text()!=overlay.overlay(overlay.SOURCE.read_text()):raise ValueError('More than exact serial dispatch overlay')
    old=build.OBJ/'osfmk/DEVELOPMENT/serial_console.o';new=directory/'serial-console-target.o'
    if report['replaced_objects']!={str(old):str(new)}:raise ValueError('Wrong replaced kernel object')
    originals=(build.BASE/'kernel.root-confirmed.filelist').read_text().splitlines()
    actual=(directory/'kernel.mirror.filelist').read_text().splitlines()
    if originals.count(str(old))!=1 or actual!=[str(new) if p==str(old) else p for p in originals]:
        raise ValueError('Kernel filelist is not exact one-object replacement')
    if report['unchanged_link_objects']!=[p for p in originals if p!=str(old)]:raise ValueError('Unchanged object list differs')
    if report['kernel']!=str(directory/'NOT_RUN_kernel.console-mirror') or build.sha(report['kernel'])!=report['kernel_sha256']:
        raise ValueError('Target kernel differs')
    if (directory/'kernel-undefined.log').read_text().strip():raise ValueError('Unresolved target kernel')
    asm=(directory/'serial_console.s').read_text()
    body=asm.split('_rpi5_console_mirror_putc:',1)[1].split('; -- End function',1)[0]
    if body.index('_serial_putc_options')>body.index('_vcputc_options') or '\tldapr\t' not in body:
        raise ValueError('Actual UART-first acquire dispatch missing')
    if '\tcasl\t' not in asm or '\tstlr\t' not in asm:raise ValueError('Actual one-way atomic gate missing')
    if asm.count('\tbl\t_rpi5_console_mirror_publish') or asm.count('\tb\t_rpi5_console_mirror_publish'):
        raise ValueError('Unexpected publisher call site')
    if report['boot_video_elf']!=str(directory/'NOT_RUN_boot_video.elf'):raise ValueError('Wrong ELF path')
    if build.elf_symbols(Path(report['boot_video_elf']).read_bytes())!=report['elf_defined_symbols']:
        raise ValueError('Actual linked helper differs')
    for name,expected in (('native-invalid-index',91),('native-bad-expectation',74)):
        rows=[r for r in report['commands'] if r['log']==str(directory/(name+'.log'))]
        if len(rows)!=1 or rows[0]['returncode']!=expected:raise ValueError('Negative control missing')
    return dict(input_count=len(pins),compiler_units=len(report['compiler_scans']),
        native_renderer_cases=12288,one_kernel_object_replaced=True,mirror_enabled=False,
        full_vt100_tested=False,mapping_or_scanout_proven=False)


def inspect(directory,expected_manifest_sha256):
    directory=Path(directory).resolve();path=directory/'manifest.json'
    if build.sha(path)!=expected_manifest_sha256:raise ValueError('Separately retained manifest pin differs')
    return validate(json.loads(path.read_text()),directory)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
    p.add_argument('--manifest-sha256',required=True)
    args=p.parse_args();print(json.dumps(inspect(args.directory,args.manifest_sha256),sort_keys=True))
