/* SPDX-License-Identifier: BSD-2-Clause */
#include "cpu_tree.h"
int rpi5_cpu_tree_init(const uint64_t *affinity, size_t count,
    uint64_t boot_affinity, uint32_t counter_hz, struct rpi5_cpu_tree *out)
{
    if (!affinity || !out || !count || count>4 || !counter_hz) return -1;
    uint64_t ids[4];
    unsigned boots=0;
    for (size_t i=0;i<count;i++) {
        ids[i]=affinity[i];
        if (ids[i]>0x300 || (ids[i]&0xff)) return -1;
        for (size_t j=0;j<i;j++) if (ids[i]==ids[j]) return -1;
        boots += ids[i]==boot_affinity;
    }
    if (boots!=1) return -1;
    static const char *const names[]={"cpu0","cpu1","cpu2","cpu3"};
    *out=(struct rpi5_cpu_tree){0};
    for (unsigned b=0;b<4;b++) out->frequency[b]=(uint8_t)(counter_hz>>(8*b));
    for (size_t i=0;i<count;i++) {
        for (unsigned b=0;b<4;b++) out->reg[i][b]=(uint8_t)(ids[i]>>(8*b));
        int boot=ids[i]==boot_affinity;
        out->properties[i][0]=(struct rpi5_adt_property){"reg",out->reg[i],4};
        out->properties[i][1]=(struct rpi5_adt_property){"state",boot ? "running" : "stopped",8};
        out->properties[i][2]=(struct rpi5_adt_property){"timebase-frequency",out->frequency,4};
        /* IODTPlatformExpert only publishes logical CPU IDs for CPU nubs. */
        out->properties[i][3]=(struct rpi5_adt_property){"device_type","cpu",4};
        out->cpu[i]=(struct rpi5_adt_node){names[ids[i]>>8],out->properties[i],0,4,0};
        out->children[i]=&out->cpu[i];
    }
    out->root=(struct rpi5_adt_node){"cpus",0,out->children,0,(uint32_t)count};
    return 0;
}
