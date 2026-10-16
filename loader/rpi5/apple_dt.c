/* SPDX-License-Identifier: BSD-2-Clause */
#include "apple_dt.h"
struct context {
    const struct rpi5_adt_node *active[RPI5_ADT_MAX_DEPTH+1];
    size_t used, capacity, nodes;
    uint8_t *output;
};
static size_t name_length(const char *s, size_t limit, int node)
{
    if (!s) return 0;
    for (size_t i=0;i<=limit;i++) {
        uint8_t c=(uint8_t)s[i];
        if (!c) return i;
        if (c>127 || (node && c=='/')) return 0;
    }
    return 0;
}
static int equal(const char *a, const char *b)
{
    while (*a && *a==*b) { a++; b++; }
    return *a==*b;
}
static void put32(uint8_t *p, uint32_t v)
{
    for (unsigned i=0;i<4;i++) p[i]=(uint8_t)(v>>(8*i));
}
static int property(struct context *c, const char *name, size_t namesize,
    const void *data, uint32_t size)
{
    size_t padded=((size_t)size+3)&~(size_t)3;
    if (c->used>c->capacity || padded>c->capacity-c->used || 36>c->capacity-c->used-padded) return -1;
    if (c->output) {
        uint8_t *p=c->output+c->used;
        for (size_t i=0;i<36+padded;i++) p[i]=0;
        for (size_t i=0;i<namesize;i++) p[i]=(uint8_t)name[i];
        put32(p+32,size);
        for (size_t i=0;i<size;i++) p[36+i]=((const uint8_t *)data)[i];
    }
    c->used+=36+padded;
    return 0;
}
static int node(struct context *c, const struct rpi5_adt_node *n, size_t depth)
{
    if (!n || depth>RPI5_ADT_MAX_DEPTH || ++c->nodes>256) return -1;
    for (size_t i=0;i<depth;i++) if (c->active[i]==n) return -1;
    c->active[depth]=n;
    size_t length=name_length(n->name,63,1);
    if (!length || n->property_count>128 || n->child_count>128 ||
        (n->property_count && !n->properties) || (n->child_count && !n->children) ||
        c->used>c->capacity || c->capacity-c->used<8) return -1;
    if (c->output) { put32(c->output+c->used,n->property_count+1); put32(c->output+c->used+4,n->child_count); }
    c->used+=8;
    if (property(c,"name",4,n->name,(uint32_t)length+1)) return -1;
    for (uint32_t i=0;i<n->property_count;i++) {
        const struct rpi5_adt_property *p=&n->properties[i];
        length=name_length(p->name,31,0);
        if (!length || equal(p->name,"name") || (p->length && !p->data)) return -1;
        for (uint32_t j=0;j<i;j++) if (equal(p->name,n->properties[j].name)) return -1;
        if (property(c,p->name,length,p->data,p->length)) return -1;
    }
    for (uint32_t i=0;i<n->child_count;i++) {
        const struct rpi5_adt_node *child=n->children[i];
        if (!child || !name_length(child->name,63,1)) return -1;
        for (uint32_t j=0;j<i;j++) if (equal(child->name,n->children[j]->name)) return -1;
        if (node(c,child,depth+1)) return -1;
    }
    return 0;
}
int rpi5_adt_measure(const struct rpi5_adt_node *root, size_t capacity, size_t *written)
{
    if (!written || !capacity) return -1;
    struct context c={0};
    c.capacity=capacity<(1u<<24)?capacity:(1u<<24);
    if (node(&c,root,0)) return -1;
    *written=c.used;
    return 0;
}

int rpi5_adt_encode(const struct rpi5_adt_node *root, void *output,
    size_t capacity, size_t *written)
{
    if (!output || !written || !capacity) return -1;
    struct context c={0};
    c.capacity=capacity<(1u<<24)?capacity:(1u<<24);
    if (node(&c,root,0)) return -1;
    c.used=0; c.nodes=0; c.output=output;
    if (node(&c,root,0)) return -1; /* Inputs must remain stable across passes. */
    *written=c.used;
    return 0;
}
