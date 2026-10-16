#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact combined RP1 v2/96-node/SSH-buffer package, without board I/O."""
import argparse
import json
from pathlib import Path
import types
import re
import subprocess
try:
    from . import root_capacity_profile as root
    from . import check_serial_terminal_package as terminal
    from . import check_zsh_trial_package as zsh
    from . import root_capacity_package as packing
    from .prepare_pid1 import inspect as macho
except ImportError:
    import root_capacity_profile as root
    import check_serial_terminal_package as terminal
    import check_zsh_trial_package as zsh
    import root_capacity_package as packing
    from prepare_pid1 import inspect as macho

ROOT=root.ROOT
KERNEL_SHA='a3a1f4836989462d40f601507d502fe366e5c9d448ea8caaca1f924c1d9d7460'
KERNEL_MANIFEST_SHA='30a8a72bacd9add432d631b0097bf3938f193eac586298e4cb7e072886b23a7a'
ROOT_SHA='18b2213c02353ea6f41baad9af6e5be0df7eadf31b61a19620c023b96f375340'
ROOT_MANIFEST_SHA='7d3c5240cd9b57b9634e2a9e86183a899b7c45823cce26bd12af3ec457f2d9f4'
PROBE_SHA='8b311da88fa7bf19bd7b7d0ad098186f196022afdc7aa2ef6b759d1d4cdbf17e'
NORMAL_FIRMWARE_SHA='413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46'
PACKAGE_SHA='0a9593c91d52dca88e587c155dd3fe53b89cf7d8100faf815c0ddd118348ad91'
CAPACITY_SHA='223318e3f41c7804aad6e1f0baa9dd1e8b538c40311daa04ec05fb4d43c30b08'
sha=terminal.sha256


def inspect(directory):
    directory=directory.resolve()
    if directory.parent!=ROOT/'build/rpi5':raise ValueError('Distinct local loader package required')
    if sha(directory/'capacity.json')!=CAPACITY_SHA or sha(directory/'probe.bin')!=PACKAGE_SHA:
        raise ValueError('Exact topology-enabled final combined package required')
    record=json.loads((directory/'capacity.json').read_text())
    manifest=json.loads((directory/'manifest.json').read_text())
    root_manifest=Path(record['root_manifest']);kernel_manifest=Path(record['kernel_manifest'])
    if sha(root_manifest)!=ROOT_MANIFEST_SHA or sha(kernel_manifest)!=KERNEL_MANIFEST_SHA:
        raise ValueError('Exact corrected combined kernel/root receipts required')
    receipt=json.loads(root_manifest.read_text());kernel=json.loads(kernel_manifest.read_text())
    init=root_manifest.parent/'ramdisk.bin';raw=init.read_bytes()
    pins=record['inputs_sha256']|receipt['inputs_sha256']|receipt['generated_sha256']|kernel['inputs_sha256']|kernel['generated_sha256']
    for name,pin in pins.items():
        if sha(Path(name))!=pin:raise ValueError('Combined package dependency changed: '+name)
    namespace=dict(terminal.inspect.__globals__,inspect_ramroot=root.inspect)
    report=types.FunctionType(terminal.inspect.__code__,namespace,argdefs=terminal.inspect.__defaults__)(
        directory,Path(kernel['kernel']),init,zsh.BASELINE,shell_trial=True)
    image=(directory/'probe.bin').read_bytes();layout=root.inspect(raw);files=root.files_from(raw)
    watchdog_source=(kernel_manifest.parent/'pe_fiq.c').read_text()
    originals=[Path(p) for p,pin in kernel['inputs_sha256'].items() if Path(p).name=='pe_fiq.c' and pin==kernel['original_pe_source_sha256']]
    if len(originals)!=1:raise ValueError('Exact original watchdog source ambiguous')
    baseline_watchdog=originals[0].read_text()
    watchdog_assembly=(kernel_manifest.parent/'pe_fiq.s').read_text().split('_pe_rpi5_watchdog_enable_terminal:',1)[1].split('; -- End function',1)[0]
    baseline=root.files_from((packing.BASE/'ramdisk.bin').read_bytes())
    expected=[]
    for row in layout['entries']:
        isdir=row['type']=='directory'
        expected.append(dict(path=row['path'],mode=row['mode']|(0o40000 if isdir else 0o100000),
            bytes=row['size'],sha256='' if isdir else root.sha(raw[row['offset']:row['offset']+row['size']])))
    loads=zsh.inspect_elf((directory/'probe.elf').read_bytes(),image,0x9000000)
    checks=report['checks'];checks.update(zsh.profile_checks(manifest))
    checks.update(exact_combined_profiles=record.get('profile')=='rpi5-serial-root96-sshbuffer-v1' and
        kernel.get('kernel_profile')=='root96-rp1-config-bounded-v1' and record.get('node_capacity')==96,
        actual_dependency_scans=record.get('actual_compiler_dependencies_verified') is True and bool(record.get('actual_compiles')),
        receipt_image_exact=record['image']==str(directory/'probe.bin') and record['image_sha256']==report['image_sha256'],
        loader_manifest_exact=sha(directory/'manifest.json')==record['loader_manifest_sha256'],
        exact_kernel=report['kernel_sha256']==KERNEL_SHA,
        bounded_watchdog_only_change=watchdog_source==baseline_watchdog.replace(
            '#define RPI5_TERMINAL_WDOG_SECONDS 3600U','#define RPI5_TERMINAL_WDOG_SECONDS 180U',1),
        actual_compiled_180_deadline=len(re.findall(r'mov\s+w\d+, #180\b',watchdog_assembly))==2 and '#3600' not in watchdog_assembly,
        exact_root=report['init_sha256']==ROOT_SHA and record['root_sha256']==ROOT_SHA,
        exact_root_extent=receipt['output_nodes']==33 and len(layout['entries'])==33 and receipt['output_bytes']==len(raw),
        complete_22_file_catalog=expected==receipt['identity_catalog'] and sum(bool(v['sha256']) for v in expected)==22,
        recovery_unchanged=all(files[p]==value for p,value in baseline.items() if p!=packing.IDENTITY_PATH),
        exactly_one_addition=set(files)-set(baseline)=={packing.PROBE_PATH},
        probe_exact=macho(files[packing.PROBE_PATH][0])['sha256']==PROBE_SHA,
        no_kernel_controller_admission=kernel.get('boot_caller_added') is False and kernel.get('full_lifecycle_provider_added') is False,
        static_link_complete=not subprocess.run(['xcrun','nm','-ju',kernel['kernel']],check=True,capture_output=True,text=True,timeout=15).stdout.strip() and kernel.get('complete_kernel_link_proven') is True,
        fixed_storage_off_command=image.count(terminal.TERMINAL_COMMAND+b'\0')==1,
        exact_loader_entry=loads['entry']==manifest.get('entry')==0x9000000,
        stack_budget=zsh.stack_check(manifest['stack_frames'])==manifest.get('gate5_pcie_topology_stack_budget'),
        exact_loader_outputs=all(sha(ROOT/name)==digest for name,digest in manifest['sha256'].items()),
        buffer_result_markers=all(m in files[packing.PROBE_PATH][0] for m in
            (b'RPI5XNU:SSHBUFFER:BEGIN ORIGINAL_BUFFERS RESET_OVERLAY NO_NETWORK NO_KEYS',
             b'RPI5XNU:SSHBUFFER:PASS ROUNDTRIP LOW_MAX_RESET REUSE NOT_SSH_OR_CRYPTO_PROOF')))
    segments=manifest['embedded_kernel']['segments'];base=manifest['embedded_kernel']['virtual_base']
    envelope=max(v['vmaddr']+v['vmsize'] for v in segments)-base
    init_pa=((0x7004000+envelope+0x3fff)&~0x3fff)+0x8000
    report.update(preflight_pass=all(checks.values()),profile='root96-rp1-sshbuffer-bounded-v1',image_bytes=len(image),
        terminal_watchdog_seconds=180,hardware_watchdog_seconds=15,serial_return_deadline_seconds=225,
        capacity_manifest_sha256=sha(directory/'capacity.json'),loader_manifest_sha256=sha(directory/'manifest.json'),
        root_manifest=str(root_manifest),root_manifest_sha256=ROOT_MANIFEST_SHA,identity_catalog=expected,
        kernel_manifest=str(kernel_manifest),kernel_manifest_sha256=KERNEL_MANIFEST_SHA,
        root_mount_marker=f'RPI5XNU:RAMROOT:MOUNT NODES=33 BYTES={len(raw)} READONLY',
        root_copy_marker=f'RPI5XNU:BL33:RAMDISK_MATERIALIZED PA={init_pa:016x} BYTES={len(raw):016x} VERIFIED',
        kernel_copy_marker=f'RPI5XNU:BL33:KERNEL_MATERIALIZED BYTES={envelope:016x} FULL_ENVELOPE_VERIFIED NO_BOOT_ARGS_WRITTEN NO_TRANSFER',
        normal_firmware_sha256=NORMAL_FIRMWARE_SHA,probe_install_path=packing.PROBE_PATH,
        pi_executed=False,ssh_daemon=False,networking=False,controller_initialized=False,durability=False,
        scope='Compiled package/source/layout proof; runtime requires fresh guarded serial trial')
    if not report['preflight_pass']:raise ValueError('Combined package rejected: '+repr([k for k,v in checks.items() if not v]))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path);p.add_argument('--report',type=Path)
    args=p.parse_args();report=inspect(args.package)
    if args.report:
        with args.report.open('x') as out:json.dump(report,out,indent=2);out.write('\n')
    print(json.dumps(report,indent=2))
