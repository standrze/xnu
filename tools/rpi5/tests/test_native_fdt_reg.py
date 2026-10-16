# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class NativeRegTests(unittest.TestCase):
    def test_pinned_board_translations(self):
        blob = ROOT / "build/rpi5/bcm2712-rpi-5-b-2768f610.dtb"
        if not blob.exists():
            self.skipTest("pinned firmware DTB not downloaded")
        source = r'''
#include "fdt.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv) {
    assert(argc==2); FILE *f=fopen(argv[1],"rb"); assert(f);
    assert(!fseek(f,0,SEEK_END)); long n=ftell(f); assert(n>0); rewind(f);
    unsigned char *b=malloc((size_t)n); assert(b); assert(fread(b,1,(size_t)n,f)==(size_t)n); fclose(f);
    struct rpi5_ranges out, prior; memset(&prior,0xa5,sizeof prior);
    assert(!rpi5_fdt_probe_mmio(b,(size_t)n));
    assert(!rpi5_fdt_uart_irq(b,(size_t)n));
    struct rpi5_fdt_property uart_irq, root_parent, gic_cells;
    assert(!rpi5_fdt_property(b,(size_t)n,"/soc@107c000000/serial@7d001000","interrupts",&uart_irq));
    assert(uart_irq.length==12);
    for (unsigned i=0;i<uart_irq.length;i++) {
        b[uart_irq.offset+i]^=1;
        assert(rpi5_fdt_uart_irq(b,(size_t)n)==-1);
        b[uart_irq.offset+i]^=1;
    }
    assert(!rpi5_fdt_property(b,(size_t)n,"/","interrupt-parent",&root_parent));
    b[root_parent.offset+3]^=1;
    assert(rpi5_fdt_uart_irq(b,(size_t)n)==-1);
    b[root_parent.offset+3]^=1;
    assert(!rpi5_fdt_property(b,(size_t)n,"/soc@107c000000/interrupt-controller@7fff9000","#interrupt-cells",&gic_cells));
    b[gic_cells.offset+3]^=1;
    assert(rpi5_fdt_uart_irq(b,(size_t)n)==-1);
    b[gic_cells.offset+3]^=1;
    struct rpi5_range watchdog, saved_watchdog={123,456};
    assert(!rpi5_fdt_watchdog(b,(size_t)n,&watchdog));
    assert(watchdog.start==0x107d200000ull && watchdog.end==0x107d200308ull);
    struct rpi5_fdt_property wdreg;
    assert(!rpi5_fdt_property(b,(size_t)n,"/soc@107c000000/watchdog@7d200000","reg",&wdreg));
    for (unsigned i=0;i<wdreg.length;i++) {
        b[wdreg.offset+i]^=1; watchdog=saved_watchdog;
        assert(rpi5_fdt_watchdog(b,(size_t)n,&watchdog)==-1);
        assert(!memcmp(&watchdog,&saved_watchdog,sizeof watchdog));
        b[wdreg.offset+i]^=1;
    }
    assert(rpi5_fdt_watchdog(b,(size_t)n,0)==-1);
    struct rpi5_range rng, prior_rng={123,456};
    assert(!rpi5_fdt_rng200(b,(size_t)n,&rng));
    assert(rng.start==0x107d208000ull && rng.end==0x107d208028ull);
    struct rpi5_fdt_property rng_reg;
    assert(!rpi5_fdt_property(b,(size_t)n,"/soc@107c000000/rng@7d208000","reg",&rng_reg));
    b[rng_reg.offset+7]^=1; rng=prior_rng;
    assert(rpi5_fdt_rng200(b,(size_t)n,&rng)==-1 && !memcmp(&rng,&prior_rng,sizeof rng));
    b[rng_reg.offset+7]^=1;
    assert(!rpi5_fdt_phandles(b,(size_t)n));
    struct rpi5_fdt_property handle_a, handle_b;
    assert(!rpi5_fdt_property(b,(size_t)n,"/clocks/clk-uart","phandle",&handle_a));
    assert(!rpi5_fdt_property(b,(size_t)n,"/clocks/clk-vpu","phandle",&handle_b));
    unsigned char handle_saved[4]; memcpy(handle_saved,b+handle_b.offset,4);
    memcpy(b+handle_b.offset,b+handle_a.offset,4);
    assert(rpi5_fdt_phandles(b,(size_t)n)==-1);
    memcpy(b+handle_b.offset,handle_saved,4);
    assert(!rpi5_fdt_probe_timer(b,(size_t)n));
    struct rpi5_uart_clocks clocks, old={123,456};
    assert(!rpi5_fdt_uart_clocks(b,(size_t)n,&clocks));
    assert(clocks.uart_hz==9216000 && clocks.apb_hz==750000000);
    struct rpi5_fdt_property rate;
    assert(!rpi5_fdt_property(b,(size_t)n,"/clocks/clk-uart","clock-frequency",&rate));
    unsigned char saved[4]; memcpy(saved,b+rate.offset,4);
    /* Live 8 GB board, 2026-09-06: firmware declares 44.2368 MHz.
     * This mutation tests rate decoding, not the complete live clock graph. */
    const unsigned char live_rate[4]={0x02,0xa3,0x00,0x00};
    memcpy(b+rate.offset,live_rate,4);
    assert(!rpi5_fdt_uart_clocks(b,(size_t)n,&clocks));
    assert(clocks.uart_hz==44236800 && clocks.apb_hz==750000000);
    memset(b+rate.offset,0,4); clocks=old;
    assert(rpi5_fdt_uart_clocks(b,(size_t)n,&clocks)==-1 && !memcmp(&clocks,&old,sizeof old));
    memcpy(b+rate.offset,saved,4);
    struct rpi5_fdt_property timer_prop;
    assert(!rpi5_fdt_property(b,(size_t)n,"/timer","interrupts",&timer_prop));
    b[timer_prop.offset+31]^=1;
    assert(rpi5_fdt_probe_timer(b,(size_t)n)==-1);
    b[timer_prop.offset+31]^=1;
    assert(!rpi5_fdt_reg(b,(size_t)n,"/soc@107c000000/serial@7d001000",&out));
    assert(out.count==1 && out.extent[0].start==0x107d001000ull && out.extent[0].end==0x107d001200ull);
    assert(!rpi5_fdt_reg(b,(size_t)n,"/soc@107c000000/interrupt-controller@7fff9000",&out));
    assert(out.count==4 && out.extent[0].start==0x107fff9000ull && out.extent[1].start==0x107fffa000ull);
    struct rpi5_fdt_property p;
    assert(!rpi5_fdt_property(b,(size_t)n,"/soc@107c000000","ranges",&p));
    memset(b+p.offset,0,p.length); out=prior;
    assert(rpi5_fdt_probe_mmio(b,(size_t)n)==-1);
    assert(rpi5_fdt_reg(b,(size_t)n,"/soc@107c000000/serial@7d001000",&out)==-1 && !memcmp(&out,&prior,sizeof out));
    free(b); return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory); (path/"test.c").write_text(source)
            subprocess.run(["xcrun","clang","-Wall","-Wextra","-Werror","-fsanitize=address,undefined",
                            "-I"+str(ROOT/"loader/rpi5"),str(path/"test.c"),str(ROOT/"loader/rpi5/fdt.c"),
                            str(ROOT/"loader/rpi5/fdt_reg.c"),"-o",str(path/"test")],check=True)
            subprocess.run([str(path/"test"),str(blob)],check=True)
