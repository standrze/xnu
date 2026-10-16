/* SPDX-License-Identifier: BSD-2-Clause */
/* Real window programmer and released checker, explicit MMIO/lifecycle model. */
#define main original_windows_tests
#include "pcie_windows_host.c"
#undef main
#include "pcie_released_windows.h"
struct released_model {
    struct model prior;
    struct rpi5_pcie_windows windows;
    struct rpi5_pcie_released_windows checker;
    uint32_t regs[0x9310/4];
    unsigned calls, reads, fail_at, dependency_at, bad_read;
    unsigned mutate_read;uint32_t mutation;
    unsigned read_offsets[90];
};
static int released_step(struct released_model *m)
{
    assert(m->checker.state==RPI5_PCIE_RELEASED_BUSY);m->calls++;
    struct rpi5_pcie_released_observation out;
    assert(rpi5_pcie_released_windows_check(&m->checker,&out)==-2);
    if(m->calls==m->dependency_at)m->windows.state=RPI5_PCIE_WINDOWS_QUARANTINED;
    return m->calls==m->fail_at;
}
static int released_owner(void *p){return released_step(p)?-1:0;}
static int released_order(void *p){return released_step(p)?-1:0;}
static int released_read(void *p,uint32_t offset,uint32_t *out)
{
    struct released_model *m=p;
    assert(!(offset&3)&&offset<sizeof m->regs);
    if(released_step(m))return -1;
    assert(m->reads<90);m->read_offsets[m->reads++]=offset;
    *out=m->regs[offset/4];
    if(m->reads==m->bad_read)*out=UINT32_MAX;
    if(m->reads==m->mutate_read)*out^=m->mutation;
    return 0;
}
static void released_prepare(struct released_model *m)
{
    memset(m,0,sizeof *m);
    struct rpi5_pcie_fdt f;prepare(&m->prior,&m->windows,&f);
    struct rpi5_pcie_windows_observation programmed;
    assert(!rpi5_pcie_windows_program(&m->windows,&programmed));
    memcpy(m->regs,m->prior.regs,sizeof m->prior.regs);
    m->regs[0x4068/4]=0xb0;m->regs[0x4064/4]=4;
    m->regs[0x4304/4]=0;
    for(unsigned i=0;i<7;i++) {
        m->regs[(0x40d4+8*i)/4]=0x10000;m->regs[(0x410c+8*i)/4]=0x20001;
    }
    for(unsigned i=2;i<4;i++) {
        m->regs[(0x4070+4*i)/4]=0x10;
        m->regs[(0x4080+8*i)/4]=m->regs[(0x4084+8*i)/4]=0;
    }
    struct rpi5_pcie_released_windows_io io={m,0x1000120000,0x9310,released_owner,released_read,released_order};
    assert(!rpi5_pcie_released_windows_init(&m->checker,&m->windows,&io));
    assert(!m->calls);
}
static void released_reject(struct released_model *m)
{
    struct rpi5_pcie_released_observation out;memset(&out,0xa5,sizeof out);const struct rpi5_pcie_released_observation before=out;
    assert(rpi5_pcie_released_windows_check(&m->checker,&out));
    assert(!memcmp(&out,&before,sizeof out)&&m->checker.state==RPI5_PCIE_RELEASED_FAILED);
    unsigned count=m->calls;assert(rpi5_pcie_released_windows_check(&m->checker,&out)==-2);
    assert(m->calls==count);
}
int main(void)
{
    struct released_model m;struct rpi5_pcie_released_observation out;
    released_prepare(&m);assert(!rpi5_pcie_released_windows_check(&m.checker,&out));
    assert(m.calls==277&&m.reads==90&&out.callbacks==277&&out.successful_checks==1);
    uint32_t offsets[90];memcpy(offsets,m.read_offsets,sizeof offsets);
    for(unsigned fail=1;fail<=277;fail++) {
        released_prepare(&m);m.fail_at=fail;released_reject(&m);assert(m.calls==fail);
        released_prepare(&m);m.dependency_at=fail;released_reject(&m);assert(m.calls==fail);
    }
    for(unsigned bad=1;bad<=90;bad++) {
        released_prepare(&m);m.bad_read=bad;released_reject(&m);assert(m.reads==bad);
    }
    for(unsigned i=3;i<25;i++) {
        released_prepare(&m);m.mutate_read=46+i;
        m.mutation=(offsets[i]==0x4070||offsets[i]==0x4074)?0x10:1;
        released_reject(&m);assert(m.reads==46+i);
    }
    for(unsigned i=25;i<45;i++) {
        released_prepare(&m);m.mutate_read=46+i;m.mutation=0x10000;
        released_reject(&m);
    }
    for(unsigned slot=0;slot<7;slot++) {
        released_prepare(&m);m.regs[(0x40d4+8*slot)/4]|=1;released_reject(&m);
    }
    for(unsigned slot=2;slot<4;slot++) {
        released_prepare(&m);m.regs[(0x4070+4*slot)/4]=0;released_reject(&m);
    }
    for(unsigned status=0x80;status<=0xb0;status+=0x10)for(unsigned control=0;control<=4;control+=4) {
        released_prepare(&m);m.regs[0x4068/4]=status;m.regs[0x4064/4]=control;
        assert(!rpi5_pcie_released_windows_check(&m.checker,&out));
    }
    for(unsigned index=0;index<5;index++) {
        released_prepare(&m);
        if(index==0)m.regs[0x4068/4]=0x30;
        if(index==1)m.regs[0x4068/4]|=0x40;
        if(index==2)m.regs[0x4064/4]|=1;
        if(index==3)m.regs[0x4304/4]|=8;
        if(index==4)m.regs[0x4304/4]|=0x08000000;
        released_reject(&m);
    }
    /* Transition observations may differ between snapshots without requiring
     * link-down or pretending that RELEASED already means posted completion. */
    released_prepare(&m);m.mutate_read=46;m.mutation=0x30;
    assert(!rpi5_pcie_released_windows_check(&m.checker,&out)&&out.status==0x80);
    released_prepare(&m);m.mutate_read=47;m.mutation=4;
    assert(!rpi5_pcie_released_windows_check(&m.checker,&out)&&out.control==0);
    released_prepare(&m);m.checker.checks=65536;released_reject(&m);assert(!m.calls);
    puts("RELEASED_WINDOWS_PASS READS=90 CALLBACKS=277 FAILURE_POSITIONS=277 DEPENDENCY_POSITIONS=277 NO_HARDWARE=1");
    return 0;
}
