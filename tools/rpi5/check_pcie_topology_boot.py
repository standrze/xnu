#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Offline audit of one RX-only full-FDT boot; never opens serial or SSH.

The fixed declaration profile matches the independently accepted Linux
reference. Declaration addresses are not proof of programmed PCIe windows.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

import stage_pcie_topology as stage

PREFIX = b'RPI5XNU:BL33:PCIE_TOPOLOGY:'
EXPECTED = (
    b'BEGIN DECLARATIONS_ONLY',
    b'BRIDGE CPU_START=0000001000120000 CPU_END=0000001000129310',
    b'MIP CPU_START=0000001000130000 MSI_PCI_TARGET=000000fffffff000',
    b'GEM BAR_OFFSET=0000000000100000 BYTES=0000000000004000 RP1_IRQ=0000000000000006 PHY_ADDRESS=0000000000000001',
    b'OUTBOUND SPACE=0000000002000000 PCI_BASE=0000000000000000 CPU_BASE=0000001f00000000 BYTES=00000000fffffffc NOT_PROGRAMMING_PROOF',
    b'OUTBOUND SPACE=0000000043000000 PCI_BASE=0000000400000000 CPU_BASE=0000001c00000000 BYTES=0000000300000000 NOT_PROGRAMMING_PROOF',
    b'PASS PCIE_MMIO=0 CONFIG_ACCESS=0 DMA=0 NIC_READY=0',
)
TRANSFER = b'RPI5XNU:BL33:XNU_TRANSFER_PENDING WATCHDOG_15S SEED_COMMIT_NEXT'
RAMROOT = b'RPI5XNU:RAMROOT:MOUNT NODES=19 BYTES=589824 READONLY'
SHELL = b'RPI5XNU:SHELL:READY'


def validate(raw):
    if not raw or len(raw) > 2 * 1024 * 1024: raise ValueError('Bounded nonempty boot capture required')
    normalized = raw.replace(b'\r', b'')
    lines = normalized.split(b'\n')
    rows = [line[len(PREFIX):] for line in lines if line.startswith(PREFIX)]
    if rows != list(EXPECTED) or normalized.count(PREFIX) != len(EXPECTED):
        raise ValueError('Not the exact one-boot accepted declaration profile')
    if (normalized.count(b'RPI5XNU:BL33:ENTRY EL=') != 1 or
            normalized.count(b'Boot mode: SD (01)') != 1 or
            lines.count(TRANSFER) != 1 or lines.count(RAMROOT) != 1 or lines.count(SHELL) < 1):
        raise ValueError('Fresh single SD/loader/transfer/RAM-root/shell readiness evidence required')
    ordered = (b'Boot mode: SD (01)', b'RPI5XNU:BL33:ENTRY EL=', PREFIX + EXPECTED[0],
               PREFIX + EXPECTED[-1], TRANSFER, RAMROOT, SHELL)
    positions = [normalized.index(marker) for marker in ordered]
    if positions != sorted(positions): raise ValueError('Boot evidence out of order')
    forbidden = (b'panic(cpu', b'REJECTED', b'EXCEPTION', b'RPI5XNU:BL33:STOP',
                 b'RPI5XNU:SD:', b'RPI5XNU:HFS:', b'RPI5XNU:HFSRW:', b'RPI5XNU:HFSWRITE:')
    if any(marker in normalized for marker in forbidden): raise ValueError('Failure or storage activity in topology-only boot')
    if b'xnu:/# ' not in normalized[positions[-1]:]: raise ValueError('Shell readiness lacks subsequent prompt')
    return dict(status='runtime_declarations_passed', declarations=[row.decode() for row in rows],
        kernel_reached_shell_ready=True, shell_commands_tested=False,
        pcie_mmio_enabled=False, dma_enabled=False, nic_ready=False,
        scope='One physical full-firmware-FDT declaration boot and shell readiness; no PCIe bring-up, traffic or durability proof')


def audit(capture, installed, package):
    state = json.loads((capture / 'state.json').read_text())
    raw = (capture / 'serial.bin').read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if (state.get('status') != 'finished' or type(state.get('transmitted_bytes')) is not int or state['transmitted_bytes'] != 0
            or state.get('bytes') != len(raw) or state.get('sha256') != sha or state.get('baud') != 115200
            or state.get('format') != '8N1' or state.get('device') != '/dev/cu.usbmodem102'):
        raise ValueError('Complete exact RX-only capture state/hash required')
    plan = json.loads((installed / 'plan.json').read_text())
    stage.validate_result(json.loads((installed / 'result.json').read_text()), plan)
    preflight = stage.package_report(package)
    if preflight['image_sha256'] != plan['new_image_sha256']: raise ValueError('Boot package differs from installed image')
    reboot = (installed / 'reboot.log').read_text()
    boot_time = datetime.fromisoformat(reboot.splitlines()[0].replace('Z', '+00:00'))
    if not datetime.fromisoformat(state['started_utc']) < boot_time < datetime.fromisoformat(state['ended_utc']):
        raise ValueError('Recorder was not armed across the recorded boot request')
    report = validate(raw)
    report.update(image_sha256=preflight['image_sha256'], serial_sha256=sha, bytes=len(raw),
        transmitted_bytes=0, started_utc=state['started_utc'], ended_utc=state['ended_utc'],
        installer_result_sha256=stage.terminal.sha256(installed / 'result.json'),
        loader_manifest_sha256=preflight['loader_manifest_sha256'])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('capture', 'installed', 'package'): parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.capture, args.installed, args.package), indent=2))


if __name__ == '__main__': main()
