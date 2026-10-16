# SPDX-License-Identifier: BSD-2-Clause
"""Full original-FDT option parsing and malformed/unsupported declarations."""
import copy
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from tools.rpi5.tests.test_pcie_fdt import _synthetic_tree, _encode_fdt, _cells, PINNED, PINNED_SHA256

ROOT = Path(__file__).resolve().parents[3]
LOADER = ROOT / 'loader/rpi5'


class PCIeProfileTests(unittest.TestCase):
    def test_real_decoder_full_original_options_and_atomic_rejection(self):
        root = _synthetic_tree()
        def modified(properties):
            tree = copy.deepcopy(root)
            bridge = tree['children'][1]['children'][0]
            bridge['properties'].update(properties)
            return _encode_fdt(tree)
        cases = [(modified({}), 0, 0, 0, 0, 0)]
        cases += [(modified({'brcm,clkreq-mode': value}), 0, 0, 0, kind, 0)
                  for kind, value in enumerate((b'safe\0', b'default\0', b'no-l1ss\0'), 1)]
        cases += [(modified({'aspm-no-l0s': b'', 'brcm,vdm-qos-map': bytes((8,8,8,9,10,10,11,11))}),
                   0, 2, 0xbbaa9888, 0, 1),
                  (modified({'brcm,fifo-qos-map': bytes((1,2,3,4)), 'brcm,tperst-clk-ms': _cells(0)}),
                   0, 1, 0x4321, 0, 0),
                  (modified({'brcm,vdm-qos-map': bytes([15]*8)}), 0, 2, 0xffffffff, 0, 0)]
        for name in ('brcm,enable-ssc', 'brcm,scb-sizes', 'clocks', 'clock-names', 'power-domains',
                     'power-domain-names', 'iommus', 'iommu-map', 'iommu-map-mask'):
            cases.append((modified({name: b''}), -4, 0, 0, 0, 0))
        for value in (_cells(1), _cells(100), _cells(0xffffffff)):
            cases.append((modified({'brcm,tperst-clk-ms': value}), -4, 0, 0, 0, 0))
        for name, values in (
            ('brcm,clkreq-mode', (b'', b'safe', b'SAFE\0', b'safe\0default\0', b'unknown\0', b'\0')),
            ('brcm,tperst-clk-ms', (b'', b'\0', bytes(3), bytes(8))),
            ('aspm-no-l0s', (_cells(0), b'\0')),
            ('brcm,fifo-qos-map', (b'', bytes(3), bytes(5), _cells(1,2,3,4), bytes((0,0,0,16)))),
            ('brcm,vdm-qos-map', (b'', bytes(7), bytes(9), bytes((0,0,0,0,0,0,0,255))))):
            for value in values: cases.append((modified({name: value}), -3, 0, 0, 0, 0))
        cases.append((modified({'brcm,fifo-qos-map': bytes(4), 'brcm,vdm-qos-map': bytes(8)}),
                      -3, 0, 0, 0, 0))
        for name, value in (('num-lanes', 1), ('max-link-speed', 3)):
            cases.append((modified({name: _cells(value)}), -2, 0, 0, 0, 0))
        for data in (b'not FDT', modified({})[:-1]): cases.append((data, -2, 0, 0, 0, 0))
        # The existing parser rejects duplicates, not just the first property.
        data = bytearray(modified({'brcm,fifo-qos-map': bytes(4), 'brcm,vdm-qos-map': bytes(8)}))
        strings = struct.unpack_from('>I', data, 12)[0]
        fifo = data.index(b'brcm,fifo-qos-map\0', strings) - strings
        vdm = data.index(b'brcm,vdm-qos-map\0', strings) - strings
        marker = _cells(3, 8, vdm)
        position = data.index(marker, 56)
        struct.pack_into('>I', data, position + 8, fifo)
        cases.append((bytes(data), -3, 0, 0, 0, 0))
        if PINNED.exists():
            self.assertEqual(hashlib.sha256(PINNED.read_bytes()).hexdigest(), PINNED_SHA256)
            cases.append((PINNED.read_bytes(), 0, 2, 0xbbaa9888, 0, 1))
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary); program = work / 'profile'
            subprocess.run(['xcrun', 'clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-I', str(LOADER),
                str(Path(__file__).with_name('pcie_profile_host.c')),
                *(str(LOADER / (name + '.c')) for name in ('pcie_profile', 'pcie_fdt', 'fdt', 'fdt_reg')),
                '-o', str(program)], check=True, capture_output=True, timeout=60)
            for i, (data, *expected) in enumerate(cases):
                path = work / (str(i) + '.dtb'); path.write_bytes(data)
                result = subprocess.run([str(program), str(path), *map(str, expected)],
                                        capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, (i, expected, result.stderr))
                self.assertEqual(result.stdout, b'PCIE_PROFILE_HOST_PASS NO_MMIO=1\n')


if __name__ == '__main__':
    unittest.main()
