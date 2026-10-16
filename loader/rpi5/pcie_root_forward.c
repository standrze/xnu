/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_root_forward.h"

/* Independent implementation from Raspberry Pi Linux at
 * 80d4218cb877ccb07d09a9f21f0678e78d8b36f5:
 * pci/setup-bus.c pci_setup_bridge_mmio, pci/setup-res.c pci_enable_resources,
 * pci/pci.c pci_enable_bridge, controller/pcie-brcmstb.c map_bus/outbound_win.
 * Root bridge forwarding is distinct from host outbound translation and from
 * endpoint COMMAND.MEM. We deliberately do NOT copy Linux's pci_set_master. */
static int fail(struct rpi5_root_forward *s,int rc)
{s->pending=0;s->state=RPI5_ROOT_FORWARD_QUARANTINED;return rc;}
static int retained(const struct rpi5_root_forward *s)
{
    const struct rpi5_rp1_decode_cycle *d=s->decode;
    return d && d->state==RPI5_RP1_DECODE_MAPPED && d->mapped==3 && !d->unmapped &&
        !d->pending_map && !d->pending_write && d->assignment && d->assignment->config &&
        d->assignment->state==RPI5_RP1_ASSIGN_ASSIGNED && s->io.current && s->io.read &&
        s->io.write && s->io.identify && s->io.context==d->io.context && d->io.current &&
        !d->io.current(d->io.context,d,d->assignment) && !s->io.current(s->io.context,s,d);
}
static int plan(const struct rpi5_root_forward *s,uint32_t *out)
{
    if(!retained(s))return -3;
    const struct rpi5_rp1_assignment *a=s->decode->assignment;
    struct rpi5_rp1_mapping_candidate g;
    if(rpi5_rp1_bars_mapping_candidate(a,a->binding,&g) ||
        g.bar1_cpu.start!=s->decode->geometry.bar1_cpu.start || g.bar1_cpu.end!=s->decode->geometry.bar1_cpu.end ||
        g.gem_pages.start!=s->decode->geometry.gem_pages.start || g.gem_pages.end!=s->decode->geometry.gem_pages.end ||
        g.clock_pages.start!=s->decode->geometry.clock_pages.start || g.clock_pages.end!=s->decode->geometry.clock_pages.end)return -3;
    uint64_t low=UINT64_MAX,high=0;
    for(unsigned n=0;n<6;n++)if(a->plan.present&(1u<<n)){
        uint64_t start=a->plan.pci_base[n],size=a->sizes_saved[n];
        if(!size || start>=UINT64_C(0x100000000) || size>UINT64_C(0x100000000)-start)return -3;
        if(start<low)low=start;
        if(start+size>high)high=start+size;
    }
    if(low>=high)return -3;
    low&=~UINT64_C(0xfffff);high=((high-1)|UINT64_C(0xfffff))+1;
    const struct rpi5_pcie_outbound_encoding *w=&a->windows[0];
    if(low<w->pci_base || high-low>w->size || low-w->pci_base>w->size-(high-low))return -3;
    *out=(uint32_t)((low>>16)&0xfff0)|(uint32_t)((high-1)&0xfff00000);return 0;
}
int rpi5_root_forward_access_allowed(const struct rpi5_root_forward *s,uint32_t offset,
    unsigned width,unsigned write,uint32_t value)
{
    if(!s || !s->pending || !retained(s) || s->state==RPI5_ROOT_FORWARD_EMPTY ||
        s->state>=RPI5_ROOT_FORWARD_COMPLETE || s->offset!=offset || s->width!=width ||
        s->write!=write || s->value!=value)return 0;
    if(write)return (offset==4 && width==2 && ((s->state==RPI5_ROOT_FORWARD_ENABLING &&
        value==(s->before.command|2)) || (s->state==RPI5_ROOT_FORWARD_DISABLING && value==s->before.command))) ||
        (offset==0x20 && width==4 && ((s->state==RPI5_ROOT_FORWARD_WINDOW && value==s->wanted_window) ||
        (s->state==RPI5_ROOT_FORWARD_RESTORING && value==s->before.window)));
    if(value)return 0;
    if(offset==4)return width==2;
    if(width!=4)return 0;
    if(offset==0 || offset==0xc || offset==0x18 || offset==0x20)return 1;
    for(unsigned i=0;i<2;i++)if(offset==0x400c+8*i || offset==0x4010+8*i ||
        offset==0x4070+4*i || offset==0x4080+8*i || offset==0x4084+8*i)return 1;
    return 0;
}
static int read_reg(struct rpi5_root_forward *s,uint32_t offset,unsigned width,uint32_t *out)
{
    if(!retained(s) || s->reads>=79)return -3;
    s->offset=offset;s->width=width;s->write=0;s->value=0;s->pending=1;s->reads++;
    if(!rpi5_root_forward_access_allowed(s,offset,width,0,0))return -3;
    uint32_t value=0;int rc=s->io.read(s->io.context,offset,width,&value);s->pending=0;
    if(rc)return -4;
    s->value=value;
    if(!retained(s))return -3;
    if(value==(width==2?UINT16_MAX:UINT32_MAX) || (width==2 && value>UINT16_MAX))return -5;
    *out=value;return 0;
}
static int write_reg(struct rpi5_root_forward *s,uint32_t offset,unsigned width,uint32_t value)
{
    if(!retained(s) || s->writes>=4)return -3;
    s->offset=offset;s->width=width;s->write=1;s->value=value;s->pending=1;s->writes++;
    if(!rpi5_root_forward_access_allowed(s,offset,width,1,value))return -3;
    int rc=s->io.write(s->io.context,offset,width,value);s->pending=0;
    if(rc)return -4;
    if(!retained(s))return -3;
    uint32_t actual;rc=read_reg(s,offset,width,&actual);
    return rc?rc:(actual==value?0:-5);
}
static int inventory(struct rpi5_root_forward *s,uint32_t command,uint32_t window,
    struct rpi5_root_forward_snapshot *out,unsigned initial)
{
    int rc;struct rpi5_root_forward_snapshot v={};
    if((rc=read_reg(s,0,4,&v.id)) || (rc=read_reg(s,0xc,4,&v.header)) ||
        (rc=read_reg(s,0x18,4,&v.buses)) || (rc=read_reg(s,4,2,&v.command)) ||
        (rc=read_reg(s,0x20,4,&v.window)))return rc;
    if(v.id!=0x271214e4 || (v.header&0xff0000)!=0x10000 || (v.buses&0xffffff)!=0x10100 ||
        (initial?((v.command&7) || (v.window&0x000f000f)):
        (v.command!=command || v.window!=window || v.header!=s->before.header || v.buses!=s->before.buses)))return -5;
    for(unsigned i=0;i<2;i++){
        const struct rpi5_pcie_outbound_encoding *w=&s->decode->assignment->windows[i];
        const uint32_t offset[]={0x400c+8*i,0x4010+8*i,0x4070+4*i,0x4080+8*i,0x4084+8*i};
        const uint32_t mask[]={UINT32_MAX,UINT32_MAX,0xfff0fff0,0xff,0xff};
        const uint32_t expected[]={w->pci_lo,w->pci_hi,w->base_limit,w->base_hi,w->limit_hi};
        for(unsigned n=0;n<5;n++){
            uint32_t actual;if((rc=read_reg(s,offset[n],4,&actual)))return rc;
            if((actual&mask[n])!=expected[n] || (!initial && actual!=s->outbound[5*i+n]))return -5;
            if(initial)s->outbound[5*i+n]=actual;
        }
    }
    *out=v;return 0;
}
int rpi5_root_forward_run(struct rpi5_root_forward *s,const struct rpi5_rp1_decode_cycle *d,
    const struct rpi5_root_forward_io *io,struct rpi5_root_forward_observation *out)
{
    if(!s || !d || !io || !out || !io->current || !io->read || !io->write || !io->identify)return -1;
    if(s->state!=RPI5_ROOT_FORWARD_EMPTY)return -2;
    if(s->decode || s->io.context || s->io.current || s->io.read || s->io.write || s->io.identify ||
        s->wanted_window || s->reads || s->writes || s->pending || s->offset || s->width || s->write || s->value)return fail(s,-2);
    const struct rpi5_root_forward_snapshot *snap[]={&s->before,&s->live,&s->after};
    for(unsigned n=0;n<3;n++)if(snap[n]->id || snap[n]->header || snap[n]->buses || snap[n]->command || snap[n]->window)return fail(s,-2);
    for(unsigned n=0;n<10;n++)if(s->outbound[n])return fail(s,-2);
    s->decode=d;s->io=*io;s->state=RPI5_ROOT_FORWARD_CHECKING;
    int rc=plan(s,&s->wanted_window);if(rc)return fail(s,rc);
    if((rc=inventory(s,0,0,&s->before,1)))return fail(s,rc);
    s->state=RPI5_ROOT_FORWARD_WINDOW;
    if((rc=write_reg(s,0x20,4,s->wanted_window)))return fail(s,rc);
    struct rpi5_root_forward_snapshot scratch;
    if((rc=inventory(s,s->before.command,s->wanted_window,&scratch,0)))return fail(s,rc);
    s->state=RPI5_ROOT_FORWARD_ENABLING;
    if((rc=write_reg(s,4,2,s->before.command|2)))return fail(s,rc);
    if((rc=inventory(s,s->before.command|2,s->wanted_window,&s->live,0)))return fail(s,rc);
    s->state=RPI5_ROOT_FORWARD_LIVE;
    if((rc=s->io.identify(s->io.context,d)))return fail(s,rc);
    if(!retained(s))return fail(s,-3);
    if((rc=inventory(s,s->before.command|2,s->wanted_window,&scratch,0)))return fail(s,rc);
    s->state=RPI5_ROOT_FORWARD_DISABLING;
    if((rc=write_reg(s,4,2,s->before.command)))return fail(s,rc);
    s->state=RPI5_ROOT_FORWARD_RESTORING;
    if((rc=write_reg(s,0x20,4,s->before.window)) ||
        (rc=inventory(s,s->before.command,s->before.window,&s->after,0)))return fail(s,rc);
    uint32_t checked;
    if(plan(s,&checked) || checked!=s->wanted_window || s->reads!=79 || s->writes!=4)return fail(s,-3);
    struct rpi5_root_forward_observation result={s->before,s->live,s->after,s->wanted_window,s->reads,s->writes};
    s->state=RPI5_ROOT_FORWARD_COMPLETE;*out=result;return 0;
}
