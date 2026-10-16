/* SPDX-License-Identifier: BSD-2-Clause */
#include "display_mailbox_fdt.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define REQUIRE(x) do{if(!(x)){fprintf(stderr,"line %d\n",__LINE__);return 1;}}while(0)
int main(int argc,char **argv)
{
    REQUIRE(argc==3);FILE *f=fopen(argv[1],"rb");REQUIRE(f);
    REQUIRE(!fseek(f,0,SEEK_END));long bytes=ftell(f);REQUIRE(bytes>0 && bytes<=1048576);
    REQUIRE(!fseek(f,0,SEEK_SET));size_t n=(size_t)bytes;
    unsigned char *b=malloc(n+sizeof(struct rpi5_display_mailbox_fdt));REQUIRE(b);
    REQUIRE(fread(b,1,n,f)==n);fclose(f);
    struct rpi5_display_mailbox_fdt out,before;
    memset(&before,0x5a,sizeof before);out=before;
    int rc=rpi5_display_mailbox_from_fdt(b,n,&out);
    if(!strcmp(argv[2],"reject")){REQUIRE(rc && !memcmp(&out,&before,sizeof out));puts("MAILBOX_FDT REJECT ATOMIC=1");}
    else {
        REQUIRE(!rc && out.mmio.start==0x107c013880ull && out.mmio.end==0x107c0138c0ull);
        REQUIRE(out.reg_bus_address==0x7c013880 && out.reg_bytes==0x40);
        REQUIRE(out.ranges_child==0 && out.ranges_cpu==0x1000000000ull && out.ranges_bytes==0x80000000);
        REQUIRE(out.fdt_bytes==n && out.fb_node && out.firmware_node && out.mailbox_node);
        REQUIRE(out.firmware_phandle==0x55 && out.mailbox_phandle==0x22);
        REQUIRE(out.dma_profile==RPI5_MAILBOX_DMA_PI5_NO_RANGES_DIRECT);
        REQUIRE(!out.root_dma_ranges && !out.soc_dma_ranges && !out.mailbox_dma_ranges);
        REQUIRE(out.firmware_dma_ranges==RPI5_MAILBOX_PROP_EMPTY && out.linux_default_dma_mask_bits==32);
        REQUIRE(!out.coherent_property_present && !out.iommu_property_present);
        /* Every truncated input fails without output mutation. */
        for(size_t i=0;i<n;i++){out=before;REQUIRE(rpi5_display_mailbox_from_fdt(b,i,&out));REQUIRE(!memcmp(&out,&before,sizeof out));}
        /* The complete declared input, including trailing capacity, is protected
         * from output aliasing. Overflow/NULL/oversize cannot be read. */
        unsigned char *saved=malloc(n);REQUIRE(saved);memcpy(saved,b,n);
        REQUIRE(rpi5_display_mailbox_from_fdt(b,n,(void *)b));REQUIRE(!memcmp(saved,b,n));
        REQUIRE(rpi5_display_mailbox_from_fdt(b,n+sizeof out,(void *)(b+n)));
        out=before;REQUIRE(rpi5_display_mailbox_from_fdt(b,SIZE_MAX,&out));REQUIRE(!memcmp(&out,&before,sizeof out));
        REQUIRE(rpi5_display_mailbox_from_fdt(NULL,n,&out));REQUIRE(rpi5_display_mailbox_from_fdt(b,n,NULL));free(saved);
        puts("MAILBOX_FDT PASS PHANDLE_CHAIN=1 MMIO_TRANSLATION=1 NO_TRANSPORT=1 NO_BUFFER_AUTHORITY=1");
    }
    free(b);return 0;
}
