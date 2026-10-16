#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Compile real IOKit PHY MMIO plus existing PCI/watchdog objects; never boot."""
import argparse
import json
from pathlib import Path

try:
    from . import build_apple_pci_config as config
    from . import build_pcie_watchdog_owner as watchdog
except ImportError:
    import build_apple_pci_config as config
    import build_pcie_watchdog_owner as watchdog

audit = config.audit
ROOT = audit.ROOT
BASELINES = (
    (ROOT / 'build/rpi5/apple-pci-resources-20261012-final',
     'f2a37ca0988cbbcdc8d3cbf1925c63dd613a5d010655981e9e9827f8a00617ba',
     'apple-bcm2712-pci-resources.o'),
    (ROOT / 'build/rpi5/pcie-watchdog-owner-20261012-final-v2',
     '643ce20a2bbda45ea313ae4ba182e69dcb1a1538d04d01a412ede8a037525c86',
     'bcm2712-pcie-watchdog-owner.o'),
)
SOURCE = ROOT / 'iokit/Kernel/BCM2712PCIePHYTransport.cpp'
CORES = tuple(ROOT / ('loader/rpi5/' + name + '.c') for name in
              ('fdt', 'fdt_reg', 'pcie_fdt', 'pcie_reset', 'pcie_rescal', 'pcie_mdio', 'pcie_serdes'))


def inputs():
    captured = {}
    for directory, digest, obj in BASELINES:
        manifest = directory / 'manifest.json'
        if audit.sha(manifest) != digest:
            raise ValueError('Accepted PHY dependency manifest changed: ' + str(manifest))
        report = json.loads(manifest.read_text())
        for name, pin in {**report['inputs_sha256'], **report.get('generated_sha256', {}),
                          str(manifest): digest, str(directory / obj): report['link']['object_sha256']}.items():
            if name in captured and captured[name] != pin:
                raise ValueError('Conflicting dependency pin: ' + name)
            captured[name] = pin
    if audit.sha(audit.TEMPLATE) != audit.TEMPLATE_SHA:
        raise ValueError('Actual kernel C++ compile template changed')
    captured[str(audit.TEMPLATE)] = audit.TEMPLATE_SHA
    for source in (SOURCE, *CORES, Path(__file__).resolve(),
                   ROOT / 'osfmk/mach/arm/vm_param.h', ROOT / 'osfmk/arm/arm_init.c',
                   ROOT / 'osfmk/arm/pmap/pmap.c', ROOT / 'iokit/Kernel/IOMemoryDescriptor.cpp'):
        captured[str(source)] = audit.sha(source)
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('PHY dependency changed: ' + name)
    return captured


def build(output):
    captured = inputs()
    output = output.resolve()
    prohibited = (ROOT / 'iokit', ROOT / 'pexpert', ROOT / 'loader', audit.APPLE, audit.SDK, audit.OBJ,
                  config.BASE, *(directory for directory, _, _ in BASELINES))
    if any(output.is_relative_to(path) for path in prohibited):
        raise ValueError('PHY output must not be inside sources or accepted inputs')
    output.mkdir(parents=True, exist_ok=False)
    results, objects = [], []
    for source in (SOURCE, *CORES):
        template_path = audit.TEMPLATE if source == SOURCE else watchdog.TEMPLATE
        template = json.loads(template_path.read_text().strip().removesuffix(','))
        captured[str(Path(template['arguments'][0]))] = audit.sha(Path(template['arguments'][0]))
        cwd, obj = Path(template['directory']), output / (source.name + '.o')
        args = (config.command if source == SOURCE else watchdog.command)(template, source, obj)
        if source == SOURCE:
            args[1:1] = ['-DRPI5_PCIE_PHY_DIAGNOSTIC=1']
        dep = output / (source.name + '.d')
        dependencies = audit.execute([arg for arg in args[:-2] if arg != '-c'] +
            ['-M', '-MG', '-MF', str(dep)], cwd, output / (source.name + '.deps.log'))
        if dependencies['returncode']:
            raise ValueError('PHY dependency screen failed: ' + dependencies['log'])
        for path in audit.dependency_paths(dep, cwd):
            if not path.is_file():
                raise ValueError('Missing actual PHY dependency: ' + str(path))
            captured.setdefault(str(path), audit.sha(path))
        row = audit.execute(args, cwd, output / (source.name + '.log'))
        if row['returncode']:
            raise ValueError('PHY transport compile failed: ' + row['log'])
        row['object_sha256'] = audit.sha(obj)
        objects.append(obj); results.append(row)
    composed = output / 'apple-bcm2712-pcie-phy-diagnostic.o'
    link = audit.execute(['xcrun', 'ld', '-r', '-arch', 'arm64', '-o', composed,
        *(directory / obj for directory, _, obj in BASELINES), *objects], ROOT, output / 'link.log')
    if link['returncode']:
        raise ValueError('PHY/PCI/watchdog partial link failed: ' + link['log'])
    link['object_sha256'] = audit.sha(composed)
    undefined = set(audit.read_command(['xcrun', 'nm', '-ju', composed]).splitlines())
    defined = set(audit.read_command(['xcrun', 'nm', '-jU', composed]).splitlines())
    kernel = set(audit.read_command(['xcrun', 'nm', '-jU', audit.KERNEL]).splitlines())
    link['undefined_symbols'] = sorted(undefined)
    link['not_defined_in_reference_kernel'] = sorted(undefined - kernel)
    if link['not_defined_in_reference_kernel'] != ['___dso_handle']:
        raise ValueError('New unresolved PHY dependency beyond existing family DSO requirement')
    for symbol in ('_pe_rpi5_watchdog_claim_pcie', '_pe_rpi5_watchdog_check_pcie',
                   '_rpi5_fdt_pcie_rp1', '_rpi5_pcie_reset_pulse', '_rpi5_pcie_rescal_calibrate',
                   '_rpi5_pcie_serdes_configure54', '_rpi5_pcie_mdio_write'):
        if symbol not in defined:
            raise ValueError('Real PHY/watchdog implementation missing: ' + symbol)
    if not any('BCM2712PCIePHYTransport' in symbol and 'gMetaClass' in symbol for symbol in defined):
        raise ValueError('Actual IOKit transport metaclass missing')
    assembly = output / 'transport.s'
    args = [arg for arg in results[0]['command'][:-2] if arg != '-c'] + ['-S', '-o', str(assembly)]
    assembly_result = audit.execute(args, audit.OBJ / 'iokit/DEVELOPMENT', output / 'assembly.log')
    if assembly_result['returncode']:
        raise ValueError('Actual PHY target assembly failed: ' + assembly_result['log'])
    assembly_sha = audit.sha(assembly)
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('PHY build input changed: ' + name)
    report = dict(schema_version=1, scope='Real IOKit Device/PHY callbacks with original PCI and PM owner; uninstalled',
        inputs_sha256=captured, results=results, link=link, assembly_result=assembly_result,
        generated_sha256={str(assembly): assembly_sha},
        actual_kernel_headers=True, actual_mmio_transport_implemented=True,
        actual_fdt_decoder_reused=True, actual_initial_cores_wired=['reset44', 'shared RESCAL', '54MHz SerDes/MDIO'],
        register_resource_bytes=[0x9310, 0x10, 0x30], mapped_page_bytes=[0xc000, 0x4000, 0x4000],
        phases_restrict_register_offsets=True, watchdog_guard_before_and_after_mmio=True,
        ownership_retained_after_claim_failure=True, provider_open_implemented=True,
        rounded_pages_require_immutable_device_classification=True,
        provider_open_proves_hardware_exclusivity=False, shared_power_clock_admission_proven=False,
        final_kernel_link_proven=False, installed=False, pi_executed=False,
        physical_reset_timing_proven=False, reset_destination_proven=False,
        concrete_pci_bridge_owner_implemented=False, link_training_wired=False,
        dma_authorized=False, ethernet_proven=False, registry_boolean_admission_used=False,
        fake_kernel_declarations_used=False, cleanup_mmio=False, power_off=False,
        sd_actions=0, serial_actions=0, reboots=0)
    (output / 'manifest.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path, help='New directory only')
    report = build(parser.parse_args().output_dir)
    print(json.dumps(dict(object_sha256=report['link']['object_sha256'],
        not_defined_in_reference_kernel=report['link']['not_defined_in_reference_kernel'], pi_executed=False)))


if __name__ == '__main__':
    main()
