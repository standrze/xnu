/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_decode_cycle.h"

static int fail(struct rpi5_rp1_decode_cycle *s,int rc)
{
    s->pending_write=s->pending_map=0;
    s->state=RPI5_RP1_DECODE_QUARANTINED;return rc;
}
static int same_range(struct rpi5_range a,struct rpi5_range b)
{ return a.start==b.start && a.end==b.end; }
static int retained(const struct rpi5_rp1_decode_cycle *s)
{
    const struct rpi5_rp1_assignment *a=s->assignment;
    if(!a || !a->config || !s->io.current || !s->io.map || !s->io.unmap ||
        s->io.context!=a->config->io.context || s->io.current(s->io.context,s,a) ||
        s->original_command!=a->command || (s->original_command&~UINT32_C(0xfff8)))return 0;
    struct rpi5_rp1_mapping_candidate g;
    return !rpi5_rp1_bars_mapping_candidate(a,a->binding,&g) &&
        same_range(g.bar1_cpu,s->geometry.bar1_cpu) &&
        same_range(g.gem_pages,s->geometry.gem_pages) &&
        same_range(g.clock_pages,s->geometry.clock_pages);
}
int rpi5_rp1_decode_write_allowed(const struct rpi5_rp1_decode_cycle *s,
    const struct rpi5_pcie_config_request *r)
{
    if(!s || !r || !s->pending_write || !retained(s) || r->bus!=1 ||
        r->device || r->function || r->offset!=4 || r->width!=2 || r->write!=1)return 0;
    return (s->state==RPI5_RP1_DECODE_ENABLING && r->value==(s->original_command|2)) ||
        (s->state==RPI5_RP1_DECODE_DISABLING && r->value==s->original_command);
}
int rpi5_rp1_decode_mapping_allowed(const struct rpi5_rp1_decode_cycle *s,
    unsigned index,struct rpi5_range range,unsigned removing)
{
    if(!s || index>1 || removing>1 || !s->pending_map || s->selected!=index || !retained(s))return 0;
    struct rpi5_range expected=index?s->geometry.clock_pages:s->geometry.gem_pages;
    if(!same_range(range,expected))return 0;
    return removing ? (s->state==RPI5_RP1_DECODE_UNMAPPING && s->mapped==3 &&
        s->unmapped==(index?0u:2u)) : (s->state==RPI5_RP1_DECODE_MAPPING &&
        s->mapped==(index?1u:0u) && !s->unmapped);
}
static int read_config(struct rpi5_rp1_decode_cycle *s,uint32_t offset,uint32_t *value)
{
    if(!retained(s) || s->transactions>=34)return -3;
    const struct rpi5_pcie_config_request r={1,0,0,offset,4,0,0};
    s->transactions++;return rpi5_pcie_config_transfer(s->assignment->config,&r,value)?-4:0;
}
static int expect(struct rpi5_rp1_decode_cycle *s,uint32_t offset,uint32_t mask,uint32_t wanted)
{
    uint32_t value;int rc=read_config(s,offset,&value);
    return rc?rc:((value&mask)==wanted?0:-5);
}
static int inventory(struct rpi5_rp1_decode_cycle *s,uint32_t command)
{
    int rc;
    if((rc=expect(s,0,UINT32_MAX,0x00011de4)) || (rc=expect(s,4,0xffff,command)) ||
        (rc=expect(s,0xc,0x00ff0000,0)) || (rc=expect(s,0x30,1,0)))return rc;
    for(unsigned i=0;i<6;i++)if((rc=expect(s,0x10+4*i,UINT32_MAX,s->assignment->plan.pci_base[i])))return rc;
    return 0;
}
static int command(struct rpi5_rp1_decode_cycle *s,uint32_t value)
{
    if(!retained(s) || s->transactions>=34 || s->writes_started>=2)return -3;
    const struct rpi5_pcie_config_request r={1,0,0,4,2,1,value};
    s->pending_write=1;s->transactions++;s->writes_started++;
    if(!rpi5_rp1_decode_write_allowed(s,&r))return -3;
    int rc=rpi5_pcie_config_transfer(s->assignment->config,&r,0);s->pending_write=0;
    return rc?-4:0;
}
static int mapping(struct rpi5_rp1_decode_cycle *s,unsigned index,unsigned removing)
{
    s->selected=index;s->pending_map=1;
    struct rpi5_range range=index?s->geometry.clock_pages:s->geometry.gem_pages;
    if(!rpi5_rp1_decode_mapping_allowed(s,index,range,removing))return -3;
    int rc=(removing?s->io.unmap:s->io.map)(s->io.context,index,range);
    s->pending_map=0;
    if(rc)return -4;
    if(!retained(s))return -3;
    if(removing)s->unmapped|=1u<<index;else s->mapped|=1u<<index;
    return 0;
}
int rpi5_rp1_decode_run(struct rpi5_rp1_decode_cycle *s,
    const struct rpi5_rp1_assignment *a,const struct rpi5_rp1_decode_io *io,
    struct rpi5_rp1_decode_observation *out)
{
    if(!s || !a || !io || !out || !io->current || !io->map || !io->unmap)return -1;
    if(s->state!=RPI5_RP1_DECODE_EMPTY)return -2;
    if(s->assignment || s->io.context || s->io.current || s->io.map || s->io.unmap ||
        s->original_command || s->transactions || s->writes_started || s->pending_write ||
        s->pending_map || s->selected || s->mapped || s->unmapped ||
        s->geometry.bar1_cpu.start || s->geometry.bar1_cpu.end ||
        s->geometry.gem_pages.start || s->geometry.gem_pages.end ||
        s->geometry.clock_pages.start || s->geometry.clock_pages.end)return fail(s,-2);
    s->state=RPI5_RP1_DECODE_CHECKING;s->assignment=a;s->io=*io;s->original_command=a->command;
    if(!a->config || io->context!=a->config->io.context || io->current(io->context,s,a) ||
        rpi5_rp1_bars_mapping_candidate(a,a->binding,&s->geometry) || !retained(s))return fail(s,-3);
    int rc=inventory(s,s->original_command);if(rc)return fail(s,rc);
    s->state=RPI5_RP1_DECODE_ENABLING;
    if((rc=command(s,s->original_command|2)) || (rc=expect(s,4,0xffff,s->original_command|2)))return fail(s,rc);
    s->state=RPI5_RP1_DECODE_ENABLED;
    if((rc=inventory(s,s->original_command|2)))return fail(s,rc);
    s->state=RPI5_RP1_DECODE_MAPPING;
    for(unsigned i=0;i<2;i++)if((rc=mapping(s,i,0)))return fail(s,rc);
    s->state=RPI5_RP1_DECODE_MAPPED;
    /* No device-register dereference in this mapping-only version. */
    s->state=RPI5_RP1_DECODE_UNMAPPING;
    for(unsigned i=2;i;i--)if((rc=mapping(s,i-1,1)))return fail(s,rc);
    s->state=RPI5_RP1_DECODE_DISABLING;
    if((rc=expect(s,4,0xffff,s->original_command|2)) || (rc=command(s,s->original_command)) ||
        (rc=inventory(s,s->original_command)))return fail(s,rc);
    if(!retained(s))return fail(s,-3);
    s->state=RPI5_RP1_DECODE_COMPLETE;
    struct rpi5_rp1_decode_observation result={s->original_command,s->original_command|2,
        s->original_command,s->transactions,s->writes_started,s->mapped,s->unmapped,s->geometry};
    *out=result;return 0;
}
