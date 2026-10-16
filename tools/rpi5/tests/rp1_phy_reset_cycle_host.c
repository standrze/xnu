/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_phy_reset_cycle.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct model {
 struct rpi5_phy_reset_session s;struct rpi5_phy_gpio_binding binding;
 struct rpi5_phy_reset_io io;struct rpi5_phy_reset_observation out;
 uint32_t ctrl,pad,rio_out,rio_oe,inte;
 uint64_t now;unsigned events,owners,writes,manages,waits,fail_event,fail_owner,mutate_owner,reenter_owner;
 unsigned mutate_event,reenter_event,read_corrupt,read_count,bad_stamp,bad_mode;int manage_rc;
};
static int run(struct model *m){return rpi5_phy_reset_run(&m->s,&m->binding,&m->io,&m->out);}
static int event(struct model *m)
{
 m->events++;
 if(m->events==m->mutate_event)m->binding.pin=31;
 if(m->events==m->reenter_event)assert(run(m));
 return m->events==m->fail_event?-1:0;
}
static int current(void *v,const struct rpi5_phy_reset_session *s)
{
 struct model *m=v;assert(s==&m->s);m->owners++;
 if(m->owners==m->mutate_owner)m->s.step++;
 if(m->owners==m->reenter_owner)assert(run(m));
 return m->owners==m->fail_owner?-1:0;
}
static int now(void *v,uint64_t *out)
{struct model *m=v;assert(m->s.pending==3);*out=++m->now;return event(m);}
static int finish(struct model *m,uint64_t previous,uint64_t deadline,uint64_t *done)
{
 assert(previous==m->s.last_us&&deadline==m->s.deadline_us);m->now++;
 *done=m->now;
 if(m->events+1==m->bad_stamp)*done=m->bad_mode==1?previous-1:deadline;
 return event(m);
}
static int read_reg(void *v,unsigned bank,uint32_t offset,uint64_t previous,uint64_t deadline,uint32_t *out,uint64_t *done)
{
 struct model *m=v;assert(rpi5_phy_reset_read_allowed(&m->s,bank,offset));m->read_count++;
 if(bank==0)*out=offset==0x24?m->ctrl:m->inte;
 else if(bank==2)*out=m->pad;
 else if(offset==0)*out=m->rio_out;
 else if(offset==4)*out=m->rio_oe;
 else {*out=(m->rio_out&m->rio_oe)&0x10;assert(m->ctrl==5&&!(m->pad&0x80)&&(m->pad&0x40));}
 if(m->read_count==m->read_corrupt)*out^=0x10;
 return finish(m,previous,deadline,done);
}
static int write_reg(void *v,unsigned bank,uint32_t offset,uint32_t value,uint64_t previous,uint64_t deadline,uint64_t *done)
{
 struct model *m=v;assert(rpi5_phy_reset_write_allowed(&m->s,bank,offset,value));m->writes++;
 if(bank==0)m->ctrl=value;else if(bank==2)m->pad=value;
 else {assert(value==0x10);uint32_t *p=(offset&4)?&m->rio_oe:&m->rio_out;
 if((offset&0x3000)==0x2000)*p|=value;else *p&=~value;}
 return finish(m,previous,deadline,done);
}
static int wait_until(void *v,uint64_t previous,uint64_t target,uint64_t deadline,uint64_t *done)
{
 struct model *m=v;assert(m->s.pending==4&&target==previous+5000&&deadline==m->s.deadline_us);
 assert(m->ctrl==5&&!(m->rio_out&0x10)&&(m->rio_oe&0x10));m->now=target;m->waits++;
 return finish(m,previous,deadline,done);
}
static int manage(void *v,uint64_t previous,uint64_t deadline,struct rpi5_gem_mdio_observation *out,uint64_t *done)
{
 struct model *m=v;assert(m->s.pending==5&&m->ctrl==5&&(m->rio_out&0x10)&&(m->rio_oe&0x10));
 m->manages++;out->phy_id=0x600d84a2;out->transfers=5;m->now+=2000;
 int rc=finish(m,previous,deadline,done);return rc?rc:m->manage_rc;
}
static void setup(struct model *m)
{
 memset(m,0,sizeof *m);memset(&m->out,0xa5,sizeof m->out);m->now=100;
 m->binding=(struct rpi5_phy_gpio_binding){1,32,1,5,{0xd4000,0xe4000,0xf4000}};
 m->io=(struct rpi5_phy_reset_io){m,current,now,read_reg,write_reg,wait_until,manage};
 m->ctrl=31;m->pad=0x96;m->rio_out=0xa50000;m->rio_oe=0x5a0000;
}
static void failed(struct model *m)
{
 struct rpi5_phy_reset_observation before=m->out;assert(run(m)<0);
 assert(!memcmp(&before,&m->out,sizeof before)&&m->s.state==RPI5_PHY_RESET_QUARANTINED&&!m->s.pending&&!m->s.busy);
 unsigned events=m->events,owners=m->owners,writes=m->writes;
 assert(run(m)<0&&m->events==events&&m->owners==owners&&m->writes==writes);
}
int main(void)
{
 struct model m;setup(&m);assert(!run(&m));
 assert(m.s.state==RPI5_PHY_RESET_COMPLETE&&m.writes==12&&m.s.reads==19&&m.waits==1&&m.manages==1);
 assert(m.ctrl==31&&m.pad==0x96&&m.rio_out==0xa50000&&m.rio_oe==0x5a0000);
 assert(m.out.phy.phy_id==0x600d84a2&&m.out.low_input==0&&m.out.high_input==0x10);
 assert(m.out.deasserted_us-m.out.asserted_us>=5000&&m.out.completed_us<m.s.deadline_us);
 unsigned events=m.events,owners=m.owners,cases=0;
 for(unsigned i=1;i<=events;i++){
  setup(&m);m.fail_event=i;failed(&m);assert(m.events==i);cases++;
  setup(&m);m.mutate_event=i;failed(&m);assert(m.events==i);cases++;
  setup(&m);m.reenter_event=i;failed(&m);assert(m.events==i);cases++;
  if(i>1)for(unsigned mode=1;mode<=2;mode++){setup(&m);m.bad_stamp=i;m.bad_mode=mode;failed(&m);assert(m.events==i);cases++;}}
 for(unsigned i=1;i<=owners;i++){
  setup(&m);m.fail_owner=i;failed(&m);cases++;
  setup(&m);m.mutate_owner=i;failed(&m);cases++;
  setup(&m);m.reenter_owner=i;failed(&m);cases++;}
 for(unsigned i=6;i<=19;i++){setup(&m);m.read_corrupt=i;failed(&m);cases++;}
 for(unsigned bit=0;bit<32;bit++){
  if(!((1u<<bit)&0xf01f)){setup(&m);m.ctrl|=1u<<bit;failed(&m);assert(!m.writes);cases++;}
  if(bit>=8){setup(&m);m.pad|=1u<<bit;failed(&m);assert(!m.writes);cases++;}}
 setup(&m);m.inte=0x10;failed(&m);assert(!m.writes);
 setup(&m);m.manage_rc=-6;failed(&m);assert(m.s.error==-6&&m.writes==7&&m.ctrl==5&&(m.rio_out&0x10));
 setup(&m);m.now=UINT64_MAX-10;failed(&m);assert(!m.writes&&!m.read_count);
 for(unsigned out=0;out<2;out++)for(unsigned oe=0;oe<2;oe++)for(unsigned over=0;over<4;over++){
  setup(&m);m.ctrl=5|(over<<14);m.pad=0x56;m.rio_out|=out<<4;m.rio_oe|=oe<<4;
  uint32_t original=m.ctrl;assert(!run(&m)&&m.ctrl==original&&m.pad==0x56&&((m.rio_out>>4)&1)==out&&((m.rio_oe>>4)&1)==oe);cases++;}
 printf("PHY_RESET_CORE_PASS EVENTS=%u OWNERS=%u FAULTS=%u READS=19 WRITES=12 OTHER_PINS_PRESERVED=1 NO_HARDWARE=1\n",events,owners,cases);return 0;
}
