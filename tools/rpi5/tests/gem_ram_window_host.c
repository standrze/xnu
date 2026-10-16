/* SPDX-License-Identifier: BSD-2-Clause */
/* Real fresh-FDT decoder/encoder, not live hardware evidence. */
#include "rpi5_gem_ram_window.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define BAD(field) do { struct rpi5_pcie_window_plan q=p; q.field^=1; \
    assert(rpi5_gem_ram_window_match(&f,&q)); cases++; } while(0)
int main(int argc,char **argv)
{
    assert(argc==2);
    FILE *file=fopen(argv[1],"rb");assert(file);
    assert(!fseek(file,0,SEEK_END));long n=ftell(file);assert(n>40);rewind(file);
    void *blob=malloc((size_t)n);assert(blob);
    assert(fread(blob,1,(size_t)n,file)==(size_t)n && !fclose(file));
    struct rpi5_pcie_fdt f;assert(!rpi5_fdt_pcie_rp1(blob,n,&f));free(blob);
    struct rpi5_pcie_window_plan p,all;
    assert(!rpi5_pcie_windows_plan(&f,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES,&all));
    assert(!rpi5_gem_ram_window_plan(&f,&p));assert(!rpi5_gem_ram_window_match(&f,&p));
    assert(!p.inbound[0].bar_lo && p.inbound[1].bar_lo==21 && p.inbound[2].bar_lo==0xfffff000);
    assert(p.inbound[1].bar_hi==16 && p.inbound[1].remap_lo==1 && !p.inbound[1].remap_hi);
    assert(rpi5_gem_ram_window_match(&f,&all));
    all.inbound[0].bar_lo&=~31u;all.inbound[2].bar_lo&=~31u;
    assert(!rpi5_gem_ram_window_match(&f,&all));
    unsigned cases=0;
    for(unsigned i=0;i<3;i++) {
        BAD(inbound[i].cpu_base);BAD(inbound[i].pci_base);BAD(inbound[i].size);
        BAD(inbound[i].bar_lo);BAD(inbound[i].bar_hi);BAD(inbound[i].remap_lo);BAD(inbound[i].remap_hi);
        for(unsigned bit=0;bit<32;bit++) {
            struct rpi5_pcie_window_plan q=p;q.inbound[i].bar_lo^=UINT32_C(1)<<bit;
            assert(rpi5_gem_ram_window_match(&f,&q));cases++;
        }
    }
    for(unsigned i=0;i<2;i++) {
        BAD(outbound[i].cpu_base);BAD(outbound[i].declared_end);BAD(outbound[i].decode_end);
        BAD(outbound[i].pci_base);BAD(outbound[i].size);BAD(outbound[i].pci_lo);BAD(outbound[i].pci_hi);
        BAD(outbound[i].base_limit);BAD(outbound[i].base_hi);BAD(outbound[i].limit_hi);BAD(outbound[i].padding_bytes);
    }
    for(unsigned i=0;i<13;i++) {
        struct rpi5_pcie_fdt q=f;
        switch(i) {
        case 0:q.dma_count--;break;case 1:q.rp1_dma_count--;break;
        case 2:q.dma[1].space^=1;break;case 3:q.dma[1].cpu_base++;break;
        case 4:q.dma[1].pci_base^=0x1000000000;break;case 5:q.dma[1].size>>=1;break;
        case 6:q.rp1_dma[0].space^=1;break;case 7:q.rp1_dma[0].pci_base++;break;
        case 8:q.rp1_dma[0].rp1_base=0;break;case 9:q.rp1_dma[0].size>>=1;break;
        case 10:q.bridge_regs.start++;break;case 11:q.outbound[0].size--;break;
        case 12:q.dma[0].cpu_base=0;break;
        }
        struct rpi5_pcie_window_plan out,before;memset(&out,0xa5,sizeof out);memcpy(&before,&out,sizeof out);
        assert(rpi5_gem_ram_window_plan(&q,&out) && !memcmp(&out,&before,sizeof out));
        assert(rpi5_gem_ram_window_match(&q,&p));cases++;
    }
    assert(rpi5_gem_ram_window_plan(0,&p) && rpi5_gem_ram_window_plan(&f,0));
    assert(rpi5_gem_ram_window_match(0,&p) && rpi5_gem_ram_window_match(&f,0));
    printf("GEM_RAM_WINDOW_PASS NEGATIVES=%u NO_HARDWARE=1\n",cases);return 0;
}
