#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Check the distinct socket diagnostic image without serial, media or reboot."""
import argparse
import json
from pathlib import Path

try:
    from . import prepare_socketprobe_root as root
    from . import check_zsh_metadata_package as metadata
    from . import check_serial_terminal_package as terminal
    from .check_zsh_trial_package import profile_checks, BASELINE
    from .build_probe import inspect as inspect_elf
    from .pcie_stack import check as stack_check
except ImportError:
    import prepare_socketprobe_root as root
    import check_zsh_metadata_package as metadata
    import check_serial_terminal_package as terminal
    from check_zsh_trial_package import profile_checks, BASELINE
    from build_probe import inspect as inspect_elf
    from pcie_stack import check as stack_check

INIT = root.ROOT/'build/rpi5/socketprobe-root-20261012/ramdisk.bin'
INIT_SHA = 'ce5c8d7ecd9f55ea9cbd988af6ffcf308252065e591a1fd66c1233bfcb566ab7'
PROBE_SHA = 'c60c81856e469bbeddc8e493f1464c63aa2c6687ebff446fbf70ebbf95f1d68d'
ROOT_RECEIPT_SHA = 'f02aeb071d9fb4caa2e5c18a7abe11b264ae7c38637015ed7b5cffb532265fba'
ACCEPTED = root.ROOT/'build/rpi5/bl33-probe-wdmzdtem'


def inspect(package):
    package = package.resolve()
    if not package.is_relative_to(root.ROOT/'build/rpi5'):
        raise ValueError('Separate local build/rpi5 package required')
    accepted = metadata.inspect(ACCEPTED)
    wiring, _ = root.kernel_calls()
    report = terminal.inspect(package, metadata.KERNEL, INIT, BASELINE, shell_trial=True)
    manifest = json.loads((package/'manifest.json').read_text())
    receipt = json.loads(INIT.with_name('manifest.json').read_text())
    diagnostic = INIT.with_name('socketprobe').read_bytes()
    reconstructed, preservation = root.prepare(root.ACCEPTED_ROOT.read_bytes(), diagnostic, root.ROOT_PIN)
    image = (package/'probe.bin').read_bytes()
    loads = inspect_elf((package/'probe.elf').read_bytes(), image, 0x9000000)
    checks = report['checks']
    checks.update(profile_checks(manifest))
    checks.update(
        accepted_kernel_unchanged=report['kernel_sha256'] == metadata.KERNEL_SHA == accepted['kernel_sha256'],
        diagnostic_binary_pinned=terminal.sha256(INIT.with_name('socketprobe')) == PROBE_SHA,
        diagnostic_root_pinned=report['init_sha256'] == INIT_SHA,
        diagnostic_receipt_pinned=terminal.sha256(INIT.with_name('manifest.json')) == ROOT_RECEIPT_SHA,
        exact_additive_root=reconstructed == INIT.read_bytes(),
        preserved_files_match=receipt.get('preserved_files_sha256') == preservation['preserved_files_sha256'],
        exact_local_helper_path=receipt.get('install_path') == root.INSTALL_PATH,
        exact_root_extent=receipt.get('output_nodes') == 32 and receipt.get('output_bytes') == 1900544
            and receipt.get('output_sha256') == INIT_SHA,
        actual_linked_sysent=receipt.get('linked_sysent') == wiring,
        actual_storage_guard=accepted['linked_storage_entry_guard']['absent_or_not_one_returns_false'] is True,
        storage_off_command=image.count(terminal.TERMINAL_COMMAND+b'\0') == 1,
        loader_entry_exact=loads['entry'] == manifest.get('entry') == 0x9000000,
        diagnostic_markers_embedded=all(marker in image for marker in (
            b'SOCKETPROBE:BEGIN:RAW_DARWIN_V1', b'SOCKETPROBE:MODE=inet_LOOPBACK_ONLY',
            b'SOCKETPROBE:END:NOT_ETHERNET_OR_SSH_PROOF')),
        root_sources_and_sdk_unchanged=all(mapping and all(
            terminal.sha256(Path(name)) == pin for name, pin in mapping.items())
            for mapping in (receipt.get('source_inputs_sha256', {}), receipt.get('sdk_headers_sha256', {}))),
        loader_sources_and_outputs_unchanged=bool(manifest.get('sha256')) and all(
            terminal.sha256(root.ROOT/name) == pin for name, pin in manifest['sha256'].items()),
        expected_stack=stack_check(manifest['stack_frames']) == manifest.get('gate5_pcie_topology_stack_budget'),
    )
    report.update(preflight_pass=all(checks.values()), image_bytes=len(image),
                  loader_manifest_sha256=terminal.sha256(package/'manifest.json'),
                  root_manifest_sha256=terminal.sha256(INIT.with_name('manifest.json')),
                  root_mount_marker='RPI5XNU:RAMROOT:MOUNT NODES=32 BYTES=1900544 READONLY',
                  install_path=root.INSTALL_PATH, linked_sysent=wiring,
                  scope='Unstaged socket diagnostic package; not Pi socket, NIC or SSH acceptance',
                  pi_executed=False, socket_semantics_proven=False, networking=False,
                  nic_ready=False, ssh_proven=False, durability=False,
                  sd_actions=0, serial_actions=0, reboots=0)
    if not report['preflight_pass']:
        raise ValueError('Socket package refused: '+repr([k for k, v in checks.items() if not v]))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = inspect(args.package)
    with args.report.open('x') as output:
        json.dump(report, output, indent=2, sort_keys=True); output.write('\n')
    print(json.dumps(dict(image_sha256=report['image_sha256'], image_bytes=report['image_bytes'],
                         checks=len(report['checks']), preflight_pass=True, pi_executed=False)))


if __name__ == '__main__':
    main()
