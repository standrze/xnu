#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only admission audit of the distinct no-input PCIe-ID package."""
import argparse
import json
from pathlib import Path
import struct
try:
    from . import build_pcie_id_trial_package as builder
except ImportError:
    import build_pcie_id_trial_package as builder


def inspect(package):
    package = package.resolve()
    if package.parent != builder.ROOT / 'build/rpi5' or not package.name.startswith('pcie-id-trial-'):
        raise ValueError('Distinct local PCIe-ID package required')
    manifest = package / 'manifest.json'
    m = json.loads(manifest.read_text())
    inputs, previous = builder.inputs()
    actual_headers = builder.actual_header_closure(package)
    native_handoff = builder.handoff_contract.audit(builder.LOADER)
    builder.verify(m['headers_sha256'])
    builder.verify(m['generated_sha256'])
    raw, elf = (package / 'probe.bin').read_bytes(), package / 'probe.elf'
    layout = builder.inspect_elf(elf.read_bytes(), raw, builder.BASE)
    symbols = builder.symbols_for(elf)
    query = symbols.get('rpi5_psci_query')
    query_words = ()
    if query and query[0] in ('t', 'T') and int(query[2], 16) == 16:
        query_words = struct.unpack_from('<4I', raw, int(query[1], 16) - builder.BASE)
    payload = builder.encode_container((builder.KERNEL_PACKAGE / 'kernel.rp1-config').read_bytes(), None)
    frames, budgets = builder.stack_for(package, previous[0])
    commands = builder.commands_for(package)
    actual = [c + ['-MD', '-MF', str(package / ('step-' + str(i) + '.d'))] if '-c' in c else c
              for i, c in enumerate(commands)]
    main = commands[0]
    disabled = [x for x in main if x.startswith(('-DRPI5_GATE3_', '-DRPI5_GATE4_', '-DRPI5_SERIAL_TERMINAL='))]
    checks = dict(
        exact_profile=m.get('profile') == builder.PROFILE,
        exact_dependency_chain=m.get('inputs_sha256') == inputs,
        complete_header_closure=m.get('headers_sha256') == actual_headers,
        complete_generated_closure=set(m['generated_sha256']) ==
            {str(package / name) for name in builder.generated_names()},
        native_emitted_fdt_contract=m.get('native_handoff_contract') == native_handoff,
        actual_kernel_fdt_binding=m.get('kernel_handoff_binding') == builder.kernel_handoff_binding(),
        exact_watchdog=m.get('watchdog') == builder.WATCHDOG,
        ordered_boot_markers=m.get('boot_markers') == builder.boot_markers(m['trial_tag']),
        actual_compilation_commands=m.get('commands') == commands and
            [r['command'] for r in m['actual_commands']] == actual and
            all(r['returncode'] == 0 for r in m['actual_commands']),
        actual_tools=m.get('tool_identity') == builder.tool_identity(),
        exact_derived_main=(package / 'probe_main.c').read_text() == builder.derive_main(m['trial_tag'])[1],
        exact_no_cpu_on_assembly=(package / 'psci.S').read_text() == builder.derive_psci()[1],
        no_executable_cpu_on_helper='rpi5_psci_cpu_on' not in symbols and 'start_secondaries' not in symbols,
        real_readonly_psci_query=query_words == (0xaa1f03e2, 0xaa1f03e3, 0xd4000003, 0xd65f03c0),
        readonly_affinity_guard_retained=b'INITIAL_AFFINITY_STATE_REJECTED' in raw,
        single_cpu_no_terminal_no_storage_flags=bool(disabled) and all(x.endswith(('=0', '=""')) for x in disabled),
        explicit_bootargs=m.get('bootargs') == builder.BOOTARGS and (builder.BOOTARGS.encode() + b'\0') in raw,
        no_unsafe_bootargs=not any(value in raw[:m['payload_offset']] for value in
            (b'bcm2712_cpu_on_all=1', b'bcm2712_register_secondaries=1', b'bcm2712_terminal_watchdog=1', b'rd=md0')),
        exact_tag=m.get('marker') == builder.marker(m['trial_tag']) and
            raw.count((builder.marker(m['trial_tag']) + '\r\n').encode()) == 1,
        retained_device_and_fdt=all(name in symbols for name in
            ('rpi5_pcie_device_handoff', 'rpi5_firmware_fdt_tree_attach', 'rpi5_firmware_seed_tree')),
        real_device_and_fdt_compile_paths=all(flag in main for flag in
            ('-DRPI5_PCIE_DEVICE_HANDOFF=1', '-DRPI5_FIRMWARE_FDT_HANDOFF=1',
             '-DRPI5_GATE5_PCIE_TOPOLOGY=1')),
        exact_kernel_only_payload=(package / 'payload.bin').read_bytes() == payload and raw.count(payload) == 1
            and raw.find(payload) == m['payload_offset'] and not m['payload_offset'] % 64,
        fixed_kernel=m.get('kernel_sha256') == builder.KERNEL_SHA and
            m.get('kernel_manifest_sha256') == builder.KERNEL_MANIFEST_SHA,
        paired_secure_firmware=m.get('firmware') == str(builder.FIRMWARE_BIN) and
            m.get('firmware_sha256') == builder.FIRMWARE_SHA and
            m.get('firmware_manifest_sha256') == builder.FIRMWARE_MANIFEST_SHA,
        elf_and_raw=m.get('entry') == layout['entry'] == builder.BASE and m.get('loads') == layout['loads']
            and m.get('image_bytes') == len(raw) and m.get('image_sha256') == builder.sha(package / 'probe.bin'),
        actual_stack=m.get('stack_frames') == frames and m.get('stack_budgets') == budgets,
        no_expanded_claims=all(m.get(name) is False for name in
            ('cpu_on', 'root_embedded', 'serial_input_allowed', 'storage', 'dma', 'ethernet_proven',
             'installed', 'physical_execution')) and m.get('embedded_init') is None,
    )
    if not all(checks.values()):
        raise ValueError('PCIe-ID package refused: ' + repr([k for k, v in checks.items() if not v]))
    return dict(preflight_pass=True, checks=checks, image=str(package / 'probe.bin'), image_bytes=len(raw),
                image_sha256=builder.sha(package / 'probe.bin'), manifest_sha256=builder.sha(manifest),
                firmware=str(builder.FIRMWARE_BIN), firmware_sha256=builder.FIRMWARE_SHA,
                kernel_sha256=builder.KERNEL_SHA, trial_tag=m['trial_tag'], profile=builder.PROFILE,
                marker=m['marker'], boot_markers=m['boot_markers'],
                bootargs=builder.BOOTARGS, watchdog=builder.WATCHDOG,
                native_handoff_contract=native_handoff,
                kernel_handoff_binding=m['kernel_handoff_binding'],
                stack_budgets=budgets, serial_input_allowed=False, physical_execution=False,
                installation_admitted=False, scope='Actual source/ELF/payload audit; not board or Ethernet acceptance')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    print(json.dumps(inspect(parser.parse_args().package), indent=2, sort_keys=True))
