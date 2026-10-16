/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_gem_mdio.h"
/* Original implementation from pinned raspberrypi/linux80d4218 macb.h,
 * macb_mdio_read_c22/gem_mdc_clk_div, mdio.yaml and genphy_update_link.
 * No Linux code imported. NCFGR is ordinary configuration R/W (the driver
 * also preserves it via read/modify/write); NCR command bits are excluded. */
#define NCR 0u
#define NCFGR 4u
#define NSR 8u
#define MAN 0x34u
#define MPE 0x10u
#define CLK_MASK 0x001c0000u
#define CLK_DIV96 0x00140000u
/* Pinned macb.h names these non-command R/W configuration bits: TXLPIEN19,
 * PTPUNI20, OSSMODE24, MIIONRGMII28. Every other set bit, including unknown
 * bits, RE/TE, MPE, loopback, statistics/transmit commands and HS_MAC, refuses
 * admission. Never echo an unknown potentially strobed/W1C NCR bit. */
#define NCR_SAFE_RW 0x11180000u
static const uint32_t phy_registers[5]={2,3,0,1,1};
static int same(const void *a,const void *b,size_t n)
{const unsigned char *x=a,*y=b;for(size_t i=0;i<n;i++)if(x[i]!=y[i])return 0;return 1;}
static void copy(void *a,const void *b,size_t n)
{unsigned char *x=a;const unsigned char *y=b;for(size_t i=0;i<n;i++)x[i]=y[i];}
static int apart(const void *a,size_t na,const void *b,size_t nb)
{uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return a&&b&&na<=UINTPTR_MAX-x&&nb<=UINTPTR_MAX-y&&(x+na<=y||y+nb<=x);}
int rpi5_gem_mdio_binding_equal(const struct rpi5_pcie_fdt *a,const struct rpi5_pcie_fdt *b)
{
    if(!a||!b)return 0;
#define RANGE(f) if(a->f.start!=b->f.start||a->f.end!=b->f.end)return 0
#define FIELD(f) if(a->f!=b->f)return 0
    RANGE(bridge_regs);RANGE(mip_regs);RANGE(mip_target);RANGE(rescal_regs);RANGE(bridge_reset_regs);
    FIELD(outbound_count);FIELD(dma_count);FIELD(rp1_dma_count);
    for(unsigned i=0;i<2;i++){FIELD(outbound[i].space);FIELD(outbound[i].pci_base);FIELD(outbound[i].cpu_base);FIELD(outbound[i].size);FIELD(bridge_intid[i]);}
    for(unsigned i=0;i<3;i++){FIELD(dma[i].space);FIELD(dma[i].pci_base);FIELD(dma[i].cpu_base);FIELD(dma[i].size);
        FIELD(rp1_dma[i].space);FIELD(rp1_dma[i].rp1_base);FIELD(rp1_dma[i].pci_base);FIELD(rp1_dma[i].size);}
    for(unsigned i=0;i<4;i++){FIELD(intx_intid[i]);FIELD(gem_clock_id[i]);}
    FIELD(gic_phandle);FIELD(mip_phandle);FIELD(rp1_phandle);FIELD(clock_phandle);FIELD(phy_phandle);FIELD(phy_address);
    FIELD(mip_intid_base);FIELD(mip_intid_count);FIELD(bridge_reset_id);FIELD(rp1_irq);FIELD(rp1_irq_flags);
    FIELD(rp1_local_base);FIELD(rp1_pci_base);FIELD(rp1_aperture_size);FIELD(clock_bar_offset);FIELD(clock_size);FIELD(gem_bar_offset);FIELD(gem_size);
#undef RANGE
#undef FIELD
    return 1;
}
static int retained(const struct rpi5_gem_mdio_session *s)
{
    const struct rpi5_gem_cap_session *c=s->capabilities;
    const struct rpi5_gem_identify *g=c?c->identity:0;
    const struct rpi5_rp1_decode_cycle *d=g?g->decode:0;
    const struct rpi5_pcie_fdt *b=s->binding;
    return s->self==s&&s->state==RPI5_GEM_MDIO_ACTIVE&&s->busy==1&&
        c&&c->self==c&&c->state==RPI5_GEM_CAP_COMPLETE&&!c->busy&&!c->pending&&c->reads==16&&
        same(c->words[0],c->words[1],sizeof c->words[0])&&
        g&&g->stage==RPI5_GEM_MID_SECOND&&!g->pending&&g->reads==17&&g->clocks_ready==1&&
        g->mid[0]==0x00070109&&g->mid[1]==g->mid[0]&&c->words[0][0]==g->mid[0]&&
        rpi5_gem_clock_profile(g->before)&&d&&d->state==RPI5_RP1_DECODE_MAPPED&&
        d->mapped==3&&!d->unmapped&&!d->pending_write&&!d->pending_map&&
        b&&b->phy_address==1&&b->phy_phandle&&b->gem_bar_offset==0x100000&&b->gem_size==0x4000&&
        b->gem_clock_id[0]==12&&b->gem_clock_id[1]==12&&b->gem_clock_id[2]==29&&b->gem_clock_id[3]==16&&
        s->io.current&&s->io.read&&s->io.write&&s->io.now_us&&s->io.context==g->io.context&&
        s->io.context==d->io.context&&s->io.context==c->io.context;
}
int rpi5_gem_mdio_read_allowed(const struct rpi5_gem_mdio_session *s,uint32_t offset)
{return s&&retained(s)&&s->pending==1&&s->offset==offset&&s->reads<=46&&
    (offset==NCR||offset==NCFGR||offset==NSR||offset==MAN);}
int rpi5_gem_mdio_write_allowed(const struct rpi5_gem_mdio_session *s,uint32_t offset,uint32_t value)
{
    if(!s||!retained(s)||s->pending!=2||s->offset!=offset||s->value!=value||s->writes>9)return 0;
    if(offset==MAN)return s->stage==RPI5_GEM_MDIO_READ_PHY&&s->transfer<5&&
        value==(0x60020000u|(s->phy_address<<23)|(phy_registers[s->transfer]<<18));
    if(offset==NCR)return (s->stage==RPI5_GEM_MDIO_ENABLE&&value==(s->ncr_before|MPE))||
        (s->stage==RPI5_GEM_MDIO_DISABLE&&value==s->ncr_before);
    if(offset==NCFGR)return s->changed_divider&&
        ((s->stage==RPI5_GEM_MDIO_DIVIDER&&value==s->ncfgr_live)||
         (s->stage==RPI5_GEM_MDIO_RESTORE_DIVIDER&&value==s->ncfgr_before));
    return 0;
}
int rpi5_gem_mdio_clock_allowed(const struct rpi5_gem_mdio_session *s)
{return s&&retained(s)&&s->pending==3&&s->clocks<=57;}
struct run {
    struct rpi5_gem_mdio_session *s;
    const struct rpi5_gem_mdio_io *original;
    struct rpi5_gem_mdio_io io;
    const struct rpi5_gem_cap_session *cap;
    const struct rpi5_gem_identify *gem;
    const struct rpi5_rp1_decode_cycle *dec;
    const struct rpi5_pcie_fdt *binding;
    struct rpi5_gem_cap_session saved_cap;
    struct rpi5_gem_identify saved_gem;
    struct rpi5_rp1_decode_cycle saved_dec;
    struct rpi5_pcie_fdt saved_binding;
};
static int fail(struct run *r,int rc)
{r->s->state=RPI5_GEM_MDIO_QUARANTINED;r->s->busy=0;r->s->pending=0;r->s->error=rc;return rc;}
static int intact(struct run *r)
{return r->s->capabilities==r->cap&&r->s->binding==r->binding&&r->cap->identity==r->gem&&
    r->gem->decode==r->dec&&same(r->original,&r->io,sizeof r->io)&&same(&r->s->io,&r->io,sizeof r->io)&&
    same(r->cap,&r->saved_cap,sizeof r->saved_cap)&&same(r->gem,&r->saved_gem,sizeof r->saved_gem)&&
    same(r->dec,&r->saved_dec,sizeof r->saved_dec)&&same(r->binding,&r->saved_binding,sizeof r->saved_binding)&&retained(r->s);}
static int guard(struct run *r)
{
    if(!intact(r))return fail(r,-3);
    struct rpi5_gem_mdio_session held;copy(&held,r->s,sizeof held);
    int rc=r->io.current(r->io.context,r->s,r->cap,r->binding);
    if(rc||!intact(r)||!same(&held,r->s,sizeof held))return fail(r,-3);
    return 0;
}
static int now(struct run *r,uint64_t *out)
{
    struct rpi5_gem_mdio_session *s=r->s;if(s->clocks>=57)return fail(r,-4);
    s->pending=3;s->clocks++;if(guard(r)||!rpi5_gem_mdio_clock_allowed(s))return fail(r,-3);
    struct rpi5_gem_mdio_session held;copy(&held,s,sizeof held);uint64_t value=0;
    int rc=r->io.now_us(r->io.context,&value);
    if(!same(s,&held,sizeof held)||guard(r))return fail(r,-3);
    if(rc)return fail(r,-4);s->pending=0;*out=value;return 0;
}
static int tick(struct run *r)
{
    uint64_t value;if(now(r,&value))return r->s->error;
    if(value<r->s->last_us||value>=r->s->deadline_us)return fail(r,-5);
    r->s->last_us=value;return 0;
}
static int read_reg(struct run *r,uint32_t offset,uint32_t *out)
{
    struct rpi5_gem_mdio_session *s=r->s;
    if(tick(r))return s->error;if(s->reads>=46)return fail(r,-4);
    s->pending=1;s->offset=offset;s->reads++;
    if(guard(r)||!rpi5_gem_mdio_read_allowed(s,offset))return fail(r,-3);
    struct rpi5_gem_mdio_session held;copy(&held,s,sizeof held);uint32_t value=0;
    int rc=r->io.read(r->io.context,offset,&value);
    if(!same(s,&held,sizeof held)||guard(r))return fail(r,-3);
    if(rc)return fail(r,-4);s->pending=0;*out=value;return 0;
}
static int write_reg(struct run *r,uint32_t offset,uint32_t value)
{
    struct rpi5_gem_mdio_session *s=r->s;
    if(tick(r))return s->error;if(s->writes>=9)return fail(r,-4);
    s->pending=2;s->offset=offset;s->value=value;s->writes++;
    if(guard(r)||!rpi5_gem_mdio_write_allowed(s,offset,value))return fail(r,-3);
    struct rpi5_gem_mdio_session held;copy(&held,s,sizeof held);
    int rc=r->io.write(r->io.context,offset,value);
    if(!same(s,&held,sizeof held)||guard(r))return fail(r,-3);
    if(rc)return fail(r,-4);s->pending=0;return 0;
}
static int idle(struct run *r)
{
    struct rpi5_gem_mdio_session *s=r->s;
    for(;;){
        if(s->polls>=32)return fail(r,-5);s->polls++;
        if(read_reg(r,NSR,&s->last_nsr))return s->error;
        if(s->last_nsr==UINT32_MAX)return fail(r,-6);
        if(s->last_nsr&4)return 0;
    }
}
int rpi5_gem_mdio_run(struct rpi5_gem_mdio_session *s,const struct rpi5_gem_cap_session *cap,
    const struct rpi5_pcie_fdt *binding,const struct rpi5_gem_mdio_io *io,struct rpi5_gem_mdio_observation *out)
{
    if(!s)return -1;
    if(s->state!=RPI5_GEM_MDIO_UNUSED){
        if(s->state==RPI5_GEM_MDIO_ACTIVE){s->state=RPI5_GEM_MDIO_QUARANTINED;s->busy=0;s->pending=0;s->error=-2;}return -2;
    }
    if(s->self||s->capabilities||s->binding||s->io.context||s->io.current||s->io.read||s->io.write||s->io.now_us||
        s->busy||s->stage||s->pending||s->offset||s->value||s->reads||s->writes||s->clocks||s->polls||s->transfer||
        s->ncr_before||s->ncr_live||s->ncr_after||s->ncfgr_before||s->ncfgr_live||s->ncfgr_after||
        s->changed_divider||s->phy_address||s->command||s->last_nsr||s->last_man||s->start_us||s->last_us||s->deadline_us||s->error||
        !cap||!cap->identity||!cap->identity->decode||!binding||!io||!out||
        !io->current||!io->read||!io->write||!io->now_us)return -1;
    for(unsigned i=0;i<5;i++)if(s->raw[i])return -1;
    const void *objects[]={s,cap,cap->identity,cap->identity->decode,binding,io,out};
    const size_t sizes[]={sizeof *s,sizeof *cap,sizeof *cap->identity,sizeof *cap->identity->decode,sizeof *binding,sizeof *io,sizeof *out};
    for(unsigned i=0;i<7;i++)for(unsigned j=0;j<i;j++)if(!apart(objects[i],sizes[i],objects[j],sizes[j]))return -1;
    struct run r={.s=s,.original=io,.cap=cap,.gem=cap->identity,.dec=cap->identity->decode,.binding=binding};
    copy(&r.io,io,sizeof *io);copy(&r.saved_cap,cap,sizeof *cap);copy(&r.saved_gem,r.gem,sizeof *r.gem);
    copy(&r.saved_dec,r.dec,sizeof *r.dec);copy(&r.saved_binding,binding,sizeof *binding);
    s->self=s;s->capabilities=cap;s->binding=binding;copy(&s->io,io,sizeof *io);
    s->state=RPI5_GEM_MDIO_ACTIVE;s->busy=1;s->stage=RPI5_GEM_MDIO_PREFLIGHT;s->phy_address=binding->phy_address;
    if(guard(&r))return s->error;
    uint64_t start;if(now(&r,&start))return s->error;
    if(start>UINT64_MAX-RPI5_GEM_MDIO_US)return fail(&r,-5);
    s->start_us=s->last_us=start;s->deadline_us=start+RPI5_GEM_MDIO_US;
    if(read_reg(&r,NCR,&s->ncr_before)||read_reg(&r,NCFGR,&s->ncfgr_before))return s->error;
    if(s->ncfgr_before==UINT32_MAX||(s->ncr_before&~NCR_SAFE_RW))return fail(&r,-6);
    if(idle(&r))return s->error;
    s->ncr_live=s->ncr_before|MPE;
    s->ncfgr_live=(s->ncfgr_before&CLK_MASK)<CLK_DIV96?(s->ncfgr_before&~CLK_MASK)|CLK_DIV96:s->ncfgr_before;
    s->changed_divider=s->ncfgr_live!=s->ncfgr_before;
    uint32_t value;
    s->stage=RPI5_GEM_MDIO_DIVIDER;
    if(s->changed_divider&&(write_reg(&r,NCFGR,s->ncfgr_live)||read_reg(&r,NCFGR,&value)))return s->error;
    if(s->changed_divider&&value!=s->ncfgr_live)return fail(&r,-6);
    s->stage=RPI5_GEM_MDIO_ENABLE;
    if(read_reg(&r,NCR,&value))return s->error;if(value!=s->ncr_before)return fail(&r,-6);
    if(write_reg(&r,NCR,s->ncr_live)||read_reg(&r,NCR,&value))return s->error;
    if(value!=s->ncr_live)return fail(&r,-6);
    s->stage=RPI5_GEM_MDIO_READ_PHY;
    for(unsigned i=0;i<5;i++){
        s->transfer=i;s->command=0x60020000u|(s->phy_address<<23)|(phy_registers[i]<<18);
        if(idle(&r)||write_reg(&r,MAN,s->command)||idle(&r)||read_reg(&r,MAN,&s->last_man))return s->error;
        s->raw[i]=s->last_man&0xffff;
    }
    s->transfer=5;
    s->stage=RPI5_GEM_MDIO_DISABLE;
    if(idle(&r)||read_reg(&r,NCR,&value))return s->error;if(value!=s->ncr_live)return fail(&r,-6);
    if(write_reg(&r,NCR,s->ncr_before)||read_reg(&r,NCR,&s->ncr_after))return s->error;
    if(s->ncr_after!=s->ncr_before)return fail(&r,-6);
    s->stage=RPI5_GEM_MDIO_RESTORE_DIVIDER;
    if(read_reg(&r,NCFGR,&value))return s->error;if(value!=s->ncfgr_live)return fail(&r,-6);
    if(s->changed_divider&&write_reg(&r,NCFGR,s->ncfgr_before))return s->error;
    if(read_reg(&r,NCFGR,&s->ncfgr_after))return s->error;
    if(s->ncfgr_after!=s->ncfgr_before)return fail(&r,-6);
    s->stage=RPI5_GEM_MDIO_FINISH;
    if(tick(&r)||guard(&r))return s->error;
    uint32_t id=(s->raw[0]<<16)|s->raw[1];
    if(!id||id==UINT32_MAX||s->raw[2]==0xffff||s->raw[3]==0xffff||s->raw[4]==0xffff||s->last_us<=s->start_us)return fail(&r,-6);
    struct rpi5_gem_mdio_observation result={s->phy_address,id,s->raw[2],s->raw[3],s->raw[4],
        (s->raw[4]>>2)&1,(s->raw[4]>>5)&1,s->ncr_before,s->ncr_live,s->ncr_after,
        s->ncfgr_before,s->ncfgr_live,s->ncfgr_after,s->reads,s->writes,s->polls,s->clocks,s->transfer,s->changed_divider,s->last_us-s->start_us};
    s->state=RPI5_GEM_MDIO_COMPLETE;s->busy=0;*out=result;return 0;
}
