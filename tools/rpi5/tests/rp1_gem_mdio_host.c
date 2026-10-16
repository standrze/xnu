/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_gem_mdio.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct model {
    struct rpi5_gem_mdio_session s;
    struct rpi5_gem_cap_session cap;
    struct rpi5_gem_identify gem;
    struct rpi5_rp1_decode_cycle dec;
    struct rpi5_pcie_fdt binding;
    struct rpi5_gem_mdio_io io;
    struct rpi5_gem_mdio_observation out;
    uint32_t ncr,ncfgr,man,reply[5],commands[5];
    unsigned events,owners,reads,writes,times,nsr,commands_count;
    unsigned event_fail,owner_fail,owner_mutate,owner_reenter,mutation,mutation_at;
    unsigned busy_extra,corrupt_read,read_index,clock_mode,clock_target;
    uint64_t time;
};
static const uint32_t caps[8]={0x70109,0x08508513,0x6eb13fff,0x502e5b45,0x08820000,0,0x24444444,0};
static int run(struct model *m){return rpi5_gem_mdio_run(&m->s,&m->cap,&m->binding,&m->io,&m->out);}
static void mutate(struct model *m)
{
    switch(m->mutation){
    case 1:m->cap.state=RPI5_GEM_CAP_QUARANTINED;break;
    case 2:m->gem.stage=RPI5_GEM_CLOCK_AFTER;break;
    case 3:m->dec.unmapped=1;break;
    case 4:m->binding.phy_address=2;break;
    case 5:m->s.binding=(void *)(uintptr_t)1;break;
    case 6:m->cap.identity=(void *)(uintptr_t)1;break;
    case 7:m->gem.decode=(void *)(uintptr_t)1;break;
    case 8:m->io.current=0;break;
    case 9:m->s.reads++;break;
    case 10:m->gem.before[0]=0;break;
    case 11:m->cap.words[1][3]^=1;break;
    default:assert(run(m));break;
    }
}
static int event(struct model *m)
{m->events++;if(m->mutation_at==m->events)mutate(m);return m->events==m->event_fail?-1:0;}
static int current(void *v,const struct rpi5_gem_mdio_session *s,const struct rpi5_gem_cap_session *c,const struct rpi5_pcie_fdt *b)
{
    struct model *m=v;m->owners++;assert(s==&m->s&&c==&m->cap&&b==&m->binding);
    if(m->owners==m->owner_mutate)m->s.polls++;
    if(m->owners==m->owner_reenter)assert(run(m));
    return m->owners==m->owner_fail?-1:0;
}
static int read_reg(void *v,uint32_t off,uint32_t *out)
{
    struct model *m=v;m->reads++;assert(rpi5_gem_mdio_read_allowed(&m->s,off));
    assert(!rpi5_gem_mdio_read_allowed(&m->s,0x24));
    if(off==0)*out=m->ncr;
    else if(off==4)*out=m->ncfgr;
    else if(off==8){m->nsr++;*out=m->busy_extra?0:4;if(m->busy_extra)m->busy_extra--;}
    else {assert(off==0x34);*out=m->man;}
    if(m->corrupt_read==m->reads)*out^=1;
    return event(m);
}
static int write_reg(void *v,uint32_t off,uint32_t value)
{
    struct model *m=v;m->writes++;assert(rpi5_gem_mdio_write_allowed(&m->s,off,value));
    assert(!rpi5_gem_mdio_write_allowed(&m->s,off,value^1));
    if(off==0)m->ncr=value;
    else if(off==4)m->ncfgr=value;
    else {
        const unsigned regs[]={2,3,0,1,1};assert(off==0x34&&m->commands_count<5);
        unsigned i=m->commands_count++;assert(value==(0x60820000u|(regs[i]<<18)));
        assert(m->ncr&0x10);assert(((m->ncfgr>>18)&7)>=5);
        m->commands[i]=value;m->man=(value&~0xffffu)|m->reply[i];
    }
    return event(m);
}
static int clock_us(void *v,uint64_t *out)
{
    struct model *m=v;m->times++;assert(rpi5_gem_mdio_clock_allowed(&m->s));
    if(m->clock_mode!=1)m->time++;
    if(m->times==m->clock_target){
        if(m->clock_mode==2)m->time=0;
        if(m->clock_mode==3)m->time+=20000;
    }
    *out=m->time;return event(m);
}
static void setup(struct model *m)
{
    memset(m,0,sizeof *m);memset(&m->out,0xa5,sizeof m->out);
    m->io=(struct rpi5_gem_mdio_io){m,current,read_reg,write_reg,clock_us};
    m->cap.self=&m->cap;m->cap.state=RPI5_GEM_CAP_COMPLETE;m->cap.reads=16;m->cap.identity=&m->gem;m->cap.io.context=m;
    memcpy(m->cap.words[0],caps,sizeof caps);memcpy(m->cap.words[1],caps,sizeof caps);
    m->gem.stage=RPI5_GEM_MID_SECOND;m->gem.reads=17;m->gem.clocks_ready=1;m->gem.mid[0]=m->gem.mid[1]=caps[0];
    m->gem.decode=&m->dec;m->gem.io.context=m;
    const uint32_t clocks[15]={2,1,4,0x80000001,4,20,0,0x51010,0x10000800,1,1,0x10000800,1,1,0x80000800};
    memcpy(m->gem.before,clocks,sizeof clocks);
    m->dec.state=RPI5_RP1_DECODE_MAPPED;m->dec.mapped=3;m->dec.io.context=m;
    m->binding.phy_address=1;m->binding.phy_phandle=7;m->binding.gem_bar_offset=0x100000;m->binding.gem_size=0x4000;
    const unsigned ids[4]={12,12,29,16};memcpy(m->binding.gem_clock_id,ids,sizeof ids);
    const unsigned replies[5]={0x600d,0x84a2,0x1140,0x7909,0x792d};memcpy(m->reply,replies,sizeof replies);
    m->time=100;
}
static void failed(struct model *m)
{
    struct rpi5_gem_mdio_observation before=m->out;assert(run(m)<0);
    assert(!memcmp(&m->out,&before,sizeof before)&&m->s.state==RPI5_GEM_MDIO_QUARANTINED&&!m->s.busy&&!m->s.pending);
    unsigned events=m->events,owners=m->owners;assert(run(m)<0&&m->events==events&&m->owners==owners);
}
int main(void)
{
    struct model m;setup(&m);assert(!run(&m));
    assert(m.s.state==RPI5_GEM_MDIO_COMPLETE&&m.commands_count==5&&m.ncr==0&&m.ncfgr==0);
    assert(m.out.phy_id==0x600d84a2&&m.out.bmcr==0x1140&&m.out.bmsr_latched==0x7909&&m.out.bmsr_current==0x792d);
    assert(m.out.link==1&&m.out.autoneg_complete==1&&m.out.changed_divider==1);
    assert(m.out.reads==26&&m.out.writes==9&&m.out.polls==12&&m.out.clocks==37);
    unsigned owners=m.owners,events=m.events,cases=0;
    for(unsigned i=1;i<=events;i++){
        setup(&m);m.event_fail=i;failed(&m);assert(m.events==i);cases++;
        for(unsigned n=1;n<=12;n++){
            setup(&m);m.mutation=n;m.mutation_at=i;failed(&m);assert(m.events==i);cases++;
        }
    }
    for(unsigned i=1;i<=owners;i++){
        setup(&m);m.owner_fail=i;failed(&m);cases++;
        setup(&m);m.owner_mutate=i;failed(&m);cases++;
        setup(&m);m.owner_reenter=i;failed(&m);cases++;
    }
    for(unsigned code=0;code<8;code++){
        setup(&m);m.ncfgr=0xa5234567u&~0x1c0000u;m.ncfgr|=code<<18;uint32_t original=m.ncfgr;
        assert(!run(&m)&&m.ncfgr==original&&m.out.ncfgr_after==original);
        assert(m.out.changed_divider==(code<5));assert(((m.out.ncfgr_live>>18)&7)==(code<5?5:code));
    }
    for(unsigned bit=0;bit<32;bit++){
        setup(&m);m.ncr=1u<<bit;
        if(m.ncr&0x11180000u){assert(!run(&m)&&m.ncr==(1u<<bit));}
        else {failed(&m);assert(!m.writes);}
    }
    setup(&m);m.busy_extra=20;assert(!run(&m));
    assert(m.s.polls==32&&m.s.reads==46&&m.s.writes==9&&m.s.clocks==57&&m.events==112);
    setup(&m);m.busy_extra=21;failed(&m);assert(m.s.polls==32&&m.s.transfer==5&&m.ncr==0x10&&m.ncfgr==0x140000);
    setup(&m);m.clock_mode=1;failed(&m);assert(m.ncr==0&&m.ncfgr==0);
    for(unsigned i=2;i<=37;i++)for(unsigned mode=2;mode<=3;mode++){
        setup(&m);m.clock_mode=mode;m.clock_target=i;failed(&m);cases++;
    }
    setup(&m);m.time=UINT64_MAX-10;failed(&m);assert(!m.reads&&!m.writes);
    const unsigned checks[]={4,5,6,23,24,25,26};
    for(unsigned i=0;i<sizeof checks/sizeof checks[0];i++){setup(&m);m.corrupt_read=checks[i];failed(&m);cases++;}
    for(unsigned i=0;i<5;i++){setup(&m);m.reply[i]=0xffff;if(i<2)m.reply[0]=m.reply[1]=0xffff;failed(&m);assert(m.ncr==0&&m.ncfgr==0);cases++;}
    setup(&m);m.binding.phy_address=2;failed(&m);assert(!m.events);
    setup(&m);m.cap.words[1][7]=1;failed(&m);assert(!m.events);
    setup(&m);m.gem.before[0]=0;failed(&m);assert(!m.events);
    setup(&m);assert(rpi5_gem_mdio_run(&m.s,&m.cap,&m.binding,&m.io,(void *)&m.s)<0&&!m.events&&!m.owners);
    struct rpi5_pcie_fdt b=m.binding;assert(rpi5_gem_mdio_binding_equal(&b,&m.binding));b.outbound[1].size++;assert(!rpi5_gem_mdio_binding_equal(&b,&m.binding));
    printf("GEM_MDIO_CORE_PASS EVENTS=%u OWNER_CHECKS=%u FAULT_CASES=%u MAX_EVENTS=112 NO_PHY_WRITES=1 NO_HARDWARE=1\n",events,owners,cases);
    return 0;
}
