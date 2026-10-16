#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Additional read-only SD trial preflight; no staging, serial or board access."""
import argparse
import json
from pathlib import Path
import subprocess

from check_serial_terminal_package import inspect as shell_inspect, sha256
from ramroot import inspect as ramroot_inspect
from kernel_config_syntax import inspect_kernel_config

SHELL_BASELINE_SHA256 = 'bf01b0eedcce48249a7358772f74613d0b0453217f35576369945de25d50374f'
SD_LOADER = b'RPI5XNU:BL33:SD_READONLY_TRIAL DMA=0 WRITES=0'
REQUIRED_SD_CHECKS = frozenset((
    'image_hash_matches_manifest', 'kernel_matches_manifest', 'init_matches_manifest',
    'baseline_is_unchanged_gate3_image', 'terminal_four_cpu_transfer', 'no_gate3_trial_or_qualification',
    'shell_archive_fully_embedded', 'working_shell_baseline_preserved',
    'storage_trial_distinct_from_working_shell', 'separate_sd_trial_flags',
    'sd_trial_loader_and_boot_argument', 'kernel_storage_classes_and_transport_linked',
    'fresh_storage_kernel_build_succeeded', 'distinct_readonly_sdread_program', 'linked_kernel_config_parses'))


def inspect(package, kernel, init, gate3_baseline, shell_baseline, kernel_build):
    report = shell_inspect(package, kernel, init, gate3_baseline, shell_trial=True)
    manifest = json.loads((package / 'manifest.json').read_text())
    build = json.loads(kernel_build.read_text())
    userland = json.loads((init.parent / 'manifest.json').read_text())
    image = (package / 'probe.bin').read_bytes()
    commands = [c for c in manifest['commands'] if any(Path(x).name == 'probe_main.c' for x in c)]
    entries = {e['path']: e for e in ramroot_inspect(init.read_bytes())['entries']}
    symbols = set(subprocess.check_output(['xcrun', 'nm', '-jU', str(kernel)], text=True).splitlines())
    undefined = subprocess.check_output(['xcrun', 'nm', '-ju', str(kernel)], text=True).splitlines()
    syntax = inspect_kernel_config(kernel)
    required = {'__ZN16BCM2712SDStorage10gMetaClassE', '__ZN20IOBlockStorageDriver10gMetaClassE',
                '__ZN16IOMediaBSDClient10gMetaClassE', '__ZN22IOFDiskPartitionScheme10gMetaClassE',
                '_rpi5_sd_start', '_rpi5_sd_read_sector', '_rpi5_sd_handoff', '_rpi5_sd_binding_decode'}
    checks = report['checks']
    checks.update({
        'working_shell_baseline_preserved': sha256(shell_baseline) == SHELL_BASELINE_SHA256,
        'storage_trial_distinct_from_working_shell': report['image_sha256'] != SHELL_BASELINE_SHA256,
        'separate_sd_trial_flags': manifest.get('gate4_storage_binding_snapshot') is True
            and manifest.get('gate4_sd_readonly') is True and len(commands) == 1
            and '-DRPI5_GATE4_STORAGE=1' in commands[0] and '-DRPI5_GATE4_SD_READONLY=1' in commands[0],
        'sd_trial_loader_and_boot_argument': SD_LOADER in image and b' bcm2712_sd_readonly=1\0' in image,
        'kernel_storage_classes_and_transport_linked': required <= symbols and not undefined,
        'linked_kernel_config_parses': syntax['syntax_pass'],
        'fresh_storage_kernel_build_succeeded': build.get('exit_code') == 0
            and build.get('source_unchanged_during_build') is True
            and build.get('fresh_kernel_outputs') is True and bool(build.get('storage_provider'))
            and kernel.resolve() == Path(build['output_root']) / 'obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712',
        'distinct_readonly_sdread_program': userland.get('sd_read_trial') is True
            and entries.get('/bin/sdread', {}).get('mode') == 0o555
            and entries.get('/bin/sdread', {}).get('type') == 'file'
            and b'RPI5XNU:SDREAD:SECTOR LBA=' in init.read_bytes(),
    })
    report.update({'preflight_pass': all(checks.values()), 'sd_readonly_trial': True,
                   'linked_kernel_config': syntax,
                   'shell_baseline_sha256': sha256(shell_baseline),
                   'kernel_build_manifest': str(kernel_build.resolve()),
                   'kernel_build_manifest_sha256': sha256(kernel_build),
                   'scope': 'Host image/build identity only; not SD handoff, reads, a mounted filesystem or durability'})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    for name in ('kernel', 'init', 'gate3-baseline', 'shell-baseline', 'kernel-build'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    report = inspect(args.package, args.kernel, args.init, args.gate3_baseline, args.shell_baseline, args.kernel_build)
    print(json.dumps(report, indent=2))
    return 0 if report['preflight_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
