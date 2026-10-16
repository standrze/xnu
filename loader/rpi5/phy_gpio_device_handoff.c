/* SPDX-License-Identifier: BSD-2-Clause */
#include "phy_gpio_device_handoff.h"
#include "fdt.h"
static uint32_t phy_gpio_be32(const uint8_t *p)
{return (uint32_t)p[0]<<24|(uint32_t)p[1]<<16|(uint32_t)p[2]<<8|p[3];}
static int phy_gpio_equal(const void *a,const void *b,size_t n)
{const uint8_t *x=a,*y=b;for(size_t i=0;i<n;i++)if(x[i]!=y[i])return 0;return 1;}
int rpi5_phy_gpio_device_handoff(const void *fdt,size_t bytes,
    const struct rpi5_memory_types *input,struct rpi5_memory_types *out)
{
    static const char path[]="/axi/pcie@1000120000/rp1/gpio@d0000";
    if(!input||!out||input==out||!fdt||input->device.count>27)return -1;
    uintptr_t f=(uintptr_t)fdt,o=(uintptr_t)out;
    if(bytes>UINTPTR_MAX-f||sizeof *out>UINTPTR_MAX-o||!(f+bytes<=o||o+sizeof *out<=f))return -1;
    struct rpi5_memory_types result;
    /* Existing helper proves the original Pi5 PCIe/RP1 ranges and full tree. */
    if(rpi5_rp1_device_handoff(fdt,bytes,input,&result))return -1;
    struct rpi5_fdt_property p;
    if(rpi5_fdt_property(fdt,bytes,path,"compatible",&p)||p.length!=sizeof "raspberrypi,rp1-gpio"||
        !phy_gpio_equal((const uint8_t *)fdt+p.offset,"raspberrypi,rp1-gpio",p.length))return -1;
    int rc=rpi5_fdt_property(fdt,bytes,path,"status",&p);
    if(rc!=-2&&(rc||!((p.length==5&&phy_gpio_equal((const uint8_t *)fdt+p.offset,"okay",5))||
        (p.length==3&&phy_gpio_equal((const uint8_t *)fdt+p.offset,"ok",3)))))return -1;
    if(rpi5_fdt_property(fdt,bytes,path,"reg",&p)||p.length!=48)return -1;
    const uint8_t *reg=(const uint8_t *)fdt+p.offset;
    for(unsigned n=0;n<3;n++)if(phy_gpio_be32(reg+16*n)!=0xc0||
        phy_gpio_be32(reg+16*n+4)!=0x400d0000u+n*0x10000u||phy_gpio_be32(reg+16*n+8)||
        phy_gpio_be32(reg+16*n+12)!=0xc000)return -1;
    for(unsigned n=0;n<3;n++){
        struct rpi5_range add={UINT64_C(0x1f000d4000)+n*0x10000u,UINT64_C(0x1f000d8000)+n*0x10000u};
        size_t position=0;
        for(size_t i=0;i<result.device.count;i++){
            struct rpi5_range old=result.device.extent[i];
            if(old.start<add.end&&add.start<old.end)return -1;
            if(old.start<add.start)position++;
        }
        for(size_t i=result.device.count;i>position;i--)result.device.extent[i]=result.device.extent[i-1];
        result.device.extent[position]=add;result.device.count++;
    }
    if(rpi5_memory_types_validate(&result))return -1;*out=result;return 0;
}
