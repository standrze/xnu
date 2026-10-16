/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual forwarding core; owner/assignment, root registers and GEM are doubles. */
#include "pcie_root_forward.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static struct rpi5_root_forward session;
static struct rpi5_rp1_decode_cycle decode;
static struct rpi5_rp1_assignment assignment;
static struct rpi5_pcie_config config;
static struct rpi5_pcie_fdt binding;
static uint32_t regs[0x5000/4],original[0x5000/4];
static unsigned callbacks,fail_callback,currents,fail_current,reads,corrupt_read,writes,identify_calls,identify_fail;
static int owner;
int rpi5_rp1_bars_mapping_candidate(const struct rpi5_rp1_assignment *a,const struct rpi5_pcie_fdt *b,
    struct rpi5_rp1_mapping_candidate *out)
{
    if(a!=&assignment || b!=&binding || !owner || a->state!=RPI5_RP1_ASSIGN_ASSIGNED)return -1;
    *out=(struct rpi5_rp1_mapping_candidate){a->plan.cpu[1],a->plan.gem_pages,a->plan.clock_pages};return 0;
}
static int current_decode(void *c,const struct rpi5_rp1_decode_cycle *d,const struct rpi5_rp1_assignment *a)
{return c!=&owner || d!=&decode || a!=&assignment || !owner;}
static int current(void *c,const struct rpi5_root_forward *s,const struct rpi5_rp1_decode_cycle *d)
{currents++;return currents==fail_current || c!=&owner || s!=&session || d!=&decode || !owner;}
static int read_root(void *c,uint32_t offset,unsigned width,uint32_t *out)
{
    if(c!=&owner || !rpi5_root_forward_access_allowed(&session,offset,width,0,0))return -1;
    if(++callbacks==fail_callback)return -1;
    uint32_t value=regs[offset/4];if(width==2)value&=0xffff;
    if(++reads==corrupt_read)value^=1;
    if(++callbacks==fail_callback)return -1;
    *out=value;return 0;
}
static int write_root(void *c,uint32_t offset,unsigned width,uint32_t value)
{
    if(c!=&owner || !rpi5_root_forward_access_allowed(&session,offset,width,1,value))return -1;
    assert((offset==4 && width==2 && !(value&5)) || (offset==0x20 && width==4));
    if(++callbacks==fail_callback)return -1;
    writes++;regs[offset/4]=width==2?((regs[offset/4]&0xffff0000)|value):value;
    assert((regs[1]&0xffff0000)==0xa5a50000);
    if(++callbacks==fail_callback)return -1;
    return 0;
}
static int identify(void *c,const struct rpi5_rp1_decode_cycle *d)
{
    assert(c==&owner && d==&decode && session.state==RPI5_ROOT_FORWARD_LIVE);
    assert((regs[1]&0xffff)==0x402 && regs[0x20/4]==0x00400000);identify_calls++;
    return identify_fail?-5:0;
}
static struct rpi5_root_forward_io io={&owner,current,read_root,write_root,identify};
static void reset(void)
{
    memset(&session,0,sizeof session);memset(&decode,0,sizeof decode);memset(&assignment,0,sizeof assignment);
    memset(&config,0,sizeof config);memset(&binding,0,sizeof binding);memset(regs,0,sizeof regs);
    callbacks=fail_callback=currents=fail_current=reads=corrupt_read=writes=identify_calls=identify_fail=0;owner=1;
    decode.state=RPI5_RP1_DECODE_MAPPED;decode.mapped=3;decode.assignment=&assignment;
    decode.io.context=&owner;decode.io.current=current_decode;
    assignment.state=RPI5_RP1_ASSIGN_ASSIGNED;assignment.config=&config;assignment.binding=&binding;
    assignment.plan.present=7;assignment.plan.pci_base[0]=0x410000;assignment.plan.pci_base[2]=0x400000;
    assignment.sizes_saved[0]=0x4000;assignment.sizes_saved[1]=0x400000;assignment.sizes_saved[2]=0x10000;
    assignment.plan.cpu[1]=(struct rpi5_range){0x1f00000000,0x1f00400000};
    assignment.plan.gem_pages=(struct rpi5_range){0x1f00100000,0x1f00104000};
    assignment.plan.clock_pages=(struct rpi5_range){0x1f00018000,0x1f0002c000};
    decode.geometry=(struct rpi5_rp1_mapping_candidate){assignment.plan.cpu[1],assignment.plan.gem_pages,assignment.plan.clock_pages};
    assignment.windows[0]=(struct rpi5_pcie_outbound_encoding){.cpu_base=0x1f00000000,.pci_base=0,.size=0xfffffffc,
        .pci_lo=0,.pci_hi=0,.base_limit=0xfff00000,.base_hi=0x1f,.limit_hi=0x1f};
    assignment.windows[1]=(struct rpi5_pcie_outbound_encoding){.cpu_base=0x1c00000000,.pci_base=0x400000000,.size=0x300000000,
        .pci_lo=0,.pci_hi=4,.base_limit=0xfff00000,.base_hi=0x1c,.limit_hi=0x1e};
    regs[0]=0x271214e4;regs[1]=0xa5a50400;regs[0xc/4]=0x00010000;regs[0x18/4]=0xa5010100;regs[0x20/4]=0x0000fff0;
    for(unsigned i=0;i<2;i++){
        const struct rpi5_pcie_outbound_encoding *w=&assignment.windows[i];
        regs[(0x400c+8*i)/4]=w->pci_lo;regs[(0x4010+8*i)/4]=w->pci_hi;
        regs[(0x4070+4*i)/4]=w->base_limit;regs[(0x4080+8*i)/4]=w->base_hi;regs[(0x4084+8*i)/4]=w->limit_hi;
    }
    memcpy(original,regs,sizeof regs);
}
static void rejected(void)
{
    struct rpi5_root_forward_observation out,before;memset(&out,0xa5,sizeof out);before=out;
    assert(rpi5_root_forward_run(&session,&decode,&io,&out));
    assert(session.state==RPI5_ROOT_FORWARD_QUARANTINED && !session.pending && !memcmp(&out,&before,sizeof out));
    assert(reads<=79 && writes<=4 && identify_calls<=1);
    for(unsigned i=0;i<sizeof regs/sizeof regs[0];i++)if(i!=1 && i!=0x20/4)assert(regs[i]==original[i]);
    assert((regs[1]&0xffff0000)==(original[1]&0xffff0000));
    unsigned stopped=callbacks,stopped_current=currents,stopped_identify=identify_calls;
    assert(rpi5_root_forward_run(&session,&decode,&io,&out)==-2);
    assert(callbacks==stopped && currents==stopped_current && identify_calls==stopped_identify);
    assert(!rpi5_root_forward_access_allowed(&session,4,2,1,0x402));
}
int main(void)
{
    reset();struct rpi5_root_forward_observation out;
    assert(!rpi5_root_forward_run(&session,&decode,&io,&out));
    assert(session.state==RPI5_ROOT_FORWARD_COMPLETE && reads==79 && writes==4 && identify_calls==1);
    assert(!memcmp(regs,original,sizeof regs));
    assert(out.before.command==0x400 && out.live.command==0x402 && out.after.command==0x400);
    assert(out.before.window==0xfff0 && out.live.window==0x00400000 && out.after.window==0xfff0);
    assert(out.before.buses==0xa5010100 && out.live.buses==out.before.buses && out.after.buses==out.before.buses);
    unsigned all_callbacks=callbacks,all_currents=currents,faults=0;
    for(unsigned i=1;i<=all_callbacks;i++){reset();fail_callback=i;rejected();faults++;}
    for(unsigned i=1;i<=all_currents;i++){reset();fail_current=i;rejected();faults++;}
    for(unsigned i=1;i<=79;i++){reset();corrupt_read=i;rejected();faults++;}
    reset();identify_fail=1;rejected();assert(writes==2 && (regs[1]&0xffff)==0x402);faults++;
    for(unsigned i=0;i<16;i++){
        reset();switch(i){
        case 0:owner=0;break;case 1:decode.state=RPI5_RP1_DECODE_UNMAPPING;break;
        case 2:decode.mapped=1;break;case 3:decode.pending_map=1;break;
        case 4:assignment.state=RPI5_RP1_ASSIGN_RESTORED;break;case 5:assignment.plan.present=0;break;
        case 6:assignment.sizes_saved[1]=0;break;case 7:assignment.plan.pci_base[0]=0xffffe000;break;
        case 8:assignment.windows[0].size=0x414000;break;case 9:assignment.windows[0].pci_base=0x100000;break;
        case 10:decode.geometry.clock_pages.start+=0x4000;break;case 11:regs[1]|=4;break;
        case 12:regs[1]|=1;break;case 13:regs[1]|=2;break;case 14:regs[0x20/4]|=1;break;
        case 15:regs[0x18/4]=0;break;
        }memcpy(original,regs,sizeof regs);rejected();assert(!writes);faults++;
    }
    for(unsigned i=0;i<16;i++){
        reset();switch(i){
        case 0:session.decode=&decode;break;case 1:session.io.context=&owner;break;case 2:session.io.current=current;break;
        case 3:session.io.read=read_root;break;case 4:session.io.write=write_root;break;case 5:session.io.identify=identify;break;
        case 6:session.wanted_window=1;break;case 7:session.reads=1;break;case 8:session.writes=1;break;
        case 9:session.pending=1;break;case 10:session.offset=1;break;case 11:session.width=1;break;
        case 12:session.write=1;break;case 13:session.before.command=1;break;case 14:session.outbound[8]=1;break;
        case 15:session.after.header=1;break;
        }rejected();assert(!callbacks && !currents);faults++;
    }
    printf("ROOT_FORWARD_CORE_PASS READS=79 WRITES=4 FAULTS=%u STATUS_PRESERVED=1 NO_HARDWARE=1\n",faults);
}
