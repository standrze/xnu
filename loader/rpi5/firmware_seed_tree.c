/* SPDX-License-Identifier: BSD-2-Clause */
#include "firmware_seed_tree.h"
#include "seed_tree.h"
int rpi5_firmware_seed_tree(struct rpi5_board_tree *tree,uint8_t seed[64],
    uint8_t *consumed,void *output,size_t capacity,size_t *written,
    int (*consume)(uint8_t *,size_t,uint8_t *,size_t,uint8_t *))
{
    if (!tree || !seed || !consumed || !output || !written || !consume ||
        (tree->chosen.property_count!=2 && tree->chosen.property_count!=3) ||
        tree->chosen.properties!=tree->chosen_props)
        return -1;
    unsigned original_count=tree->chosen.property_count;
    size_t expected;
    if (rpi5_seed_tree_measure(&tree->root,capacity,&expected)) return -1;
    uint8_t derived[256]={0};
    int status=consume(seed,64,derived,sizeof derived,consumed);
    if (status) goto clear;
    struct rpi5_adt_property properties[4];
    for (unsigned i=0;i<original_count;i++) properties[i]=tree->chosen_props[i];
    properties[original_count]=(struct rpi5_adt_property){"random-seed",derived,sizeof derived};
    tree->chosen.properties=properties;
    tree->chosen.property_count=original_count+1;
    size_t encoded=0;
    status=rpi5_adt_encode(&tree->root,output,capacity,&encoded);
    tree->chosen.properties=tree->chosen_props;
    tree->chosen.property_count=original_count;
    if (!status && encoded==expected) *written=encoded;
    else {
        /* Encoding may have published seed bytes: erase the entire bounded
         * intended output on any post-consumption encoding failure. */
        volatile uint8_t *p=output;
        for(size_t i=0;i<expected;i++) p[i]=0;
        status=-1;
    }
clear:
    for(size_t i=0;i<sizeof derived;i++) ((volatile uint8_t *)derived)[i]=0;
    return status;
}
