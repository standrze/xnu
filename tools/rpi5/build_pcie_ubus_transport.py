#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Wire UBUS into a copied real IOKit PHY transport; never install or boot."""
import argparse
import json
from pathlib import Path
import shutil

try:
    from . import build_pcie_phy_transport as phy
except ImportError:
    import build_pcie_phy_transport as phy

audit, ROOT = phy.audit, phy.ROOT
BASE = ROOT / 'build/rpi5/pcie-phy-transport-20261012-final'
BASE_SHA = 'bef1c4f8e022c6512628613b1d3a696985bb70dfc4b361399e5e53dab22bd731'
PATCH = ROOT / 'tools/rpi5/patches/pcie-ubus-transport.patch'
POLICY = ROOT / 'iokit/Kernel/BCM2712PCIeUBUSPolicy.h'
CONTINUATION = ROOT / 'iokit/Kernel/BCM2712PCIeUBUS.inc'
CORE = ROOT / 'loader/rpi5/pcie_ubus.c'


def inputs():
    manifest = BASE / 'manifest.json'
    if audit.sha(manifest) != BASE_SHA:
        raise ValueError('Accepted PHY manifest changed')
    prior = json.loads(manifest.read_text())
    captured = {**prior['inputs_sha256'], **prior['generated_sha256'], str(manifest): BASE_SHA,
                str(BASE / 'apple-bcm2712-pcie-phy-diagnostic.o'): prior['link']['object_sha256']}
    for name, digest in phy.inputs().items():
        if name in captured and captured[name] != digest:
            raise ValueError('Conflicting accepted PHY input: ' + name)
        captured[name] = digest
    # The composed old object contains the old class. Reuse its seven real C
    # objects only, and replace the transport with a separately compiled copy.
    objects = []
    for source, row in zip(phy.CORES, prior['results'][1:], strict=True):
        obj = BASE / (source.name + '.o')
        captured[str(obj)] = row['object_sha256']
        objects.append(obj)
    for source in (PATCH, POLICY, CONTINUATION, CORE, Path(__file__).resolve()):
        captured[str(source)] = audit.sha(source)
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('UBUS dependency changed: ' + name)
    return captured, objects


def build(output):
    captured, prior_objects = inputs()
    output = output.resolve()
    prohibited = (ROOT / 'iokit', ROOT / 'loader', ROOT / 'pexpert', ROOT / 'tools',
                  ROOT / 'docs', audit.APPLE, audit.SDK, audit.OBJ, phy.config.BASE, BASE,
                  ROOT / 'build/rpi5/bl33-probe-vszhh6o4',
                  ROOT / 'build/rpi5/pcie-device-handoff-20261012-final',
                  *(directory for directory, _, _ in phy.BASELINES))
    if any(output.is_relative_to(path.resolve()) for path in prohibited):
        raise ValueError('UBUS output must not be inside sources or accepted inputs')
    output.mkdir(parents=True, exist_ok=False)
    overlay = output / 'overlay'
    overlay.mkdir()
    for name in ('BCM2712PCIePHYTransport.cpp', 'BCM2712PCIePHYTransport.h'):
        shutil.copyfile(ROOT / 'iokit/Kernel' / name, overlay / name)
    patch = audit.execute(['patch', '--batch', '--fuzz=0', '-p1', '-i', PATCH],
                          overlay, output / 'patch.log')
    if patch['returncode']:
        raise ValueError('UBUS transport copy patch failed: ' + patch['log'])
    copied = overlay / 'BCM2712PCIePHYTransport.cpp'
    results, new_objects = [], []
    for source in (copied, CORE):
        cpp = source == copied
        template_path = audit.TEMPLATE if cpp else phy.watchdog.TEMPLATE
        template = json.loads(template_path.read_text().strip().removesuffix(','))
        compiler = Path(template['arguments'][0])
        captured.setdefault(str(compiler), audit.sha(compiler))
        cwd, obj = Path(template['directory']), output / (source.name + '.o')
        args = (phy.config.command if cpp else phy.watchdog.command)(template, source, obj)
        if cpp:
            args[1:1] = ['-DRPI5_PCIE_PHY_DIAGNOSTIC=1', '-DRPI5_PCIE_UBUS_DIAGNOSTIC=1',
                         '-iquote', str(ROOT / 'iokit/Kernel')]
        captured[str(source)] = audit.sha(source)
        dep = output / (source.name + '.d')
        dependencies = audit.execute([arg for arg in args[:-2] if arg != '-c'] +
            ['-M', '-MG', '-MF', str(dep)], cwd, output / (source.name + '.deps.log'))
        if dependencies['returncode']:
            raise ValueError('UBUS dependency screen failed: ' + dependencies['log'])
        for path in audit.dependency_paths(dep, cwd):
            if not path.is_file():
                raise ValueError('Missing actual UBUS dependency: ' + str(path))
            captured.setdefault(str(path), audit.sha(path))
        row = audit.execute(args, cwd, output / (source.name + '.log'))
        if row['returncode'] or row['warning_count']:
            raise ValueError('UBUS actual kernel compile failed or warned: ' + row['log'])
        row['object_sha256'] = audit.sha(obj)
        results.append(row)
        new_objects.append(obj)
    composed = output / 'apple-bcm2712-pcie-ubus-diagnostic.o'
    link = audit.execute(['xcrun', 'ld', '-r', '-arch', 'arm64', '-o', composed,
        *(directory / name for directory, _, name in phy.BASELINES),
        *prior_objects, *new_objects], ROOT, output / 'link.log')
    if link['returncode']:
        raise ValueError('UBUS/PCI/watchdog partial link failed: ' + link['log'])
    link['object_sha256'] = audit.sha(composed)
    undefined = set(audit.read_command(['xcrun', 'nm', '-ju', composed]).splitlines())
    defined = set(audit.read_command(['xcrun', 'nm', '-jU', composed]).splitlines())
    kernel = set(audit.read_command(['xcrun', 'nm', '-jU', audit.KERNEL]).splitlines())
    link['undefined_symbols'] = sorted(undefined)
    link['not_defined_in_reference_kernel'] = sorted(undefined - kernel)
    if link['not_defined_in_reference_kernel'] != ['___dso_handle']:
        raise ValueError('New unresolved UBUS dependency beyond existing family DSO requirement')
    for symbol in ('_pe_rpi5_watchdog_claim_pcie', '_pe_rpi5_watchdog_check_pcie',
                   '_rpi5_pcie_reset_pulse', '_rpi5_pcie_rescal_calibrate',
                   '_rpi5_pcie_serdes_configure54', '_rpi5_pcie_ubus_init', '_rpi5_pcie_ubus_configure'):
        if symbol not in defined:
            raise ValueError('Real PHY/UBUS implementation missing: ' + symbol)
    if not any('BCM2712PCIePHYTransport' in s and 'runPHYAndUBUS' in s for s in defined):
        raise ValueError('Actual IOKit continuation missing')
    assembly = output / 'transport.s'
    args = [arg for arg in results[0]['command'][:-2] if arg != '-c'] + ['-S', '-o', str(assembly)]
    assembly_result = audit.execute(args, audit.OBJ / 'iokit/DEVELOPMENT', output / 'assembly.log')
    if assembly_result['returncode']:
        raise ValueError('Actual UBUS target assembly failed: ' + assembly_result['log'])
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('UBUS input changed during build: ' + name)
    generated = {str(path): audit.sha(path) for path in output.rglob('*') if path.is_file()}
    report = dict(schema_version=1, scope='Copied IOKit PHY transport with real UBUS continuation; uninstalled',
        inputs_sha256=captured, generated_sha256=generated, patch=patch, results=results,
        link=link, assembly_result=assembly_result, actual_kernel_headers=True,
        actual_initial_cores_wired=['reset44', 'shared RESCAL', '54MHz SerDes/MDIO', 'UBUS/AXI'],
        original_sources_changed=False, actual_ubus_core_wired=True,
        same_owned_serdes_session=True, single_watchdog_claim=True,
        failure_quarantines_all_four_stages=True, output_committed_after_final_guard=True,
        no_new_mapped_pages=True, real_phase_restricted_mmio=True,
        installed=False, pi_executed=False, final_kernel_link_proven=False,
        power_clock_shared_ownership_proven=False, physical_recovery_proven=False,
        rc_windows_link_wired=False, config_bar_authorized=False, irq_dma_authorized=False,
        ethernet_proven=False, cleanup_mmio=False, sd_actions=0, serial_actions=0, reboots=0)
    (output / 'manifest.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    report = build(parser.parse_args().output_dir)
    print(json.dumps(dict(object_sha256=report['link']['object_sha256'],
                         actual_ubus_core_wired=True, pi_executed=False)))


if __name__ == '__main__':
    main()
