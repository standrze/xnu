# SPDX-License-Identifier: BSD-2-Clause
"""Exercise actual private UBUS/QoS/clock cores; callback hardware models only."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.rpi5 import pcie_axi_reserved_profile as overlay

TESTS = Path(__file__).resolve().parent
ROOT = overlay.ROOT


class AXIReservedTests(unittest.TestCase):
    def native(self, folder, name, body, source=None):
        c, binary = folder / (name + '.c'), folder / name
        c.write_text(body)
        command = ['xcrun', 'clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
            '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
            '-I', folder / 'overlay', '-I', ROOT / 'loader/rpi5', '-I', ROOT / 'iokit/Kernel', c]
        if source:
            command.append(folder / 'overlay' / source)
        result = subprocess.run([*map(str, command), '-o', str(binary)], capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        result = subprocess.run([binary], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stderr, b'')
        return result.stdout

    def test_complete_capability_truth_table(self):
        body = r'''
#include "rpi5_axi_reserved_profile.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    for (uint32_t value=0; value<65536; value++) {
        unsigned f=(value>>11)&7, count=value&63;
        int available=(f==7 || f==5 || f==0) && !(value&128);
        int configured=available && (f==7 || count==15);
        assert(rpi5_axi_capabilities_valid(value)==available);
        assert(rpi5_axi_configured(value)==configured);
    }
    assert(rpi5_axi_capabilities_valid(0x60));
    assert(!rpi5_axi_configured(0x60));
    assert(rpi5_axi_configured(0x4f));
    assert(!rpi5_axi_configured(0xcf));
    assert(!rpi5_axi_configured(UINT32_MAX));
    puts("AXI_EXACT_PROFILES_65536_PASS"); return 0;
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary); overlay.emit(p / 'overlay')
            self.assertEqual(self.native(p, 'profiles', body), b'AXI_EXACT_PROFILES_65536_PASS\n')

    def test_actual_ubus_three_shapes_and_all_existing_failures(self):
        body = (TESTS / 'pcie_ubus_host.c').read_text()
        body = overlay.once(body, 'reserved < 2', 'reserved < 3')
        body = overlay.once(body, 'm->reserved ? 0x1000u : 0u',
            'm->reserved == 2 ? 0x3800u : m->reserved ? 0x1000u : 0u')
        body = overlay.once(body, 'm->axi = 0x900080ff;', 'm->axi = reserved == 2 ? 0x60 : 0x900080ff;')
        body = overlay.once(body, 'uint32_t wanted = (0x900080ffu & ~0x80u) | 0x3800;',
            'uint32_t initial = reserved == 2 ? 0x60 : 0x900080ffu;\n'
            '        uint32_t wanted = (initial & ~0x80u) | 0x3800;')
        body = overlay.once(body, '(wanted & ~(0x1000u | 0x3fu)) | 15',
            '(wanted & ~((reserved == 2 ? 0x3800u : 0x1000u) | 0x3fu)) | 15')
        body = overlay.once(body, 'out.axi_before == 0x900080ff', 'out.axi_before == initial')
        body = body.replace('== reserved', '== (reserved != 0)').replace('6+reserved', '6+(reserved != 0)')
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary); overlay.emit(p / 'overlay')
            self.assertEqual(self.native(p, 'ubus', body, 'pcie_ubus.c'), b'PCIE_UBUS_HOST_PASS\n')

    def test_actual_downstream_qos_and_clock_all_failures_in_three_profiles(self):
        expected = {
            'qos': b'PCIE_QOS_HOST_PASS CALLBACK_FAILURES=425 DEPENDENCY_FAILURES=425 NO_MMIO=1\n',
            'clock': b'PCIE_CLOCK_HOST_PASS CALLBACK_FAILURES=1124 DEPENDENCY_FAILURES=1124 READ_FAILURES=280 NO_MMIO=1\n',
        }
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary); overlay.emit(p / 'overlay')
            for kind in ('qos', 'clock'):
                original = (TESTS / ('pcie_' + kind + '_host.c')).read_text()
                for value in ('0x3800', '0x280f', '0x4f'):
                    body = overlay.once(original, 'm->axi = ' + ('0x2800' if kind == 'qos' else '0x3800'),
                        'm->axi = ' + value)
                    body = overlay.once(body, 'm.axi &= ~0x2000u;', 'm.axi ^= 0x2000u;')
                    self.assertEqual(self.native(p, kind + value, body, 'pcie_' + kind + '.c'), expected[kind])

    def test_observed_c1_rejects_every_single_bit_readback_corruption(self):
        body = (TESTS / 'pcie_ubus_host.c').read_text()
        body = overlay.once(body, 'm->reserved ? 0x1000u : 0u', '0x3800u')
        body = overlay.once(body, 'm->axi = 0x900080ff;', 'm->axi = 0x60;')
        body = overlay.once(body, 'static int read32(', 'static unsigned corrupt_at;\nstatic uint32_t corrupt_mask;\nstatic int read32(')
        body = overlay.once(body, '    if (m->calls == m->bad_at)',
            '    if (m->calls == corrupt_at) *value ^= corrupt_mask;\n    if (m->calls == m->bad_at)')
        body = overlay.once(body, 'int main(void)', 'int preserved_original_main(void)')
        body += r'''
int main(void) {
    struct model m;
    struct rpi5_pcie_ubus session;
    struct rpi5_pcie_serdes serdes;
    struct rpi5_pcie_rescal rescal;
    struct rpi5_pcie_reset reset;
    for (unsigned at=16; at<=19; at+=3) {
        for (unsigned bit=0; bit<32; bit++) {
            prepare(&m,&session,&serdes,&rescal,&reset,1);
            corrupt_at=at; corrupt_mask=UINT32_C(1)<<bit;
            rejects(&m,RPI5_PCIE_UBUS_READBACK);
            assert(m.calls==at);
        }
    }
    puts("AXI_C1_64_READBACK_CORRUPTIONS_REJECTED"); return 0;
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary); overlay.emit(p / 'overlay')
            self.assertEqual(self.native(p, 'c1_corruptions', body, 'pcie_ubus.c'),
                b'AXI_C1_64_READBACK_CORRUPTIONS_REJECTED\n')

    def test_each_actual_freestanding_core_adds_no_runtime_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary)
            for source in overlay.emit(p / 'overlay'):
                imports = []
                for variant, path in (('original', ROOT / 'loader/rpi5' / source.name), ('private', source)):
                    obj = p / (source.stem + '-' + variant + '.o')
                    subprocess.run(['xcrun', 'clang', '--target=aarch64-none-elf', '-mcpu=cortex-a76',
                        '-mstrict-align', '-mgeneral-regs-only', '-ffreestanding', '-fno-builtin',
                        '-fno-stack-protector', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-I', ROOT / 'loader/rpi5', '-c', path, '-o', obj], check=True, capture_output=True)
                    symbols = subprocess.check_output(['xcrun', 'llvm-nm', '--undefined-only', obj]).splitlines()
                    imports.append({line.split()[-1] for line in symbols if line.strip()})
                # Structure copies may use the kernel's existing memcpy provider.
                # Full kernel link closure is a separate candidate-package check.
                self.assertEqual(imports[0], imports[1])
                self.assertLessEqual(imports[1], {b'memcpy'})


if __name__ == '__main__':
    unittest.main()
