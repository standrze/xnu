# SPDX-License-Identifier: BSD-2-Clause
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_pcie_topology_boot as boot


def fixture():
    return b'\r\n'.join((b'Boot mode: SD (01)', b'RPI5XNU:BL33:ENTRY EL=0000000000000008',
        *(boot.PREFIX + row for row in boot.EXPECTED), boot.TRANSFER, boot.RAMROOT,
        boot.SHELL, b'xnu:/# '))


class TopologyBootTests(unittest.TestCase):
    def test_declarations_and_readiness_do_not_claim_network_or_shell_commands(self):
        result = boot.validate(fixture())
        self.assertEqual(result['status'], 'runtime_declarations_passed')
        for key in ('shell_commands_tested', 'pcie_mmio_enabled', 'dma_enabled', 'nic_ready'):
            self.assertFalse(result[key])

    def test_missing_changed_duplicate_reordered_or_failed_boot_refuses(self):
        raw = fixture()
        for marker in (boot.TRANSFER, boot.RAMROOT, boot.SHELL, *[boot.PREFIX + row for row in boot.EXPECTED]):
            with self.subTest(missing=marker), self.assertRaises(ValueError): boot.validate(raw.replace(marker, b''))
        faults = [raw + b'\n' + boot.PREFIX + boot.EXPECTED[-1], raw.replace(b'CPU_END=0000001000129310', b'CPU_END=0000001000120000'),
                  raw + b'\npanic(cpu 0)', raw + b'\nRPI5XNU:SD:START',
                  raw.replace(boot.TRANSFER, b'') + b'\n' + boot.TRANSFER,
                  raw + b'\nRPI5XNU:BL33:ENTRY EL=0000000000000008', b'', b'x'*(2*1024*1024+1)]
        for index, fault in enumerate(faults):
            with self.subTest(fault=index), self.assertRaises(ValueError): boot.validate(fault)


if __name__ == '__main__': unittest.main()
