#!/usr/bin/env python3
"""Inventory disassembly for manual ISA review; never a compatibility certificate."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

from audit_macho import inspect

LABEL = re.compile(r'^([0-9a-f]+) <(.+)>:$')
INSN = re.compile(r'^([0-9a-f]+):\s+(\S+)(?:\s+(.*))?$')
CONTROL = {'mrs', 'msr', 'sys', 'sysl', 'at', 'dc', 'ic', 'tlbi',
           'hint', 'dmb', 'dsb', 'isb', 'eret', 'hvc', 'smc'}


def inventory(lines):
    section = None
    label = None
    counts = Counter()
    unknown = []
    control = []
    for line in lines:
        line = line.strip()
        if line.startswith('Disassembly of section ') and line.endswith(':'):
            section = line[len('Disassembly of section '):-1]
            label = None
            continue
        match = LABEL.fullmatch(line)
        if match:
            label = {'address': '0x' + match[1], 'name': match[2]}
            continue
        match = INSN.fullmatch(line)
        if not match:
            continue
        if section is None:
            raise ValueError('Instruction outside a named disassembly section')
        mnemonic = match[2]
        counts[mnemonic] += 1
        if mnemonic in CONTROL:
            control.append({'address': '0x' + match[1], 'section': section,
                            'mnemonic': mnemonic, 'operands': match[3] or '',
                            'nearest_label': label})
        if mnemonic == '<unknown>':
            unknown.append({'address': '0x' + match[1], 'section': section,
                            'nearest_label': label})
    if not counts:
        raise ValueError('No disassembly records found')
    return {'status': 'manual_review_required',
            'scope': 'Linear disassembly includes data; nearest labels are not proven function extents. Known mnemonics are not automatically A76-compatible.',
            'decoded_words': sum(counts.values()),
            'mnemonics': dict(sorted(counts.items())),
            'unknown_words': unknown,
            'control_words': control}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    parser.add_argument('--output', type=Path, help='Optional JSON evidence artifact')
    args = parser.parse_args()
    data = args.kernel.read_bytes()
    structural = inspect(data)
    command = ['xcrun', 'llvm-objdump', '-d', '--no-show-raw-insn', str(args.kernel)]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    if hashlib.sha256(args.kernel.read_bytes()).hexdigest() != structural['sha256']:
        raise ValueError('Kernel changed during disassembly')
    report = inventory(result.stdout.splitlines())
    report.update(kernel=str(args.kernel.resolve()), sha256=structural['sha256'],
                  command=command, tool_version=subprocess.check_output(
                      ['xcrun', 'llvm-objdump', '--version'], text=True).strip())
    encoded = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end='')


if __name__ == '__main__':
    main()
