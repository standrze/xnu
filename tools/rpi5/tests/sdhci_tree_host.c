/* SPDX-License-Identifier: BSD-2-Clause */
#include "board_tree.h"
#include "rpi5_sd_contract.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void)
{
    const uint64_t ids[]={0};
    struct rpi5_board_tree tree;
    assert(!rpi5_board_tree_init(ids,1,0,54000000,
        (struct rpi5_range){0x107d001000ull,0x107d001200ull},0,0x200000000ull,&tree));
    unsigned char before[sizeof tree]; memcpy(before,&tree,sizeof tree);
    struct rpi5_fdt_sdhci sd={
        .host={0x1000fff000ull,0x1000fff260ull},
        .cfg={0x1000fff400ull,0x1000fff600ull},
        .source_hz=200000000,.irq=305,.bus_width=4,.vmmc=12,.vqmmc=11
    }, bad=sd;
    bad.host.start=0x1001100000ull;
    assert(rpi5_board_tree_sdhci(&tree,&bad)==-1 && !memcmp(before,&tree,sizeof tree));
    bad=sd; bad.source_hz=0;
    assert(rpi5_board_tree_sdhci(&tree,&bad)==-1 && !memcmp(before,&tree,sizeof tree));
    assert(!rpi5_board_tree_sdhci(&tree,&sd));
    assert(tree.root.child_count==5 && tree.children[4]==&tree.sdhci);
    assert(tree.serial.arm_io.child_count==2); /* Not a fictional arm-io window. */
    assert(!strcmp(tree.sdhci.name,"sdio1"));
    assert(tree.sdhci_props[0].length==19);
    const unsigned char expected[32]={
        0x00,0xf0,0xff,0x00,0x10,0,0,0,0x60,0x02,0,0,0,0,0,0,
        0x00,0xf4,0xff,0x00,0x10,0,0,0,0x00,0x02,0,0,0,0,0,0
    };
    assert(!memcmp(tree.sdhci_reg,expected,32));
    assert(tree.sdhci_clock[0]==0 && tree.sdhci_clock[1]==0xc2 &&
        tree.sdhci_clock[2]==0xeb && tree.sdhci_clock[3]==0x0b);
    assert(tree.sdhci_irq[0]==0x31 && tree.sdhci_irq[1]==1);
    struct rpi5_fdt_sd_power power={
        .gpio={0x107d517c00ull,0x107d517c40ull},
        .pins={0x107d504100ull,0x107d504130ull},
        .aon_pins={0x107d510700ull,0x107d510720ull},.variant=0,.settling_us=5000
    }, bad_power=power;
    memcpy(before,&tree,sizeof tree); bad_power.gpio.start++;
    assert(rpi5_board_tree_sd_power(&tree,&bad_power)==-1 && !memcmp(before,&tree,sizeof tree));
    bad_power=power; bad_power.variant=2;
    assert(rpi5_board_tree_sd_power(&tree,&bad_power)==-1 && !memcmp(before,&tree,sizeof tree));
    assert(!rpi5_board_tree_sd_power(&tree,&power));
    assert(tree.sdhci.property_count==7 && tree.sdhci_props[4].length==48);
    const unsigned char power_expected[48]={
        0x00,0x7c,0x51,0x7d,0x10,0,0,0, 0x40,0,0,0,0,0,0,0,
        0x00,0x41,0x50,0x7d,0x10,0,0,0, 0x30,0,0,0,0,0,0,0,
        0x00,0x07,0x51,0x7d,0x10,0,0,0, 0x20,0,0,0,0,0,0,0
    };
    assert(!memcmp(tree.sd_power_reg,power_expected,48));
    assert(tree.sd_pad_variant[0]==0 && tree.sd_settling_us[0]==0x88 && tree.sd_settling_us[1]==0x13);
    memcpy(before,&tree,sizeof tree);
    assert(rpi5_board_tree_sd_power(&tree,&power)==-1 && !memcmp(before,&tree,sizeof tree));
    memcpy(before,&tree,sizeof tree);
    assert(rpi5_board_tree_sdhci(&tree,&sd)==-1 && !memcmp(before,&tree,sizeof tree));
    unsigned char encoded[4096]; size_t length=0;
    assert(!rpi5_adt_encode(&tree.root,encoded,sizeof encoded,&length));
    unsigned matches=0;
    for (size_t i=0;i+32<=length;i++) if (!memcmp(encoded+i,expected,32)) matches++;
    assert(matches==1);
    /* Producer and actual kernel consumer must agree on names, lengths and
     * native bytes, not just two independently hard-coded fixtures. */
    const struct rpi5_adt_property *p=tree.sdhci_props;
    assert(!strcmp(p[1].name,"reg") && !strcmp(p[2].name,"clock-frequency") &&
        !strcmp(p[3].name,"rpi5-gic-intid") && !strcmp(p[4].name,"rpi5-sd-power-reg") &&
        !strcmp(p[5].name,"rpi5-sd-pad-variant") && !strcmp(p[6].name,"rpi5-sd-settling-us"));
    struct rpi5_sd_binding binding;
    assert(!rpi5_sd_binding_decode(p[1].data,p[1].length,p[4].data,p[4].length,
        p[5].data,p[5].length,p[2].data,p[2].length,p[6].data,p[6].length,
        p[3].data,p[3].length,&binding));
    assert(binding.base[RPI5_SD_HOST]==sd.host.start && binding.base[RPI5_SD_GPIO]==power.gpio.start &&
        binding.source_hz==sd.source_hz && binding.variant==power.variant && binding.settling_us==power.settling_us);
    puts("SDHCI_TREE_PASS"); return 0;
}
