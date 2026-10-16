#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct write-trial package screen. No serial, mounting, staging or reboot.

Does not reuse/relax the read-only package screen. All checks are host identity,
linked wiring or provenance checks, never card-cache or durability evidence.
"""
import argparse
import json
from pathlib import Path
import subprocess

from audit_macho import inspect as inspect_macho
from audit_storage_build import PI_STORAGE_WRITE_INPUTS, PI_STORAGE_WRITE_UNITS
from check_hfs_read_package import REQUIRED_HFS_CONFIG
from check_hfs_stats_package import linked_getter
from check_sd_read_package import SHELL_BASELINE_SHA256
from check_serial_terminal_package import inspect as shell_inspect, sha256
from kernel_config_syntax import inspect_kernel_config
from ramroot import inspect as inspect_ramroot

ROOT = Path(__file__).resolve().parents[2]
HFS_READ_BASELINE_SHA256 = '9defaf57a932aca9dfca06ad928eca4fe3e9bbd07fb5c7562b1b80c4df28222a'
WRITE_LOADER = b'RPI5XNU:BL33:HFS_WRITE_TRIAL DMA=0 HFS_EXTENT_ONLY DURABILITY_VERIFIED=0'
WRITE_ARGUMENT = b' bcm2712_hfs=1 bcm2712_sd_write_trial=1\0'
WRITE_CLASS = "'IOClass'=BCM2712SDWriteStorage;"
READ_CLASS = "'IOClass'=BCM2712SDStorage;"


def profile_checks(package, userland, build, screen):
    """Pure metadata checks; caller separately verifies actual bytes/hashes."""
    commands = [c for c in package.get('commands', []) if any(Path(x).name == 'probe_main.c' for x in c)]
    required = {'-DRPI5_GATE4_STORAGE=1', '-DRPI5_GATE4_HFS_WRITE_TRIAL=1',
                '-DRPI5_GATE4_SD_READONLY=0', '-DRPI5_GATE4_HFS_READONLY=0'}
    return {
        'explicit_distinct_write_loader_profile': package.get('gate4_hfs_write_trial') is True
            and package.get('gate4_storage_binding_snapshot') is True
            and package.get('gate4_sd_readonly') is False and package.get('gate4_hfs_readonly') is False
            and len(commands) == 1 and required <= set(commands[0]),
        'explicit_distinct_write_userland_profile': userland.get('hfs_write_trial') is True
            and userland.get('hfs_read_trial') is False and userland.get('sd_read_trial') is False,
        'fresh_successful_source_stable_write_kernel': build.get('exit_code') == 0
            and build.get('fresh_kernel_outputs') is True and build.get('source_unchanged_during_build') is True
            and build.get('storage_provider', {}).get('write_trial') is True
            and 'RPI5_STORAGE_WRITE_TRIAL=1' in build.get('command', []),
        'exclusive_complete_write_provider_screen': screen.get('write_trial') is True
            and screen.get('adapted') is True and screen.get('all_core_units') is True
            and screen.get('all_screened_units_compiled') is True
            and screen.get('partial_link', {}).get('returncode') == 0
            and all(screen.get('partial_link', {}).get(key) == [] for key in
                    ('missing_required_definitions', 'not_defined_in_reference_kernel', 'forbidden_profile_definitions')),
    }


def inspect(package, kernel, init, gate3_baseline, shell_baseline, hfs_baseline, kernel_build):
    report = shell_inspect(package, kernel, init, gate3_baseline, shell_trial=True)
    loader = json.loads((package / 'manifest.json').read_text())
    userland = json.loads((init.parent / 'manifest.json').read_text())
    build = json.loads(kernel_build.read_text())
    provider = build['storage_provider']
    screen_path = Path(provider['screen_manifest'])
    screen = json.loads(screen_path.read_text())
    checks = report['checks']
    checks.update(profile_checks(loader, userland, build, screen))
    image = (package / 'probe.bin').read_bytes()
    archive = init.read_bytes()
    entries = {e['path']: e for e in inspect_ramroot(archive)['entries']}
    executable = (init.parent / 'userland').read_bytes()
    kernel_bytes = kernel.read_bytes()
    symbols = set(subprocess.check_output(['xcrun', 'nm', '-jU', str(kernel)], text=True).splitlines())
    undefined = subprocess.check_output(['xcrun', 'nm', '-ju', str(kernel)], text=True).splitlines()
    user_symbols = set(subprocess.check_output(['xcrun', 'nm', '-jU', str(init.parent / 'userland')], text=True).splitlines())
    required_symbols = {'__ZN21BCM2712SDWriteStorage10gMetaClassE', '__ZN20IOBlockStorageDriver10gMetaClassE',
                        '__ZN16IOMediaBSDClient10gMetaClassE', '__ZN22IOFDiskPartitionScheme10gMetaClassE',
                        '_rpi5_sd_start_identified', '_rpi5_sd_cache_probe', '_rpi5_sd_cache_probe_traced', '_rpi5_sd_write_authorize',
                        '_rpi5_sd_write_sector', '_rpi5_sd_write_wait_ready', '_rpi5_sd_transfer'}
    for name in ('com_apple_filesystems_hfs', 'com_apple_filesystems_hfs_encodings'):
        required_symbols.add('__ZN' + str(len(name)) + name + '10gMetaClassE')
    syntax = inspect_kernel_config(kernel, (*REQUIRED_HFS_CONFIG, WRITE_CLASS, READ_CLASS))
    fragments = syntax['required_fragments_present']
    artifact = build.get('kernel_artifact', {})
    storage_inputs = screen.get('pi_storage_input_sha256', {})
    pi_rows = [r for r in screen.get('results', []) if r.get('family') == 'rpi5-storage']
    checks.update({
        'passed_shell_and_hfs_images_preserved': sha256(shell_baseline) == SHELL_BASELINE_SHA256
            and sha256(hfs_baseline) == HFS_READ_BASELINE_SHA256
            and report['image_sha256'] not in (SHELL_BASELINE_SHA256, HFS_READ_BASELINE_SHA256),
        'actual_exclusive_write_boot_command': WRITE_LOADER in image and WRITE_ARGUMENT in image
            and b' bcm2712_sd_readonly=' not in image and b'RPI5XNU:BL33:HFS_READONLY_TRIAL' not in image,
        'actual_linked_write_provider_and_transport': required_symbols <= symbols and not undefined
            and '__ZN16BCM2712SDStorage10gMetaClassE' not in symbols,
        'actual_linked_exclusive_configuration_and_hfs_ordering': syntax['syntax_pass']
            and all(fragments.get(name) is True for name in (*REQUIRED_HFS_CONFIG, WRITE_CLASS))
            and fragments.get(READ_CLASS) is False,
        'kernel_bytes_bound_to_fresh_build': artifact.get('sha256') == sha256(kernel)
            and artifact.get('bytes') == len(kernel_bytes) and artifact.get('path') == str(kernel.resolve())
            and kernel.resolve() == Path(build['output_root']) / 'obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712',
        'storage_screen_manifest_unchanged': sha256(screen_path) == provider.get('screen_manifest_sha256'),
        'complete_write_sources_and_headers_unchanged': storage_inputs.keys() == set(PI_STORAGE_WRITE_INPUTS)
            and all(sha256(ROOT / 'iokit/Kernel' / name) == value for name, value in storage_inputs.items())
            and len(pi_rows) == len(PI_STORAGE_WRITE_UNITS)
            and {r['unit'] for r in pi_rows} == set(PI_STORAGE_WRITE_UNITS),
        'actual_write_utilities_embedded_and_linked': {'_hfsrw_main', '_hfswrite_main'} <= user_symbols
            and '_hfsro_main' not in user_symbols and '_sdread_main' not in user_symbols
            and all(entries.get('/bin/' + name, {}).get('mode') == 0o555
                    and entries['/bin/' + name].get('type') == 'file'
                    and archive[entries['/bin/' + name]['offset']:entries['/bin/' + name]['offset']
                                + entries['/bin/' + name]['size']] == executable for name in ('hfsrw', 'hfswrite'))
            and b'RPI5XNU:HFSRW:UNMOUNTED' in archive
            and b'RPI5XNU:HFSWRITE:BATCH_FSYNCED FILES=5 RAW_WRITES=0 DURABILITY_VERIFIED=0' in archive,
        'write_utilities_explicitly_compiled_and_inputs_unchanged': bool(userland.get('source_inputs_sha256'))
            and all(sha256(Path(name)) == value for name, value in userland['source_inputs_sha256'].items())
            and all('-DRPI5_HFS_WRITE_TRIAL=1' in c for c in userland['commands'][:-1]),
        'fixed_immutable_covered_mountpoint': entries.get('/mnt/hfs', {}).get('type') == 'directory'
            and entries.get('/mnt/hfs', {}).get('mode') == 0o555
            and entries.get('/mnt/hfs/.anchor', {}).get('type') == 'file'
            and entries.get('/mnt/hfs/.anchor', {}).get('size') == 0,
    })
    wiring = linked_getter(kernel_bytes, inspect_macho(kernel_bytes)['segments'],
        subprocess.check_output(['xcrun', 'nm', '-nm', str(kernel)], text=True),
        (ROOT / 'bsd/sys/mount.h').read_text())
    checks['ramroot_statfs_getter_wired'] = True
    report.update(preflight_pass=all(checks.values()), hfs_write_trial=True,
        kernel_build_manifest=str(kernel_build.resolve()), kernel_build_manifest_sha256=sha256(kernel_build),
        linked_write_configuration=syntax, linked_ramroot_statfs=wiring,
        hfs_read_baseline_sha256=sha256(hfs_baseline),
        scope='Host write-package identity and linked wiring only; not card admission/cache state, SD writes or durability')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    for name in ('kernel', 'init', 'gate3-baseline', 'shell-baseline', 'hfs-baseline', 'kernel-build', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    report = inspect(args.package, args.kernel, args.init, args.gate3_baseline, args.shell_baseline,
                     args.hfs_baseline, args.kernel_build)
    with args.output.open('x') as output:
        output.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['preflight_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
