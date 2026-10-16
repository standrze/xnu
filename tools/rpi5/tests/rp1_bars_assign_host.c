/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual probe -> planner -> assignment -> restoration, real config engine.
 * Register/mask/locking/controller-completion are explicit host doubles. */
#include "prior_bars_probe_host.c"
#include "rp1_bars_assign.h"

static struct rpi5_rp1_assignment *assignment;
static unsigned char assign_releases[2048];
static unsigned assign_corrupt_read;
static struct rpi5_rp1_assignment_source source;
static const struct rpi5_pcie_config *owned_config;
static const struct rpi5_pcie_fdt *owned_binding;
static const struct rpi5_rp1_bars_probe *owned_probe;
static const struct rpi5_rp1_bars_size *owned_sizes;
static unsigned owner_live,owner_thread,owner_phase,current_calls,current_fail;
static int current(void *context,const struct rpi5_pcie_config *config,
    const struct rpi5_pcie_fdt *binding,const struct rpi5_rp1_bars_probe *probe,
    const struct rpi5_rp1_bars_size *sizes)
{
    current_calls++;
    return current_calls==current_fail || !owner_live || !owner_thread || !owner_phase ||
        context!=source.context || config!=owned_config || binding!=owned_binding ||
        probe!=owned_probe || sizes!=owned_sizes ? -1:0;
}
static int assign_authorize(void *context,const struct rpi5_pcie_config_request *r)
{
    return authorize(context,r) || !rpi5_rp1_assignment_write_allowed(assignment,r)?-1:0;
}
static int assign_read(void *context,uint32_t offset,uint32_t width,uint32_t *out)
{
    int rc=read_value(context,offset,width,out);struct model *m=context;
    if(!rc && offset>=0x8000 && offset<0x9000 && m->reads==assign_corrupt_read)
        *out^=offset==0x800c?0x10000:1;
    return rc;
}
static int assign_write(void *context,uint32_t offset,uint32_t width,uint32_t value)
{
    if(offset!=0x9000) {
        assert(offset>=0x8010 && offset<=0x8024 && width==4);
        const struct rpi5_pcie_config_request request={1,0,0,offset-0x8000,4,1,value};
        if(!rpi5_rp1_assignment_write_allowed(assignment,&request))return -1;
        assert(value!=UINT32_MAX && !(value&15));
    }
    return write_value(context,offset,width,value);
}
static void assign_release(void *context)
{
    struct model *m=context;assert(m->calls+1<sizeof assign_releases);
    assign_releases[m->calls+1]=1;release(context);
}
static void prepare(struct fixture *f,struct rpi5_rp1_bars_probe *probe,
    struct rpi5_rp1_bars_size *sizes,struct rpi5_pcie_fdt *binding,
    struct rpi5_rp1_assignment *s,unsigned all_six)
{
    struct rpi5_rp1_config_snapshot snapshot;bars_setup(f,probe,&snapshot);
    for(unsigned i=0;i<6;i++) {
        if(all_six && i>=3)masks[i]=0xffffc000;
        snapshot.header[4+i]=masks[i];
        memcpy(&f->m.bytes[1][0x10+4*i],&masks[i],4);
    }
    snapshot.bar1_pci_base=snapshot.header[5];
    assert(!rpi5_rp1_bars_probe(probe,&f->config,&snapshot,sizes));
    memset(binding,0,sizeof *binding);binding->bridge_regs=(struct rpi5_range){0x1000120000,0x1000129310};
    binding->outbound_count=2;binding->dma_count=3;
    binding->outbound[0]=(struct rpi5_pcie_window){0x02000000,0,UINT64_C(0x1f00000000),0xfffffffc};
    binding->outbound[1]=(struct rpi5_pcie_window){0x43000000,UINT64_C(0x400000000),UINT64_C(0x1c00000000),UINT64_C(0x300000000)};
    binding->dma[0]=(struct rpi5_pcie_window){0x02000000,0,UINT64_C(0x1f00000000),0x400000};
    binding->dma[1]=(struct rpi5_pcie_window){0x43000000,UINT64_C(0x1000000000),0,UINT64_C(0x1000000000)};
    binding->dma[2]=(struct rpi5_pcie_window){0x03000000,UINT64_C(0xfffffff000),UINT64_C(0x1000130000),0x1000};
    binding->mip_target=(struct rpi5_range){0xfffffff000,0x10000000000};
    binding->mip_regs=(struct rpi5_range){0x1000130000,0x10001300c0};
    binding->rp1_aperture_size=0x410000;binding->gem_bar_offset=0x100000;binding->gem_size=0x4000;
    binding->clock_bar_offset=0x18000;binding->clock_size=0x10038;
    assert(!rpi5_pcie_windows_plan(binding,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES,&f->windows.plan));
    memset(s,0,sizeof *s);assignment=s;assign_corrupt_read=0;
    source=(struct rpi5_rp1_assignment_source){&f->m,current};
    owned_config=&f->config;owned_binding=binding;owned_probe=probe;owned_sizes=sizes;
    owner_live=owner_thread=owner_phase=1;current_calls=current_fail=0;
    f->m.calls=f->m.reads=f->m.writes=0;memset(assign_releases,0,sizeof assign_releases);
    f->config.io.authorize_write=assign_authorize;f->config.io.read=assign_read;
    f->config.io.write=assign_write;f->config.io.release=assign_release;
}
static void partial_only(const struct fixture *f,const struct rpi5_rp1_assignment *s,
    const unsigned char initial[2][4096])
{
    assert(!memcmp(f->m.bytes[0],initial[0],4096));
    for(unsigned offset=0;offset<4096;offset++) {
        if(offset>=0x10 && offset<0x28)continue;
        assert(f->m.bytes[1][offset]==initial[1][offset]);
    }
    for(unsigned i=0;i<6;i++) {
        uint32_t actual,original;memcpy(&actual,&f->m.bytes[1][0x10+4*i],4);
        memcpy(&original,&initial[1][0x10+4*i],4);
        assert(actual==original || ((s->plan.present&(1u<<i)) && actual==s->plan.pci_base[i]));
    }
    assert(!f->m.locked);
}
int main(void)
{
    struct fixture f;struct rpi5_rp1_bars_probe probe;struct rpi5_rp1_bars_size sizes;
    struct rpi5_pcie_fdt binding;struct rpi5_rp1_assignment s;
    struct rpi5_rp1_assignment_observation out;struct rpi5_rp1_mapping_candidate map;
    unsigned char nonfailing[2048];unsigned callbacks,reads,assign_calls,faults=0;
    for(unsigned all=0;all<2;all++) {
        prepare(&f,&probe,&sizes,&binding,&s,all);
        unsigned char initial[2][4096];memcpy(initial,f.m.bytes,sizeof initial);
        assert(!rpi5_rp1_bars_assign(&s,&f.config,&binding,&probe,&sizes,&source,&out));
        assert(s.state==RPI5_RP1_ASSIGN_ASSIGNED && out.command==0x400 && out.bar[1]==0);
        assert(out.bar[0]==0x410000 && out.bar[2]==0x400000 && s.assigned_mask==(all?63u:7u));
        unsigned before=f.m.calls;
        assert(!rpi5_rp1_bars_mapping_candidate(&s,&binding,&map) && f.m.calls==before);
        assert(map.bar1_cpu.start==UINT64_C(0x1f00000000) && map.bar1_cpu.end==UINT64_C(0x1f00400000));
        assert(map.gem_pages.start==UINT64_C(0x1f00100000) && map.clock_pages.start==UINT64_C(0x1f00018000));
        assign_calls=f.m.calls;
        assert(!rpi5_rp1_bars_restore(&s,&out));
        assert(s.state==RPI5_RP1_ASSIGN_RESTORED && s.restored_mask==s.plan.present);
        assert(s.transactions==(all?76u:58u) && s.writes_started==(all?12u:6u));
        assert(!memcmp(f.m.bytes,initial,sizeof initial));
        assert(rpi5_rp1_bars_mapping_candidate(&s,&binding,&map));
        callbacks=f.m.calls;reads=f.m.reads;memcpy(nonfailing,assign_releases,sizeof nonfailing);finish(&f);
        for(unsigned fault=1;fault<=callbacks;fault++)if(!nonfailing[fault]) {
            prepare(&f,&probe,&sizes,&binding,&s,all);f.m.fail_at=fault;
            memcpy(initial,f.m.bytes,sizeof initial);memset(&out,0xa5,sizeof out);
            struct rpi5_rp1_assignment_observation before_out=out;
            int rc=rpi5_rp1_bars_assign(&s,&f.config,&binding,&probe,&sizes,&source,&out);
            if(!rc) {assert(fault>assign_calls);memset(&out,0xa5,sizeof out);rc=rpi5_rp1_bars_restore(&s,&out);}
            assert(rc && s.state==RPI5_RP1_ASSIGN_QUARANTINED && !memcmp(&out,&before_out,sizeof out));
            assert(f.m.calls==fault || f.m.calls==fault+1);partial_only(&f,&s,initial);
            unsigned stopped=f.m.calls;
            assert(rpi5_rp1_bars_restore(&s,&out)==-2 && rpi5_rp1_bars_assign(&s,&f.config,&binding,&probe,&sizes,&source,&out)==-2);
            assert(f.m.calls==stopped && !s.pending_write);finish(&f);faults++;
        }
        for(unsigned read=1;read<=reads;read++) {
            prepare(&f,&probe,&sizes,&binding,&s,all);assign_corrupt_read=read;
            memcpy(initial,f.m.bytes,sizeof initial);memset(&out,0xa5,sizeof out);
            struct rpi5_rp1_assignment_observation before_out=out;
            int rc=rpi5_rp1_bars_assign(&s,&f.config,&binding,&probe,&sizes,&source,&out);
            if(!rc){memset(&out,0xa5,sizeof out);rc=rpi5_rp1_bars_restore(&s,&out);}
            assert(rc && s.state==RPI5_RP1_ASSIGN_QUARANTINED && f.m.reads==read && !memcmp(&out,&before_out,sizeof out));
            partial_only(&f,&s,initial);finish(&f);
        }
    }
    for(unsigned bad=0;bad<12;bad++) {
        prepare(&f,&probe,&sizes,&binding,&s,0);
        if(bad==0)probe.state=RPI5_RP1_BARS_FAILED;
        else if(bad==1)probe.transactions--;
        else if(bad==2)sizes.command|=2;
        else if(bad==3)sizes.bar[1].mask|=4;
        else if(bad==4)f.windows.plan.outbound[0].base_limit^=0x10;
        else if(bad==5)f.windows.plan.outbound[0].pci_base+=0x100000;
        else if(bad==6)binding.outbound[0].size=0x400000;
        else if(bad==7)binding.outbound[0].cpu_base+=0x4000;
        else if(bad==8)binding.gem_bar_offset=UINT64_MAX;
        else if(bad==9)sizes.present&=~2u;
        else if(bad==10)f.config.link=0;
        else probe.originals[0]^=0x4000;
        memset(&out,0xa5,sizeof out);struct rpi5_rp1_assignment_observation before_out=out;
        assert(rpi5_rp1_bars_assign(&s,&f.config,&binding,&probe,&sizes,&source,&out) && !f.m.calls);
        assert(!memcmp(&out,&before_out,sizeof out));finish(&f);
    }
    for(unsigned change=0;change<6;change++) {
        prepare(&f,&probe,&sizes,&binding,&s,0);assert(!rpi5_rp1_bars_assign(&s,&f.config,&binding,&probe,&sizes,&source,&out));
        if(change==0)probe.state=RPI5_RP1_BARS_FAILED;
        else if(change==1)sizes.bar[1].size>>=1;
        else if(change==2)sizes.bar[1].mask^=0x400000;
        else if(change==3)f.windows.plan.outbound[0].cpu_base+=0x100000;
        else if(change==4)sizes.command|=4;
        else s.assigned_mask^=1;
        unsigned stopped=f.m.calls;memset(&map,0xa5,sizeof map);struct rpi5_rp1_mapping_candidate before_map=map;
        assert(rpi5_rp1_bars_mapping_candidate(&s,&binding,&map) && !memcmp(&map,&before_map,sizeof map));
        memset(&out,0xa5,sizeof out);struct rpi5_rp1_assignment_observation before_out=out;
        assert(rpi5_rp1_bars_restore(&s,&out) && f.m.calls==stopped && !memcmp(&out,&before_out,sizeof out));finish(&f);
    }
    /* A source must be this live owner's exact session set, not equal copied
     * historical structs. Also check live thread/phase revocation after assign. */
    for(unsigned stale=0;stale<9;stale++) {
        prepare(&f,&probe,&sizes,&binding,&s,0);
        struct rpi5_pcie_config other_config=f.config;
        struct rpi5_rp1_bars_probe other_probe=probe;
        struct rpi5_rp1_bars_size other_sizes=sizes;
        struct rpi5_pcie_fdt other_binding=binding;
        if(stale==0)owner_live=0;
        if(stale==1)owner_thread=0;
        if(stale==2)owner_phase=0;
        if(stale==7)source.context=&s;
        if(stale==8)source.current=0;
        memset(&out,0xa5,sizeof out);struct rpi5_rp1_assignment_observation before_out=out;
        assert(rpi5_rp1_bars_assign(&s,stale==3?&other_config:&f.config,stale==4?&other_binding:&binding,
            stale==5?&other_probe:&probe,stale==6?&other_sizes:&sizes,&source,&out));
        assert(!f.m.calls && !memcmp(&out,&before_out,sizeof out));finish(&f);
    }
    for(unsigned stale=0;stale<7;stale++) {
        prepare(&f,&probe,&sizes,&binding,&s,0);
        assert(!rpi5_rp1_bars_assign(&s,&f.config,&binding,&probe,&sizes,&source,&out));
        struct rpi5_pcie_config other_config=f.config;struct rpi5_rp1_bars_probe other_probe=probe;
        struct rpi5_rp1_bars_size other_sizes=sizes;struct rpi5_pcie_fdt other_binding=binding;
        if(stale==0)owner_live=0;if(stale==1)owner_thread=0;if(stale==2)owner_phase=0;
        if(stale==3)s.config=&other_config;if(stale==4)s.binding=&other_binding;
        if(stale==5)s.probe=&other_probe;if(stale==6)s.sizes=&other_sizes;
        unsigned stopped=f.m.calls;memset(&map,0xa5,sizeof map);
        struct rpi5_rp1_mapping_candidate before_map=map;
        assert(rpi5_rp1_bars_mapping_candidate(&s,s.binding,&map) && !memcmp(&map,&before_map,sizeof map));
        memset(&out,0xa5,sizeof out);struct rpi5_rp1_assignment_observation before_out=out;
        assert(rpi5_rp1_bars_restore(&s,&out) && f.m.calls==stopped && !memcmp(&out,&before_out,sizeof out));
        assert(s.state==RPI5_RP1_ASSIGN_QUARANTINED);finish(&f);
    }
    prepare(&f,&probe,&sizes,&binding,&s,1);
    assert(!rpi5_rp1_bars_assign(&s,&f.config,&binding,&probe,&sizes,&source,&out));
    assert(!rpi5_rp1_bars_restore(&s,&out));unsigned source_checks=current_calls;finish(&f);
    for(unsigned fault=1;fault<=source_checks;fault++) {
        prepare(&f,&probe,&sizes,&binding,&s,1);current_fail=fault;
        unsigned char initial[2][4096];memcpy(initial,f.m.bytes,sizeof initial);
        memset(&out,0xa5,sizeof out);struct rpi5_rp1_assignment_observation before_out=out;
        int rc=rpi5_rp1_bars_assign(&s,&f.config,&binding,&probe,&sizes,&source,&out);
        if(!rc){memset(&out,0xa5,sizeof out);rc=rpi5_rp1_bars_restore(&s,&out);}
        assert(rc && current_calls==fault && s.state==RPI5_RP1_ASSIGN_QUARANTINED);
        assert(!memcmp(&out,&before_out,sizeof out));partial_only(&f,&s,initial);
        unsigned stopped=f.m.calls;assert(rpi5_rp1_bars_restore(&s,&out)==-2 && f.m.calls==stopped);finish(&f);
    }
    prepare(&f,&probe,&sizes,&binding,&s,1);assert(!rpi5_rp1_bars_assign(&s,&f.config,&binding,&probe,&sizes,&source,&out));
    for(unsigned i=0;i<6;i++)for(unsigned restoring=0;restoring<2;restoring++) {
        s.selected=i;s.pending_write=1;s.state=restoring?RPI5_RP1_ASSIGN_RESTORING:RPI5_RP1_ASSIGN_WRITING;
        struct rpi5_pcie_config_request r={1,0,0,0x10+4*i,4,1,restoring?s.originals[i]:s.plan.pci_base[i]};
        assert(rpi5_rp1_assignment_write_allowed(&s,&r));
        for(unsigned field=0;field<7;field++){struct rpi5_pcie_config_request bad=r;((uint32_t*)&bad)[field]^=1;assert(!rpi5_rp1_assignment_write_allowed(&s,&bad));}
        s.pending_write=0;assert(!rpi5_rp1_assignment_write_allowed(&s,&r));
    }
    finish(&f);
    printf("RP1_ASSIGN_PASS MAX_TRANSFERS=76 MAX_WRITES=12 CALLBACK_FAILURES=%u SOURCE_FAILURES=%u REAL_PROBE_CONFIG=1 NO_MEM_ENABLE=1 NO_HARDWARE=1\n",faults,source_checks);
}
