# SPDX-License-Identifier: BSD-2-Clause
import platform
from pathlib import Path
import subprocess
import tempfile
import unittest
import struct

ROOT = Path(__file__).parents[3]


@unittest.skipUnless(platform.system() == "Darwin", "requires native arm64 compiler")
class LoaderUARTTests(unittest.TestCase):
    def test_native_register_model_and_freestanding_dependencies(self):
        source = r'''
#include "uart.h"
#include <assert.h>
#include <string.h>
int main(void) {
    uint32_t regs[20] = {0};
    uintptr_t base = (uintptr_t)regs;
    assert(rpi5_uart_putc(0, 1, 1) == RPI5_UART_INVALID);
    assert(rpi5_uart_putc(base, 1, 0) == RPI5_UART_INVALID);
    assert(rpi5_uart_putc(base, 1, 1) == RPI5_UART_DISABLED);
    regs[12] = 0x101; regs[6] = 1u << 5; regs[0] = 0xdead;
    assert(rpi5_uart_putc(base, 'A', 8) == RPI5_UART_TIMEOUT);
    assert(regs[0] == 0xdead && regs[12] == 0x101);
    regs[6] = 0;
    assert(rpi5_uart_putc(base, 'A', 1) == RPI5_UART_OK);
    assert(regs[0] == 'A' && regs[12] == 0x101);
    assert(rpi5_uart_drain(base, 2) == RPI5_UART_TIMEOUT);
    regs[6] = (1u << 7) | (1u << 3);
    assert(rpi5_uart_drain(base, 2) == RPI5_UART_TIMEOUT);
    regs[6] = 1u << 7;
    assert(rpi5_uart_drain(base, 1) == RPI5_UART_OK);
    regs[9]=5; regs[10]=17; regs[11]=0x70;
    struct rpi5_uart_snapshot snapshot={0};
    assert(rpi5_uart_snapshot(base,&snapshot)==RPI5_UART_OK);
    assert(snapshot.control==0x101 && snapshot.flags==0x80 &&
        snapshot.integer_divisor==5 && snapshot.fractional_divisor==17 && snapshot.line_control==0x70);
    assert(regs[9]==5 && regs[10]==17 && regs[11]==0x70 && regs[0]=='A');
    assert(rpi5_uart_snapshot(0,&snapshot)==RPI5_UART_INVALID && snapshot.integer_divisor==5);
    assert(rpi5_uart_snapshot(base+1,&snapshot)==RPI5_UART_INVALID);
    assert(rpi5_uart_snapshot(UINTPTR_MAX-3,&snapshot)==RPI5_UART_INVALID);
    assert(rpi5_uart_snapshot(base,0)==RPI5_UART_INVALID);
    struct rpi5_uart_snapshot nominal={0x101,0,5,0,0x70};
    assert(rpi5_uart_check_nominal(&nominal,9216000,115200)==RPI5_UART_OK);
    nominal.integer_divisor=24;
    assert(rpi5_uart_check_nominal(&nominal,44236800,115200)==RPI5_UART_OK);
    assert(rpi5_uart_check_nominal(&nominal,9216000,115200)==RPI5_UART_INVALID);
    nominal.line_control=0x60;
    assert(rpi5_uart_check_nominal(&nominal,44236800,115200)==RPI5_UART_OK);
    for (unsigned bit=0;bit<32;bit++) {
        if (bit==4) continue; /* FIFO is optional. */
        nominal.line_control=0x60u^(1u<<bit);
        assert(rpi5_uart_check_nominal(&nominal,44236800,115200)==RPI5_UART_INVALID);
    }
    nominal.line_control=0x70;
    for (unsigned bit=0;bit<2;bit++) {
        nominal.control=bit ? 0x100 : 1;
        assert(rpi5_uart_check_nominal(&nominal,44236800,115200)==RPI5_UART_DISABLED);
    }
    const unsigned forbidden[]={7,14,15};
    for (unsigned i=0;i<3;i++) {
        nominal.control=0x101|(1u<<forbidden[i]);
        assert(rpi5_uart_check_nominal(&nominal,44236800,115200)==RPI5_UART_INVALID);
    }
    nominal.control=0x101; nominal.integer_divisor=1; nominal.fractional_divisor=32;
    assert(rpi5_uart_check_nominal(&nominal,2764800,115200)==RPI5_UART_OK);
    assert(rpi5_uart_check_nominal(&nominal,2764801,115200)==RPI5_UART_INVALID);
    nominal.fractional_divisor=64;
    assert(rpi5_uart_check_nominal(&nominal,2764800,115200)==RPI5_UART_INVALID);
    nominal.fractional_divisor=0; nominal.integer_divisor=0;
    assert(rpi5_uart_check_nominal(&nominal,9216000,115200)==RPI5_UART_INVALID);
    nominal.integer_divisor=65536;
    assert(rpi5_uart_check_nominal(&nominal,9216000,115200)==RPI5_UART_INVALID);
    nominal.integer_divisor=65535; nominal.fractional_divisor=63;
    assert(rpi5_uart_check_nominal(&nominal,UINT32_MAX,UINT32_MAX)==RPI5_UART_INVALID);
    assert(rpi5_uart_check_nominal(&nominal,0,115200)==RPI5_UART_INVALID);
    assert(rpi5_uart_check_nominal(&nominal,9216000,0)==RPI5_UART_INVALID);
    assert(rpi5_uart_check_nominal(0,9216000,115200)==RPI5_UART_INVALID);
    regs[9]=23; regs[10]=55; regs[11]=0x70; regs[12]=0x301;
    regs[6]=0x90;
    uint32_t saved[20];
#define UNCHANGED(call, expected) do { \
    memcpy(saved, regs, sizeof regs); \
    assert((call)==(expected)); \
    assert(memcmp(saved, regs, sizeof regs)==0); \
} while (0)
    UNCHANGED(rpi5_uart_set_exact(0,44236800,115200,8),RPI5_UART_INVALID);
    UNCHANGED(rpi5_uart_set_exact(base+1,44236800,115200,8),RPI5_UART_INVALID);
    UNCHANGED(rpi5_uart_set_exact(UINTPTR_MAX-3,44236800,115200,8),RPI5_UART_INVALID);
    UNCHANGED(rpi5_uart_set_exact(base,44236800,115200,0),RPI5_UART_INVALID);
    UNCHANGED(rpi5_uart_set_exact(base,0,115200,8),RPI5_UART_INVALID);
    UNCHANGED(rpi5_uart_set_exact(base,44236800,0,8),RPI5_UART_INVALID);
    UNCHANGED(rpi5_uart_set_exact(base,44000000,115200,8),RPI5_UART_INVALID);
    UNCHANGED(rpi5_uart_set_exact(base,1,1,8),RPI5_UART_INVALID);
    UNCHANGED(rpi5_uart_set_exact(base,UINT32_MAX,1,8),RPI5_UART_INVALID);
    regs[14]=1;
    UNCHANGED(rpi5_uart_set_exact(base,44236800,115200,8),RPI5_UART_INVALID);
    regs[14]=0; regs[18]=1;
    UNCHANGED(rpi5_uart_set_exact(base,44236800,115200,8),RPI5_UART_INVALID);
    regs[18]=0; regs[12]=0x300;
    UNCHANGED(rpi5_uart_set_exact(base,44236800,115200,8),RPI5_UART_DISABLED);
    regs[12]=0x301; regs[11]=0x72;
    UNCHANGED(rpi5_uart_set_exact(base,44236800,115200,8),RPI5_UART_INVALID);
    regs[11]=0x70; regs[6]=0x98;
    UNCHANGED(rpi5_uart_set_exact(base,44236800,115200,8),RPI5_UART_TIMEOUT);
    regs[6]=0x10;
    UNCHANGED(rpi5_uart_set_exact(base,44236800,115200,8),RPI5_UART_TIMEOUT);
    regs[6]=0x90;
    memcpy(saved,regs,sizeof regs);
    assert(rpi5_uart_set_exact(base,44236800,115200,8)==RPI5_UART_OK);
    saved[9]=24; saved[10]=0;
    assert(memcmp(saved,regs,sizeof regs)==0);
    UNCHANGED(rpi5_uart_set_exact(base,44236800,115200,8),RPI5_UART_OK);
    assert(rpi5_uart_set_exact(base,2764800,115200,8)==RPI5_UART_OK);
    assert(regs[9]==1 && regs[10]==32 && regs[12]==0x301 && regs[11]==0x70);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "test.c").write_text(source)
            obj = path / "uart.o"
            subprocess.run(["xcrun", "clang", "-arch", "arm64", "-mcpu=cortex-a76",
                            "-ffreestanding", "-fno-stack-protector", "-Wall", "-Wextra", "-Werror",
                            "-c", str(ROOT / "loader/rpi5/uart.c"), "-o", str(obj)], check=True)
            self.assertEqual(subprocess.check_output(["xcrun", "nm", "-u", str(obj)], text=True).strip(), "")
            subprocess.run(["xcrun", "clang", "-I" + str(ROOT / "loader/rpi5"),
                            str(path / "test.c"), str(obj), "-o", str(path / "test")], check=True)
            subprocess.run([str(path / "test")], check=True)
            elf = path / "uart-elf.o"
            subprocess.run(["xcrun", "clang", "--target=aarch64-none-elf", "-mcpu=cortex-a76",
                            "-ffreestanding", "-fno-stack-protector", "-nostdlib", "-Wall", "-Wextra", "-Werror",
                            "-c", str(ROOT / "loader/rpi5/uart.c"), "-o", str(elf)], check=True)
            header = elf.read_bytes()[:64]
            self.assertEqual(header[:7], b"\x7fELF\x02\x01\x01")
            self.assertEqual(struct.unpack_from("<HH", header, 16), (1, 183))
