#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only HFS trial package identity; never stages, mounts or opens serial."""
import argparse
import json
from pathlib import Path
import subprocess

from check_sd_read_package import inspect as sd_inspect, sha256
from ramroot import inspect as ramroot_inspect
from kernel_config_syntax import inspect_kernel_config

HFS_LOADER = b'RPI5XNU:BL33:HFS_READONLY_TRIAL'
REQUIRED_HFS_CHECKS = frozenset((
    'separate_hfs_readonly_flags', 'hfs_loader_marker_and_boot_argument',
    'hfs_services_linked_and_ordered', 'reviewed_hfs_service_adaptation',
    'distinct_readonly_hfsro_program', 'fixed_hfs_mountpoint_in_ramroot'))
REQUIRED_HFS_CONFIG = (
    "'IOClass'='com_apple_filesystems_hfs_encodings'",
    "'IOClass'='com_apple_filesystems_hfs'",
    "'IOResourceMatch'=(IOBSD, 'RPI5HFSEncodingsReady')",
)


def inspect(package, kernel, init, gate3_baseline, shell_baseline, kernel_build):
    report = sd_inspect(package, kernel, init, gate3_baseline, shell_baseline, kernel_build)
    manifest = json.loads((package / 'manifest.json').read_text())
    userland = json.loads((init.parent / 'manifest.json').read_text())
    build = json.loads(kernel_build.read_text())
    screen = Path(build['storage_provider']['screen_manifest'])
    provider = json.loads(screen.read_text())
    service_patch = Path(__file__).with_name('patches') / 'hfs-builtin-service.patch'
    image = (package / 'probe.bin').read_bytes()
    entries = {e['path']: e for e in ramroot_inspect(init.read_bytes())['entries']}
    commands = [c for c in manifest['commands'] if any(Path(x).name == 'probe_main.c' for x in c)]
    symbols = set(subprocess.check_output(['xcrun', 'nm', '-jU', str(kernel)], text=True).splitlines())
    classes = ('com_apple_filesystems_hfs', 'com_apple_filesystems_hfs_encodings')
    required = {'__ZN' + str(len(name)) + name + '10gMetaClassE' for name in classes}
    syntax = inspect_kernel_config(kernel, REQUIRED_HFS_CONFIG)
    checks = report['checks']
    checks.update({
        'separate_hfs_readonly_flags': manifest.get('gate4_hfs_readonly') is True and
            len(commands) == 1 and '-DRPI5_GATE4_HFS_READONLY=1' in commands[0],
        'hfs_loader_marker_and_boot_argument': HFS_LOADER in image and
            b' bcm2712_hfs=1 bcm2712_sd_readonly=1\0' in image,
        'hfs_services_linked_and_ordered': required <= symbols and syntax['syntax_pass'] and
            syntax['required_fragments_present'].keys() == set(REQUIRED_HFS_CONFIG) and
            all(syntax['required_fragments_present'].values()),
        'reviewed_hfs_service_adaptation': provider.get('adapted') is True and
            provider.get('service_patch_sha256') == sha256(service_patch) and
            sha256(screen) == build['storage_provider'].get('screen_manifest_sha256'),
        'distinct_readonly_hfsro_program': userland.get('hfs_read_trial') is True and
            entries.get('/bin/hfsro', {}).get('type') == 'file' and
            entries.get('/bin/hfsro', {}).get('mode') == 0o555 and
            b'RPI5XNU:HFSRO:MOUNTED' in init.read_bytes(),
        'fixed_hfs_mountpoint_in_ramroot': entries.get('/mnt/hfs', {}).get('type') == 'directory' and
            entries.get('/mnt/hfs', {}).get('mode') == 0o555 and
            entries.get('/mnt/hfs/.anchor', {}).get('type') == 'file' and
            entries.get('/mnt/hfs/.anchor', {}).get('mode') == 0o444 and
            entries.get('/mnt/hfs/.anchor', {}).get('size') == 0,
    })
    report.update({'preflight_pass': all(checks.values()), 'hfs_readonly_trial': True,
                   'linked_hfs_configuration': syntax,
                   'scope': 'Host package/build identity only; not HFS registration, partitioning, mounts, file reads or durability'})
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
