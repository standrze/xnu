#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Link a separate complete PCI/FDT kernel, never install or activate hardware."""
import argparse
import json
from pathlib import Path
import re
import shlex
import struct

try:
    from . import build_firmware_fdt_handoff as fdt
    from . import check_zsh_metadata_package as accepted
    from .audit_macho import inspect as inspect_macho
except ImportError:
    import build_firmware_fdt_handoff as fdt
    import check_zsh_metadata_package as accepted
    from audit_macho import inspect as inspect_macho

audit, ROOT = fdt.audit, fdt.ROOT
BASE = ROOT / 'build/rpi5/firmware-fdt-handoff-20261012-final'
BASE_SHA = 'eed613aaa91207b3c6db298fe811e4400bb4dca2d1a7ec8858243f817561b301'
COMPONENT = BASE / 'apple-bcm2712-firmware-fdt.o'
FILELIST = audit.OBJ / 'link.filelist'
FLAGS = audit.OBJ / '.LDFLAGS'
ARCHIVES = audit.OBJ / 'kernel.development.bcm2712.link/kernel.development.bcm2712.linkarchives'
WATCHDOG = fdt.ubus.phy.BASELINES[1][0]
REPLACED = (audit.OBJ / 'osfmk/DEVELOPMENT/arm_init.o',
            audit.OBJ / 'pexpert/DEVELOPMENT/pe_fiq.o')
INITIALIZERS = tuple('__GLOBAL__sub_I_' + name + '.cpp' for name in (
    'IOPCIBridge', 'IOPCIDevice', 'IOPCIMessagedInterruptController',
    'BCM2712PCIConfigBridge', 'IOPCIConfigurator', 'BCM2712PCIResourceBridge',
    'BCM2712PCIePHYTransport'))


def symbols(listing):
    result = {}
    for line in listing.splitlines():
        match = re.match(r'^([0-9a-fA-F]{16})\s+.*\s(\S+)$', line)
        if match:
            result.setdefault(match[2], []).append(int(match[1], 16))
    return result


def verify_replay(raw, reference):
    """The old non-reproducible link may differ ONLY in its LC_UUID payload."""
    normalized, uuids = [], []
    for data in (raw, reference):
        inspect_macho(data)
        cursor, found, copy = 32, [], bytearray(data)
        for _ in range(struct.unpack_from('<I', data, 16)[0]):
            command, size = struct.unpack_from('<II', data, cursor)
            if command == 0x1b:
                found.append(data[cursor + 8:cursor + 24].hex())
                copy[cursor + 8:cursor + 24] = bytes(16)
            cursor += size
        if len(found) != 1:
            raise ValueError('Replay needs exactly one LC_UUID')
        normalized.append(copy); uuids.append(found[0])
    if normalized[0] != normalized[1]:
        raise ValueError('Original object replay differs outside its LC_UUID metadata')
    return dict(all_non_uuid_bytes_identical=True, entire_file_identical=raw == reference,
                replay_uuid=uuids[0], accepted_uuid=uuids[1], excluded_metadata_bytes=16)


def linked_audit(raw, listing, linkmap):
    """Bind real constructor pointers and fixup sites, not just symbol presence."""
    report, names = inspect_macho(raw), symbols(listing)

    def address(name):
        values = names.get(name, [])
        if len(values) != 1:
            raise ValueError('Missing/ambiguous linked implementation: ' + name)
        return values[0]

    def executable(value):
        return sum(bool(s['initprot'] & 4) and s['vmaddr'] <= value and
                   value + 4 <= s['vmaddr'] + s['filesize'] for s in report['segments']) == 1

    header = address('__mh_execute_header')
    # ld's synthetic boundary symbol is deliberately absent from nlist even
    # before strip. Bind the sole [0] zero-size map entry, not an invented var.
    dso = re.findall(r'^0x([0-9A-Fa-f]+)\s+0x0+\s+\[\s*0\]\s+___dso_handle$', linkmap, re.M)
    if len(dso) != 1 or int(dso[0], 16) != header:
        raise ValueError('Static built-in logging DSO must alias the real kernel header')
    if not any(s['fileoff'] == 0 and s['vmaddr'] == header and
               s['filesize'] >= 32 and not s['initprot'] & 2 for s in report['segments']):
        raise ValueError('Logging DSO is not the read-only file-backed Mach-O header')
    required = ('_arm_init', '_rpi5_firmware_fdt_view', '_pe_rpi5_watchdog_claim_pcie',
                '_pe_rpi5_watchdog_check_pcie', '_rpi5_pcie_ubus_configure',
                '_OSRuntimeInitializeCPP', '_OSlibkernInit', '_pthread_start', '_hfs_mount',
                '_rpi5_crypto_platform_start', '__Z27rpi5_copy_boot_firmware_fdtv')
    for name in required:
        if not executable(address(name)):
            raise ValueError('Linked implementation is not executable: ' + name)
    prepares = [name for name in names if 'BCM2712PCIePHYTransport' in name and 'prepareBoot' in name]
    if len(prepares) != 1 or not executable(address(prepares[0])):
        raise ValueError('Actual firmware-FDT PCIe preparation missing')
    tables = [(s, section) for s in report['segments'] for section in s['sections']
              if section['name'] == '__mod_init_func' and section['size']]
    main_tables = [(s, table) for s, table in tables if s['name'] == '__DATA_CONST']
    if len(main_tables) != 1:
        raise ValueError('Expected one DATA_CONST runtime initializer table')
    segment, table = main_tables[0]
    if segment['name'] != '__DATA_CONST' or segment['initprot'] != 1 or table['size'] % 8:
        raise ValueError('Initializer table is not read-only pointer-sized DATA_CONST')
    offset = segment['fileoff'] + table['address'] - segment['vmaddr']
    pointers = struct.unpack_from('<' + 'Q' * (table['size'] // 8), raw, offset)
    all_pointers = []
    for owner, other in tables:
        if other['size'] % 8:
            raise ValueError('Malformed kernel initializer table')
        start = owner['fileoff'] + other['address'] - owner['vmaddr']
        all_pointers.extend(struct.unpack_from('<' + 'Q' * (other['size'] // 8), raw, start))
    # Every new pointer must participate in the kernel loader's local rebasing.
    cursor, relocations = 32, set()
    for _ in range(struct.unpack_from('<I', raw, 16)[0]):
        command, size = struct.unpack_from('<II', raw, cursor)
        if command == 0xb:
            location, count = struct.unpack_from('<II', raw, cursor + 72)
            for i in range(count):
                site, bits = struct.unpack_from('<II', raw, location + 8 * i)
                if bits >> 24 != 6:
                    raise ValueError('Unsupported initializer relocation encoding')
                relocations.add(report['relocation_base'] + site)
        cursor += size
    rows = []
    for name in INITIALIZERS:
        target = address(name)
        if not executable(target) or pointers.count(target) != 1 or all_pointers.count(target) != 1:
            raise ValueError('Initializer not present exactly once: ' + name)
        site = table['address'] + 8 * pointers.index(target)
        if site not in relocations:
            raise ValueError('Initializer lacks real local relocation: ' + name)
        rows.append(dict(symbol=name, address=hex(target), pointer_site=hex(site)))
    return dict(macho=report, logging_dso_address=hex(header),
                required_implementations=list(required) + prepares,
                initializer_table_segment=segment['name'], initializer_count=len(pointers),
                added_initializers=rows, initializer_runtime_executed=False)


def inputs():
    manifest = BASE / 'manifest.json'
    if audit.sha(manifest) != BASE_SHA:
        raise ValueError('Accepted retained-FDT receipt changed')
    report = json.loads(manifest.read_text())
    captured = {**report['inputs_sha256'], **report['generated_sha256'], str(manifest): BASE_SHA}
    composition = report['kernel_link']['command']
    if composition[:6] != ['xcrun', 'ld', '-r', '-arch', 'arm64', '-o'] or composition[6] != str(COMPONENT):
        raise ValueError('Accepted component composition changed')
    # ld -r localizes private externs, including the reset entry arm_init.
    # Reuse its actual pinned constituent objects at the FINAL link instead.
    constituents = list(map(Path, composition[7:]))
    if constituents.count(BASE / 'arm_init.c.o') != 1 or len(constituents) != len(set(constituents)):
        raise ValueError('Actual early-kernel replacement is ambiguous')
    if any(str(path) not in captured for path in constituents):
        raise ValueError('Unpinned component constituent')
    if audit.sha(accepted.BUILD) != accepted.BUILD_SHA or audit.sha(audit.KERNEL) != accepted.KERNEL_SHA:
        raise ValueError('Accepted kernel or original build receipt changed')
    build = json.loads(accepted.BUILD.read_text())
    if build['exit_code'] != 0 or not build['source_unchanged_during_build'] or not build['fresh_kernel_outputs']:
        raise ValueError('Original kernel receipt is not a successful stable build')
    objects = [Path(line) for line in FILELIST.read_text().splitlines() if line]
    if len(objects) != len(set(objects)) or any(objects.count(path) != 1 for path in REPLACED):
        raise ValueError('Original kernel object replacement is ambiguous')
    if any(not path.is_relative_to(audit.OBJ) or path.suffix not in ('.o', '.cpo') for path in objects):
        raise ValueError('Unexpected original kernel filelist input')
    extras = [audit.OBJ / name for name in
              ('lastkerneldataconst.o', 'lastkernelconstructor.o', 'nonlto.o', 'version.o')]
    for key in ('RPI5_CRYPTO_CANDIDATE_OBJECT', 'RPI5_PTHREAD_PROVIDER_OBJECT', 'RPI5_STORAGE_PROVIDER_OBJECT'):
        values = [arg.split('=', 1)[1] for arg in build['command'] if arg.startswith(key + '=')]
        if len(values) != 1 or not values[0]:
            raise ValueError('Missing original source-built provider: ' + key)
        extras.append(Path(values[0]))
    archive = audit.SDK / 'usr/local/lib/kernel/libfirehose_kernel.a'
    archive_args = shlex.split(ARCHIVES.read_text())
    expected = ['-L' + str(audit.SDK / 'usr/local/lib/kernel'),
                '-L' + str(audit.SDK / 'usr/local/lib/kernel/platform'), '-lfirehose_kernel']
    if archive_args != expected:
        raise ValueError('Original kernel archive dependencies changed')
    flags = shlex.split(FLAGS.read_text().rstrip('\0\n'))
    compiler = Path(json.loads(audit.TEMPLATE.read_text().strip().removesuffix(','))['arguments'][0])
    if Path(flags[0]) != compiler.with_name('clang++'):
        raise ValueError('Original link driver differs from actual XNU compiler')
    if any('undefined' in arg or 'multiply_defined' in arg or 'force_load' in arg for arg in flags):
        raise ValueError('Unsafe unresolved/duplicate/archive link policy')
    for path in (*objects, *extras, archive, FLAGS, ARCHIVES, FILELIST, accepted.BUILD,
                 Path(flags[0]), Path(audit.read_command(['xcrun', '--find', 'ld'])),
                 Path(audit.read_command(['xcrun', '--find', 'strip'])),
                 ROOT / 'libkern/c++/OSRuntime.cpp', ROOT / 'libkern/os/log.c',
                 ROOT / 'libkern/os/log.h', ROOT / 'makedefs/MakeInc.kernel',
                 Path(__file__).resolve(), ROOT / 'tools/rpi5/audit_macho.py',
                 ROOT / 'tools/rpi5/tests/test_pcie_kernel.py'):
        digest = audit.sha(path)
        if str(path) in captured and captured[str(path)] != digest:
            raise ValueError('Conflicting complete-kernel dependency: ' + str(path))
        captured[str(path)] = digest
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('Complete-kernel dependency changed: ' + name)
    return captured, objects, extras, flags, archive, constituents


def build(output):
    captured, original, extras, flags, archive, constituents = inputs()
    output = output.resolve()
    # Only a fresh direct build child or a fresh temporary directory is allowed.
    if not (output.parent == ROOT / 'build/rpi5' or output.is_relative_to(Path('/private/tmp'))
            or output.is_relative_to(Path('/private/var/folders'))):
        raise ValueError('Complete kernel requires a separate fresh build/temporary directory')
    output.mkdir(parents=True, exist_ok=False)
    commands = []

    def execute(command, name):
        row = audit.execute(command, ROOT, output / (name + '.log'))
        commands.append(row)
        if row['returncode']:
            raise ValueError('Complete kernel step failed: ' + row['log'])
        return row

    def link(objects, stem):
        filelist = output / (stem + '.filelist')
        filelist.write_text(''.join(str(path) + '\n' for path in objects))
        unstripped, stripped = output / (stem + '.unstripped'), output / stem
        command = [('-Wl,-map,' + str(output / (stem + '.map')))
                   if arg.startswith('-Wl,-map,') else arg for arg in flags]
        # The MH_EXECUTE final linker supplies ___dso_handle as a boundary
        # symbol. Do not define a dummy or duplicate it with an explicit alias.
        command += ['-filelist', str(filelist), *map(str, extras), '-o', str(unstripped), str(archive)]
        row = execute(command, stem + '-link')
        execute(['xcrun', 'strip', '-S', unstripped, '-o', stripped], stem + '-strip')
        return stripped, row

    replay, replay_row = link(original, 'baseline-replay')
    replay_audit = verify_replay(replay.read_bytes(), audit.KERNEL.read_bytes())
    candidates = [path for path in original if path not in REPLACED] + constituents
    kernel, row = link(candidates, 'kernel.pcie-fdt')
    baseline_warnings = [line for line in Path(replay_row['log']).read_text().splitlines() if 'warning:' in line]
    warnings = [line for line in Path(row['log']).read_text().splitlines() if 'warning:' in line]
    if warnings != baseline_warnings:
        raise ValueError('Complete kernel introduced new linker warnings')
    listing = audit.read_command(['xcrun', 'nm', '-nm', kernel])
    (output / 'kernel.symbols').write_text(listing + '\n')
    if audit.read_command(['xcrun', 'nm', '-ju', kernel]):
        raise ValueError('Complete kernel has unresolved symbols')
    textmap = (output / 'kernel.pcie-fdt.map').read_text(errors='surrogateescape')
    linked = linked_audit(kernel.read_bytes(), listing, textmap)
    for path in REPLACED:
        if str(path) in textmap:
            raise ValueError('Superseded object survived complete linkage: ' + str(path))
    if any(str(path) not in textmap for path in constituents):
        raise ValueError('Accepted actual PCI/FDT constituent missing from map')
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('Complete-kernel input changed during link: ' + name)
    generated = {str(path): audit.sha(path) for path in output.rglob('*') if path.is_file()}
    report = dict(schema_version=1, profile='pcie-fdt-static-kernel-link-v1',
        inputs_sha256=captured, generated_sha256=generated, commands=commands,
        kernel=str(kernel), kernel_sha256=audit.sha(kernel), kernel_bytes=kernel.stat().st_size,
        original_kernel_replay=replay_audit, replaced_objects=list(map(str, REPLACED)),
        component_sha256=audit.sha(COMPONENT), component_objects=list(map(str, constituents)), link=linked,
        baseline_linker_warnings=baseline_warnings, new_linker_warnings=[],
        complete_kernel_link_proven=True, initializer_runtime_executed=False,
        provider_personality_added=False, boot_caller_added=False,
        power_clock_ownership_proven=False, hardware_recovery_proven=False,
        installed=False, pi_executed=False, pcie_mmio_enabled=False, ethernet_proven=False,
        loader_package_created=False, sd_actions=0, serial_actions=0, reboots=0)
    (output / 'manifest.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    report = build(parser.parse_args().output_dir)
    print(json.dumps(dict(kernel_sha256=report['kernel_sha256'],
        kernel_bytes=report['kernel_bytes'], complete_kernel_link_proven=True, pi_executed=False)))


if __name__ == '__main__':
    main()
