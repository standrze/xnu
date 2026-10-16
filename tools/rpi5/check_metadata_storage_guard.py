# SPDX-License-Identifier: BSD-2-Clause
"""Review the exact preserved corrective kernel's SD-start rejection path.

Not a generic disassembler or hardware test. The independently reviewed A76
bytes bind the absent/!=1 opt-in branches to a false-return epilogue before
readBinding, register mapping, or other calls. Reject any byte/layout drift.
"""
import hashlib
import re

START = '__ZN16BCM2712SDStorage5startEP9IOService'
PARSE = '_PE_parse_boot_argn'
START_ADDRESS = 0xfffffe00079ac4e0
PARSE_ADDRESS = 0xfffffe0007905c20
ARG_ADDRESS = 0xfffffe00070ea4c5
REJECT_ADDRESS = 0xfffffe00079ac7a4
PREFIX = bytes.fromhex(
    'ffc303d1f85f0ba9f6570ca9f44f0da9fd7b0ea9fd830391f40301aaf30300aa'
    'bfc31cb8e0b9ffd000141391a1d300d182008052c365fd97e803002ae0031f2a'
    '28140034a8c35cb81f050071c1130054')
EPILOGUE = bytes.fromhex('fd7b4ea9f44f4da9f6574ca9f85f4ba9ffc30391c0035fd6')
ARGUMENT = b'bcm2712_sd_readonly\0'


def address(symbols, name):
    rows = [line.split() for line in symbols.splitlines() if line.endswith(' ' + name)]
    if len(rows) != 1 or not re.fullmatch('[0-9a-fA-F]{16}', rows[0][0]):
        raise ValueError('Missing/ambiguous reviewed guard symbol: ' + name)
    return int(rows[0][0], 16)


def extent(raw, segments, address, size, executable):
    owners = [s for s in segments if s['vmaddr'] <= address and
              address + size <= s['vmaddr'] + s['filesize']]
    if len(owners) != 1 or bool(owners[0]['initprot'] & 4) != executable:
        raise ValueError('Guard bytes lack unique expected file-backed protection')
    offset = owners[0]['fileoff'] + address - owners[0]['vmaddr']
    if not 0 <= offset <= len(raw) - size:
        raise ValueError('Guard extent exceeds kernel bytes')
    return raw[offset:offset+size]


def inspect(raw, segments, symbols):
    if address(symbols, START) != START_ADDRESS or address(symbols, PARSE) != PARSE_ADDRESS:
        raise ValueError('Not the reviewed corrective-kernel guard layout')
    prefix = extent(raw, segments, START_ADDRESS, len(PREFIX), True)
    epilogue = extent(raw, segments, REJECT_ADDRESS, len(EPILOGUE), True)
    argument = extent(raw, segments, ARG_ADDRESS, len(ARGUMENT), False)
    if prefix != PREFIX or epilogue != EPILOGUE or argument != ARGUMENT:
        raise ValueError('Reviewed SD-start guard bytes/argument changed')
    if b'bcm2712_sd_write_trial' in raw or any('BCM2712SDWriteStorage' in line for line in symbols.splitlines()):
        raise ValueError('Write-provider kernel is outside this reviewed profile')
    return dict(start_address=hex(START_ADDRESS), boot_argument_address=hex(ARG_ADDRESS),
                parse_target=hex(PARSE_ADDRESS), false_return_target=hex(REJECT_ADDRESS),
                prefix_bytes=len(PREFIX), epilogue_bytes=len(EPILOGUE),
                prefix_sha256=hashlib.sha256(prefix).hexdigest(),
                epilogue_sha256=hashlib.sha256(epilogue).hexdigest(),
                argument=ARGUMENT[:-1].decode(), absent_or_not_one_returns_false=True,
                write_provider_absent=True,
                scope='Exact reviewed linked A76 entry guard; not a runtime storage-access observation')
