#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Compile the CPU-translated resource bridge over the preserved Apple family.

Not a final kernel link, concrete provider, boot image or hardware trial.
"""
import argparse
import json
from pathlib import Path
import shutil

try:
    from . import build_apple_pci_config as config
except ImportError:
    import build_apple_pci_config as config

audit = config.audit
ROOT = config.ROOT
BASE = ROOT / 'build/rpi5/apple-pci-config-20261012-final'
MANIFEST_SHA = '7588f60a64495f648d8e41fa16f25bb0bd4a0c4584e9b39039ae66c2f7e9ac8b'
SOURCES = (ROOT / 'iokit/Kernel/BCM2712PCIWindowCore.cpp',
           ROOT / 'iokit/Kernel/BCM2712PCIResourceBridge.cpp')
PATCH = ROOT / 'tools/rpi5/patches/pci-bcm2712-assigned-addresses.patch'


def inputs():
    result = config.base_inputs()
    manifest = BASE / 'manifest.json'
    if audit.sha(manifest) != MANIFEST_SHA:
        raise ValueError('Accepted config manifest changed')
    report = json.loads(manifest.read_text())
    if (not report['original_family_reused'] or report['concrete_provider_implemented'] or
            report['link']['returncode'] or
            report['link']['not_defined_in_reference_kernel'] != ['___dso_handle']):
        raise ValueError('Wrong config build profile')
    result.update(report['inputs_sha256'])
    result[str(manifest)] = MANIFEST_SHA
    result[str(BASE / 'apple-bcm2712-pci-config.o')] = report['link']['object_sha256']
    result[str(Path(__file__).resolve())] = audit.sha(Path(__file__).resolve())
    result[str(PATCH)] = audit.sha(PATCH)
    family = json.loads((config.BASE / 'manifest.json').read_text())
    for row in family['results']:
        result[str(config.BASE / (row['unit'] + '.o'))] = row['object_sha256']
    for row in report['results']:
        result[row['command'][-1]] = row['object_sha256']
    for name, digest in result.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('Resource integration input changed: ' + name)
    return result


def build(output):
    captured = inputs()
    output = output.resolve()
    if any(output.is_relative_to(path) for path in
           (BASE, config.BASE, audit.APPLE, audit.OBJ, audit.SDK)):
        raise ValueError('Resource output must not be inside accepted inputs')
    output.mkdir(parents=True, exist_ok=False)
    template = json.loads(audit.TEMPLATE.read_text().strip().removesuffix(','))
    cwd = Path(template['directory'])
    # A separate copy and opt-in patch; never edit pristine or accepted sources.
    adapted = output / 'IOPCIConfigurator.cpp'
    shutil.copyfile(config.BASE / 'IOPCIFamily-adapted/IOPCIConfigurator.cpp', adapted)
    adaptation = audit.execute(['patch', '--batch', '--fuzz=0', '-p1', '-d', output, '-i', PATCH],
                               ROOT, output / 'assigned-addresses.patch.log')
    if adaptation['returncode']:
        raise ValueError('Assigned-address adaptation failed: ' + adaptation['log'])
    results, objects = [], []
    for source in (adapted, *SOURCES):
        obj = output / (source.name + '.o')
        captured[str(source)] = audit.sha(source)
        args = config.command(template, source, obj)
        if source == adapted:
            args = ['-Wno-error' if arg == '-Werror' else arg for arg in args]
            args[1:1] = ['-I', str(ROOT / 'iokit/Kernel'), '-DRPI5_PCI_CPU_TRANSLATED_RESOURCES=1']
        dep = output / (source.name + '.d')
        dependencies = audit.execute([arg for arg in args[:-2] if arg != '-c'] +
                                     ['-M', '-MG', '-MF', str(dep)], cwd,
                                     output / (source.name + '.deps.log'))
        if dependencies['returncode']:
            raise ValueError('Resource dependency screen failed: ' + dependencies['log'])
        for path in audit.dependency_paths(dep, cwd):
            if not path.is_file():
                raise ValueError('Missing actual resource dependency: ' + str(path))
            captured.setdefault(str(path), audit.sha(path))
        row = audit.execute(args, cwd, output / (source.name + '.log'))
        results.append(row)
        if row['returncode']:
            raise ValueError('Resource bridge compile failed: ' + row['log'])
        row['object_sha256'] = audit.sha(obj)
        objects.append(obj)
    family_report = json.loads((config.BASE / 'manifest.json').read_text())
    family_objects = [config.BASE / (row['unit'] + '.o') for row in family_report['results']
                      if row['unit'] != 'IOPCIConfigurator.cpp']
    config_report = json.loads((BASE / 'manifest.json').read_text())
    config_objects = [Path(row['command'][-1]) for row in config_report['results']]
    composed = output / 'apple-bcm2712-pci-resources.o'
    link = audit.execute(['xcrun', 'ld', '-r', '-arch', 'arm64', '-o', composed,
                          *family_objects, *config_objects, *objects],
                         ROOT, output / 'link.log')
    if link['returncode']:
        raise ValueError('Resource/family relocatable link failed: ' + link['log'])
    link['object_sha256'] = audit.sha(composed)
    undefined = set(audit.read_command(['xcrun', 'nm', '-ju', composed]).splitlines())
    kernel = set(audit.read_command(['xcrun', 'nm', '-jU', audit.KERNEL]).splitlines())
    link['undefined_symbols'] = sorted(undefined)
    link['not_defined_in_reference_kernel'] = sorted(undefined - kernel)
    if link['not_defined_in_reference_kernel'] != ['___dso_handle']:
        raise ValueError('New unresolved resource dependency beyond the existing DSO requirement')
    defined = audit.read_command(['xcrun', 'nm', '-jU', composed]).splitlines()
    if '_rpi5_pcie_windows_plan' not in defined or not any(
            'BCM2712PCIResourceBridge' in symbol and 'gMetaClass' in symbol for symbol in defined):
        raise ValueError('Actual resource/window implementation missing')
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('Resource build input changed: ' + name)
    report = dict(schema_version=1, scope='Abstract original-Apple PCI resource bridge; not a driver',
                  inputs_sha256=captured, source_commit=audit.COMMIT, results=results, link=link,
                  original_family_reused=True, original_sources_unchanged=True,
                  allocator_shim_used=False, fake_kernel_declarations_used=False,
                  allocator_address_space='PCI bus', descriptor_address_space='CPU physical',
                  maximum_bar_records=6, decode_padding_allocatable=False,
                  adaptation=adaptation, adapted_units=['IOPCIConfigurator.cpp'],
                  live_owner_admission_required=True, concrete_provider_implemented=False,
                  final_kernel_link_proven=False, driver_attachment_proven=False,
                  hardware_access_enabled=False, pi_executed=False, bar_assignment_proven=False,
                  dma_authorized=False, sd_actions=0, serial_actions=0, reboots=0,
                  original_zero_base_assignment_publication_fixed=True,
                  original_64bit_assignment_tag_publication_fixed=True)
    (output / 'manifest.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True, help='New directory only')
    report = build(parser.parse_args().output_dir)
    print(json.dumps(dict(object_sha256=report['link']['object_sha256'],
                          not_defined_in_reference_kernel=report['link']['not_defined_in_reference_kernel'],
                          pi_executed=False)))


if __name__ == '__main__':
    main()
