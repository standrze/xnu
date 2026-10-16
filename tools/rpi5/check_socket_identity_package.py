#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Pinned v2 identity/socket boot package; no hardware or installation actions."""
import argparse
import json
from pathlib import Path

try:
    from . import check_socketprobe_package as old
    from . import prepare_socket_identity_root as root
except ImportError:
    import check_socketprobe_package as old
    import prepare_socket_identity_root as root

INIT = root.old.ROOT/'build/rpi5/socket-identity-root-20261012-devfs/ramdisk.bin'
INIT_SHA = '3fa5ed9f501cedd744b0d6d75cc0886837db562f3bd42282284d82e2798d9a27'
PROBE_SHA = '45c08337ce9ba453a56f7097af5240bb93a17a48c081d511bd878c659c25d0ca'
RECEIPT_SHA = 'ea24195e8e816583654006856285812b133464f32e02bc6d2208497336ae4abe'


def inspect(package):
    package=package.resolve()
    if not package.is_relative_to(root.old.ROOT/'build/rpi5'):
        raise ValueError('Separate build/rpi5 package required')
    accepted=old.metadata.inspect(old.ACCEPTED)
    wiring,_=root.kernel_calls()
    report=old.terminal.inspect(package,old.metadata.KERNEL,INIT,old.BASELINE,shell_trial=True)
    manifest=json.loads((package/'manifest.json').read_text())
    receipt=json.loads(INIT.with_name('manifest.json').read_text())
    diagnostic=INIT.with_name('socketprobe').read_bytes()
    reconstructed,preservation=root.old.prepare(root.old.ACCEPTED_ROOT.read_bytes(),diagnostic,root.old.ROOT_PIN)
    image=(package/'probe.bin').read_bytes()
    loads=old.inspect_elf((package/'probe.elf').read_bytes(),image,0x9000000)
    layout=root.inspect(INIT.read_bytes())
    expected=[]
    for entry in layout['entries']:
        directory=entry['type']=='directory'
        data=INIT.read_bytes()[entry['offset']:entry['offset']+entry['size']]
        expected.append(dict(path=entry['path'],mode=entry['mode']|(0o40000 if directory else 0o100000),
                             bytes=entry['size'],sha256='' if directory else root.old.sha(data)))
    checks=report['checks']; checks.update(old.profile_checks(manifest))
    checks.update(
        accepted_kernel_unchanged=report['kernel_sha256']==old.metadata.KERNEL_SHA==accepted['kernel_sha256'],
        diagnostic_binary_pinned=old.terminal.sha256(INIT.with_name('socketprobe'))==PROBE_SHA,
        diagnostic_root_pinned=report['init_sha256']==INIT_SHA,
        diagnostic_receipt_pinned=old.terminal.sha256(INIT.with_name('manifest.json'))==RECEIPT_SHA,
        exact_additive_root=reconstructed==INIT.read_bytes(),
        preserved_files_match=receipt.get('preserved_files_sha256')==preservation['preserved_files_sha256'],
        exact_catalog=receipt.get('identity_catalog')==expected,
        generated_catalog_exact=INIT.with_name('rootidentity_catalog.h').read_text()==root.header(root.catalog(root.old.ACCEPTED_ROOT.read_bytes())),
        exact_root_extent=receipt.get('output_nodes')==32 and receipt.get('output_bytes')==1916928,
        actual_linked_sysent=receipt.get('linked_sysent')==wiring,
        actual_storage_guard=accepted['linked_storage_entry_guard']['absent_or_not_one_returns_false'] is True,
        storage_off_command=image.count(old.terminal.TERMINAL_COMMAND+b'\0')==1,
        loader_entry_exact=loads['entry']==manifest.get('entry')==0x9000000,
        identity_and_socket_markers=all(marker in image for marker in (
            b'ROOTIDENTITY:BEGIN:FIXED_CATALOG_V1', b'ROOTIDENTITY:PASS:COMPARE_SELF_AND_EXTENT_EXTERNALLY',
            b'SOCKETPROBE:BEGIN:RAW_DARWIN_V1',b'SOCKETPROBE:END:NOT_ETHERNET_OR_SSH_PROOF')),
        root_sources_unchanged=all(mapping and all(old.terminal.sha256(Path(name))==pin
            for name,pin in mapping.items()) for mapping in
            (receipt.get('source_inputs_sha256',{}),receipt.get('sdk_headers_sha256',{}))),
        loader_sources_and_outputs_unchanged=bool(manifest.get('sha256')) and all(
            old.terminal.sha256(root.old.ROOT/name)==pin for name,pin in manifest['sha256'].items()),
        expected_stack=old.stack_check(manifest['stack_frames'])==manifest.get('gate5_pcie_topology_stack_budget'))
    report.update(preflight_pass=all(checks.values()),image_bytes=len(image),
                  loader_manifest_sha256=old.terminal.sha256(package/'manifest.json'),
                  root_manifest_sha256=RECEIPT_SHA,identity_catalog=expected,
                  root_mount_marker='RPI5XNU:RAMROOT:MOUNT NODES=32 BYTES=1916928 READONLY',
                  install_path=root.old.INSTALL_PATH,linked_sysent=wiring,
                  scope='Unstaged v2 identity/socket package; not Pi socket/NIC/SSH acceptance',
                  pi_executed=False,socket_semantics_proven=False,networking=False,
                  nic_ready=False,ssh_proven=False,durability=False,sd_actions=0,serial_actions=0,reboots=0)
    if not report['preflight_pass']:
        raise ValueError('Identity/socket package refused: '+repr([k for k,v in checks.items() if not v]))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',type=Path); parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args(); report=inspect(args.package)
    with args.report.open('x') as stream: json.dump(report,stream,indent=2,sort_keys=True); stream.write('\n')
    print(json.dumps(dict(image_sha256=report['image_sha256'],image_bytes=report['image_bytes'],
                         checks=len(report['checks']),preflight_pass=True,pi_executed=False)))


if __name__=='__main__': main()
