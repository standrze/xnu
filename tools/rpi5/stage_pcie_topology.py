#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct declaration-only loader trial; local preflight unless --execute.

Fixed authorized Pi/card and historical W3 preservation chain only. Reuses the
proven shell kernel/root. No HFS mount/write, PCIe access, reboot or rollback.
Unknown remote outcomes require inspection, never an automatic second install.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import check_serial_terminal_package as terminal
import hfs_persistence_capture_core as capture
import probe_install_core as install_core
import write_trial_backups as snapshots
from pcie_stack import check as stack_check
from build_probe import inspect as inspect_elf

ROOT = Path(__file__).resolve().parents[2]
HOST = 'sandrzej@192.168.4.23'
SSH = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
       '-o', 'ConnectTimeout=8', HOST]
CONTROL = ROOT / 'build/rpi5/sd-extension-linux-control-20261012'
CONTROL_PLAN_SHA = 'b88bb6aefd5ae6e6b53b4dd7e8a99b9fd07bdf2f6bade042e421f14ad78243f7'
W3 = '79d5b90aa9821c639e6f9476bd3c7dfd2727d26c4c551b8072dd06570ded0ec3'
KERNEL = ROOT / 'build/rpi5/shell-userland-20261011/kernel.development.bcm2712'
INIT = KERNEL.with_name('ramdisk.bin')
BASELINE = ROOT / 'build/rpi5/bl33-probe-ci45m9zs/probe.bin'
KERNEL_SHA = 'd133f3a21ff9d3397aed7dfdd04210fe79061d8919d5046010dfa1919980a10f'
INIT_SHA = 'd32891113ad2ecdb1637bfdfd58991574026877cfb827a4bd0cd229980541f55'
PASS = b'RPI5XNU:BL33:PCIE_TOPOLOGY:PASS PCIE_MMIO=0 CONFIG_ACCESS=0 DMA=0 NIC_READY=0'
PROTECTED = {
    'probe.gate3-20260927.bin': terminal.GATE3_BASELINE_SHA256,
    'probe.shell-passed-20261011.bin': 'bf01b0eedcce48249a7358772f74613d0b0453217f35576369945de25d50374f',
    'config.txt': 'aaccab184135aca272db4123fcba34e20874ae0959a90aed1ef6fd4d5e18ed28',
    'bl31.bin': '413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46',
    'bcm2712-rpi-5-b.dtb': 'e67017e5d45b97af478ebc93d651a086f2adcb6a650fe453eb9f1cf47e66473f',
}


def package_report(package):
    package = package.resolve()
    if not package.is_relative_to(ROOT / 'build/rpi5'):
        raise ValueError('A distinct local build/rpi5 package is required')
    report = terminal.inspect(package, KERNEL, INIT, BASELINE, shell_trial=True)
    manifest = json.loads((package / 'manifest.json').read_text())
    raw = (package / 'probe.bin').read_bytes()
    elf = (package / 'probe.elf').read_bytes()
    loads = inspect_elf(elf, raw, 0x9000000)
    commands = manifest['commands']
    main = [cmd for cmd in commands if any(Path(item).name == 'probe_main.c' for item in cmd)]
    units = {Path(item).name for cmd in commands for item in cmd if item.endswith('.c')}
    checks = report['checks']
    checks.update(
        proven_shell_kernel=report['kernel_sha256'] == KERNEL_SHA,
        proven_shell_root=report['init_sha256'] == INIT_SHA,
        topology_enabled=manifest.get('gate5_pcie_topology') is True,
        pcie_mmio_disabled=manifest.get('gate5_pcie_mmio_enabled') is False,
        storage_disabled=all(manifest.get(name) is False for name in
            ('gate4_storage_binding_snapshot', 'gate4_sd_readonly', 'gate4_hfs_readonly', 'gate4_hfs_write_trial')),
        topology_compile_switch=len(main) == 1 and '-DRPI5_GATE5_PCIE_TOPOLOGY=1' in main[0],
        topology_units_only={'pcie_fdt.c', 'pcie_topology.c'}.issubset(units) and
            not any(name in units for name in ('pcie_observe.c', 'gem_dma.c', 'sd_pio.c')),
        topology_marker_embedded=PASS in raw,
        expected_loader_entry=loads['entry'] == manifest['entry'] == 0x9000000,
        stack_budget_matches=stack_check(manifest['stack_frames']) == manifest.get('gate5_pcie_topology_stack_budget'),
        source_and_outputs_unchanged=bool(manifest['sha256']) and all(
            terminal.sha256(ROOT / name) == value for name, value in manifest['sha256'].items()),
    )
    report.update(preflight_pass=all(checks.values()),
        loader_manifest_sha256=terminal.sha256(package / 'manifest.json'),
        scope='Host identity/ELF/profile/stack only; placement and runtime declarations need fresh board evidence')
    if not report['preflight_pass']:
        raise ValueError('Gate5 preflight failed: ' + repr([k for k, v in checks.items() if not v]))
    return report


def load_plan(package, boot_id):
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id):
        raise ValueError('Exact current SSD Linux boot UUID required')
    control_path = CONTROL / 'plan.json'
    if terminal.sha256(control_path) != CONTROL_PLAN_SHA:
        raise ValueError('Preserved fixed-card/protected-byte/20-backup control plan changed')
    control = json.loads(control_path.read_text())
    if (len(control['nvme_backups']) != 20 or control['identity_binding']['linux_boot_id_after_write'] != boot_id
            or control['nvme_backups'][-1]['sha256'] != W3):
        raise ValueError('Not the preserved W3 chain/current Linux return')
    report = package_report(package)
    sources = [Path(__file__), Path(capture.__file__), Path(install_core.__file__), Path(snapshots.__file__)]
    return dict(host=HOST, profile='pcie-topology', candidate=report['image'],
        old_image_sha256=W3, new_image_sha256=report['image_sha256'],
        identity_binding=control['identity_binding'], nvme_backups=control['nvme_backups'],
        protected_sha256=control['protected_sha256'], protected_files=PROTECTED,
        linux_boot_id=boot_id, preflight=report, control_plan_sha256=CONTROL_PLAN_SHA,
        source_sha256={str(path): terminal.sha256(path) for path in sources},
        no_hfs_mount=True, no_pcie_access=True, no_config_change=True, no_reboot=True)


PREPARE = r'''
import json,tempfile,subprocess
from pathlib import Path
if subprocess.check_output(['findmnt','-no','SOURCE,FSTYPE,UUID','/'],text=True).split()!=[
    '/dev/nvme0n1p2','ext4','04570742-280b-43cb-9564-73d454243b1c']:
    raise ValueError('Not verified SSD Linux')
base=Path('/home/sandrzej')
if base.resolve()!=base or base.stat().st_dev!=Path('/').stat().st_dev:
    raise ValueError('Candidate directory is not on SSD root')
print(json.dumps(dict(run=tempfile.mkdtemp(prefix='xnu-gate5-topology-',dir=base))))
'''

REMOTE = r'''
if os.geteuid()!=0: raise ValueError('Root required for exact SD partition access')
binding=PLAN['identity_binding']
before=identity(binding); verify_backups(PLAN)
run=Path(PLAN['run'])
if run.resolve()!=run or run.stat().st_dev!=Path('/').stat().st_dev or {p.name for p in run.iterdir()}!={'candidate.bin'}:
    raise ValueError('Fresh exact NVMe installation directory required')
candidate=os.open(run/'candidate.bin',os.O_RDONLY|os.O_NOFOLLOW)
mounted=False; writable=False; directory=None
try:
    if digest_fd(candidate)!=PLAN['new_image_sha256']: raise ValueError('Candidate differs')
    nvme=os.open(run,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        records=[block_snapshot(node,capacity,length,nvme,name) for node,capacity,length,name in (
            ('/dev/mmcblk0',128177930240,512,'mbr.before-write.bin'),
            ('/dev/mmcblk0p1',536870912,536870912,'boot-partition.before-write.img'),
            ('/dev/mmcblk0p2',134217728,134217728,'hfs-partition.before.img'))]
        if {key:row['sha256'] for key,row in zip(('mbr','boot','hfs'),records)}!=PLAN['protected_sha256']:
            raise ValueError('Complete MBR/FAT/HFS differs before mount')
        if identity(binding)!=before: raise ValueError('Identity changed during backups')
        mp=Path('/mnt/xnu-probe')
        if mp.resolve()!=mp or not mp.is_dir(): raise ValueError('Unexpected boot mountpoint')
        subprocess.run(['mount','-o','ro,nosuid,nodev,noexec','/dev/mmcblk0p1',str(mp)],check=True,timeout=15)
        mounted=True
        if subprocess.check_output(['findmnt','-no','SOURCE,FSTYPE','--target',str(mp)],text=True).split()!=['/dev/mmcblk0p1','vfat']:
            raise ValueError('Not exact SD FAT mount')
        directory=os.open(mp,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        def boot_hash(name):
            fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
            try: return digest_fd(fd)
            finally: os.close(fd)
        expected=dict(PLAN['protected_files'],**{'probe.bin':PLAN['old_image_sha256']})
        for name,sha in expected.items():
            if boot_hash(name)!=sha: raise ValueError('Protected/current image differs: '+name)
        old=os.open('probe.bin',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
        try: copy_image(old,nvme,'hfs-cache-buffer-failed.bin',PLAN['old_image_sha256']); os.fsync(nvme)
        finally: os.close(old)
        subprocess.run(['mount','-o','remount,rw,nosuid,nodev,noexec',str(mp)],check=True,timeout=15)
        writable=True
        result=install(directory,candidate,PLAN['old_image_sha256'],PLAN['new_image_sha256'],'pcie-topology')
        subprocess.run(['mount','-o','remount,ro',str(mp)],check=True,timeout=15); writable=False
        expected['probe.bin']=PLAN['new_image_sha256']; expected[result['sd_backup']]=PLAN['old_image_sha256']
        for name,sha in expected.items():
            if boot_hash(name)!=sha: raise ValueError('Post-install protected file differs: '+name)
    finally: os.close(nvme)
finally:
    if directory is not None: os.close(directory)
    os.close(candidate)
    if writable: subprocess.run(['mount','-o','remount,ro','/mnt/xnu-probe'],check=True,timeout=15)
    if mounted: subprocess.run(['umount','/mnt/xnu-probe'],check=True,timeout=15)
after=identity(binding); verify_backups(PLAN)
post={key:block_snapshot(node,capacity,length) for key,node,capacity,length in (
    ('mbr','/dev/mmcblk0',128177930240,512),('boot','/dev/mmcblk0p1',536870912,536870912),
    ('hfs','/dev/mmcblk0p2',134217728,134217728))}
if before!=after or any(post[key]['sha256']!=PLAN['protected_sha256'][key] for key in ('mbr','hfs')):
    raise ValueError('Identity/protected MBR/HFS changed')
result.update(status='installed',run=str(run),identity=after,backups=records,protected_after=post,
    protected_files_sha256=expected,nvme_backups_verified=PLAN['nvme_backups'],
    nvme_previous_image_sha256=full_hash(run/'hfs-cache-buffer-failed.bin',(run/'hfs-cache-buffer-failed.bin').stat().st_size),
    image_sha256=PLAN['new_image_sha256'],no_hfs_mount=True,no_config_change=True,no_reboot=True,boot_unmounted=True)
with (run/'result.json').open('x') as output:
    output.write(json.dumps(result,indent=2)+'\n'); output.flush(); os.fsync(output.fileno())
print(json.dumps(result))
'''


def remote_source(plan):
    sources = []
    for path, sha in plan['source_sha256'].items():
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha: raise ValueError('Installer source changed')
        if path != str(Path(__file__)): sources.append(raw.decode())
    return '\n'.join(sources) + '\nPLAN=json.loads(' + repr(json.dumps(plan)) + ')\n' + REMOTE


def validate_result(result, plan):
    required = dict(status='installed', run=plan['run'], image_sha256=plan['new_image_sha256'],
        preserved_sd_image_sha256=W3, nvme_previous_image_sha256=W3,
        boot_unmounted=True, no_hfs_mount=True, no_config_change=True, no_reboot=True,
        power_loss_atomicity_claimed=False, temporary_published=True,
        sd_backup=install_core.INSTALL_NAMES['pcie-topology'][0],
        nvme_backups_verified=plan['nvme_backups'])
    if any(type(result.get(k)) is not type(v) or result[k] != v for k, v in required.items()):
        raise ValueError('Incomplete install outcome; inspect existing run')
    expected_files = dict(PROTECTED, **{'probe.bin': plan['new_image_sha256'], required['sd_backup']: W3})
    expected_identity = dict(identity=plan['identity_binding']['expected'],
        boot_id=plan['linux_boot_id'], hostname='kamidana')
    if result.get('identity') != expected_identity or result.get('protected_files_sha256') != expected_files:
        raise ValueError('Post-install identity/protected files differ')
    for key, node, length in (('mbr', '/dev/mmcblk0', 512), ('boot', '/dev/mmcblk0p1', 536870912),
                              ('hfs', '/dev/mmcblk0p2', 134217728)):
        after = result.get('protected_after', {}).get(key, {})
        if after.get('device') != node or after.get('bytes') != length or not re.fullmatch('[0-9a-f]{64}', after.get('sha256', '')):
            raise ValueError('Incomplete post-install raw protection coverage')
        if key != 'boot' and after['sha256'] != plan['protected_sha256'][key]:
            raise ValueError('Protected MBR/HFS changed')
    names = ('mbr.before-write.bin', 'boot-partition.before-write.img', 'hfs-partition.before.img')
    expected_backups = [dict(device=node, bytes=size, sha256=plan['protected_sha256'][key], saved_as=name)
        for key, node, size, name in zip(('mbr', 'boot', 'hfs'),
            ('/dev/mmcblk0', '/dev/mmcblk0p1', '/dev/mmcblk0p2'), (512, 536870912, 134217728), names)]
    if result.get('backups') != expected_backups: raise ValueError('Incomplete fresh NVMe snapshots')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--linux-boot-id', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT / 'build/rpi5'):
        parser.error('Fresh local build/rpi5 output directory required')
    plan = load_plan(args.package, args.linux_boot_id)
    args.output.mkdir(parents=True, exist_ok=False)
    def save(): (args.output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    save()
    if not args.execute:
        print('LOCAL_PLAN_ONLY_NO_NETWORK_OR_DEVICE_ACCESS ' + str(args.output)); return 0
    if load_plan(args.package, args.linux_boot_id) != plan: raise ValueError('Inputs changed before SSH')
    prepared = subprocess.run(SSH + ['python3 -'], input=PREPARE, text=True, capture_output=True, check=True, timeout=30)
    run = json.loads(prepared.stdout)['run']
    if not re.fullmatch(r'/home/sandrzej/xnu-gate5-topology-[a-z0-9_]{8}', run): raise ValueError('Unexpected remote run')
    plan['run'] = run; save()
    subprocess.run(['scp', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8',
                    plan['candidate'], HOST + ':' + run + '/candidate.bin'], check=True, timeout=120)
    source = remote_source(plan)
    (args.output / 'remote-source.sha256').write_text(hashlib.sha256(source.encode()).hexdigest() + '\n')
    try:
        response = subprocess.run(SSH + ['sudo -n python3 -'], input=source, text=True, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired as error:
        for name, value in (('remote.stdout', error.stdout), ('remote.stderr', error.stderr)):
            (args.output / name).write_bytes(value.encode() if isinstance(value, str) else value or b'')
        (args.output / 'outcome-unknown.txt').write_text('Inspect existing remote run; do not retry or roll back automatically.\n')
        raise
    for name, value in (('remote.stdout', response.stdout), ('remote.stderr', response.stderr)):
        (args.output / name).write_text(value)
    response.check_returncode()
    result = json.loads(response.stdout)
    validate_result(result, plan)
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(args.output); return 0


if __name__ == '__main__': raise SystemExit(main())
