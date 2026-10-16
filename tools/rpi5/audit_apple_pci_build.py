#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Screen Apple IOPCIFamily against the actual Pi XNU build headers.

No allocator shim, fake IOKit declarations, kernel installation or hardware I/O.
Diagnostics are evidence of incompatibility, never a successful driver build.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
APPLE = ROOT / 'build/rpi5/apple-IOPCIFamily-726.100.6'
COMMIT = '503b7da7c8d67bc2dedecd83dd07b72f4644ec4b'
OBJ = ROOT / 'build/rpi5-xcode27/fresh-435uage7/obj/DEVELOPMENT_ARM64_BCM2712'
TEMPLATE = OBJ / 'iokit/DEVELOPMENT/IOService.cpo.json'
TEMPLATE_SHA = '3a943ae690f9847687ef0b1a93ac466f8b8c389ced74d6f4e595f91d6499fd81'
SDK = ROOT / 'build/rpi5-xcode27/sdk/MacOSX27.0.sdk'
KERNEL = OBJ / 'kernel.development.bcm2712'
PHASE = 'A613B27F0D46AA65007BA726'
PATCH = ROOT / 'tools/rpi5/patches/pci-bcm2712-no-apple-dart.patch'
RETURN_PATCH = ROOT / 'tools/rpi5/patches/pci-cxx-return-types.patch'
UNITS = ('IOPCIBridge.cpp', 'IOPCIDevice.cpp', 'IOPCIDevice.iig', 'AppleVTD.cpp',
         'IOPCIDeviceI386.cpp', 'IOPCIConfigurator.cpp', 'IOPCIDeviceMappedIO.cpp',
         'IOPCIRange.cpp', 'IOPCIBridgeLegacy.cpp', 'IOPCITraceEventBuffer.cpp',
         'IOPCIMessagedInterruptController.cpp')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_command(command, cwd=ROOT):
    return subprocess.check_output(list(map(str, command)), cwd=cwd, text=True, timeout=60).strip()


def original_inputs():
    if read_command(['git', '-C', APPLE, 'rev-parse', 'HEAD']) != COMMIT:
        raise ValueError('Wrong Apple PCI commit')
    if read_command(['git', '-C', APPLE, 'status', '--porcelain', '--untracked-files=all']):
        raise ValueError('Apple PCI source must remain pristine')
    names = read_command(['git', '-C', APPLE, 'ls-files', '-z']).split('\0')
    return {str(APPLE / name): sha(APPLE / name) for name in names if name}


def target_units():
    project = APPLE / 'IOPCIFamily.xcodeproj/project.pbxproj'
    objects = json.loads(read_command(['plutil', '-convert', 'json', '-o', '-', project]))['objects']
    names = tuple(objects[objects[key]['fileRef']]['path'] for key in objects[PHASE]['files'])
    if names != UNITS:
        raise ValueError('Original kext source phase changed')
    return names


def compile_command(template, source, overlay, output, family=APPLE, no_apple_dart=False):
    """Reuse actual flags; discard every original output/dependency destination."""
    args, result, i = template['arguments'], [], 0
    while i < len(args):
        arg = args[i]
        if arg in ('-o', '-MF', '-MT', '-MQ', '-MJ'):
            i += 2
            continue
        if arg in ('-MMD', '-MD', '-MP', '-M', '-MM', '-MG'):
            i += 1
            continue
        if any(arg.startswith(prefix) and arg != prefix for prefix in ('-MF', '-MT', '-MQ', '-MJ')):
            i += 1
            continue
        result.append(str(source) if arg == template['file'] else arg)
        i += 1
    # Precedence matters: SDK availability macros and their helpers are a set.
    # All IOKit/kernel API declarations still come from the real XNU/family.
    result[1:1] = ['-I', str(overlay), '-I', str(family), '-I', str(family / 'PCIDriverKit')]
    if no_apple_dart:
        result.append('-DRPI5_PCI_NO_APPLE_DART=1')
    return result + ['-Wno-error', '-o', str(output)]


def header_overlay(output):
    include = output / 'include'
    (include / 'os').mkdir(parents=True)
    sdk_include = SDK / 'usr/include'
    headers = sorted(sdk_include.glob('Availability*.h'))
    headers += [sdk_include / name for name in ('TargetConditionals.h', 'AssertMacros.h', 'os/availability.h')]
    copied = {}
    for source in headers:
        destination = include / source.relative_to(sdk_include)
        shutil.copyfile(source, destination)
        copied[str(source)] = sha(source)
        if sha(destination) != copied[str(source)]:
            raise ValueError('Header overlay copy differs')
    return include, copied


def execute(command, cwd, log):
    try:
        result = subprocess.run(list(map(str, command)), cwd=cwd, capture_output=True, timeout=60)
        data, rc = result.stdout + result.stderr, result.returncode
    except subprocess.TimeoutExpired as error:
        data, rc = (error.stdout or b'') + (error.stderr or b'') + b'\nSCREEN TIMEOUT\n', 124
    log.write_bytes(data)
    lines = data.decode(errors='replace').splitlines()
    errors = [line for line in lines
              if 'error:' in line or 'SCREEN TIMEOUT' in line]
    return dict(command=list(map(str, command)), returncode=rc, log=str(log),
                log_sha256=sha(log), errors=errors,
                warning_count=sum('warning:' in line for line in lines))


def dependency_paths(path, cwd):
    tokens = shlex.split(path.read_text().replace('\\\n', ' '))
    if not tokens or not tokens[0].endswith(':'):
        raise ValueError('Invalid dependency output')
    return {(cwd / name).resolve() for name in tokens[1:]}


def audit(output, no_apple_dart=False):
    inputs = original_inputs()
    if sha(TEMPLATE) != TEMPLATE_SHA:
        raise ValueError('Actual XNU compile template changed')
    units = target_units()
    inputs.update({str(TEMPLATE): sha(TEMPLATE), str(Path(__file__).resolve()): sha(Path(__file__).resolve()),
                   str(KERNEL): sha(KERNEL)})
    template = json.loads(TEMPLATE.read_text().strip().removesuffix(','))
    cwd = Path(template['directory'])
    output = output.resolve()
    if any(output.is_relative_to(path) for path in (APPLE, OBJ, SDK)):
        raise ValueError('Screen output must not be inside original sources, XNU objects or SDK')
    output.mkdir(parents=True, exist_ok=False)
    family, adaptation = APPLE, []
    if no_apple_dart:
        family = output / 'IOPCIFamily-adapted'
        for name in original_inputs():
            relative = Path(name).relative_to(APPLE)
            destination = family / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(name, destination)
        for patch in (PATCH, RETURN_PATCH):
            inputs[str(patch)] = sha(patch)
            row = execute(['patch', '--batch', '--fuzz=0', '-p1', '-d', family, '-i', patch],
                          ROOT, output / (patch.stem + '.log'))
            adaptation.append(row)
            if row['returncode']:
                raise ValueError('BCM2712 adaptation failed; inspect ' + row['log'])
        for path in family.rglob('*'):
            if path.is_file():
                inputs[str(path)] = sha(path)
    overlay, copied = header_overlay(output)
    inputs.update(copied)
    generator = read_command(['xcrun', '--find', 'iig'])
    inputs[str(Path(generator))] = sha(Path(generator))
    generated_header = overlay / 'PCIDriverKit/IOPCIDevice.h'
    generated_header.parent.mkdir()
    generated_impl = output / 'IOPCIDevice.iig.cpp'
    command = [generator, '--def', family / 'PCIDriverKit/IOPCIDevice.iig',
               '--header', generated_header, '--impl', generated_impl,
               '--framework-name', 'PCIDriverKit', '--', '-I', overlay,
               '-I', family, '-I', ROOT / 'iokit', '-I', ROOT / 'osfmk',
               '-I', ROOT / 'bsd', '-I', OBJ / 'bsd', '-isysroot', SDK,
               '-x', 'c++', '-std=gnu++2b', '-D__IIG=1', '-DDRIVERKIT_PRIVATE=1',
               '-DPRIVATE_WIFI_ONLY=1', '-D__MAC_OS_X_VERSION_MIN_REQUIRED=270000']
    generation = execute(command, ROOT, output / 'iig.log')
    generated = {}
    if generation['returncode'] == 0:
        shutil.copyfile(generated_header, overlay / 'IOPCIDevice.h')
        generated = {str(path): sha(path) for path in
                     (generated_header, overlay / 'IOPCIDevice.h', generated_impl)}
    results = []
    compiler = Path(template['arguments'][0])
    inputs[str(compiler)] = sha(compiler)
    for unit in units:
        source = generated_impl if unit.endswith('.iig') else family / unit
        if unit.endswith('.iig') and generation['returncode']:
            results.append(dict(unit=unit, skipped='Actual IIG generation failed', returncode=None))
            continue
        obj = output / (unit + '.o')
        command = compile_command(template, source, overlay, obj, family, no_apple_dart)
        dep = output / (unit + '.d')
        dep_command = command[:-2] + ['-M', '-MG', '-MF', str(dep)]
        dependency = execute(dep_command, cwd, output / (unit + '.deps.log'))
        missing = []
        if dependency['returncode'] == 0:
            for path in dependency_paths(dep, cwd):
                if path.is_file():
                    inputs.setdefault(str(path), sha(path))
                else:
                    missing.append(str(path))
        row = execute(command, cwd, output / (unit + '.log'))
        row.update(unit=unit, dependencies=dependency, missing_headers=sorted(missing))
        if row['returncode'] == 0:
            if dependency['returncode'] or missing:
                raise ValueError('Successful compile lacks closed dependency inventory: ' + unit)
            row['object_sha256'] = sha(obj)
            row['defined_symbols'] = read_command(['xcrun', 'nm', '-jU', obj]).splitlines()
            row['undefined_symbols'] = read_command(['xcrun', 'nm', '-ju', obj]).splitlines()
        results.append(row)
    link = None
    compiled = generation['returncode'] == 0 and all(row['returncode'] == 0 for row in results)
    if compiled:
        composed = output / 'IOPCIFamily-partial.o'
        link = execute(['xcrun', 'ld', '-r', '-arch', 'arm64', '-o', composed,
                        *(output / (unit + '.o') for unit in units)], ROOT, output / 'link.log')
        if link['returncode'] == 0:
            link['object_sha256'] = sha(composed)
            undefined = set(read_command(['xcrun', 'nm', '-ju', composed]).splitlines())
            kernel_symbols = set(read_command(['xcrun', 'nm', '-jU', KERNEL]).splitlines())
            link['undefined_symbols'] = sorted(undefined)
            link['not_defined_in_reference_kernel'] = sorted(undefined - kernel_symbols)
    for name, digest in {**inputs, **generated}.items():
        if sha(Path(name)) != digest:
            raise ValueError('Screen input changed: ' + name)
    if original_inputs() != {name: digest for name, digest in inputs.items()
                             if Path(name).is_relative_to(APPLE)}:
        raise ValueError('Original source changed during screen')
    report = dict(schema_version=1, source_commit=COMMIT, source_tag='IOPCIFamily-726.100.6',
                  original_source_unchanged=True, source_units=list(units),
                  bcm2712_no_apple_dart=no_apple_dart, adaptation=adaptation,
                  adapted_copy_used=no_apple_dart,
                  scope='Actual XNU header compile screen and optional relocatable symbol inventory only',
                  consistent_original_sdk_availability_headers=True, allocator_shim_used=False,
                  fake_kernel_declarations_used=False, generation=generation, results=results, link=link,
                  original_notices_retained=True,
                  warning_policy='Keep original warnings in logs; semantic errors remain failures',
                  compiler_version=read_command([compiler, '--version']).splitlines()[0],
                  all_source_units_compile=compiled, inputs_sha256=inputs, generated_sha256=generated,
                  final_kernel_link_proven=False, abi_compatibility_proven=False,
                  driver_attachment_proven=False, pi_executed=False, hardware_access_enabled=False,
                  sd_actions=0, serial_actions=0, reboots=0)
    (output / 'manifest.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True, help='New directory only')
    parser.add_argument('--bcm2712-no-apple-dart', action='store_true',
                        help='Patch a separate copy to omit Apple-only DART calls, not DMA support')
    args = parser.parse_args()
    report = audit(args.output_dir, args.bcm2712_no_apple_dart)
    print(json.dumps(dict(all_source_units_compile=report['all_source_units_compile'],
                          partial_link_returncode=report['link']['returncode'] if report['link'] else None,
                          not_defined_in_reference_kernel=report['link'].get('not_defined_in_reference_kernel')
                          if report['link'] else None,
                          units=[dict(unit=row['unit'], returncode=row['returncode'],
                                      errors=row.get('errors', [])[:5]) for row in report['results']]), indent=2))
    raise SystemExit(0 if report['all_source_units_compile'] and report['link']
                     and report['link']['returncode'] == 0 else 1)


if __name__ == '__main__':
    main()
