#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Cross-build unmodified Apple range allocator + isolated RP1 policy, never boot."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]
APPLE = ROOT/'build/rpi5/apple-IOPCIFamily-726.100.6'
COMMIT = '503b7da7c8d67bc2dedecd83dd07b72f4644ec4b'
PINS = {
    'IOPCIRange.cpp': '9306bea541846afd632b17c7b7030d39d20d79540fe0fd7ddfca7c636a3f5ca9',
    'IOKit/pci/IOPCIConfigurator.h': '8658be1892e3cbb0354b84c6d9700778c80c6413b2556b5f69896ddf19a21c39',
    'APPLE_LICENSE': '4407579a41ee5062dd5451539a05b495e699c4f1c4965c8ad65c9bc3b38d9860',
}
SHIM = ROOT/'tools/rpi5/apple_pci_shim'
POLICY = ROOT/'loader/rpi5/pcie_apple_ranges.cpp'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(command):
    result = subprocess.run([str(x) for x in command], capture_output=True,
                            check=True, text=True, timeout=30, cwd=ROOT)
    return result.stdout.strip()


def inputs():
    if run(['git', '-C', APPLE, 'rev-parse', 'HEAD']) != COMMIT:
        raise ValueError('Apple allocator commit mismatch')
    if run(['git', '-C', APPLE, 'status', '--porcelain', '--untracked-files=all']):
        raise ValueError('Apple source checkout must remain pristine')
    snapshots = {}
    for name, pin in PINS.items():
        path = APPLE/name
        data = path.read_bytes()
        if sha(data) != pin:
            raise ValueError('Apple source/license hash mismatch: '+name)
        snapshots[path] = data
    for path in (Path(__file__).resolve(), POLICY, POLICY.with_suffix('.h'),
                 POLICY.with_name('pcie_fdt.h'), POLICY.with_name('ranges.h'),
                 SHIM/'IOKit/pci/IOPCIPrivate.h'):
        snapshots[path] = path.read_bytes()
    return snapshots


def dependencies(output):
    tokens = shlex.split(output.replace('\\\n', ' '))
    if not tokens or not tokens[0].endswith(':'):
        raise ValueError('Invalid compiler dependencies')
    return {Path(name).resolve() for name in tokens[1:]}


def build(output):
    captured = inputs()
    compiler = run(['xcrun', '--find', 'clang++'])
    flags = [compiler, '--target=aarch64-none-elf', '-mcpu=cortex-a76', '-mstrict-align',
             '-mgeneral-regs-only', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
             '-fno-exceptions', '-fno-rtti', '-fno-strict-aliasing', '-std=c++17',
             '-DKERNEL=1', '-DDEVELOPMENT=0', '-Os', '-Wall', '-Wextra', '-Werror',
             '-I', str(SHIM), '-I', str(APPLE)]
    sources = [('original', APPLE/'IOPCIRange.cpp', ['-Wno-parentheses', '-Wno-unused-parameter']),
               ('policy', POLICY, [])]
    compiler_inputs = {}
    for _, source, extra in sources:
        for path in dependencies(run([*flags, *extra, '-M', source])):
            if path not in captured:
                compiler_inputs[path] = path.read_bytes()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    commands, objects, frames = [], [], []
    for name, source, extra in sources:
        obj = output/(name+'.o')
        command = [*flags, *extra, '-fstack-usage', '-c', str(source), '-o', str(obj)]
        run(command); commands.append(command); objects.append(obj)
        for line in obj.with_suffix('.su').read_text().splitlines():
            location, size, kind = line.split('\t')
            if kind != 'static':
                raise ValueError('Nonstatic emitted stack frame')
            frames.append(dict(location=location, bytes=int(size), kind=kind))
    linked = output/'apple-rp1-ranges.o'
    linker = ROOT/'tools/rpi5/tfa-lld'
    command = [str(linker), '-r', *(str(obj) for obj in objects), '-o', str(linked)]
    run(command); commands.append(command)
    if run(['xcrun', 'llvm-nm', '--undefined-only', linked]):
        raise ValueError('Unexpected allocator runtime dependency')
    original_symbols = run(['xcrun', 'llvm-nm', '--defined-only', objects[0]])
    linked_symbols = run(['xcrun', 'llvm-nm', '--defined-only', linked])
    if ('IOPCIRangeListAllocateSubRange' not in original_symbols or
            'IOPCIRangeListAllocateSubRange' not in linked_symbols or
            ' T rpi5_apple_rp1_bar_candidates' not in linked_symbols or
            '_GLOBAL__sub_I' in linked_symbols):
        raise ValueError('Original allocator or C policy entry linkage changed')
    for path, data in {**captured, **compiler_inputs}.items():
        if path.read_bytes() != data:
            raise ValueError('Build input changed: '+str(path))
    if inputs() != captured:
        raise ValueError('Apple/source input changed during build')
    report = dict(
        schema_version=1, scope='Original Apple PCI allocator subset + RP1 BAR candidates; not a driver',
        source_url='https://github.com/apple-oss-distributions/IOPCIFamily',
        source_tag='IOPCIFamily-726.100.6', source_commit=COMMIT,
        original_source_unchanged=True, original_range_header_unchanged=True,
        original_allocator_linked=True, original_notices_and_license_retained=True,
        license='APSL-2.0 for the selected original unit/header; no whole-repository license claim',
        source_inputs_sha256={str(p): sha(data) for p, data in captured.items()},
        compiler_headers_sha256={str(p): sha(data) for p, data in compiler_inputs.items()},
        commands=commands, compiler_version=run([compiler, '--version']).splitlines()[0],
        linker_sha256=sha(linker.read_bytes()),
        outputs_sha256={p.name: sha(p.read_bytes()) for p in [*objects, linked,
                        *(obj.with_suffix('.su') for obj in objects)]},
        stack_frames=frames, stack_usage_not_whole_program_bound=True,
        kernel_classes_omitted=True, heap_and_unexpected_logger_paths_trap=True,
        exceptions_rtti_global_constructors=False, dynamic_runtime_dependencies=False,
        fixed_bar_count=3, max_reserved_spans=8, max_upstream_allocate_calls=11,
        unused_decode_padding_allocatable=False, bar_assignment_proven=False,
        entire_iopcifamily_kernel_compatibility_proven=False,
        pi_executed=False, hardware_access_enabled=False, nic_ready=False,
        sd_actions=0, serial_actions=0, reboots=0)
    with (output/'manifest.json').open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True); stream.write('\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path, help='New directory only')
    args = parser.parse_args()
    report = build(args.output_dir)
    print(json.dumps(dict(source_commit=report['source_commit'], original_allocator_linked=True,
                         outputs_sha256=report['outputs_sha256'], pi_executed=False)))


if __name__ == '__main__':
    main()
