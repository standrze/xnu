/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual core/service bodies, explicit MMIO/counter/SMCCC/lock doubles. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "pcie_verifier.c"
#include "pcie_verifier_sip.c"
static struct {uint64_t now,freq,step,armed;unsigned reads,bad_at;uint32_t bad_value;
    uint32_t typer,groups[3],enable[3],active[3],reset,rescal,status,route;int stalled,reenter;} fake;
uint64_t rpi5_fw_counter(void){fake.now+=fake.step;return fake.now;}
uint64_t rpi5_fw_frequency(void){return fake.freq;}
int rpi5_fw_trylock(volatile uint32_t *p){if(*p)return 0;*p=1;return 1;}
void rpi5_fw_unlock(volatile uint32_t *p){assert(*p==1);*p=0;}
uint32_t rpi5_fw_load32(uint64_t address)
{
    fake.reads++;
    if(fake.reenter){struct rpi5_fw_observation out;assert(rpi5_fw_verifier_call(RPI5_FW_PCIE_CLAIM,7,&out)==RPI5_FW_STATE);}
    uint32_t result;
    if(address==GIC+4)result=fake.typer;
    else if(address==RESET)result=fake.reset;
    else if(address==RESCAL)result=fake.rescal;
    else if(address==RESCAL+8)result=fake.status;
    else if(address==PM+0x1c)result=fake.route;
    else if(address==PM+0x24)result=(15u<<16)-(fake.stalled?0:(uint32_t)((fake.now-fake.armed)*65536/fake.freq));
    else{
        static const unsigned banks[]={5,6,8};unsigned found=0;result=0;
        for(unsigned i=0;i<3;i++){
            if(address==GIC+0x80+4*banks[i]){result=fake.groups[i];found++;}
            if(address==GIC+0x100+4*banks[i]){result=fake.enable[i];found++;}
            if(address==GIC+0x300+4*banks[i]){result=fake.active[i];found++;}
        }
        assert(found==1); /* Fixed private allowlist, no arbitrary raw address. */
    }
    return fake.reads==fake.bad_at?fake.bad_value:result;
}
static void reset(void)
{
    memset(&fake,0,sizeof(fake));memset(&verifier,0,sizeof(verifier));verifier_lock=0;
    fake.now=fake.armed=1000000;fake.freq=1000000;fake.step=1000;fake.route=0x222;fake.typer=0xfc69;
    for(unsigned i=0;i<3;i++)fake.groups[i]=UINT32_MAX;
}
static int call(uint32_t fid,uint64_t token){struct rpi5_fw_observation out;return rpi5_fw_verifier_call(fid,token,&out);}
static void failed_claim(void)
{
    struct rpi5_fw_observation out,saved;memset(&out,0xa5,sizeof(out));saved=out;
    assert(rpi5_fw_verifier_call(RPI5_FW_PCIE_CLAIM,7,&out)<0 && !memcmp(&out,&saved,sizeof(out)));
    assert(verifier.state==QUARANTINED);unsigned reads=fake.reads;
    assert(call(RPI5_FW_PCIE_CLAIM,7)==RPI5_FW_STATE && call(RPI5_FW_PCIE_CHECK,7)==RPI5_FW_STATE);
    assert(reads==fake.reads);
}
int main(void)
{
    reset();struct rpi5_fw_observation out;
    assert(!rpi5_fw_verifier_call(RPI5_FW_PCIE_QUERY,0,&out) && out.facts==3 && fake.reads==10);
    fake.reenter=1;assert(!rpi5_fw_verifier_call(RPI5_FW_PCIE_CLAIM,7,&out));
    assert(out.facts==31 && out.sequence==1 && fake.reads==25);fake.reenter=0;
    assert(!rpi5_fw_verifier_call(RPI5_FW_PCIE_CHECK,7,&out) && out.sequence==2);
    unsigned reads=fake.reads;assert(call(RPI5_FW_PCIE_CHECK,8)==RPI5_FW_STATE && fake.reads==reads);
    assert(call(RPI5_FW_PCIE_QUERY,0)==RPI5_FW_STATE);
    for(unsigned at=1;at<=15;at++){
        reset();fake.bad_at=at;fake.bad_value=(at==2||at==5||at==8)?0:UINT32_MAX;failed_claim();
        reset();assert(!call(RPI5_FW_PCIE_CLAIM,7));fake.bad_at=fake.reads+at;
        fake.bad_value=(at==2||at==5||at==8)?0:UINT32_MAX;
        struct rpi5_fw_observation saved;memset(&out,0xa5,sizeof(out));saved=out;
        assert(rpi5_fw_verifier_call(RPI5_FW_PCIE_CHECK,7,&out)<0 && !memcmp(&out,&saved,sizeof(out)) && verifier.state==QUARANTINED);
    }
    reset();fake.typer=0x407;failed_claim();reset();fake.typer=9;failed_claim();
    reset();fake.reset=1u<<11;failed_claim();reset();fake.rescal=1;failed_claim();
    reset();fake.enable[0]=1;assert(!call(RPI5_FW_PCIE_QUERY,0));failed_claim();
    reset();fake.active[2]=1u<<5;failed_claim();
    reset();fake.enable[2]=fake.active[2]=1;assert(!call(RPI5_FW_PCIE_CLAIM,7)); /* NVMe bit excluded. */
    fake.rescal=1;fake.reset=1u<<12;assert(!call(RPI5_FW_PCIE_CHECK,7)); /* Own reset/calibration in flight. */
    reset();fake.freq=999999;failed_claim();reset();fake.freq=1000000001;failed_claim();
    reset();fake.now=UINT64_MAX-100;fake.step=0;failed_claim();
    reset();assert(!call(RPI5_FW_PCIE_CLAIM,7));fake.now=0;assert(call(RPI5_FW_PCIE_CHECK,7)==RPI5_FW_CLOCK);
    reset();assert(!call(RPI5_FW_PCIE_CLAIM,7));fake.now=verifier.deadline;assert(call(RPI5_FW_PCIE_CHECK,7)==RPI5_FW_CLOCK);
    reset();fake.stalled=1;assert(!call(RPI5_FW_PCIE_CLAIM,7));assert(call(RPI5_FW_PCIE_CHECK,7)==RPI5_FW_CLOCK);
    reset();fake.step=0;fake.stalled=1;assert(!call(RPI5_FW_PCIE_CLAIM,7));
    for(unsigned i=1;i<65536;i++)assert(!call(RPI5_FW_PCIE_CHECK,7));
    assert(call(RPI5_FW_PCIE_CHECK,7)==RPI5_FW_CLOCK);
    reset();struct host_context ctx;
    assert(registered_handler==(const void *)rpi5_pcie_sip);
    assert(!rpi5_pcie_sip(RPI5_FW_PCIE_QUERY,0,0,0,0,NULL,&ctx,0) && ctx.regs[0]==SMC_UNK && !fake.reads);
    assert(!rpi5_pcie_sip(RPI5_FW_PCIE_QUERY,0,1,0,0,NULL,&ctx,1) && ctx.regs[0]==SMC_UNK && !fake.reads);
    assert(!rpi5_pcie_sip(0xc2007f13,0,0,0,0,NULL,&ctx,1) && ctx.regs[0]==SMC_UNK && !fake.reads);
    verifier_lock=1;assert(!rpi5_pcie_sip(RPI5_FW_PCIE_QUERY,0,0,0,0,NULL,&ctx,1) && (int64_t)ctx.regs[0]==RPI5_FW_STATE && !fake.reads);
    verifier_lock=0;assert(!rpi5_pcie_sip(RPI5_FW_PCIE_QUERY,0,0,0,0,NULL,&ctx,1) && ctx.count==4 && ctx.regs[0]==0 && ctx.regs[1]==1 && ctx.regs[3]==3);
    assert(!rpi5_pcie_sip(RPI5_FW_PCIE_CLAIM,7,0,0,0,NULL,&ctx,1) && ctx.regs[3]==31 && !verifier_lock);
    puts("FW_VERIFIER_HOST_PASS fixed reads, real protocol/service, 30 MMIO failures, counter/owner/ABI/lock cases");return 0;
}
