#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Compile the Pi config bridge against the recorded real Apple family; never boot."""
import argparse
import json
from pathlib import Path

try:
    from . import audit_apple_pci_build as audit
except ImportError:
    import audit_apple_pci_build as audit

ROOT = audit.ROOT
BASE = ROOT / 'build/rpi5/apple-pci-bcm2712-headers-20261012-final'
BASE_MANIFEST_SHA = '70b44e294bf2e55c4d9bb2eeacab5d89db361636ae40a2bcae12b092a0a3c117'
SOURCES = (ROOT / 'loader/rpi5/pcie_config.c', ROOT / 'iokit/Kernel/BCM2712PCIConfigBridge.cpp')


def base_inputs():
    manifest = BASE / 'manifest.json'
    if audit.sha(manifest) != BASE_MANIFEST_SHA:
        raise ValueError('Accepted Apple family compile manifest changed')
    report = json.loads(manifest.read_text())
    if (not report['all_source_units_compile'] or report['source_commit'] != audit.COMMIT or
            not report['adapted_copy_used'] or report['link']['returncode'] or
            report['link']['not_defined_in_reference_kernel'] != ['___dso_handle']):
        raise ValueError('Wrong Apple family build profile')
    inputs = {**report['inputs_sha256'], **report['generated_sha256']}
    inputs[str(manifest)] = BASE_MANIFEST_SHA
    inputs[str(BASE / 'IOPCIFamily-partial.o')] = report['link']['object_sha256']
    inputs[str(Path(__file__).resolve())] = audit.sha(Path(__file__).resolve())
    for name, digest in inputs.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('Apple family integration input changed: ' + name)
    original = audit.original_inputs()
    if any(inputs.get(name) != digest for name, digest in original.items()):
        raise ValueError('Original Apple source no longer matches the accepted screen')
    return inputs


def command(template, source, output):
    family, overlay = BASE / 'IOPCIFamily-adapted', BASE / 'include'
    args = audit.compile_command(template, source, overlay, output, family, no_apple_dart=True)
    # Retain strict checking for new board code without promoting original
    # SDK/family header warnings to board-code errors. No fake declarations.
    for i, arg in enumerate(args):
        if arg == '-I' and args[i+1] in (str(family), str(family / 'PCIDriverKit')):
            args[i] = '-isystem'
    args = ['-Werror' if arg == '-Wno-error' else arg for arg in args]
    return args


def build(output):
    inputs = base_inputs()
    output = output.resolve()
    if any(output.is_relative_to(path) for path in (BASE, audit.APPLE, audit.OBJ, audit.SDK)):
        raise ValueError('Config output must not be inside accepted inputs')
    output.mkdir(parents=True, exist_ok=False)
    template = json.loads(audit.TEMPLATE.read_text().strip().removesuffix(','))
    cwd = Path(template['directory'])
    results, objects = [], []
    for source in SOURCES:
        obj = output / (source.name + '.o')
        inputs[str(source)] = audit.sha(source)
        args = command(template, source, obj)
        dep = output / (source.name + '.d')
        dependencies = audit.execute([arg for arg in args[:-2] if arg != '-c'] +
                                     ['-M', '-MG', '-MF', str(dep)], cwd,
                                     output / (source.name + '.deps.log'))
        if dependencies['returncode']:
            raise ValueError('Board config dependency screen failed: ' + dependencies['log'])
        for path in audit.dependency_paths(dep, cwd):
            if not path.is_file():
                raise ValueError('Missing actual config dependency: ' + str(path))
            inputs.setdefault(str(path), audit.sha(path))
        row = audit.execute(args, cwd, output / (source.name + '.log'))
        results.append(row)
        if row['returncode']:
            raise ValueError('Board config compile failed: ' + row['log'])
        row['object_sha256'] = audit.sha(obj)
        objects.append(obj)
    composed = output / 'apple-bcm2712-pci-config.o'
    link = audit.execute(['xcrun', 'ld', '-r', '-arch', 'arm64', '-o', composed,
                          BASE / 'IOPCIFamily-partial.o', *objects], ROOT, output / 'link.log')
    if link['returncode']:
        raise ValueError('Board/family relocatable link failed: ' + link['log'])
    link['object_sha256'] = audit.sha(composed)
    undefined = set(audit.read_command(['xcrun', 'nm', '-ju', composed]).splitlines())
    kernel_symbols = set(audit.read_command(['xcrun', 'nm', '-jU', audit.KERNEL]).splitlines())
    link['undefined_symbols'] = sorted(undefined)
    link['not_defined_in_reference_kernel'] = sorted(undefined - kernel_symbols)
    if link['not_defined_in_reference_kernel'] != ['___dso_handle']:
        raise ValueError('New unresolved config dependencies beyond the existing DSO requirement')
    defined = audit.read_command(['xcrun', 'nm', '-jU', composed]).splitlines()
    for symbol in ('_rpi5_pcie_config_init', '_rpi5_pcie_config_transfer', '_rpi5_pcie_config_ready'):
        if symbol not in defined:
            raise ValueError('Actual config core missing: ' + symbol)
    if not any('BCM2712PCIConfigBridge' in name and 'gMetaClass' in name for name in defined):
        raise ValueError('Actual Apple API adapter metaclass missing')
    for name, digest in inputs.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('Config build input changed: ' + name)
    report = dict(schema_version=1, scope='Abstract original-IOPCIBridge config layer and C core; not a driver',
                  inputs_sha256=inputs, source_commit=audit.COMMIT, results=results, link=link,
                  original_family_reused=True, allocator_shim_used=False, fake_kernel_declarations_used=False,
                  config_methods_compiled=6, supported_bdfs=['00:00.0', '01:00.0'],
                  maximum_transaction_callbacks=15, retries=0, polls=0,
                  every_config_write_requires_provider_authorization=True,
                  concrete_provider_implemented=False, final_kernel_link_proven=False,
                  hardware_access_enabled=False, driver_attachment_proven=False,
                  pi_executed=False, bar_assignment_proven=False, dma_authorized=False,
                  sd_actions=0, serial_actions=0, reboots=0)
    (output / 'manifest.json').write_text(json.dumps(report, sort_keys=True, indent=2)+'\n')
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
