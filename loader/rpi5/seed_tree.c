/* SPDX-License-Identifier: BSD-2-Clause */
#include "seed_tree.h"
static int same(const char *a,const char *b)
{
    while (*a && *a==*b) { ++a; ++b; }
    return *a==*b;
}
int rpi5_seed_tree_measure(const struct rpi5_adt_node *root,
    size_t capacity, size_t *written)
{
    size_t base;
    if (!written || rpi5_adt_measure(root,capacity,&base)) return -1;
    const struct rpi5_adt_node *chosen=0;
    for (size_t i=0;i<root->child_count;i++)
        if (same(root->children[i]->name,"chosen")) chosen=root->children[i];
    if (!chosen || chosen->property_count>=128) return -1;
    for (size_t i=0;i<chosen->property_count;i++)
        if (same(chosen->properties[i].name,"random-seed")) return -1;
    /* Apple property header is 32 name bytes + uint32 length. Seed size is
     * already four-byte aligned; no node or other property is added. */
    const size_t extra=36+RPI5_BOOT_SEED_BYTES;
    size_t limit=capacity<(1u<<24) ? capacity : (1u<<24);
    if (base>limit || extra>limit-base) return -1;
    *written=base+extra;
    return 0;
}
int rpi5_seed_tree_encode(const struct rpi5_adt_node *root,
    const struct rpi5_seed_source *source, uint64_t ticks, size_t polls,
    void *output, size_t capacity, size_t *written)
{
    size_t size;
    if (!output || !written || rpi5_seed_tree_measure(root,capacity,&size)) return -1;
    const struct rpi5_adt_node *chosen=0;
    size_t index=0;
    for (size_t i=0;i<root->child_count;i++)
        if (same(root->children[i]->name,"chosen")) { chosen=root->children[i]; index=i; }
    if (!chosen || chosen->property_count>=128) return -1;
    for (size_t i=0;i<chosen->property_count;i++)
        if (same(chosen->properties[i].name,"random-seed")) return -1;
    uint8_t seed[RPI5_BOOT_SEED_BYTES]={0};
    struct rpi5_adt_property properties[128];
    for (size_t i=0;i<chosen->property_count;i++) properties[i]=chosen->properties[i];
    properties[chosen->property_count]=(struct rpi5_adt_property){"random-seed",seed,sizeof seed};
    struct rpi5_adt_node child=*chosen, parent=*root;
    child.properties=properties; ++child.property_count;
    const struct rpi5_adt_node *children[128];
    for (size_t i=0;i<root->child_count;i++) children[i]=root->children[i];
    children[index]=&child; parent.children=children;
    if (rpi5_adt_measure(&parent,capacity,&size)) return -1;
    int result=rpi5_boot_seed_collect(source,ticks,polls,seed);
    if (!result) result=rpi5_adt_encode(&parent,output,capacity,written);
    volatile uint8_t *wipe=seed;
    for (size_t i=0;i<sizeof seed;i++) wipe[i]=0;
    return result;
}
