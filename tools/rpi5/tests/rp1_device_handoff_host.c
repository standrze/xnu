/* SPDX-License-Identifier: BSD-2-Clause */
#define main prior_device_handoff_test_main
#include "pcie_device_handoff_host.c"
#undef main
#include "rp1_device_handoff.h"
static void reject_rp1(const void *fdt,size_t bytes,const struct rpi5_memory_types *input)
{
    struct rpi5_memory_types out,before;memset(&out,0xa5,sizeof out);before=out;
    assert(rpi5_rp1_device_handoff(fdt,bytes,input,&out));assert(!memcmp(&out,&before,sizeof out));
}
int main(int argc,char **argv)
{
    assert(argc==3);FILE *file=fopen(argv[1],"rb");assert(file);assert(!fseek(file,0,SEEK_END));
    long length=ftell(file);assert(length>0 && length<256*1024);rewind(file);
    unsigned char *data=malloc((size_t)length+4);assert(data);
    assert(fread(data+4,1,(size_t)length,file)==(size_t)length);fclose(file);
    struct rpi5_memory_types in=initial(),host,out;
    if(!strcmp(argv[2],"reject")){reject_rp1(data+4,length,&in);free(data);puts("RP1_DEVICE_REJECT");return 0;}
    assert(!rpi5_pcie_device_handoff(data+4,length,&in,&host));
    assert(!rpi5_rp1_device_handoff(data+4,length,&host,&out));assert(out.device.count==host.device.count+2);
    assert(!memcmp(&host.normal,&out.normal,sizeof host.normal));
    for(size_t i=0;i<host.device.count;i++)assert(!memcmp(&out.device.extent[i],&host.device.extent[i],sizeof(struct rpi5_range)));
    const struct rpi5_range extra[2]={{0x1f00018000,0x1f0002c000},{0x1f00100000,0x1f00104000}};
    unsigned char encoded[RPI5_MEMORY_MAP_MAX_BYTES];size_t written;
    assert(!rpi5_memory_types_encode(&out,encoded,sizeof encoded,&written));
    struct rpi5_kernel_memory_map kernel={0};assert(!rpi5_map_decode(encoded,written,&kernel));
    for(unsigned i=0;i<2;i++) {
        assert(rpi5_map_type(&kernel,extra[i].start,extra[i].end)==2);
        assert(!rpi5_map_type(&kernel,extra[i].start-1,extra[i].start));
        assert(!rpi5_map_type(&kernel,extra[i].end,extra[i].end+1));
        struct rpi5_memory_types bad=host;bad.normal.extent[bad.normal.count++]=extra[i];reject_rp1(data+4,length,&bad);
        bad=host;bad.device.extent[bad.device.count++]=extra[i];reject_rp1(data+4,length,&bad);
    }
    assert(!rpi5_map_type(&kernel,0x1f00000000,0x1f00400000));
    assert(!rpi5_map_type(&kernel,0x1f00104000,0x1f00108000)); /* eth_cfg is not admitted. */
    reject_rp1(data+4,length,&out);reject_rp1(data+4,length-1,&host);
    assert(rpi5_rp1_device_handoff(data+4,length,&host,&host));
    struct rpi5_memory_types full=initial();full.device.count=30;
    for(unsigned i=0;i<31;i++)full.device.extent[i]=(struct rpi5_range){0x1100000000+i*0x8000ull,0x1100004000+i*0x8000ull};
    assert(!rpi5_rp1_device_handoff(data+4,length,&full,&out) && out.device.count==32);
    full.device.count=31;reject_rp1(data+4,length,&full);
    free(data);puts("RP1_DEVICE_PASS EXACT_NEW_PAGES=6 KERNEL_DECODE=1 NO_ACCESS_AUTHORITY=1");
}
