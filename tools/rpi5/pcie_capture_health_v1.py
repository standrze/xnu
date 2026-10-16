#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Supplemental raw-trace fault observation, never a replacement acceptance test.

The original recorder, raw bytes and receipts stay unchanged. This independently
checks a retained whole-file digest and detects faults even AFTER a valid END
line. Absence of signatures does not establish runtime or recovery acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

MAX_BYTES = 4 * 1024 * 1024
END = re.compile(rb'(?m)^RPI5XNU:PCIEID:END [^\r\n]*\r?\n')
SIGNATURES = (b'panic(cpu ', b'Assertion failed:', b'Debugger message: panic',
              b'FAILED_STOP', b'RPI5XNU:RAMROOT:REJECT')


def inspect(raw, expected_sha256):
    if (not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES or
            not isinstance(expected_sha256, str) or
            not re.fullmatch('[0-9a-f]{64}', expected_sha256)):
        raise ValueError('Bounded nonempty raw capture and retained SHA256 required')
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise ValueError('Raw capture differs from separately retained digest')
    endings = list(END.finditer(raw))
    terminal = endings[0].end() if len(endings) == 1 else None
    faults = []
    for signature in SIGNATURES:
        start = 0
        while (offset := raw.find(signature, start)) >= 0:
            line_end = raw.find(b'\n', offset)
            line_end = len(raw) if line_end < 0 else line_end
            faults.append(dict(signature=signature.decode('ascii'), offset=offset,
                excerpt=raw[offset:min(line_end, offset + 512)].decode('ascii', 'backslashreplace'),
                after_unique_terminal_end=terminal is not None and offset >= terminal))
            start = offset + len(signature)
    faults.sort(key=lambda item: item['offset'])
    return dict(format='rpi5-supplemental-capture-health-v1', bytes=len(raw),
        serial_sha256=actual, signature_scan_completed=True,
        complete_terminal_lines=len(endings), runtime_fault_signature_observed=bool(faults),
        post_terminal_fault_observed=any(row['after_unique_terminal_end'] for row in faults),
        faults=faults, clean_trial_acceptance_established=False,
        original_capture_and_receipts_modified=False, hardware_access=False,
        scope='Supplemental fault-signature scan only; not PCIe ID, capture continuity, watchdog recovery or overall trial acceptance')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--serial-sha256', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if args.capture.is_symlink() or not args.capture.is_file() or args.capture.stat().st_size > MAX_BYTES:
        raise ValueError('Bounded regular raw file required')
    report = inspect(args.capture.read_bytes(), args.serial_sha256)
    report['capture'] = str(args.capture.resolve())
    report['supplemental_source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    encoded = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.output:
        # A new supplemental result, never an overwrite of original evidence.
        with args.output.open('x') as handle:
            handle.write(encoded)
    print(encoded, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
