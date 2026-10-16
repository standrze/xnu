/* SPDX-License-Identifier: BSD-2-Clause */
/* Real adapter/FDT/transaction code, explicit architecture/device doubles.
 * Identity-address leaf is explicitly doubled because macOS reserves low4GiB.
 * Backing is aligned host RAM; production identity leaf is exactly RET. */
#include "display_visible_adapter.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned count,mode,bad_reg,registers,cleaned,invalidated,writes,pops,reads,peeks;
static uint64_t ticks;static uint32_t pending;static unsigned char *fdt;
static unsigned char *pages;
static unsigned visible_stores,visible_barriers;
static unsigned char pixels[608128];
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
    if(mode==50&&visible_stores>=160)r->sctlr|=4;
}
uint64_t rpi5_display_query_counter(void){if(mode!=15)ticks+=(writes==4&&pops==4)?54:54000;
    if(mode==52&&visible_stores==160)ticks+=54000000;return ticks;}
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
    assert(p==0x107c0138a0ull && (word&15)==8 && !pending && writes<4);writes++;
    uintptr_t pa=word&~15u;assert(pa==0x9001000ull+4096*(writes-1));
    uint32_t *b=(uint32_t *)(pages+(pa-0x9000000));
    assert(cleaned==writes && invalidated==4+pops);
    static const uint32_t before[]={1,0,1920,1080,32,7680,1920,1080,0,0,0,0,0,0,0,0,0};
    static const uint32_t selected[]={0};
    static const uint32_t allocated[]={1920,1080,1920,1080,32,0,2,0,0,0,0,0,0,0x3f400000,8294400,7680};
    static const uint32_t verified[]={1920,1080,1920,1080,32,0,2,0,0,0,0,0,0,7680,0,1920,1080,32,7680,1920,1080,0,0,0,0,0,0,0,0,0};
    const uint32_t *values=writes==1?before:writes==2?selected:writes==3?allocated:verified;
    assert(b[1]==0);b[1]=0x80000000;unsigned value_index=0;
    for(unsigned i=2;i<b[0]/4-1;){
        assert(!b[i+2]);unsigned words=b[i+1]/4;b[i+2]=0x80000000|b[i+1];
        for(unsigned j=0;j<words;j++)b[i+3+j]=values[value_index++];i+=3+words;
    }
    if(writes==1 && count!=1)b[5]=count;
    if(writes==1 && mode==40){b[12]=16;b[13]=3840;}
    if(writes==3 && ((mode>=41 && mode<=46)||mode==48||mode==49)){
        // Corrupt returned base/size/pitch/order under successful framing.
        for(unsigned i=2;i<b[0]/4-1;){
            if(b[i]==0x40001){
                if(mode==41)b[i+3]=0xff400000;
                if(mode==42)b[i+3]=0x09000000;
                if(mode==43)b[i+4]=4096;
                if(mode==44)b[i+4]=0x02000000;
                if(mode==46)b[i+3]=0x3fc00000;
                if(mode==48)b[i+3]=0x7f400000;
                if(mode==49)b[i+3]=0xbf400000;
            }
            if(mode==45 && b[i]==0x40008)b[i+3]=3840;
            i+=3+b[i+1]/4;
        }
    }
    if(writes==4 && mode==47)b[5]^=1;
    if(mode==3)b[1]=0;
    if(mode!=2)pending=word;
    if(mode==4)fdt[0]^=1;
}
void rpi5_display_query_clean(uintptr_t p){assert(!(p&4095) && p>=(uintptr_t)pages+4096 && p<(uintptr_t)pages+20480);cleaned++;}
void rpi5_display_query_invalidate(uintptr_t p){assert(!(p&4095) && p>=(uintptr_t)pages+4096 && p<(uintptr_t)pages+20480);invalidated++;}
void rpi5_display_visible_store(uintptr_t address,uint32_t value){
    unsigned x=visible_stores%320,y=visible_stores/320;
    assert(address==UINT64_C(0x3f400000)+(y+16)*7680+(x+16)*4);
    assert(value==rpi5_display_visible_pixel(x,y));visible_stores++;
    memcpy(pixels+32+address-0x3f400000,&value,4);
    if(mode==51&&visible_stores==160)fdt[0]^=1;
}
void rpi5_display_visible_barrier(void){visible_barriers++;assert(visible_stores==visible_barriers*320);}
int main(int argc,char **argv)
{
    assert(argc==5);count=(unsigned)strtoul(argv[2],0,10);mode=(unsigned)strtoul(argv[3],0,10);bad_reg=(unsigned)strtoul(argv[4],0,10);
    assert(!posix_memalign((void **)&pages,4096,0x8000));memset(pages,0,0x8000);
    fdt=malloc(0x100000);assert(fdt);
    FILE *f=fopen(argv[1],"rb");assert(f);size_t n=fread(fdt,1,0x100000,f);assert(n>=40);fclose(f);
    struct rpi5_display_allocate_result out,prior;memset(&prior,0xa5,sizeof prior);out=prior;
    struct rpi5_display_allocate_report report={0};struct rpi5_display_visible_report draw={0};
    memset(pixels,0xa5,sizeof pixels);
    struct rpi5_range image={0x9000000,0x9008000};void *storage=pages+4096;
    if(mode==20)storage=pages+4097;
    if(mode==21)image.end=0x9003000;
    int rc=rpi5_display_visible_run(fdt,n,image,storage,0,mode==53?1:UINT64_MAX,&out,&report,&draw);
    if(rc&&!mode&&!bad_reg&&count==1)fprintf(stderr,"rc=%d admit=%u state=%u stage=%u tx=%u regs=%u reads=%u cache=%u\n",rc,report.admission,report.session.state,report.session.stage,report.session.tx_attempted,registers,reads,cleaned+invalidated);
    if(mode>=50){assert(!rc&&draw.result);}
    else if(mode || bad_reg || count!=1){assert((rc||draw.result));if(rc){assert(!memcmp(&out,&prior,sizeof out));if(report.admission)assert(report.session.quarantined_buffers==15);}}

    else {
        assert(!rc && report.admission && report.session.state==RPI5_DISPLAY_MBOX_COMPLETE);
        assert(writes==4&&pops==4&&peeks==4&&cleaned==4&&invalidated==8);
        assert(report.candidate_valid&&report.candidate.cpu_address==0x3f400000&&report.candidate.allocation_bytes==8294400);
        assert(report.decoded_replies==15);assert(!draw.result&&draw.completed==20480&&visible_stores==20480&&visible_barriers==64);

    }
    if(count!=1||mode==40)assert(writes==1);
    if(mode==1)assert(writes==1&&!pops&&peeks==1);
    if(mode==2)assert(writes==1&&!pops&&reads<=520);
    if(!rc&&!draw.result){
        struct rpi5_display_retained retained,before;
        struct rpi5_range managed={0x6000000,0x10000000};
        assert(!rpi5_display_allocation_retained(&out,&report,fdt,n,0x20000000,image,&managed,1,&retained));
        before=retained;struct rpi5_range forbidden={0x3fbea000,0x3fbeb000};
        assert(rpi5_display_allocation_retained(&out,&report,fdt,n,0x20000000,image,&forbidden,1,&retained));
        assert(!memcmp(&before,&retained,sizeof retained));
        struct rpi5_display_allocate_report changed=report;changed.candidate.cpu_address+=16384;
        assert(rpi5_display_allocation_retained(&out,&changed,fdt,n,0x20000000,image,&managed,1,&retained));
        changed=report;changed.replies[2].words[13]|=0xc0000000;
        assert(rpi5_display_allocation_retained(&out,&changed,fdt,n,0x20000000,image,&managed,1,&retained));
        assert(rpi5_display_allocation_retained(&out,&report,fdt,n,0x20000000,image,0,0,(void *)&out));
        for(unsigned i=0;i<32;i++)assert(pixels[i]==0xa5&&pixels[608096+i]==0xa5);
    }
    unsigned before=writes,draw_before=visible_stores;
    assert(rpi5_display_visible_run(fdt,n,image,storage,0,UINT64_MAX,&out,&report,&draw));assert(writes==before&&visible_stores==draw_before);
    printf("VISIBLE_ADAPTER rc=%d draw=%d stores=%u registers=%u reads=%u writes=%u pops=%u cache=%u NO_HARDWARE=1\n",rc,draw.result,visible_stores,registers,reads,writes,pops,cleaned+invalidated);
    free(fdt);free(pages);return 0;
}


