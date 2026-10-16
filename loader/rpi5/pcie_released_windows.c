/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_released_windows.h"
static int dependency(const struct rpi5_pcie_released_windows *s)
{
    return s->windows && s->windows->state == RPI5_PCIE_WINDOWS_COMPLETE &&
        s->windows->io.physical_base == UINT64_C(0x1000120000) &&
        s->windows->io.mapped_bytes == 0x9310;
}
int rpi5_pcie_released_windows_init(struct rpi5_pcie_released_windows *s,
    const struct rpi5_pcie_windows *windows, const struct rpi5_pcie_released_windows_io *io)
{
    if (!s || !windows || !io || !io->check_owner || !io->read32 || !io->order ||
        io->physical_base != UINT64_C(0x1000120000) || io->mapped_bytes != 0x9310) return -1;
    if (s->state != RPI5_PCIE_RELEASED_EMPTY) return -2;
    struct rpi5_pcie_released_windows view = {0}; view.windows = windows;
    if (!dependency(&view)) return -3;
    s->windows = windows; s->expected = windows->plan; s->io = *io;
    s->checks = s->callbacks = s->reads = 0; s->state = RPI5_PCIE_RELEASED_READY;
    return 0;
}
static int owner(struct rpi5_pcie_released_windows *s)
{
    if (!dependency(s)) return -3;
    s->callbacks++;
    if (s->io.check_owner(s->io.context)) return -4;
    return dependency(s) ? 0 : -3;
}
static int ordered(struct rpi5_pcie_released_windows *s)
{
    int rc = owner(s); if (rc) return rc;
    s->callbacks++;
    if (s->io.order(s->io.context)) return -4;
    return owner(s);
}
static int read32(struct rpi5_pcie_released_windows *s, uint32_t offset, uint32_t *out)
{
    int rc = owner(s); if (rc) return rc;
    uint32_t value; s->callbacks++;
    if (s->io.read32(s->io.context,offset,&value)) return -4;
    s->reads++;
    if ((rc = owner(s))) return rc;
    if (value == UINT32_MAX) return -5;
    *out = value; return 0;
}
static int snapshot(struct rpi5_pcie_released_windows *s, uint32_t words[45])
{
    int rc; unsigned index = 3;
#define READ(i,off) do { if ((rc=read32(s,(off),&words[(i)]))) return rc; } while (0)
#define MATCH(off,mask,value) do { READ(index,(off)); words[index]&=(mask); \
    if (words[index++]!=(value)) return -6; } while (0)
    if ((rc=ordered(s))) return rc;
    READ(0,0x4068); READ(1,0x4064); READ(2,0x4304);
    if ((words[0]&0xc0)!=0x80 || (words[1]&1) || (words[2]&0x08000008)) return -6;
    for (unsigned i=0;i<3;i++) {
        const struct rpi5_pcie_inbound_encoding *p=&s->expected.inbound[i];
        MATCH(0x402c+8*i,UINT32_MAX,p->bar_lo); MATCH(0x4030+8*i,UINT32_MAX,p->bar_hi);
        MATCH(0x40ac+8*i,UINT32_MAX,p->remap_lo); MATCH(0x40b0+8*i,UINT32_MAX,p->remap_hi);
    }
    for (unsigned i=0;i<2;i++) {
        const struct rpi5_pcie_outbound_encoding *p=&s->expected.outbound[i];
        MATCH(0x400c+8*i,UINT32_MAX,p->pci_lo); MATCH(0x4010+8*i,UINT32_MAX,p->pci_hi);
        MATCH(0x4070+4*i,UINT32_C(0xfff0fff0),p->base_limit);
        MATCH(0x4080+8*i,0xff,p->base_hi); MATCH(0x4084+8*i,0xff,p->limit_hi);
    }
    for (unsigned i=0;i<7;i++) {
        READ(index,0x40d4+8*i);
        if (words[index++]&0x1f) return -6;
        READ(index,0x410c+8*i); index++;
    }
    for (unsigned slot=2;slot<4;slot++) {
        READ(index,0x4070+4*slot); READ(index+1,0x4080+8*slot); READ(index+2,0x4084+8*slot);
        uint64_t base=((uint64_t)(words[index+1]&0xff)<<32)|((uint64_t)(words[index]&0xfff0)<<16);
        uint64_t limit=((uint64_t)(words[index+2]&0xff)<<32)|(words[index]&UINT32_C(0xfff00000))|0xfffff;
        if (base<=limit) return -6;
        index+=3;
    }
#undef MATCH
#undef READ
    return index==45 ? 0 : -1;
}
int rpi5_pcie_released_windows_check(struct rpi5_pcie_released_windows *s,
    struct rpi5_pcie_released_observation *out)
{
    if (!s || !out) return -1;
    if (s->state!=RPI5_PCIE_RELEASED_READY) return -2;
    s->state=RPI5_PCIE_RELEASED_BUSY; s->callbacks=s->reads=0;
    if (s->checks>=65536) { s->state=RPI5_PCIE_RELEASED_FAILED; return -2; }
    uint32_t first[45],second[45];
    int rc=snapshot(s,first);
    if (!rc) rc=snapshot(s,second);
    if (!rc) for (unsigned i=3;i<45;i++) if (first[i]!=second[i]) {rc=-7;break;}
    if (!rc) rc=owner(s);
    if (rc) {s->state=RPI5_PCIE_RELEASED_FAILED;return rc;}
    struct rpi5_pcie_released_observation result = {second[0],second[1],second[2],
        ++s->checks,s->reads,s->callbacks};
    *out=result;s->state=RPI5_PCIE_RELEASED_READY;return 0;
}
