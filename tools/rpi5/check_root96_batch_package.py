#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact source/link/root/FDT/readiness audit of the tagged 41-node candidate."""
import argparse
import difflib
import json
from pathlib import Path
try:
    from . import build_root96_batch_package as builder
except ImportError:
    import build_root96_batch_package as builder


def same(a,b):return json.dumps(a,sort_keys=True)==json.dumps(b,sort_keys=True)


def inspect_record(package,m):
    package=package.resolve()
    if package.parent!=builder.ROOT/'build/rpi5' or not package.name.startswith('root96-batch-'):
        raise ValueError('Distinct root96-batch package required')
    pins,old,root,km=builder.inputs()
    expected_names=builder.generated_names()
    if any(p.is_symlink() or not p.is_file() for p in package.iterdir()):raise ValueError('Regular package artifacts required')
    if {p.name for p in package.iterdir()}!=expected_names|{'manifest.json'}:raise ValueError('Generated artifact set differs')
    generated={str(package/name):builder.sha(package/name) for name in expected_names}
    if m.get('generated_sha256')!=generated:raise ValueError('Complete generated closure differs')
    headers=builder.header_closure(package,old)
    if m.get('headers_sha256')!=headers:raise ValueError('Complete header closure differs')
    commands=[dict(command=c,returncode=0,log=str(package/(label+'.log')))
              for c,label in zip(builder.commands_for(package,old),builder.LABELS)]
    if m.get('commands')!=commands:raise ValueError('Exact main/payload/link command sequence differs')
    before,after=builder.derive_main(m.get('tag'))
    diff=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='accepted/probe_main.c',tofile='probe_main.c'))
    image=(package/'probe.bin').read_bytes();rootraw=(builder.ROOT_DIR/'ramdisk.bin').read_bytes()
    payload=builder.base.encode(builder.KERNEL.read_bytes(),rootraw)
    assembly='.section .payload,"a"\n.balign 64\n.incbin "'+str(package/'payload.bin')+'"\n'
    layout=builder.base.retained.device.accepted.old.inspect_elf((package/'probe.elf').read_bytes(),image,builder.base.BASE)
    end=max(row['address']+row['memory_size'] for row in layout['loads'])
    g=builder.geometry();contract=builder.base.handoff_contract(package,builder.KERNEL)
    frames,budgets=builder.support.stack_for(package,old)
    checks=dict(
        exact_profile=m.get('profile')==builder.PROFILE,
        exact_tagged_source=(package/'probe_main.c').read_text()==after and (package/'probe_main.c.diff').read_text()==diff,
        original_loader_replayed=builder.sha(package/'baseline.bin')==old['image_sha256'] and m.get('original_loader_reproduced') is True,
        exact_payload=(package/'payload.bin').read_bytes()==payload and image.count(payload)==1 and (package/'payload.S').read_text()==assembly,
        exact_image=m.get('image')==str(package/'probe.bin') and m.get('image_sha256')==builder.sha(package/'probe.bin') and m.get('image_bytes')==len(image),
        exact_kernel=m.get('kernel')==str(builder.KERNEL) and m.get('kernel_sha256')==builder.KERNEL_SHA and
            m.get('kernel_manifest')==str(builder.KERNEL_DIR/'manifest.json') and m.get('kernel_manifest_sha256')==builder.KERNEL_MANIFEST_SHA,
        exact_root=m.get('root')==str(builder.ROOT_DIR/'ramdisk.bin') and m.get('root_sha256')==builder.root_check.IMAGE_SHA and
            m.get('root_manifest')==str(builder.ROOT_DIR/'manifest.json') and m.get('root_manifest_sha256')==builder.root_check.MANIFEST_SHA,
        actual_root_schema=m.get('embedded_init')==builder.root_profile.inspect(rootraw),
        exact_root_provenance=m.get('root_profile_audit')==root,
        actual_handoff=m.get('handoff')==contract,
        raw_elf_and_entry=m.get('elf')==layout and m.get('entry')==builder.base.BASE,
        exact_geometry=m.get('geometry')==g and g['root_end']<=builder.base.BASE and end<0xb000000,
        trial_marker=m.get('trial_marker')==builder.marker(m['tag']) and
            image[:contract['payload_offset']].count((builder.marker(m['tag'])+'\r\n\0').encode())==1,
        terminal_command=m.get('terminal_bootargs')==builder.base.failed.terminal.TERMINAL_COMMAND.decode() and
            image.count(builder.base.failed.terminal.TERMINAL_COMMAND+b'\0')==1,
        four_cpu_profile=all(flag in commands[2]['command'] for flag in
            ('-DRPI5_GATE3_CPU_ON_ALL=1','-DRPI5_SERIAL_TERMINAL=1','-DRPI5_GATE4_STORAGE=0',
             '-DRPI5_PCIE_DEVICE_HANDOFF=1','-DRPI5_FIRMWARE_FDT_HANDOFF=1')),
        unchanged_deadline=m.get('terminal_watchdog_seconds')==180 and m.get('hardware_watchdog_seconds')==15,
        ready_v2=m.get('watchdog_ready_marker')==builder.WATCHDOG_MARKER and m.get('watchdog_ready_profile')==builder.WATCHDOG_PROFILE,
        normal_firmware=m.get('normal_firmware_sha256')==builder.base.failed.NORMAL_FIRMWARE_SHA,
        actual_stack=same(m.get('stack_frames'),frames) and same(m.get('stack_budgets'),budgets),
        exact_object_scope=m.get('only_payload_and_tagged_main_replaced') is True and m.get('original_loader_manifest_sha256')==builder.base.LOADER_SHA,
        tools_unchanged=m.get('tool_identity')==builder.base.tool_identity(),
        no_board_claim=all(m.get(k) is False for k in ('installed','physical_execution','controller_initialized','networking')))
    if not all(checks.values()):raise ValueError('Batch package rejected: '+repr([k for k,v in checks.items() if not v]))
    # Independently rerun actual C geometry/serialization and the actual native
    # loader comparison, rather than trusting receipt booleans or caller maps.
    native_handoff=builder.handoff.audit(builder.LOADER,builder.KERNEL,g['kernel_end'],g['root_bytes'],end)
    native_macho=builder.native.compare(builder.KERNEL,package)
    builder.merge(pins,native_handoff['inputs_sha256']);builder.base.verify(pins)
    if m.get('inputs_sha256')!=pins:raise ValueError('Complete independent input closure differs')
    if not same(m.get('native_handoff'),native_handoff) or not same(m.get('native_macho'),native_macho):
        raise ValueError('Actual native handoff/copy proof differs')
    return dict(profile=builder.PROFILE,preflight_pass=True,checks=checks,image=str(package/'probe.bin'),
        image_sha256=m['image_sha256'],image_bytes=len(image),loader_manifest_sha256=builder.sha(package/'manifest.json'),
        trial_marker=m['trial_marker'],tag=m['tag'],kernel_sha256=builder.KERNEL_SHA,
        kernel_manifest=str(builder.KERNEL_DIR/'manifest.json'),kernel_manifest_sha256=builder.KERNEL_MANIFEST_SHA,
        root_manifest=str(builder.ROOT_DIR/'manifest.json'),root_manifest_sha256=builder.root_check.MANIFEST_SHA,
        root_sha256=builder.root_check.IMAGE_SHA,root_nodes=41,root_files=29,identity_catalog=json.loads((builder.ROOT_DIR/'manifest.json').read_text())['identity_catalog'],
        handoff=contract,root_copy_marker=g['root_copy_marker'],kernel_copy_marker=g['kernel_copy_marker'],root_mount_marker=g['root_mount_marker'],
        watchdog_ready_marker=builder.WATCHDOG_MARKER,watchdog_ready_profile=builder.WATCHDOG_PROFILE,
        terminal_watchdog_seconds=180,hardware_watchdog_seconds=15,serial_return_deadline_seconds=225,
        normal_firmware_sha256=builder.base.failed.NORMAL_FIRMWARE_SHA,native_handoff=native_handoff,
        pi_executed=False,ssh_daemon=False,networking=False,controller_initialized=False,
        scope='Tagged retained-FDT loader, actual kernel/root geometry and serialized handoff; not Pi acceptance')


def inspect(package):
    package=package.resolve()
    return inspect_record(package,json.loads((package/'manifest.json').read_text()))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('package',type=Path)
    print(json.dumps(inspect(parser.parse_args().package),indent=2,sort_keys=True))
