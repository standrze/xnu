#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct storage-off Apple network-command package; no install or board I/O."""
import argparse
import hashlib
import json
from pathlib import Path

try:
    from . import audit_apple_network_kernel as kernel_audit
    from . import prepare_apple_network_root as root
    from . import check_zsh_metadata_package as metadata
    from . import check_serial_terminal_package as terminal
    from .check_zsh_trial_package import profile_checks, BASELINE
    from .build_probe import inspect as inspect_elf
    from .pcie_stack import check as stack_check
except ImportError:
    import audit_apple_network_kernel as kernel_audit
    import prepare_apple_network_root as root
    import check_zsh_metadata_package as metadata
    import check_serial_terminal_package as terminal
    from check_zsh_trial_package import profile_checks, BASELINE
    from build_probe import inspect as inspect_elf
    from pcie_stack import check as stack_check

INIT = root.ROOT / 'build/rpi5/apple-network-root-darwin-20261012/ramdisk.bin'
INIT_SHA = '0fdb95400e7a6421602a39851eaaa6f20e43836e33c390740774165053548b7e'
ACCEPTED = root.ROOT / 'build/rpi5/bl33-probe-wdmzdtem'


def inspect(package):
    package = package.resolve()
    if not package.is_relative_to(root.ROOT/'build/rpi5'):
        raise ValueError('Separate local build/rpi5 package required')
    # Reuse the accepted package's kernel/storage-entry validation unchanged.
    accepted = metadata.inspect(ACCEPTED)
    wiring = kernel_audit.audit()
    report = terminal.inspect(package, metadata.KERNEL, INIT, BASELINE, shell_trial=True)
    manifest = json.loads((package/'manifest.json').read_text())
    image = (package/'probe.bin').read_bytes()
    loads = inspect_elf((package/'probe.elf').read_bytes(), image, 0x9000000)
    commands, _, _ = root.load_inputs()
    reconstructed, preservation = root.prepare(root.PI_ROOT.read_bytes(), commands, root.ROOT_PIN,
                                               {name: pins[0] for name,pins in root.PINS.items()})
    checks = report['checks']
    checks.update(profile_checks(manifest))
    checks.update(
        accepted_kernel_unchanged=report['kernel_sha256'] == metadata.KERNEL_SHA == accepted['kernel_sha256'],
        distinct_additive_root_pinned=report['init_sha256'] == INIT_SHA,
        root_exact_and_recovery_preserved=reconstructed == INIT.read_bytes(),
        loader_entry_exact=loads['entry'] == manifest.get('entry') == 0x9000000,
        actual_bsd_network_sysent_handlers=wiring['network_syscalls_bound_to_real_handlers'] is True,
        actual_storage_guard=accepted['linked_storage_entry_guard']['absent_or_not_one_returns_false'] is True,
        storage_off_command=image.count(terminal.TERMINAL_COMMAND+b'\0') == 1,
        apple_utility_startup_embedded=all(commands[name] in image for name in commands),
        expected_stack=stack_check(manifest['stack_frames']) == manifest.get('gate5_pcie_topology_stack_budget'),
        loader_sources_and_outputs_unchanged=bool(manifest.get('sha256')) and all(
            terminal.sha256(root.ROOT/name) == pin for name,pin in manifest['sha256'].items()),
    )
    report.update(preflight_pass=all(checks.values()), image_bytes=len(image),
                  loader_manifest_sha256=terminal.sha256(package/'manifest.json'),
                  root_manifest_sha256=terminal.sha256(INIT.with_name('manifest.json')),
                  linked_kernel_audit=wiring, preserved_files_sha256=preservation['preserved_files_sha256'],
                  root_mount_marker='RPI5XNU:RAMROOT:MOUNT NODES=27 BYTES=1867776 READONLY',
                  command_install_paths=dict(root.INSTALL_PATHS),
                  pi_executed=False, networking=False, durability=False,
                  scope='Exact additive Apple utilities and linked syscall preflight; runtime not accepted',
                  sd_actions=0, serial_actions=0, reboots=0)
    if not report['preflight_pass']:
        raise ValueError('Apple network package refused: '+repr([k for k,v in checks.items() if not v]))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = inspect(args.package)
    with args.report.open('x') as output:
        json.dump(report, output, indent=2, sort_keys=True)
        output.write('\n')
    print(json.dumps(dict(image_sha256=report['image_sha256'],
                          checks=len(report['checks']), preflight_pass=True, pi_executed=False)))


if __name__ == '__main__':
    main()
