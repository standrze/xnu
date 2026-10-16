#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Bind Apple command trap inventories to the preserved Pi kernel's sysent.

Read-only linked wiring evidence, never runtime socket or NIC acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

try:
    from . import prepare_apple_network_root as root
    from . import check_zsh_metadata_package as metadata
    from .audit_macho import inspect as inspect_macho
    from .audit_zsh_pi_binary import audit as audit_instructions
except ImportError:
    import prepare_apple_network_root as root
    import check_zsh_metadata_package as metadata
    from audit_macho import inspect as inspect_macho
    from audit_zsh_pi_binary import audit as audit_instructions

ENTRY = struct.Struct('<QQihH')  # This pinned ARM64 kernel enables u32 munging.
NETWORK = {27: '_recvmsg', 29: '_recvfrom', 31: '_getpeername', 54: '_ioctl',
           97: '_socket', 98: '_connect', 104: '_bind', 105: '_setsockopt',
           133: '_sendto', 134: '_shutdown', 202: '_sysctl'}


def linked_calls(raw, segments, listing, numbers):
    symbols = {}
    for line in listing.splitlines():
        match = re.match(r'^([0-9a-fA-F]{16})\s+.*\s(\S+)$', line)
        if match:
            symbols.setdefault(match[2], []).append(int(match[1], 16))

    def address(name):
        values = symbols.get(name, [])
        if len(values) != 1:
            raise ValueError('Missing/ambiguous kernel symbol: ' + name)
        return values[0]

    def offset(value, size, executable):
        owners = [s for s in segments if s['vmaddr'] <= value and
                  value + size <= s['vmaddr'] + s['filesize']]
        if len(owners) != 1 or bool(owners[0]['initprot'] & 4) != executable:
            raise ValueError('Kernel range lacks unique expected file-backed protection')
        result = owners[0]['fileoff'] + value - owners[0]['vmaddr']
        if result < 0 or result + size > len(raw):
            raise ValueError('Kernel range exceeds file')
        return result

    count = struct.unpack_from('<I', raw, offset(address('_nsysent'), 4, False))[0]
    if not 500 < count < 1024:
        raise ValueError('Unexpected syscall count for pinned kernel')
    table = address('_sysent')
    start = offset(table, count * ENTRY.size, False)
    nosys = address('_nosys')
    # Negative control validates the ABI stride and interpretation independently.
    if ENTRY.unpack_from(raw, start) != (nosys, 0, 1, 0, 0):
        raise ValueError('sysent[0] does not match the u32-munging negative control')
    numbers = list(numbers)
    if any(type(number) is not int or not 0 < number < count for number in numbers):
        raise ValueError('Out-of-range BSD syscall')
    rows = []
    for number in sorted(set(numbers)):
        call, munge, returns, nargs, argbytes = ENTRY.unpack_from(raw, start + number * ENTRY.size)
        offset(call, 4, True)
        if munge:
            offset(munge, 4, True)
        if not 0 <= returns <= 7 or not 0 <= nargs <= 8 or not 0 <= argbytes <= 64:
            raise ValueError('Unexpected syscall ABI fields')
        names = sorted(name for name, values in symbols.items() if values == [call])
        if not names or call == nosys:
            raise ValueError('Missing handler or nosys for syscall ' + str(number))
        if number in NETWORK and call != address(NETWORK[number]):
            raise ValueError('Network syscall table differs from expected real handler')
        rows.append(dict(number=number, slot_address=hex(table + number * ENTRY.size),
                         handler_address=hex(call), handler_symbols=names,
                         return_type=returns, argument_count=nargs, argument_bytes_32=argbytes,
                         munge32_address=hex(munge), runtime_semantics_proven=False))
    return dict(sysent_address=hex(table), sysent_entry_bytes=ENTRY.size,
                nsysent=count, nosys_control_verified=True, calls=rows)


def audit():
    commands, snapshots, provenance = root.load_inputs()
    raw = metadata.KERNEL.read_bytes()
    if hashlib.sha256(raw).hexdigest() != metadata.KERNEL_SHA:
        raise ValueError('Physically accepted kernel pin changed')
    if metadata.previous.terminal.sha256(metadata.BUILD) != metadata.BUILD_SHA:
        raise ValueError('Kernel build receipt pin changed')
    build = json.loads(metadata.BUILD.read_text())
    if (type(build.get('exit_code')) is not int or build['exit_code'] != 0 or
            build.get('source_unchanged_during_build') is not True or
            build.get('source') != build.get('source_at_finish') or
            build.get('fresh_kernel_outputs') is not True):
        raise ValueError('Kernel build receipt semantics changed')
    inventories = {name: audit_instructions(root.CAPSULE/name, root.PINS[name][0])
                   for name in commands}
    if any(value['unresolved_immediate_sites'] or value['unknown_decode_addresses']
           for value in inventories.values()):
        raise ValueError('Unresolved command trap inventory')
    numbers = {row['immediately_preceding_x16'] for value in inventories.values()
               for row in value['trap_sites'] if row['kind'] == 'bsd'}
    symbols = subprocess.check_output(['xcrun', 'nm', '-nm', str(metadata.KERNEL)],
                                      text=True, timeout=30)
    wiring = linked_calls(raw, inspect_macho(raw)['segments'], symbols, numbers)
    if metadata.KERNEL.read_bytes() != raw or any(path.read_bytes() != data
                                                 for path, data in snapshots.items()):
        raise ValueError('Audit inputs changed during inspection')
    return dict(schema_version=1, scope='Actual linked BSD syscall wiring, not runtime ABI or networking',
                kernel=str(metadata.KERNEL), kernel_sha256=metadata.KERNEL_SHA,
                kernel_build_sha256=metadata.BUILD_SHA,
                commands_sha256={name: root.PINS[name][0] for name in commands},
                source_commit=provenance['commit'], linked_sysent=wiring,
                trap_counts={name: value['trap_count'] for name, value in inventories.items()},
                network_syscalls_bound_to_real_handlers=True,
                pi_utilities_executed=False, socket_semantics_proven=False, nic_ready=False,
                mach_traps_platform_calls_and_isa_qualified=False,
                next_trial=['/sbin/ifconfig -l', '/sbin/route -n'],
                trial_limits='Names-only enumeration; route -n opens PF_ROUTE then usage/exit, no route mutation; runtime trial still required',
                serial_actions=0, sd_actions=0, reboots=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = audit()
    with args.report.open('x') as output:
        json.dump(result, output, indent=2, sort_keys=True)
        output.write('\n')
    print(json.dumps(dict(report=str(args.report), calls=len(result['linked_sysent']['calls']),
                          network_syscalls_bound=True, runtime_semantics_proven=False)))


if __name__ == '__main__':
    main()
