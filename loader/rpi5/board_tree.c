/* SPDX-License-Identifier: BSD-2-Clause */
#include "board_tree.h"
static const char rpi5_board_compatible[] = "raspberrypi,5-model-b\0brcm,bcm2712";
static void gic_le64(uint8_t *p, uint64_t value)
{
    for (unsigned i=0;i<8;i++) p[i]=(uint8_t)(value>>(8*i));
}
int rpi5_board_tree_sdhci(struct rpi5_board_tree *tree, const struct rpi5_fdt_sdhci *sd)
{
    if (!tree || !sd || tree->root.children!=tree->children || tree->root.child_count!=4 ||
        sd->host.start!=0x1000fff000ull || sd->host.end!=0x1000fff260ull ||
        sd->cfg.start!=0x1000fff400ull || sd->cfg.end!=0x1000fff600ull ||
        sd->source_hz!=200000000 || sd->irq!=305 || sd->bus_width!=4)
        return -1;
    gic_le64(tree->sdhci_reg,sd->host.start);
    gic_le64(tree->sdhci_reg+8,sd->host.end-sd->host.start);
    gic_le64(tree->sdhci_reg+16,sd->cfg.start);
    gic_le64(tree->sdhci_reg+24,sd->cfg.end-sd->cfg.start);
    for (unsigned i=0;i<4;i++) {
        tree->sdhci_clock[i]=(uint8_t)(sd->source_hz>>(8*i));
        tree->sdhci_irq[i]=(uint8_t)(sd->irq>>(8*i));
    }
    tree->sdhci_props[0]=(struct rpi5_adt_property){"compatible","brcm,bcm2712-sdhci",19};
    tree->sdhci_props[1]=(struct rpi5_adt_property){"reg",tree->sdhci_reg,32};
    tree->sdhci_props[2]=(struct rpi5_adt_property){"clock-frequency",tree->sdhci_clock,4};
    tree->sdhci_props[3]=(struct rpi5_adt_property){"rpi5-gic-intid",tree->sdhci_irq,4};
    tree->sdhci=(struct rpi5_adt_node){"sdio1",tree->sdhci_props,0,4,0};
    tree->children[4]=&tree->sdhci;
    tree->root.child_count=5;
    return 0;
}
int rpi5_board_tree_sd_power(struct rpi5_board_tree *tree, const struct rpi5_fdt_sd_power *power)
{
    if (!tree || !power || tree->root.children!=tree->children || tree->root.child_count!=5 ||
        tree->children[4]!=&tree->sdhci || tree->sdhci.properties!=tree->sdhci_props ||
        tree->sdhci.property_count!=4 || power->variant>1 || power->settling_us!=5000 ||
        power->gpio.start!=0x107d517c00ull || power->gpio.end!=0x107d517c40ull ||
        power->pins.start!=0x107d504100ull || power->pins.end!=0x107d504130ull ||
        power->aon_pins.start!=0x107d510700ull || power->aon_pins.end!=0x107d510720ull)
        return -1;
    const struct rpi5_range ranges[3]={power->gpio,power->pins,power->aon_pins};
    for (unsigned i=0;i<3;i++) {
        gic_le64(tree->sd_power_reg+i*16,ranges[i].start);
        gic_le64(tree->sd_power_reg+i*16+8,ranges[i].end-ranges[i].start);
    }
    for (unsigned i=0;i<4;i++) {
        tree->sd_pad_variant[i]=(uint8_t)(power->variant>>(i*8));
        tree->sd_settling_us[i]=(uint8_t)(power->settling_us>>(i*8));
    }
    tree->sdhci_props[4]=(struct rpi5_adt_property){"rpi5-sd-power-reg",tree->sd_power_reg,48};
    tree->sdhci_props[5]=(struct rpi5_adt_property){"rpi5-sd-pad-variant",tree->sd_pad_variant,4};
    tree->sdhci_props[6]=(struct rpi5_adt_property){"rpi5-sd-settling-us",tree->sd_settling_us,4};
    tree->sdhci.property_count=7;
    return 0;
}
int rpi5_board_tree_watchdog(struct rpi5_board_tree *tree,
    struct rpi5_range watchdog)
{
    if (!tree || tree->serial.arm_io.children!=tree->serial.children ||
        tree->serial.arm_io.child_count!=2 ||
        watchdog.start!=0x107d200000ull || watchdog.end!=0x107d200308ull)
        return -1;
    gic_le64(tree->watchdog_reg,watchdog.start-0x107c000000ull);
    gic_le64(tree->watchdog_reg+8,watchdog.end-watchdog.start);
    tree->watchdog_props[0]=(struct rpi5_adt_property){"compatible","brcm,bcm2712-pm",16};
    tree->watchdog_props[1]=(struct rpi5_adt_property){"reg",tree->watchdog_reg,16};
    tree->watchdog=(struct rpi5_adt_node){"watchdog",tree->watchdog_props,0,2,0};
    tree->serial.children[2]=&tree->watchdog;
    tree->serial.arm_io.child_count=3;
    return 0;
}
int rpi5_board_tree_ramdisk(struct rpi5_board_tree *tree,
    uint64_t physical_address, uint64_t length)
{
    if (!tree || tree->chosen.children!=tree->chosen_children ||
        tree->chosen_children[0]!=&tree->image_memory_map ||
        tree->image_memory_map.property_count ||
        !length || (physical_address&0x3fff) || (length&0x3fff) ||
        physical_address>=(1ull<<40) || length>(1ull<<40)-physical_address)
        return -1;
    gic_le64(tree->ramdisk_record,physical_address);
    gic_le64(tree->ramdisk_record+8,length);
    tree->ramdisk_prop=(struct rpi5_adt_property){"RAMDisk",tree->ramdisk_record,16};
    tree->image_memory_map.properties=&tree->ramdisk_prop;
    tree->image_memory_map.property_count=1;
    return 0;
}
int rpi5_board_tree_memory_map(struct rpi5_board_tree *tree,
    const struct rpi5_memory_types *types)
{
    if (!tree || tree->chosen.properties!=tree->chosen_props ||
        (tree->chosen.property_count!=2 && tree->chosen.property_count!=3)) return -1;
    size_t length;
    if (rpi5_memory_types_encode(types,tree->memory_map,sizeof tree->memory_map,&length))
        return -1;
    tree->chosen_props[2]=(struct rpi5_adt_property){"rpi5-memory-map",tree->memory_map,(uint32_t)length};
    tree->chosen.property_count=3;
    return 0;
}
int rpi5_board_tree_init(const uint64_t *affinity, size_t count,
    uint64_t boot_affinity, uint32_t counter_hz, struct rpi5_range uart,
    uint64_t dram_base, uint64_t dram_size, struct rpi5_board_tree *out)
{
    if (!out || !dram_size || dram_base>=(1ull<<40) ||
        dram_size>(1ull<<40)-dram_base) return -1;
    struct rpi5_cpu_tree checked_cpus;
    struct rpi5_serial_tree checked_serial;
    if (rpi5_cpu_tree_init(affinity,count,boot_affinity,counter_hz,&checked_cpus) ||
        rpi5_serial_tree_init(uart,1,&checked_serial)) return -1;
    /* Only this builder assigns phandles; its sole UART gets ID 1. Build at
     * final addresses so all nested internal pointers remain valid. */
    (void)rpi5_cpu_tree_init(affinity,count,boot_affinity,counter_hz,&out->cpus);
    (void)rpi5_serial_tree_init(uart,1,&out->serial);
    /* The caller must first validate the exact runtime GIC-400 FDT profile.
     * arm-io ranges translates these two offsets from 0x107c000000. */
    gic_le64(out->gic_reg,0x3ff9000ull);
    gic_le64(out->gic_reg+8,0x1000);
    gic_le64(out->gic_reg+16,0x3ffa000ull);
    gic_le64(out->gic_reg+24,0x2000);
    out->gic_props[0]=(struct rpi5_adt_property){"compatible","arm,gic-400",12};
    out->gic_props[1]=(struct rpi5_adt_property){"reg",out->gic_reg,sizeof out->gic_reg};
    out->gic=(struct rpi5_adt_node){"gic",out->gic_props,0,2,0};
    out->serial.children[1]=&out->gic;
    out->serial.arm_io.child_count=2;
    for (unsigned i=0;i<8;i++) {
        out->dram_base[i]=(uint8_t)(dram_base>>(8*i));
        out->dram_size[i]=(uint8_t)(dram_size>>(8*i));
    }
    out->chosen_props[0]=(struct rpi5_adt_property){"dram-base",out->dram_base,8};
    out->chosen_props[1]=(struct rpi5_adt_property){"dram-size",out->dram_size,8};
    /* XNU requires this node even when no optional TrustCache/AuxKC images
     * were supplied. It is distinct from our physical memory-type property. */
    out->image_memory_map=(struct rpi5_adt_node){"memory-map",0,0,0,0};
    out->chosen_children[0]=&out->image_memory_map;
    out->chosen=(struct rpi5_adt_node){"chosen",out->chosen_props,out->chosen_children,2,1};
    out->children[0]=&out->chosen;
    out->children[1]=&out->cpus.root;
    out->children[2]=&out->serial.arm_io;
    out->children[3]=&out->serial.defaults;
    out->root_props[0]=(struct rpi5_adt_property){"compatible",rpi5_board_compatible,
        sizeof rpi5_board_compatible};
    out->root=(struct rpi5_adt_node){"device-tree",out->root_props,out->children,1,4};
    return 0;
}
