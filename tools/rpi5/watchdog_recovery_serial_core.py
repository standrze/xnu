# SPDX-License-Identifier: BSD-2-Clause
"""Strict image-tagged PM observations, not physical reset/destination proof."""
import re

PREFIX = b'RPI5XNU:RECOVERY:'
FIELDS = ('FREQUENCY', 'START', 'DEADLINE', 'SAMPLED', 'ROUTE', 'PRIOR', 'ARMED', 'FINAL', 'WAITED', 'CHECKS')


def numeric(tail, keys):
    pattern = b' '.join(key.encode()+rb'=(0x[0-9A-F]{16})' for key in keys)
    match = re.fullmatch(pattern, tail)
    if not match: raise ValueError('Unexpected diagnostic fields')
    return dict(zip(keys, (int(value, 16) for value in match.groups())))


def inspect(data, tag):
    if not isinstance(data, bytes) or len(data) > 4*1024*1024 or not re.fullmatch('[0-9a-f]{32}', tag):
        raise ValueError('Bounded serial bytes and exact tag required')
    lines = [line.rstrip(b'\r') for line in data.split(b'\n') if line.startswith(PREFIX)]
    names = ('ENTRY', 'EL1', 'ARMED', 'CHECKED', 'RESULT', 'STOP')
    if len(lines) != len(names): raise ValueError('Incomplete, duplicated or faulted diagnostic sequence')
    tails = []
    for name,line in zip(names, lines):
        header = PREFIX+name.encode()+b' TAG='+tag.encode()+b' '
        if not line.startswith(header): raise ValueError('Wrong image/tag/phase order')
        tails.append(line[len(header):])
    if tails[0] != b'EL2 NO_XNU NO_CPU_ON PCIE_MMIO=0 DMA=0' or tails[1] != b'MMU_CACHE_OFF DAIF_MASKED PRIMARY_ONLY':
        raise ValueError('Entry profile differs')
    armed, checked = numeric(tails[2], FIELDS), numeric(tails[3], FIELDS)
    frequency = armed['FREQUENCY']
    if not (1000000 <= frequency <= 1000000000 and
            armed['DEADLINE'] == armed['START']+12*frequency < 1 << 64 and
            armed['START'] <= armed['SAMPLED'] <= armed['START']+frequency and
            armed['ROUTE'] < 0xffffffff and armed['ROUTE'] & 0x30 == 0x20 and
            2 << 16 < armed['PRIOR'] <= 0xfffff and
            14 << 16 <= armed['ARMED'] <= 15 << 16 and armed['FINAL'] == armed['ARMED'] and
            armed['WAITED'] == armed['CHECKS'] == 0): raise ValueError('Arming observation failed')
    if any(checked[k] != armed[k] for k in FIELDS if k not in ('FINAL', 'WAITED', 'CHECKS')):
        raise ValueError('Initial observation changed')
    if not (2 << 16 < checked['FINAL'] < armed['ARMED'] and checked['CHECKS'] == 1 and
            (frequency+499)//500 <= checked['WAITED'] <= frequency): raise ValueError('Countdown/wait check failed')
    result = numeric(tails[4], ('RC', 'WRITE_ATTEMPTS', 'LEASE_CALLBACKS'))
    if result != dict(RC=0, WRITE_ATTEMPTS=1, LEASE_CALLBACKS=12): raise ValueError('Protocol failed')
    if tails[5] != b'NO_RELOAD WAIT_FOR_RESET PCIE_MMIO=0 DMA=0 RESET_RETURN_PROVEN=0':
        raise ValueError('Non-servicing stop contract differs')
    stop = data.index(lines[5])+len(lines[5])
    return dict(diagnostic_pass=True, trial_tag=tag, armed=armed, checked=checked, result=result,
        firmware_bootloader_banner_after_stop=b'RPi: BOOTLOADER release VERSION:' in data[stop:],
        physical_reset_return_proven=False, watchdog_destination_proven=False,
        scope='Actual emitted tagged PM protocol observations; independent continuous reset/new-SSD-boot evidence still required')
