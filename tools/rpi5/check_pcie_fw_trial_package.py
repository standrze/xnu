#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only audit of paired-firmware ABI trial. Never hardware admission."""
import argparse
import json
from pathlib import Path
import struct
try:
    from . import build_pcie_fw_trial as builder
    from . import check_recovery_package as recovery
except ImportError:
    import build_pcie_fw_trial as builder
    import check_recovery_package as recovery


def expected_leaves():
    leaves=recovery.expected_leaves()
    leaves['rpi5_pcie_fw_smccc']=(0xa9be7bfd,0x910003fd,0xa90153f3,0xaa0203f3,
        *range(0xaa1f03e2,0xaa1f03e8),0xd5033f9f,0xd4000003,0xd5033fdf,
        0xa9000660,0xa9010e62,0xa94153f3,0xa8c27bfd,0xd65f03c0)
    leaves['rpi5_fw_trial_daif']=(0xd53b4220,0xd65f03c0)
    leaves['rpi5_fw_trial_affinity']=(0xd53800a0,0xd29fffe9,0xf2a01fe9,0xf2c01fe9,0x8a090000,0xd65f03c0)
    for name,opcode in (('rpi5_fw_trial_gic_load',0xb9400120),('rpi5_fw_trial_gic_store',0xb9000121)):
        leaves[name]=(0xd2920009,0xf2afffe9,0xf2c00209,0x8b204129,
            0xd5033f9f,opcode,0xd5033f9f,0xd65f03c0)
    return leaves


def read_manifest(package):return json.loads((package/'manifest.json').read_text())


def inspect(package):
    package=package.resolve()
    if package.parent!=builder.ROOT/'build/rpi5' or not package.name.startswith('pcie-fwabi-'):
        raise ValueError('Distinct local firmware ABI package required')
    m=read_manifest(package);tag=m.get('trial_tag')
    commands=builder.commands_for(package,tag)
    binary,elf=package/'probe.bin',package/'probe.elf';raw=binary.read_bytes()
    loads=builder.inspect_elf(elf.read_bytes(),raw,builder.BASE)
    inputs=builder.input_pins();generated={str(p):builder.sha(p) for p in builder.outputs_for(package)}
    symbols=builder.symbols_for(elf);frames,budget=builder.stack_for(package,symbols)
    leaves={}
    for name,expected in expected_leaves().items():
        leaves[name]=recovery.leaf_words(raw,symbols,name,len(expected)*4)==expected
    checks=dict(
        exact_profile=m.get('profile')==builder.PROFILE,
        exact_input_firmware_chain=m.get('inputs_sha256')==inputs,
        exact_generated_objects_and_image=m.get('generated_sha256')==generated,
        exact_commands=m.get('commands')==commands,
        actual_tools_unchanged=m.get('tool_identity')==builder.tool_identity(),
        paired_accepted_firmware=m.get('firmware_image')==str(builder.FIRMWARE_BIN) and
            m.get('firmware_sha256')==builder.FIRMWARE_SHA and
            m.get('firmware_manifest_sha256')==builder.FIRMWARE_MANIFEST_SHA,
        entry_and_loads=m.get('entry')==loads['entry']==builder.BASE and m.get('loads')==loads['loads'],
        raw_extent=m.get('image')==str(binary) and m.get('image_bytes')==len(raw),
        emitted_smccc_and_fixed_pm_gic_context_leaves=all(leaves.values()),
        actual_clients_and_fdt_decoder_linked=all(name in symbols for name in (
            'rpi5_pcie_fw_client_begin','rpi5_pcie_fw_client_check','rpi5_pcie_irq_begin','rpi5_pcie_irq_check',
            'rpi5_pcie_watchdog_begin','rpi5_pcie_watchdog_check','rpi5_fdt_pcie_rp1',
            'probe_main','probe_el1_main','probe_exception')),
        no_controller_or_secondary_implementations=not any(name.startswith(('rpi5_pcie_reset_',
            'rpi5_pcie_serdes_','rpi5_pcie_config_','rpi5_pcie_link_','rpi5_psci_cpu_')) or
            name in ('probe_secondary_entry','probe_irq_entry') for name in symbols),
        conservative_stack=m.get('stack_frames')==frames and m.get('stack_budget')==budget,
        declared_bounded_trial=m.get('selective_gic_disable_writes')==3 and
            m.get('watchdog_reload_once_seconds')==15 and m.get('firmware_checks')==3,
        no_hardware_activation_claim=all(m.get(k) is False for k in builder.FALSE_CLAIMS),
        source_stable=m.get('sources_stable') is True,
        secure_read_profile=m.get('secure_verifier_mmio_reads') is True,
        tagged_complete_markers=all(p in raw for p in (
            (' TAG='+tag).encode(),b'RPI5XNU:FWABI:',b'ENTRY\0',b'EL1\0',b'ARMED\0',b'MASKED\0',
            b'RPC_BEGIN\0',b'RPC_END\0',b'CHECKED\0',b'FAULT\0',b'RESULT\0',b'STOP\0',
            b'NO_RELOAD WAIT_FOR_RESET CONTROLLER_WRITES=0 DMA=0 RESET_RETURN_PROVEN=0')),
    )
    if not all(checks.values()):raise ValueError('Firmware ABI package refused: '+repr([k for k,v in checks.items() if not v]))
    return dict(preflight_pass=True,checks=checks,leaf_checks=leaves,image=str(binary),image_bytes=len(raw),
        image_sha256=builder.sha(binary),manifest_sha256=builder.sha(package/'manifest.json'),trial_tag=tag,
        firmware_sha256=builder.FIRMWARE_SHA,stack_budget=budget,installation_admitted=False,
        physical_execution=False,hardware_recovery_proven=False,
        scope='Actual paired source/ELF/leaves/stack audit, not permission to install or board/runtime acceptance')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('package',type=Path)
    print(json.dumps(inspect(parser.parse_args().package),indent=2,sort_keys=True))
