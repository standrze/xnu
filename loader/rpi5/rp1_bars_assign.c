/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_bars_assign.h"

static int fail(struct rpi5_rp1_assignment *s, int rc)
{
    s->pending_write=0;s->state=RPI5_RP1_ASSIGN_QUARANTINED;return rc;
}
static int same_plan(const struct rpi5_rp1_bars_plan *a,const struct rpi5_rp1_bars_plan *b)
{
    if(a->present!=b->present || a->gem_pages.start!=b->gem_pages.start ||
        a->gem_pages.end!=b->gem_pages.end || a->clock_pages.start!=b->clock_pages.start ||
        a->clock_pages.end!=b->clock_pages.end)return 0;
    for(unsigned i=0;i<6;i++)if(a->pci_base[i]!=b->pci_base[i] ||
        a->cpu[i].start!=b->cpu[i].start || a->cpu[i].end!=b->cpu[i].end)return 0;
    return 1;
}
static int same_window(const struct rpi5_pcie_outbound_encoding *a,
    const struct rpi5_pcie_outbound_encoding *b)
{
    return a->cpu_base==b->cpu_base && a->declared_end==b->declared_end &&
        a->decode_end==b->decode_end && a->pci_base==b->pci_base && a->size==b->size &&
        a->pci_lo==b->pci_lo && a->pci_hi==b->pci_hi && a->base_limit==b->base_limit &&
        a->base_hi==b->base_hi && a->limit_hi==b->limit_hi && a->padding_bytes==b->padding_bytes;
}
static int retained(const struct rpi5_rp1_assignment *s)
{
    if(!s->config || !s->config->link || !s->config->link->windows || !s->probe || !s->sizes ||
        !s->binding || !s->source.current || s->source.context!=s->config->io.context ||
        s->source.current(s->source.context,s->config,s->binding,s->probe,s->sizes) ||
        s->probe->state!=RPI5_RP1_BARS_COMPLETE || s->probe->transactions!=49 ||
        s->probe->writes_started!=12 || s->probe->selected!=5 ||
        s->sizes->transactions!=49 || s->sizes->command!=s->command ||
        (s->command&7) || s->sizes->present!=s->plan.present)return 0;
    for(unsigned i=0;i<6;i++)if(s->probe->originals[i]!=s->originals[i] ||
        s->sizes->bar[i].original!=s->originals[i] || s->sizes->bar[i].size!=s->sizes_saved[i] ||
        s->sizes->bar[i].mask!=s->masks_saved[i])return 0;
    for(unsigned i=0;i<2;i++)if(!same_window(&s->windows[i],&s->config->link->windows->plan.outbound[i]))return 0;
    return 1;
}
int rpi5_rp1_assignment_write_allowed(const struct rpi5_rp1_assignment *s,
    const struct rpi5_pcie_config_request *r)
{
    if(!s || !r || !s->pending_write || s->selected>=6 ||
        !(s->plan.present&(1u<<s->selected)) || !retained(s) ||
        r->bus!=1 || r->device || r->function || r->offset!=0x10+4*s->selected ||
        r->width!=4 || r->write!=1)return 0;
    return (s->state==RPI5_RP1_ASSIGN_WRITING && r->value==s->plan.pci_base[s->selected]) ||
        (s->state==RPI5_RP1_ASSIGN_RESTORING && r->value==s->originals[s->selected]);
}
static int read_config(struct rpi5_rp1_assignment *s,uint32_t offset,uint32_t *value)
{
    if(!retained(s) || s->transactions>=76)return -3;
    const struct rpi5_pcie_config_request r={1,0,0,offset,4,0,0};
    s->transactions++;return rpi5_pcie_config_transfer(s->config,&r,value)?-4:0;
}
static int expect(struct rpi5_rp1_assignment *s,uint32_t offset,uint32_t mask,uint32_t wanted)
{
    uint32_t value;int rc=read_config(s,offset,&value);
    return rc?rc:((value&mask)==wanted?0:-5);
}
static int inventory(struct rpi5_rp1_assignment *s,const uint32_t *bars)
{
    int rc;
    if((rc=expect(s,0,UINT32_MAX,0x00011de4)) ||
       (rc=expect(s,4,0xffff,s->command)) ||
       (rc=expect(s,0xc,0x00ff0000,0)) ||
       (rc=expect(s,0x30,1,0)))return rc;
    for(unsigned i=0;i<6;i++)if((rc=expect(s,0x10+4*i,UINT32_MAX,bars[i])))return rc;
    return 0;
}
static int write_bar(struct rpi5_rp1_assignment *s,uint32_t value)
{
    if(!retained(s) || s->transactions>=76 || s->writes_started>=12)return -3;
    const struct rpi5_pcie_config_request r={1,0,0,0x10+4*s->selected,4,1,value};
    s->pending_write=1;s->transactions++;s->writes_started++;
    if(!rpi5_rp1_assignment_write_allowed(s,&r))return -3;
    int rc=rpi5_pcie_config_transfer(s->config,&r,0);s->pending_write=0;
    return rc?-4:0;
}
static void publish(const struct rpi5_rp1_assignment *s,const uint32_t *bars,
    struct rpi5_rp1_assignment_observation *out)
{
    for(unsigned i=0;i<6;i++)out->bar[i]=bars[i];
    out->command=s->command;out->transactions=s->transactions;out->writes_started=s->writes_started;
}
int rpi5_rp1_bars_assign(struct rpi5_rp1_assignment *s,struct rpi5_pcie_config *config,
    const struct rpi5_pcie_fdt *binding,const struct rpi5_rp1_bars_probe *probe,
    const struct rpi5_rp1_bars_size *sizes,const struct rpi5_rp1_assignment_source *source,
    struct rpi5_rp1_assignment_observation *out)
{
    if(!s || !config || !binding || !probe || !sizes || !source || !source->current || !out)return -1;
    if(s->state!=RPI5_RP1_ASSIGN_EMPTY)return -2;
    s->state=RPI5_RP1_ASSIGN_CHECKING;
    struct rpi5_rp1_bars_plan plan;
    struct rpi5_pcie_window_plan windows;
    if(source->context!=config->io.context || source->current(source->context,config,binding,probe,sizes) ||
        rpi5_rp1_bars_assignment_plan(binding,probe,sizes,&plan) ||
        rpi5_pcie_windows_plan(binding,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES,&windows) ||
        !config->link || !config->link->windows)return fail(s,-3);
    for(unsigned i=0;i<2;i++) {
        if(!same_window(&windows.outbound[i],&config->link->windows->plan.outbound[i]))return fail(s,-3);
        s->windows[i]=windows.outbound[i];
    }
    s->config=config;s->binding=binding;s->probe=probe;s->sizes=sizes;s->source=*source;
    s->plan=plan;s->command=sizes->command;
    for(unsigned i=0;i<6;i++) {
        s->originals[i]=probe->originals[i];s->sizes_saved[i]=sizes->bar[i].size;s->masks_saved[i]=sizes->bar[i].mask;
    }
    int rc=inventory(s,s->originals);if(rc)return fail(s,rc);
    for(unsigned i=0;i<6;i++)if(plan.present&(1u<<i)) {
        s->selected=i;s->state=RPI5_RP1_ASSIGN_WRITING;
        if((rc=expect(s,4,0xffff,s->command)) || (rc=write_bar(s,plan.pci_base[i])))return fail(s,rc);
        s->state=RPI5_RP1_ASSIGN_VERIFYING;
        if((rc=expect(s,0x10+4*i,UINT32_MAX,plan.pci_base[i])))return fail(s,rc);
        s->assigned_mask|=1u<<i;
    }
    if((rc=inventory(s,plan.pci_base)))return fail(s,rc);
    s->state=RPI5_RP1_ASSIGN_ASSIGNED;publish(s,plan.pci_base,out);return 0;
}
int rpi5_rp1_bars_restore(struct rpi5_rp1_assignment *s,struct rpi5_rp1_assignment_observation *out)
{
    if(!s || !out)return -1;
    if(s->state!=RPI5_RP1_ASSIGN_ASSIGNED)return -2;
    s->state=RPI5_RP1_ASSIGN_VERIFYING;
    if(!retained(s) || s->assigned_mask!=s->plan.present)return fail(s,-3);
    int rc=inventory(s,s->plan.pci_base);if(rc)return fail(s,rc);
    for(unsigned i=0;i<6;i++)if(s->plan.present&(1u<<i)) {
        s->selected=i;s->state=RPI5_RP1_ASSIGN_RESTORING;
        if((rc=expect(s,4,0xffff,s->command)) || (rc=write_bar(s,s->originals[i])))return fail(s,rc);
        s->state=RPI5_RP1_ASSIGN_VERIFYING;
        if((rc=expect(s,0x10+4*i,UINT32_MAX,s->originals[i])))return fail(s,rc);
        s->restored_mask|=1u<<i;
    }
    if((rc=inventory(s,s->originals)))return fail(s,rc);
    s->state=RPI5_RP1_ASSIGN_RESTORED;publish(s,s->originals,out);return 0;
}
int rpi5_rp1_bars_mapping_candidate(const struct rpi5_rp1_assignment *s,
    const struct rpi5_pcie_fdt *binding,struct rpi5_rp1_mapping_candidate *out)
{
    if(!s || !binding || !out || binding!=s->binding || s->state!=RPI5_RP1_ASSIGN_ASSIGNED || !retained(s) ||
        s->pending_write || s->assigned_mask!=s->plan.present)return -1;
    struct rpi5_rp1_bars_plan plan;
    if(rpi5_rp1_bars_assignment_plan(binding,s->probe,s->sizes,&plan) || !same_plan(&plan,&s->plan))return -1;
    struct rpi5_rp1_mapping_candidate result={plan.cpu[1],plan.gem_pages,plan.clock_pages};
    *out=result;return 0;
}
