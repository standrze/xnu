/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_phy_reset_cycle.h"
/* Exact pinned pinctrl-rp1.c BANK1 GPIO32: index4, GPIO_CTRL0x24,
 * RIO_OUT0/RIO_OE4/RIO_IN8, PAD0x14, PCIe_INTE0x11c.
 * GPIO_CTRL unknown/IRQ/reset/input-override bits are never echoed.
 * Only ordinary PAD low8 R/W fields and GPIO FSEL/OUTOVER/OEOVER survive.
 * RIO SET/CLR aliases write only bit4, never other bank outputs/enables.
 * Linux macb's active-low reset is asserted5ms then deasserted before MDIO.
 * This core requires fresh no-ASPM admission: no Slot-Control dummy writes. */
#define BIT32 0x10u
#define CTRL_MASK 0x0000f01fu
static int same(const void *a,const void *b,size_t n)
{const unsigned char *x=a,*y=b;for(size_t i=0;i<n;i++)if(x[i]!=y[i])return 0;return 1;}
static void copy(void *a,const void *b,size_t n)
{unsigned char *x=a;const unsigned char *y=b;for(size_t i=0;i<n;i++)x[i]=y[i];}
static int apart(const void *a,size_t na,const void *b,size_t nb)
{uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return a&&b&&na<=UINTPTR_MAX-x&&nb<=UINTPTR_MAX-y&&(x+na<=y||y+nb<=x);}
struct run {struct rpi5_phy_reset_session *s;const struct rpi5_phy_reset_io *original;
 const struct rpi5_phy_gpio_binding *binding;struct rpi5_phy_gpio_binding saved_binding;struct rpi5_phy_reset_io io;};
static int fail(struct run *r,int rc)
{r->s->state=RPI5_PHY_RESET_QUARANTINED;r->s->busy=0;r->s->pending=0;r->s->error=rc;return rc;}
static int retained(const struct rpi5_phy_reset_session *s)
{return s&&s->self==s&&s->state==RPI5_PHY_RESET_ACTIVE&&s->busy==1&&s->io.current&&s->io.now&&
 s->io.read&&s->io.write&&s->io.wait&&s->io.manage;}
static int current(struct run *r)
{
 if(!retained(r->s)||!same(&r->s->io,&r->io,sizeof r->io)||!same(r->original,&r->io,sizeof r->io)||
   !same(r->binding,&r->saved_binding,sizeof r->saved_binding))return fail(r,-3);
 struct rpi5_phy_reset_session before;copy(&before,r->s,sizeof before);
 int rc=r->io.current(r->io.context,r->s);
 if(rc||!same(&before,r->s,sizeof before)||!retained(r->s)||!same(r->original,&r->io,sizeof r->io)||
   !same(r->binding,&r->saved_binding,sizeof r->saved_binding))return fail(r,-3);
 return 0;
}
int rpi5_phy_reset_read_allowed(const struct rpi5_phy_reset_session *s,unsigned bank,uint32_t off)
{return retained(s)&&s->pending==1&&s->bank==bank&&s->offset==off&&s->reads<=32&&
 ((bank==0&&(off==0x24||off==0x11c))||(bank==1&&(off==0||off==4||off==8))||(bank==2&&off==0x14));}
int rpi5_phy_reset_write_allowed(const struct rpi5_phy_reset_session *s,unsigned bank,uint32_t off,uint32_t value)
{
 if(!retained(s)||s->pending!=2||s->bank!=bank||s->offset!=off||s->value!=value||s->writes>12)return 0;
 const struct rpi5_phy_reset_observation *o=&s->observed;
 if(bank==1)return value==BIT32&&(off==0x2000||off==0x3000||off==0x2004||off==0x3004);
 if(bank==0&&off==0x24)return !(value&~CTRL_MASK)&&
   (value==((o->ctrl_before&~0xc000u)|0x8000u)||value==0x8005u||value==5||value==o->ctrl_before);
 if(bank==2&&off==0x14)return !(value&~0xffu)&&(value==((o->pad_before|0x40u)&~0x80u)||value==o->pad_before);
 return 0;
}
static int complete(struct run *r,const struct rpi5_phy_reset_session *before,int rc,uint64_t completed)
{
 if(!same(before,r->s,sizeof *before)||current(r))return fail(r,-3);
 if(rc)return fail(r,(rc==-5||rc==-6)?rc:-4);
 if(completed<r->s->last_us||completed>=r->s->deadline_us)return fail(r,-5);
 r->s->last_us=completed;r->s->pending=0;return 0;
}
static int read_reg(struct run *r,unsigned bank,uint32_t off,uint32_t *out)
{
 struct rpi5_phy_reset_session *s=r->s;if(s->reads>=32)return fail(r,-4);
 s->pending=1;s->bank=bank;s->offset=off;s->reads++;
 if(current(r)||!rpi5_phy_reset_read_allowed(s,bank,off))return fail(r,-3);
 struct rpi5_phy_reset_session before;copy(&before,s,sizeof before);uint32_t value=0;uint64_t done=0;
 int rc=r->io.read(r->io.context,bank,off,s->last_us,s->deadline_us,&value,&done);
 if(complete(r,&before,rc,done))return s->error;*out=value;return 0;
}
static int write_reg(struct run *r,unsigned bank,uint32_t off,uint32_t value)
{
 struct rpi5_phy_reset_session *s=r->s;if(s->writes>=12)return fail(r,-4);
 s->pending=2;s->bank=bank;s->offset=off;s->value=value;s->writes++;
 if(current(r)||!rpi5_phy_reset_write_allowed(s,bank,off,value))return fail(r,-3);
 struct rpi5_phy_reset_session before;copy(&before,s,sizeof before);uint64_t done=0;
 int rc=r->io.write(r->io.context,bank,off,value,s->last_us,s->deadline_us,&done);
 return complete(r,&before,rc,done);
}
static int update(struct run *r,unsigned bank,uint32_t off,uint32_t value,uint32_t read_offset,uint32_t wanted)
{uint32_t got;if(write_reg(r,bank,off,value)||read_reg(r,bank,read_offset,&got))return r->s->error;
 return got==wanted?0:fail(r,-6);}
int rpi5_phy_reset_run(struct rpi5_phy_reset_session *s,const struct rpi5_phy_gpio_binding *b,
 const struct rpi5_phy_reset_io *io,struct rpi5_phy_reset_observation *out)
{
 if(!s)return -1;if(s->state!=RPI5_PHY_RESET_UNUSED){if(s->state==RPI5_PHY_RESET_ACTIVE){s->state=RPI5_PHY_RESET_QUARANTINED;s->busy=0;s->pending=0;s->error=-2;}return -2;}
 if(!b||!io||!out||!io->current||!io->now||!io->read||!io->write||!io->wait||!io->manage)return -1;
 const void *objects[]={s,b,io,out};const size_t sizes[]={sizeof *s,sizeof *b,sizeof *io,sizeof *out};
 for(unsigned i=0;i<4;i++)for(unsigned j=0;j<i;j++)if(!apart(objects[i],sizes[i],objects[j],sizes[j]))return -1;
 /* Require zero field values explicitly; never depend on structure padding. */
 if(s->self||s->io.context||s->io.current||s->io.now||s->io.read||s->io.write||s->io.wait||s->io.manage||
 s->busy||s->pending||s->step||s->bank||s->offset||s->value||s->reads||s->writes||s->started_us||s->last_us||s->deadline_us||s->error)return -1;
 struct rpi5_phy_reset_observation blank={0};
 /* observed is written only below; typed initial diagnostics are overwritten,
  * not authority. Its padding need not be initialized. */
 if(!b->phandle||b->phandle==UINT32_MAX||b->pin!=32||b->active_low!=1||b->reset_ms!=5)return -1;
 for(unsigned i=0;i<3;i++)if(b->bank_offset[i]!=0xd4000u+i*0x10000u)return -1;
 struct run r={.s=s,.original=io,.binding=b};copy(&r.io,io,sizeof *io);copy(&r.saved_binding,b,sizeof *b);
 s->observed=blank;s->self=s;s->io=*io;s->state=RPI5_PHY_RESET_ACTIVE;s->busy=1;s->step=1;
 if(current(&r))return s->error;
 s->pending=3;struct rpi5_phy_reset_session before;copy(&before,s,sizeof before);uint64_t start=0;
 int rc=io->now(io->context,&start);
 if(!same(&before,s,sizeof before)||current(&r))return fail(&r,-3);
 if(rc||start>UINT64_MAX-RPI5_PHY_RESET_WINDOW_US)return fail(&r,-5);
 s->pending=0;s->started_us=s->last_us=start;s->deadline_us=start+RPI5_PHY_RESET_WINDOW_US;
 struct rpi5_phy_reset_observation *o=&s->observed;
 if(read_reg(&r,0,0x24,&o->ctrl_before)||read_reg(&r,2,0x14,&o->pad_before)||
 read_reg(&r,1,0,&o->out_before)||read_reg(&r,1,4,&o->oe_before)||read_reg(&r,0,0x11c,&o->initial_pcie_inte))return s->error;
 uint32_t fsel=o->ctrl_before&31;
 if((o->ctrl_before&~CTRL_MASK)||(fsel>8&&fsel!=31)||(o->pad_before&~0xffu)||(o->initial_pcie_inte&BIT32))return fail(&r,-6);
 s->step=2;
 /* Disable at the final override before preloading or changing direction. */
 uint32_t disabled=(o->ctrl_before&~0xc000u)|0x8000u;
 if(update(&r,0,0x24,disabled,0x24,disabled)||
 update(&r,1,0x2000,BIT32,0,o->out_before|BIT32)||
 update(&r,1,0x2004,BIT32,4,o->oe_before|BIT32)||
 update(&r,2,0x14,(o->pad_before|0x40u)&~0x80u,0x14,(o->pad_before|0x40u)&~0x80u)||
 update(&r,0,0x24,5,0x24,5))return s->error;
 s->step=3;
 if(update(&r,1,0x3000,BIT32,0,o->out_before&~BIT32)||read_reg(&r,1,8,&o->low_input))return s->error;
 if(o->low_input&BIT32)return fail(&r,-6);o->asserted_us=s->last_us;
 if(s->last_us>s->deadline_us-6000)return fail(&r,-5);
 s->step=4;s->pending=4;if(current(&r))return s->error;copy(&before,s,sizeof before);uint64_t done=0;
 rc=io->wait(io->context,s->last_us,s->last_us+5000,s->deadline_us,&done);
 if(complete(&r,&before,rc,done))return s->error;
 if(done<o->asserted_us+5000||done>=o->asserted_us+6000)return fail(&r,-5);
 s->step=5;
 if(update(&r,1,0x2000,BIT32,0,o->out_before|BIT32)||read_reg(&r,1,8,&o->high_input))return s->error;
 if(!(o->high_input&BIT32))return fail(&r,-6);o->deasserted_us=s->last_us;
 if(s->deadline_us-s->last_us<20000)return fail(&r,-5);
 s->step=6;s->pending=5;if(current(&r))return s->error;copy(&before,s,sizeof before);
 struct rpi5_gem_mdio_observation phy={0};done=0;
 rc=io->manage(io->context,s->last_us,s->deadline_us,&phy,&done);
 if(complete(&r,&before,rc,done))return s->error;o->phy=phy;
 s->step=7;
 if(update(&r,0,0x24,0x8005,0x24,0x8005)||
 update(&r,1,(o->out_before&BIT32)?0x2000:0x3000,BIT32,0,o->out_before)||
 update(&r,1,(o->oe_before&BIT32)?0x2004:0x3004,BIT32,4,o->oe_before)||
 update(&r,2,0x14,o->pad_before,0x14,o->pad_before)||
 update(&r,0,0x24,o->ctrl_before,0x24,o->ctrl_before))return s->error;
 /* Each update's actual readback is exact; preserve the read-back values. */
 o->ctrl_after=o->ctrl_before;o->pad_after=o->pad_before;o->out_after=o->out_before;o->oe_after=o->oe_before;
 o->reads=s->reads;o->writes=s->writes;o->completed_us=s->last_us;s->step=8;
 if(current(&r))return s->error;s->state=RPI5_PHY_RESET_COMPLETE;s->busy=0;*out=*o;return 0;
}
