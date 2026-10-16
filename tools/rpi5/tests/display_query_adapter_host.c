/* SPDX-License-Identifier: BSD-2-Clause */
/* Real adapter/FDT/transaction code, explicit architecture/device doubles.
 * Identity-address leaf is explicitly doubled because macOS reserves low4GiB.
 * Backing is aligned host RAM; production identity leaf is exactly RET. */
#include "display_query_adapter.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned count,mode,bad_reg,registers,cleaned,invalidated,writes,pops,reads,peeks;
static uint64_t ticks;static uint32_t pending;static unsigned char *fdt;
static unsigned char *pages;
uint64_t rpi5_display_query_identity(const void *p){
    uintptr_t v=(uintptr_t)p,b=(uintptr_t)pages,f=(uintptr_t)fdt;
    if(v>=b&&v<b+0x8000)return 0x9000000+(v-b);
    if(v>=f&&v<f+0x100000)return 0x20000000+(v-f);
    abort();
}
void rpi5_display_query_registers(struct rpi5_display_query_registers *r)
{
    registers++;*r=(struct rpi5_display_query_registers){4,0x30d00800,0x3c0,0,54000000,0x8444c004,0x414fd0b1};
    if(registers==bad_reg){r->daif=0;r->frequency=0;}
    if(mode==10)r->daif=0;
    if(mode==11)r->sctlr|=4;
    if(mode==12)r->ctr=0x30004;
    if(mode==13)r->midr=0x410fd030;
    if(mode==14)r->mpidr=1;
}
uint64_t rpi5_display_query_counter(void){if(mode!=15)ticks+=54000;return ticks;}
uint32_t rpi5_display_query_read(uintptr_t p)
{
    assert(p>=0x107c013880ull && p<0x107c0138c0ull);reads++;
    switch((unsigned)(p-0x107c013880ull)){
    case 0x18:return pending?0:0x40000000;
    case 0x38:return 0x40000000;
    case 0x10:peeks++;assert(pending);return pending^(mode==1?0x10u:0);
    case 0:assert(pending);pops++;{uint32_t r=pending;pending=0;return r;}
    default:abort();
    }
}
void rpi5_display_query_write(uintptr_t p,uint32_t word)
{
    assert(p==0x107c0138a0ull && (word&15)==8 && !pending && writes<3);writes++;
    uintptr_t pa=word&~15u;assert(pa==0x9001000ull+4096*(writes-1));
    uint32_t *b=(uint32_t *)(pages+(pa-0x9000000));
    assert(cleaned==writes && invalidated==3+pops);
    assert(b[1]==0 && (b[2]==0x40013 || b[2]==0x40014));
    b[1]=0x80000000;b[4]=0x80000000|b[3];
    if(b[2]==0x40013){assert(b[0]==28 && b[3]==4);b[5]=count;}
    else {assert(b[0]==88 && b[3]==64 && b[5]==writes-2);for(unsigned i=1;i<16;i++)b[5+i]=0xa0000000u+(writes-2)*16+i;}
    if(mode==3)b[1]=0;
    if(mode!=2)pending=word;
    if(mode==4)fdt[0]^=1;
}
void rpi5_display_query_clean(uintptr_t p){assert(!(p&4095) && p>=(uintptr_t)pages+4096 && p<(uintptr_t)pages+16384);cleaned++;}
void rpi5_display_query_invalidate(uintptr_t p){assert(!(p&4095) && p>=(uintptr_t)pages+4096 && p<(uintptr_t)pages+16384);invalidated++;}
int main(int argc,char **argv)
{
    assert(argc==5);count=(unsigned)strtoul(argv[2],0,10);mode=(unsigned)strtoul(argv[3],0,10);bad_reg=(unsigned)strtoul(argv[4],0,10);
    assert(!posix_memalign((void **)&pages,4096,0x8000));memset(pages,0,0x8000);
    fdt=malloc(0x100000);assert(fdt);
    FILE *f=fopen(argv[1],"rb");assert(f);size_t n=fread(fdt,1,0x100000,f);assert(n>=40);fclose(f);
    struct rpi5_display_mailbox_result out,prior;memset(&prior,0xa5,sizeof prior);out=prior;
    struct rpi5_display_query_report report={0};
    struct rpi5_range image={0x9000000,0x9008000};void *storage=pages+4096;
    if(mode==20)storage=pages+4097;
    if(mode==21)image.end=0x9003000;
    int rc=rpi5_display_query_run(fdt,n,image,storage,0,&out,&report);
    if(rc&&!mode&&!bad_reg)fprintf(stderr,"rc=%d admit=%u state=%u stage=%u tx=%u regs=%u reads=%u cache=%u\n",rc,report.admission,report.session.state,report.session.stage,report.session.tx_attempted,registers,reads,cleaned+invalidated);
    if(mode || bad_reg){assert(rc && !memcmp(&out,&prior,sizeof out));if(report.admission)assert(report.session.quarantined_buffers==7);}
    else {
        assert(!rc && out.count==count && report.admission && report.session.state==RPI5_DISPLAY_MBOX_COMPLETE);
        assert(writes==count+1 && pops==count+1 && peeks==count+1 && cleaned==count+1 && invalidated==count+4);
        for(unsigned i=0;i<count;i++)for(unsigned j=0;j<16;j++)assert(out.settings[i].words[j]==(j?0xa0000000u+i*16+j:i));
    }
    if(mode==1)assert(writes==1&&!pops&&peeks==1);
    if(mode==2)assert(writes==1&&!pops&&reads<=520);
    unsigned before=writes;assert(rpi5_display_query_run(fdt,n,image,storage,0,&out,&report));assert(writes==before);
    printf("ADAPTER rc=%d registers=%u reads=%u writes=%u pops=%u cache=%u NO_HARDWARE=1\n",rc,registers,reads,writes,pops,cleaned+invalidated);
    free(fdt);free(pages);return 0;
}
