/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_phy_gpio_observe.h"
#include "fdt.h"
static const char gem[]="/axi/pcie@1000120000/rp1/ethernet@100000";
static const char gpio[]="/axi/pcie@1000120000/rp1/gpio@d0000";
static const unsigned banks[6]={0,0,1,1,1,2};
static const uint32_t offsets[6]={0x20,0x24,0,4,8,0x14};
static int same(const void *a,const void *b,size_t n)
{const unsigned char *x=a,*y=b;for(size_t i=0;i<n;i++)if(x[i]!=y[i])return 0;return 1;}
static void copy(void *a,const void *b,size_t n)
{unsigned char *x=a;const unsigned char *y=b;for(size_t i=0;i<n;i++)x[i]=y[i];}
static int apart(const void *a,size_t na,const void *b,size_t nb)
{uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return a&&b&&na<=UINTPTR_MAX-x&&nb<=UINTPTR_MAX-y&&(x+na<=y||y+nb<=x);}
static uint32_t be(const unsigned char *p)
{return (uint32_t)p[0]<<24|(uint32_t)p[1]<<16|(uint32_t)p[2]<<8|p[3];}
static int prop(const void *f,size_t n,const char *path,const char *name,const unsigned char **p,uint32_t *len)
{struct rpi5_fdt_property q;if(rpi5_fdt_property(f,n,path,name,&q))return -1;*p=(const unsigned char *)f+q.offset;*len=q.length;return 0;}
static int cell(const void *f,size_t n,const char *path,const char *name,uint32_t *v)
{const unsigned char *p;uint32_t l;if(prop(f,n,path,name,&p,&l)||l!=4)return -1;*v=be(p);return 0;}
/* Semantic comparison, never structure padding from separately decoded FDTs. */
int rpi5_phy_gpio_pcie_equal(const struct rpi5_pcie_fdt *a,const struct rpi5_pcie_fdt *b)
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
int rpi5_phy_gpio_fdt(const void *f,size_t n,struct rpi5_phy_gpio_binding *out)
{
    struct rpi5_pcie_fdt b;const unsigned char *p;uint32_t l,v,ph;
    if(!f||!out||!apart(f,n,out,sizeof *out)||rpi5_fdt_pcie_rp1(f,n,&b))return -1;
    if(cell(f,n,gpio,"phandle",&ph)||!ph||ph==UINT32_MAX||cell(f,n,gpio,"#gpio-cells",&v)||v!=2||
        prop(f,n,gpio,"gpio-controller",&p,&l)||l||
        prop(f,n,gpio,"compatible",&p,&l)||l!=sizeof "raspberrypi,rp1-gpio"||!same(p,"raspberrypi,rp1-gpio",l))return -1;
    struct rpi5_fdt_property q;int rc=rpi5_fdt_property(f,n,gpio,"status",&q);
    if(rc!=-2 && (rc|| !((q.length==5&&same((const char *)f+q.offset,"okay",5)) ||
        (q.length==3&&same((const char *)f+q.offset,"ok",3)))))return -1;
    if(prop(f,n,gpio,"reg",&p,&l)||l!=48)return -1;
    for(unsigned i=0;i<3;i++)if(be(p+i*16)!=0xc0||be(p+i*16+4)!=(0x400d0000u+i*0x10000u)||
        be(p+i*16+8)||be(p+i*16+12)!=0xc000)return -1;
    if(prop(f,n,gem,"phy-reset-gpios",&p,&l)||l!=12||be(p)!=ph||be(p+4)!=32||be(p+8)!=1||
        cell(f,n,gem,"phy-reset-duration",&v)||v!=5)return -1;
    /* Unexpected secondary reset or pinctrl plans are not silently ignored. */
    const char *deny[]={"resets","reset-gpios","pinctrl-0","pinctrl-names","phy-reset-post-delay"};
    for(unsigned i=0;i<sizeof deny/sizeof *deny;i++)if(rpi5_fdt_property(f,n,gem,deny[i],&q)!=-2)return -1;
    struct rpi5_phy_gpio_binding r={.phandle=ph,.pin=32,.active_low=1,.reset_ms=5,
        .bank_offset={0xd4000,0xe4000,0xf4000}};*out=r;return 0;
}
static int retained(const struct rpi5_phy_gpio_session *s)
{
    const struct rpi5_gem_cap_session *c=s->cap;const struct rpi5_gem_identify *g=c?c->identity:0;
    const struct rpi5_rp1_decode_cycle *d=g?g->decode:0;
    return s->self==s&&s->state==RPI5_PHY_GPIO_ACTIVE&&s->busy==1&&c&&c->self==c&&
        c->state==RPI5_GEM_CAP_COMPLETE&&!c->busy&&!c->pending&&c->reads==16&&
        same(c->words[0],c->words[1],sizeof c->words[0])&&g&&g->stage==RPI5_GEM_MID_SECOND&&
        !g->pending&&g->reads==17&&g->clocks_ready==1&&g->mid[0]==0x70109&&g->mid[1]==g->mid[0]&&
        c->words[0][0]==g->mid[0]&&rpi5_gem_clock_profile(g->before)&&d&&
        d->state==RPI5_RP1_DECODE_MAPPED&&d->mapped==3&&!d->unmapped&&!d->pending_write&&!d->pending_map&&
        s->io.current&&s->io.map&&s->io.unmap&&s->io.read&&s->io.context==g->io.context;
}
int rpi5_phy_gpio_map_allowed(const struct rpi5_phy_gpio_session *s,unsigned i,struct rpi5_range p,unsigned revoke)
{return s&&retained(s)&&i<3&&revoke<=1&&s->index==i&&s->pending==(revoke?3u:1u)&&
    same(&p,&s->page[i],sizeof p)&&(revoke?((s->mapped&(1u<<i))&&!(s->unmapped&(1u<<i))):!(s->mapped&(1u<<i)));}
int rpi5_phy_gpio_read_allowed(const struct rpi5_phy_gpio_session *s,unsigned i,uint32_t offset)
{return s&&retained(s)&&s->pending==2&&s->mapped==7&&!s->unmapped&&s->word<6&&s->pass<2&&
    s->reads==s->pass*6+s->word+1&&i==banks[s->word]&&offset==offsets[s->word];}
struct run {struct rpi5_phy_gpio_session *s;const struct rpi5_phy_gpio_io *original;
    const struct rpi5_phy_gpio_binding *binding;struct rpi5_phy_gpio_binding saved_binding;
    struct rpi5_phy_gpio_io io;const struct rpi5_gem_cap_session *cap;
    struct rpi5_gem_cap_session saved_cap;struct rpi5_gem_identify saved_gem;struct rpi5_rp1_decode_cycle saved_decode;};
static int fail(struct run *r,int rc)
{r->s->state=RPI5_PHY_GPIO_QUARANTINED;r->s->busy=0;r->s->pending=0;r->s->error=rc;return rc;}
static int intact(struct run *r)
{return r->s->cap==r->cap&&same(r->original,&r->io,sizeof r->io)&&same(&r->s->io,&r->io,sizeof r->io)&&
    same(r->binding,&r->saved_binding,sizeof r->saved_binding)&&same(r->cap,&r->saved_cap,sizeof r->saved_cap)&&
    same(r->cap->identity,&r->saved_gem,sizeof r->saved_gem)&&
    same(r->cap->identity->decode,&r->saved_decode,sizeof r->saved_decode)&&retained(r->s);}
static int guard(struct run *r)
{if(!intact(r))return fail(r,-3);struct rpi5_phy_gpio_session held;copy(&held,r->s,sizeof held);
 int rc=r->io.current(r->io.context,r->s);if(rc||!intact(r)||!same(&held,r->s,sizeof held))return fail(r,-3);return 0;}
int rpi5_phy_gpio_run(struct rpi5_phy_gpio_session *s,const struct rpi5_gem_cap_session *cap,
    const struct rpi5_phy_gpio_binding *b,const struct rpi5_phy_gpio_io *io,struct rpi5_phy_gpio_observation *out)
{
    if(!s)return -1;if(s->state!=RPI5_PHY_GPIO_UNUSED){if(s->state==RPI5_PHY_GPIO_ACTIVE){s->state=RPI5_PHY_GPIO_QUARANTINED;s->busy=0;s->pending=0;s->error=-2;}return -2;}
    if(s->self||s->cap||s->io.context||s->io.current||s->io.map||s->io.unmap||s->io.read||
        s->busy||s->pending||s->index||s->pass||s->word||s->reads||s->mapped||s->unmapped||s->error||
        !cap||!cap->identity||!cap->identity->decode||!b||!io||!out)return -1;
    for(unsigned i=0;i<3;i++)if(s->page[i].start||s->page[i].end)return -1;
    for(unsigned p=0;p<2;p++)for(unsigned w=0;w<6;w++)if(s->raw[p][w])return -1;
    const void *objects[]={s,cap,cap->identity,cap->identity->decode,b,io,out};
    const size_t sizes[]={sizeof *s,sizeof *cap,sizeof *cap->identity,sizeof *cap->identity->decode,sizeof *b,sizeof *io,sizeof *out};
    for(unsigned i=0;i<7;i++)for(unsigned j=0;j<i;j++)if(!apart(objects[i],sizes[i],objects[j],sizes[j]))return -1;
    if(!b->phandle||b->phandle==UINT32_MAX||b->pin!=32||b->active_low!=1||b->reset_ms!=5)return -1;
    struct rpi5_range bar=cap->identity->decode->geometry.bar1_cpu;
    if(bar.start>=bar.end||(bar.start&0x3fff)||bar.end-bar.start<0xf8000)return -1;
    for(unsigned i=0;i<3;i++)if(b->bank_offset[i]!=0xd4000u+i*0x10000u)return -1;
    struct run r={.s=s,.original=io,.binding=b,.cap=cap};copy(&r.io,io,sizeof *io);copy(&r.saved_binding,b,sizeof *b);
    copy(&r.saved_cap,cap,sizeof *cap);copy(&r.saved_gem,cap->identity,sizeof r.saved_gem);copy(&r.saved_decode,cap->identity->decode,sizeof r.saved_decode);
    s->self=s;s->cap=cap;copy(&s->io,io,sizeof *io);s->state=RPI5_PHY_GPIO_ACTIVE;s->busy=1;
    for(unsigned i=0;i<3;i++)s->page[i]=(struct rpi5_range){bar.start+b->bank_offset[i],bar.start+b->bank_offset[i]+0x4000};
    if(guard(&r))return s->error;
    for(unsigned i=0;i<3;i++){
        s->pending=1;s->index=i;if(guard(&r)||!rpi5_phy_gpio_map_allowed(s,i,s->page[i],0))return fail(&r,-3);
        struct rpi5_phy_gpio_session held;copy(&held,s,sizeof held);int rc=io->map(io->context,i,s->page[i]);
        if(!same(&held,s,sizeof held)||guard(&r))return fail(&r,-3);if(rc)return fail(&r,-4);
        s->pending=0;s->mapped|=1u<<i;
    }
    for(unsigned p=0;p<2;p++)for(unsigned w=0;w<6;w++){
        s->pending=2;s->pass=p;s->word=w;s->reads++;
        if(guard(&r)||!rpi5_phy_gpio_read_allowed(s,banks[w],offsets[w]))return fail(&r,-3);
        struct rpi5_phy_gpio_session held;copy(&held,s,sizeof held);uint32_t value=0;
        int rc=io->read(io->context,banks[w],offsets[w],&value);
        if(!same(&held,s,sizeof held)||guard(&r))return fail(&r,-3);if(rc)return fail(&r,-4);
        s->pending=0;s->raw[p][w]=value;
    }
    for(unsigned j=3;j;j--){unsigned i=j-1;s->pending=3;s->index=i;
        if(guard(&r)||!rpi5_phy_gpio_map_allowed(s,i,s->page[i],1))return fail(&r,-3);
        struct rpi5_phy_gpio_session held;copy(&held,s,sizeof held);int rc=io->unmap(io->context,i,s->page[i]);
        if(!same(&held,s,sizeof held)||guard(&r))return fail(&r,-3);if(rc)return fail(&r,-4);
        s->pending=0;s->unmapped|=1u<<i;
    }
    if(guard(&r))return s->error;
    struct rpi5_phy_gpio_observation result={.reads=s->reads,.mapped=s->mapped,.unmapped=s->unmapped};
    copy(result.raw,s->raw,sizeof result.raw);s->state=RPI5_PHY_GPIO_COMPLETE;s->busy=0;*out=result;return 0;
}
