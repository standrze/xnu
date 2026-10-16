from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class BootUartTests(unittest.TestCase):
    def test_bounded_polling_and_byte_write(self):
        code = r'''
#include "rpi5_boot_uart.h"
#include <assert.h>
int main(void) {
    static _Alignas(16384) uint64_t root[2048];
    for (unsigned i=0;i<2048;i++) root[i]=0xdeadbeef;
    assert(!rpi5_boot_uart_root_init(root, 1));
    for (unsigned i=0;i<2048;i++) assert(root[i]==0xdeadbeef);
    assert(!rpi5_boot_uart_root_init(root, 1ull<<40));
    assert(!rpi5_boot_uart_root_init(root+1, 0x71c0000));
    assert(rpi5_boot_uart_root_init(root, 0x71c0000));
    for (unsigned i=0;i<2048;i++) assert(root[i]==(i==1 ? 0x71c0003 : 0));
    uint32_t regs[8] = {0};
    assert(rpi5_boot_uart_mark_at((uintptr_t)regs, 'I') == 1);
    assert(regs[0] == 'I');
    for (unsigned i=1;i<8;i++) assert(regs[i] == 0);
    regs[6] = 1u << 5;
    assert(rpi5_boot_uart_mark_at((uintptr_t)regs, 'S') == 0);
    assert(regs[0] == 'I');
    regs[6] = 1u << 3;
    assert(rpi5_boot_uart_mark_at((uintptr_t)regs, 'T') == 0);
    assert(regs[0] == 'T');
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.c').write_text(code)
            subprocess.run(['xcrun', 'clang', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined',
                            '-I' + str(ROOT / 'osfmk/arm64'), str(path / 'test.c'),
                            '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], check=True, timeout=5)

    def test_no_checkpoint_after_vm_takeover(self):
        source = (ROOT / 'osfmk/arm/arm_init.c').read_text()
        entry = source.split('arm_init(\n', 1)[1]
        before, after = entry.split('arm_vm_init(xmaxmem, args);', 1)
        self.assertNotIn('RPI5_BOOT_MARK(', after)
        self.assertIn('ml_io_map(0x107d000000ull, 0x4000)', after)
        self.assertIn('rpi5_boot_uart_mark_at(rpi5_uart_kva + 0x1000, stage)', after)
        positions = [after.index("RPI5_POST_VM_MARK('" + stage + "')") for stage in 'RPUNQF']
        self.assertEqual(positions, sorted(positions))
        call = after.index('kprintf("kprintf initialized\\n");')
        self.assertLess(after.index("RPI5_POST_VM_MARK(disable_kprintf_output ? '1' : '0')"), call)
        self.assertLess(call, positions[-1])
        for stage in 'ISTBDELHKW':
            self.assertEqual(before.count("RPI5_BOOT_MARK('" + stage + "')"), 1)

    def test_vm_checkpoints_stop_before_ttbr0_invalidation(self):
        source = (ROOT / 'osfmk/arm64/arm_vm_init.c').read_text()
        entry = source.split('arm_vm_init(uint64_t memory_size, boot_args * args)', 1)[1]
        before, after = entry.rsplit('set_mmu_ttb(invalid_ttep & TTBR_BADDR_MASK);', 1)
        self.assertNotIn('RPI5_VM_MARK(', after)
        positions = [before.index("RPI5_VM_MARK('" + stage + "')") for stage in 'abcdefghijklmnoz']
        self.assertEqual(positions, sorted(positions))
        self.assertLess(before.index('set_mmu_ttb_alternate(cpu_ttep'), positions[-1])
        self.assertIn('set_mmu_ttb(rpi5_uart_root_pa & TTBR_BADDR_MASK);', before)
        self.assertLess(after.index('flush_mmu_tlb();'), after.index('enable_preemption();'))
