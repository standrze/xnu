#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the opt-in kernel PM owner in separate objects; never stage or reboot."""
import argparse
import json
from pathlib import Path
import shutil

try:
    from . import audit_apple_pci_build as audit
except ImportError:
    import audit_apple_pci_build as audit

ROOT = audit.ROOT
SOURCE = ROOT / 'pexpert/arm/pe_fiq.c'
SOURCE_SHA = '18422248b3a07ee2d7b54d29ff2e07af741a125930227c2f3eb6d916f8589036'
TEMPLATE = audit.OBJ / 'pexpert/DEVELOPMENT/pe_fiq.o.json'
TEMPLATE_SHA = '2e5ade5ca87a93ff0cc4c468d6f7f185cced2e2d33c25f0670946986f250ed56'
PATCH = ROOT / 'tools/rpi5/patches/pcie-watchdog-lease.patch'
CORE = ROOT / 'loader/rpi5/pcie_watchdog_lease.c'


def command(template, source, obj, enabled=True):
    # Actual pexpert C template, without the PCI-family/header-overlay flags.
    args = audit.compile_command(template, source, ROOT / 'pexpert', obj)
    # No Apple PCI headers are used by this unit; remove the helper's default
    # family paths rather than introducing an accidental dependency.
    remove = {str(audit.APPLE), str(audit.APPLE / 'PCIDriverKit')}
    for path in remove:
        i = args.index(path)
        del args[i-1:i+1]
    args = ['-Werror' if arg == '-Wno-error' else arg for arg in args]
    args[1:1] = ['-I', str(ROOT), '-DRPI5_PCI_WDOG_LEASE=' + ('1' if enabled else '0')]
    return args


def inputs():
    if audit.sha(SOURCE) != SOURCE_SHA:
        raise ValueError('Preserved pe_fiq source changed')
    if audit.sha(TEMPLATE) != TEMPLATE_SHA:
        raise ValueError('Actual pexpert compile template changed')
    return {str(path): audit.sha(path) for path in (SOURCE, TEMPLATE, PATCH, CORE,
        ROOT / 'loader/rpi5/pcie_watchdog_lease.h', ROOT / 'loader/rpi5/pcie_watchdog_gate.h',
        ROOT / 'pexpert/arm/rpi5_pcie_watchdog_api.h', ROOT / 'pexpert/arm/rpi5_pcie_watchdog_owner.inc',
        ROOT / 'tools/rpi5/audit_apple_pci_build.py', audit.KERNEL, Path(__file__).resolve())}


def build(output):
    captured = inputs()
    output = output.resolve()
    if any(output.is_relative_to(path) for path in (audit.OBJ, audit.SDK, ROOT / 'pexpert', ROOT / 'loader')):
        raise ValueError('Owner output must not be inside source or accepted objects')
    output.mkdir(parents=True, exist_ok=False)
    source = output / 'pe_fiq.c'
    shutil.copyfile(SOURCE, source)
    adaptation = audit.execute(['patch', '--batch', '--fuzz=0', '-p1', '-d', output, '-i', PATCH],
                               ROOT, output / 'patch.log')
    if adaptation['returncode']:
        raise ValueError('Watchdog owner adaptation failed: ' + adaptation['log'])
    template = json.loads(TEMPLATE.read_text().strip().removesuffix(','))
    cwd = Path(template['directory'])
    captured[str(Path(template['arguments'][0]))] = audit.sha(Path(template['arguments'][0]))
    results, objects = [], []
    for unit in (source, CORE):
        captured[str(unit)] = audit.sha(unit)
        obj = output / (unit.name + '.o')
        args = command(template, unit, obj)
        dep = output / (unit.name + '.d')
        dependencies = audit.execute([arg for arg in args[:-2] if arg != '-c'] +
            ['-M', '-MG', '-MF', str(dep)], cwd, output / (unit.name + '.deps.log'))
        if dependencies['returncode']:
            raise ValueError('Watchdog dependency screen failed: ' + dependencies['log'])
        for path in audit.dependency_paths(dep, cwd):
            if not path.is_file():
                raise ValueError('Missing actual watchdog dependency: ' + str(path))
            captured.setdefault(str(path), audit.sha(path))
        row = audit.execute(args, cwd, output / (unit.name + '.log'))
        if row['returncode']:
            raise ValueError('Watchdog owner compile failed: ' + row['log'])
        row['object_sha256'] = audit.sha(obj)
        results.append(row); objects.append(obj)
    composed = output / 'bcm2712-pcie-watchdog-owner.o'
    link = audit.execute(['xcrun', 'ld', '-r', '-arch', 'arm64', '-o', composed, *objects],
                         ROOT, output / 'link.log')
    if link['returncode']:
        raise ValueError('Watchdog owner partial link failed: ' + link['log'])
    link['object_sha256'] = audit.sha(composed)
    undefined = set(audit.read_command(['xcrun', 'nm', '-ju', composed]).splitlines())
    defined = set(audit.read_command(['xcrun', 'nm', '-jU', composed]).splitlines())
    kernel = set(audit.read_command(['xcrun', 'nm', '-jU', audit.KERNEL]).splitlines())
    link['undefined_symbols'] = sorted(undefined)
    link['not_defined_in_reference_kernel'] = sorted(undefined - kernel)
    if link['not_defined_in_reference_kernel']:
        raise ValueError('New unresolved watchdog dependency')
    for symbol in ('_pe_rpi5_watchdog_claim_pcie', '_pe_rpi5_watchdog_check_pcie',
                   '_pe_rpi5_watchdog_timer_tick', '_rpi5_pcie_watchdog_begin', '_rpi5_pcie_watchdog_check'):
        if symbol not in defined:
            raise ValueError('Actual watchdog implementation missing: ' + symbol)
    if '_rpi5_watchdog_service_unlocked' in defined:
        raise ValueError('Unserialized watchdog service must not be externally callable')
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('Watchdog build input changed: ' + name)
    report = dict(schema_version=1, scope='Separate opt-in real pexpert watchdog owner; not a kernel boot',
        inputs_sha256=captured, results=results, adaptation=adaptation, link=link,
        actual_xnu_pm_mapping_reused=True, original_source_unchanged=True,
        normal_servicing_suppressed_after_claim=True, claim_nonblocking=True,
        watchdog_countdown_writes_per_lease=1, watchdog_seconds=15, access_deadline_seconds=12,
        minimum_countdown_margin_seconds=2, maximum_checks=65536,
        reset_route_writes=0, reset_status_writes=0, cancel_or_release_implemented=False,
        final_kernel_link_proven=False, installed=False, pi_executed=False,
        physical_reset_timing_proven=False, reset_destination_proven=False,
        concrete_pci_provider_implemented=False, dma_authorized=False,
        sd_actions=0, serial_actions=0, reboots=0)
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
