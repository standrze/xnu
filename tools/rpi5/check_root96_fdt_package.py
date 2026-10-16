#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only compatibility audit for the corrected root96/FDT composition."""
import argparse
import json
from pathlib import Path
try:
    from . import build_root96_fdt_package as builder
except ImportError:
    import build_root96_fdt_package as builder


def inspect(package):
    package = package.resolve()
    if package.parent != builder.ROOT / 'build/rpi5' or not package.name.startswith('root96-fdt-'):
        raise ValueError('Distinct corrected root96 package required')
    m = json.loads((package / 'manifest.json').read_text())
    pins, old, previous = builder.inputs()
    builder.verify(m['headers_sha256'])
    builder.verify(m['generated_sha256'])
    kernel = Path(m['kernel'])
    image = (package / 'probe.bin').read_bytes()
    payload = builder.encode(kernel.read_bytes(), Path(m['root']).read_bytes())
    contract = builder.handoff_contract(package, kernel)
    layout = builder.retained.device.accepted.old.inspect_elf((package / 'probe.elf').read_bytes(), image, builder.BASE)
    inherited_link = next(r['command'] for r in old['commands'] if r['log'].endswith('/firmware-fdt-link.log'))
    old_payload = [value for value in inherited_link if value.endswith('/payload.o')]
    if len(old_payload) != 1:
        raise ValueError('Frozen root96 payload replacement ambiguous')
    link = [str(package / 'payload.o') if value == old_payload[0] else value for value in inherited_link]
    link[link.index('-o') + 1] = str(package / 'probe.elf')
    actual_links = [row['command'] for row in m['commands'] if row['log'].endswith('/corrected-link.log')]
    generated_names = ('baseline-copy.log', 'baseline-link.log', 'baseline.bin', 'baseline.elf',
                       'corrected-copy.log', 'corrected-link.log', 'payload-compile.log',
                       'payload-dependencies.log', 'payload.S', 'payload.bin', 'payload.d',
                       'payload.o', 'probe.bin', 'probe.elf')
    expected_generated = {str(package / name): builder.sha(package / name) for name in generated_names}
    expected_headers = builder.dependencies((package / 'payload.d').read_text())
    expected_assembly = '.section .payload,"a"\n.balign 64\n.incbin "' + str(package / 'payload.bin') + '"\n'
    checks = dict(
        exact_profile=m.get('profile') == builder.PROFILE,
        exact_frozen_source_chain=m.get('inputs_sha256') == pins,
        complete_generated_closure=m.get('generated_sha256') == expected_generated,
        complete_header_closure=m.get('headers_sha256') == expected_headers ==
            builder.dependencies((package / 'payload-dependencies.log').read_text()) ==
            {str(package / 'payload.S'): builder.sha(package / 'payload.S')},
        exact_payload_assembly=(package / 'payload.S').read_text() == expected_assembly,
        tools_unchanged=m.get('tool_identity') == builder.tool_identity(),
        original_loader_reproduced=builder.sha(package / 'baseline.bin') == old['image_sha256'] == m.get('original_loader_sha256'),
        original_link_record=m.get('original_link') == inherited_link,
        only_payload_object_replaced=actual_links == [link],
        command_success=all(row['returncode'] == 0 for row in m['commands']),
        exact_kernel=builder.sha(kernel) == m.get('kernel_sha256') == builder.failed.KERNEL_SHA,
        exact_root=builder.sha(Path(m['root'])) == m.get('root_sha256') == builder.failed.ROOT_SHA,
        full_payload=(package / 'payload.bin').read_bytes() == payload and image.count(payload) == 1,
        emitted_loader_contract=m.get('handoff') == contract,
        elf_and_raw=m.get('elf') == layout and m.get('entry') == builder.BASE and
            m.get('image') == str(package / 'probe.bin') and m.get('image_bytes') == len(image) and
            m.get('image_sha256') == builder.sha(package / 'probe.bin'),
        firmware_fdt_load_space=max(row['address'] + row['memory_size'] for row in layout['loads']) < 0xb000000,
        terminal_command_exact=image.count(builder.failed.terminal.TERMINAL_COMMAND + b'\0') == 1,
        unchanged_code_stack=m.get('stack_frames') == old['stack_frames'] and m.get('stack_budgets') == old['stack_budgets'],
        immutable_geometry=m.get('root96_geometry') == previous,
        bounded_watchdog=m.get('terminal_watchdog_seconds') == 180 and m.get('hardware_watchdog_seconds') == 15,
        normal_firmware=m.get('normal_firmware_sha256') == builder.failed.NORMAL_FIRMWARE_SHA,
        no_board_claim=all(m.get(name) is False for name in ('installed', 'physical_execution', 'controller_initialized')),
    )
    if not all(checks.values()):
        raise ValueError('Corrected root96 package rejected: ' + repr([name for name, passed in checks.items() if not passed]))
    report = dict(previous)
    report.update(profile=builder.PROFILE, image=str(package / 'probe.bin'), image_sha256=m['image_sha256'],
                  image_bytes=len(image), loader_manifest_sha256=builder.sha(package / 'manifest.json'),
                  corrected_checks=checks, handoff=contract, failed_composition_preserved=True,
                  preflight_pass=True, scope='Retained-FDT loader and exact unchanged kernel/root compatibility; not Pi acceptance')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    print(json.dumps(inspect(parser.parse_args().package), indent=2))
