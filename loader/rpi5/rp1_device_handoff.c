/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_device_handoff.h"
#include "pcie_fdt.h"
int rpi5_rp1_device_handoff(const void *fdt,size_t bytes,
    const struct rpi5_memory_types *input,struct rpi5_memory_types *out)
{
    if(!input || !out || input==out || rpi5_memory_types_validate(input) || input->device.count>30)return -1;
    struct rpi5_pcie_fdt f;
    if(rpi5_fdt_pcie_rp1(fdt,bytes,&f) || f.outbound_count!=2 ||
        f.outbound[0].space!=0x02000000 || f.outbound[0].pci_base ||
        f.outbound[0].cpu_base!=UINT64_C(0x1f00000000) || f.outbound[0].size!=0xfffffffc ||
        f.rp1_pci_base || f.rp1_aperture_size!=0x410000 ||
        f.gem_bar_offset!=0x100000 || f.gem_size!=0x4000 ||
        f.clock_bar_offset!=0x18000 || f.clock_size!=0x10038)return -1;
    const struct rpi5_range added[2]={
        {UINT64_C(0x1f00018000),UINT64_C(0x1f0002c000)},
        {UINT64_C(0x1f00100000),UINT64_C(0x1f00104000)}};
    struct rpi5_memory_types result=*input;
    for(unsigned n=0;n<2;n++) {
        size_t position=0;
        for(size_t i=0;i<result.device.count;i++) {
            struct rpi5_range old=result.device.extent[i];
            if(old.start<added[n].end && added[n].start<old.end)return -1;
            if(old.start<added[n].start)position++;
        }
        for(size_t i=result.device.count;i>position;i--)result.device.extent[i]=result.device.extent[i-1];
        result.device.extent[position]=added[n];result.device.count++;
    }
    if(rpi5_memory_types_validate(&result))return -1;
    *out=result;return 0;
}
