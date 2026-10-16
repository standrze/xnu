/* SPDX-License-Identifier: BSD-2-Clause */
#include "serial_tree.h"
static void le64(uint8_t *p,uint64_t x)
{
    for (unsigned i=0;i<8;i++) p[i]=(uint8_t)(x>>(8*i));
}
int rpi5_serial_tree_init(struct rpi5_range uart, uint32_t phandle,
    struct rpi5_serial_tree *out)
{
    const uint64_t soc=0x107c000000ull;
    if (!out || !phandle || phandle==UINT32_MAX ||
        uart.start!=0x107d001000ull || uart.end!=0x107d001200ull) return -1;
    *out=(struct rpi5_serial_tree){0};
    le64(out->ranges,0); le64(out->ranges+8,soc); le64(out->ranges+16,0x4000000);
    le64(out->reg,uart.start-soc); le64(out->reg+8,uart.end-uart.start);
    for (unsigned i=0;i<4;i++) out->phandle[i]=(uint8_t)(phandle>>(8*i));
    out->io_props[0]=(struct rpi5_adt_property){"device_type","soc",4};
    out->io_props[1]=(struct rpi5_adt_property){"ranges",out->ranges,24};
    out->uart_props[0]=(struct rpi5_adt_property){"compatible","arm,pl011",10};
    out->uart_props[1]=(struct rpi5_adt_property){"reg",out->reg,16};
    out->uart_props[2]=(struct rpi5_adt_property){"AAPL,phandle",out->phandle,4};
    out->uart=(struct rpi5_adt_node){"uart10",out->uart_props,0,3,0};
    out->children[0]=&out->uart;
    out->arm_io=(struct rpi5_adt_node){"arm-io",out->io_props,out->children,2,1};
    out->default_prop=(struct rpi5_adt_property){"serial-device",out->phandle,4};
    out->defaults=(struct rpi5_adt_node){"defaults",&out->default_prop,0,1,0};
    return 0;
}
