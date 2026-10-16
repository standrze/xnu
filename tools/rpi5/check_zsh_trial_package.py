#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only fixed zsh diagnostic package preflight, never board acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_serial_terminal_package as terminal
from build_probe import inspect as inspect_elf
from pcie_stack import check as stack_check
from prepare_zsh_trial_root import prepare

ROOT = Path(__file__).resolve().parents[2]
KERNEL = ROOT / 'build/rpi5/shell-userland-20261011/kernel.development.bcm2712'
PI_ROOT = KERNEL.with_name('ramdisk.bin')
INIT = ROOT / 'build/rpi5/zsh-pi-trial-root-20261012/ramdisk.bin'
CAPSULE = ROOT / 'experiments/darwin-container/userland/build/zsh-working-2026-10-12'
BASELINE = ROOT / 'build/rpi5/bl33-probe-ci45m9zs/probe.bin'
KERNEL_SHA = 'd133f3a21ff9d3397aed7dfdd04210fe79061d8919d5046010dfa1919980a10f'
PI_ROOT_SHA = 'd32891113ad2ecdb1637bfdfd58991574026877cfb827a4bd0cd229980541f55'
INIT_SHA = 'ddbdffe24f4441985cadf5aa1556d2b409e0c8a39d6d86dd5352d49814712e08'
CAPSULE_ROOT_SHA = '9c15abc1254963a9681eadf7fa0924cb0a1cd0425565210ac3b32e07f47c95ec'
ZSH_SHA = '78d947f6a08e26ceebbf275a7e15479aabbc61645ac407c546b1a82e74b437e5'
TOPOLOGY_PASS = b'RPI5XNU:BL33:PCIE_TOPOLOGY:PASS PCIE_MMIO=0 CONFIG_ACCESS=0 DMA=0 NIC_READY=0'
RAMROOT = b'RPI5XNU:RAMROOT:MOUNT NODES=24 BYTES=1392640 READONLY'


def profile_checks(manifest):
    commands = manifest.get('commands', [])
    main = [cmd for cmd in commands if any(Path(item).name == 'probe_main.c' for item in cmd)]
    units = {Path(item).name for cmd in commands for item in cmd if item.endswith('.c')}
    return {
        'declarations_only_profile': manifest.get('gate5_pcie_topology') is True
            and manifest.get('gate5_pcie_mmio_enabled') is False,
        'storage_disabled': all(manifest.get(name) is False for name in
            ('gate4_storage_binding_snapshot', 'gate4_sd_readonly', 'gate4_hfs_readonly', 'gate4_hfs_write_trial')),
        'topology_switch': len(main) == 1 and '-DRPI5_GATE5_PCIE_TOPOLOGY=1' in main[0],
        'no_hardware_observer_or_reset_objects': {'pcie_fdt.c', 'pcie_topology.c'}.issubset(units)
            and not units.intersection({'pcie_observe.c', 'pcie_reset.c', 'pcie_rescal.c',
                'pcie_mdio.c', 'pcie_serdes.c', 'pcie_ubus.c', 'pcie_windows.c', 'pcie_link.c',
                'pcie_access.c', 'probe_access_main.c', 'pcie_rc.c',
                'sd_pio.c', 'gem_dma.c', 'rpi5_gem_dma.c'}),
    }


def inspect(package):
    package = package.resolve()
    if not package.is_relative_to(ROOT / 'build/rpi5'):
        raise ValueError('Separate local build/rpi5 package required')
    report = terminal.inspect(package, KERNEL, INIT, BASELINE, shell_trial=True)
    manifest = json.loads((package / 'manifest.json').read_text())
    raw = (package / 'probe.bin').read_bytes()
    elf = (package / 'probe.elf').read_bytes()
    rebuilt_root, recovery = prepare(PI_ROOT.read_bytes(), (CAPSULE / 'ramdisk.bin').read_bytes(),
                                    (CAPSULE / 'zsh').read_bytes(), PI_ROOT_SHA, CAPSULE_ROOT_SHA, ZSH_SHA)
    loads = inspect_elf(elf, raw, 0x9000000)
    checks = report['checks']
    checks.update(profile_checks(manifest))
    checks.update(
        proven_kernel_unchanged=report['kernel_sha256'] == KERNEL_SHA,
        distinct_root_pinned=report['init_sha256'] == INIT_SHA,
        every_recovery_file_and_addition_exact=rebuilt_root == INIT.read_bytes(),
        expected_loader_entry=loads['entry'] == manifest.get('entry') == 0x9000000,
        topology_marker_embedded=TOPOLOGY_PASS in raw,
        zsh_diagnostic_startup_embedded=all(marker in raw for marker in
            (b'DARWIN:ZSH:ENTRY', b'DARWIN:ZSH:TSD', b'DARWIN:ZSH:ENTROPY', b'DARWIN:ZSH:MAIN')),
        stack_budget_matches=stack_check(manifest['stack_frames']) == manifest.get('gate5_pcie_topology_stack_budget'),
        source_and_outputs_unchanged=bool(manifest.get('sha256')) and all(
            terminal.sha256(ROOT / name) == value for name, value in manifest['sha256'].items()),
    )
    report.update(preflight_pass=all(checks.values()), image_bytes=len(raw),
        loader_manifest_sha256=terminal.sha256(package / 'manifest.json'),
        preserved_files_sha256=recovery['preserved_files_sha256'],
        root_mount_marker=RAMROOT.decode(), pi_executed=False,
        isa_and_abi_compatibility_proven=False,
        scope='Diagnostic package identity, ELF/profile/stack and recovery preservation; not Pi zsh acceptance')
    if not report['preflight_pass']:
        raise ValueError('zsh package refused: ' + repr([name for name, ok in checks.items() if not ok]))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--report', type=Path, help='New local report only')
    args = parser.parse_args()
    report = inspect(args.package)
    encoded = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.report:
        with args.report.open('x') as output:
            output.write(encoded)
    print(encoded, end='')


if __name__ == '__main__':
    main()
