/* SPDX-License-Identifier: BSD-2-Clause */
#include "boot_args.h"
static void put64(uint8_t *p, uint64_t value)
{
    for (unsigned i=0;i<8;i++) p[i]=(uint8_t)(value>>(8*i));
}
int rpi5_boot_args_encode(const struct rpi5_boot_args_input *input,
    const char *command, size_t length, void *output, size_t capacity)
{
    if (!input || !output || capacity<RPI5_BOOT_ARGS_SIZE || length>=1024 || (length && !command)) return -1;
    struct rpi5_boot_args_input a=*input;
    const uint64_t limit=1ull<<40;
    if (!a.virt_base || !a.mem_size || !a.mem_actual || !a.tree_length ||
        a.phys_base>=limit || a.mem_size>limit-a.phys_base || a.mem_size>UINT64_MAX-a.virt_base ||
        a.kernel_end<a.phys_base || a.tree_pa<a.kernel_end || a.tree_pa>=a.top ||
        a.tree_length>a.top-a.tree_pa || a.top>a.phys_base+a.mem_size ||
        (a.top&0x3fff) || (a.tree_pa&3)) return -1;
    for (size_t i=0;i<length;i++) if (!command[i] || (uint8_t)command[i]>127) return -1;
    uint8_t data[RPI5_BOOT_ARGS_SIZE]={0};
    data[0]=2; data[2]=2;
    put64(data+8,a.virt_base); put64(data+16,a.phys_base);
    put64(data+24,a.mem_size); put64(data+32,a.top);
    put64(data+96,a.virt_base+(a.tree_pa-a.phys_base));
    for (unsigned i=0;i<4;i++) data[104+i]=(uint8_t)(a.tree_length>>(8*i));
    for (size_t i=0;i<length;i++) data[108+i]=(uint8_t)command[i];
    put64(data+1144,a.mem_actual);
    uint8_t *dst=output;
    for (size_t i=0;i<sizeof(data);i++) dst[i]=data[i];
    return 0;
}
