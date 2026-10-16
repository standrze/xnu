/* SPDX-License-Identifier: BSD-2-Clause
 * Host diagnostic only. Input may be a filtered Linux tree, not firmware FDT.
 */
#include "fdt.h"
#include <stdio.h>
#include <stdlib.h>
int main(int argc, char **argv) {
    if(argc!=2) return 2;
    FILE *f=fopen(argv[1],"rb"); if(!f) return 2;
    if(fseek(f,0,SEEK_END)) return 2;
    long n=ftell(f); if(n<=0 || n>16*1024*1024) return 2;
    rewind(f); void *b=malloc((size_t)n); if(!b) return 2;
    if(fread(b,1,(size_t)n,f)!=(size_t)n) return 2;
    fclose(f);
    struct rpi5_fdt_memory ram;
    struct rpi5_reservation_plan plan;
    struct rpi5_fdt_cpus cpus;
    struct rpi5_uart_clocks clocks;
    struct rpi5_range rng;
    int failures=0,rc;
#define CHECK(label, call) do { rc=(call); printf(label "=%d\n",rc); failures+=(rc!=0); } while(0)
    CHECK("structure",rpi5_fdt_structure(b,(size_t)n));
    CHECK("phandles",rpi5_fdt_phandles(b,(size_t)n));
    CHECK("memory",rpi5_fdt_memory(b,(size_t)n,&ram));
    CHECK("reservations",rpi5_fdt_reservation_plan(b,(size_t)n,&plan));
    CHECK("cpus",rpi5_fdt_cpus(b,(size_t)n,&cpus));
    CHECK("psci",rpi5_fdt_psci_smc(b,(size_t)n));
    CHECK("mmio",rpi5_fdt_probe_mmio(b,(size_t)n));
    CHECK("timer",rpi5_fdt_probe_timer(b,(size_t)n));
    CHECK("uart_clocks",rpi5_fdt_uart_clocks(b,(size_t)n,&clocks));
    CHECK("rng_binding",rpi5_fdt_rng200(b,(size_t)n,&rng));
    free(b); return failures?1:0;
}
