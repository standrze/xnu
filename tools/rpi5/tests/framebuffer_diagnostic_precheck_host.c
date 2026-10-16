/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual probe_main/check/reject source is inserted below by the test.
 * Hardware and FDT decoder results are explicit doubles; no hardware proof. */
#include "framebuffer_observation.h"
#include "uart.h"
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define UART UINT64_C(0x107d001000)
#define PM UINT64_C(0x107d200000)
#define UART_BUDGET 1000000u
#define RPI5_FB_OBSERVE_TAG "0123456789abcdef0123456789abcdef"
static uint8_t __probe_start[8],__probe_end[8],fdt[40]={0xd0,0x0d,0xfe,0xed,0,0,0,40};
static struct rpi5_reservation_plan reservations;
static uintptr_t original_fdt;
static uint32_t original_size,stage,admitted;
static uint64_t frequency;
static unsigned fail_stage,guard_calls;
static char output[8192];static size_t used;static jmp_buf stopped;
static _Noreturn void park(void){longjmp(stopped,1);}
static int text(const char *s){size_t n=strlen(s);assert(used+n<sizeof output);memcpy(output+used,s,n+1);used+=n;return 1;}
static int hex(uint64_t n){char b[32];snprintf(b,sizeof b,"0x%016llX",(unsigned long long)n);return text(b);}
static uint64_t reg(const char *name){
    if(!strcmp(name,"CurrentEL"))return 8;
    if(!strcmp(name,"sctlr_el2"))return 0x30c50830;
    if(!strcmp(name,"daif"))return 0x3c0;
    if(!strcmp(name,"mpidr_el1"))return fail_stage==12?1:0;
    if(!strcmp(name,"cntfrq_el0"))return 54000000;
    abort();
}
static int gate(unsigned expected){
    assert(stage==expected);char line[96];snprintf(line,sizeof line,"RPI5XNU:FBOBS:CHECK STAGE=0x%016llX\r\n",(unsigned long long)expected);
    assert(strstr(output,line));guard_calls++;return fail_stage==expected?-1:0;
}
enum rpi5_uart_result rpi5_uart_snapshot(uintptr_t base,struct rpi5_uart_snapshot *out){
    assert(base==UART && !stage && !guard_calls && !used);*out=(struct rpi5_uart_snapshot){0x301,0x90,24,0,0x70};return RPI5_UART_OK;
}
enum rpi5_uart_result rpi5_uart_drain(uintptr_t base,size_t budget){assert(base==UART&&budget==UART_BUDGET);return RPI5_UART_OK;}
enum rpi5_uart_result rpi5_uart_set_exact(uintptr_t base,uint32_t hz,uint32_t baud,size_t budget){
    assert(base==UART&&hz==44236800&&baud==115200&&budget==UART_BUDGET);return gate(17)?RPI5_UART_INVALID:RPI5_UART_OK;
}
int rpi5_fdt_structure(const void *b,size_t n){assert(b==fdt&&n==40);assert(strstr(output," EL2 PRECHECK "));assert(strstr(output,"UART CR="));return gate(1);}
int rpi5_fdt_phandles(const void*b,size_t n){(void)b;(void)n;return gate(2);}
int rpi5_fdt_probe_mmio(const void*b,size_t n){(void)b;(void)n;return gate(3);}
int rpi5_fdt_uart_clocks(const void*b,size_t n,struct rpi5_uart_clocks*out){(void)b;(void)n;*out=(struct rpi5_uart_clocks){44236800,750000000};return gate(4);}
int rpi5_fdt_watchdog(const void*b,size_t n,struct rpi5_range*out){(void)b;(void)n;*out=(struct rpi5_range){PM,PM+0x308};return gate(5);}
int rpi5_fdt_cpus(const void*b,size_t n,struct rpi5_fdt_cpus*out){(void)b;(void)n;memset(out,0,sizeof *out);out->count=4;out->enabled_mask=15;for(unsigned i=0;i<4;i++)out->affinity[i]=i*256;return gate(6);}
int rpi5_fdt_psci_smc(const void*b,size_t n){(void)b;(void)n;return gate(7);}
int rpi5_fdt_memory(const void*b,size_t n,struct rpi5_fdt_memory*out){(void)b;(void)n;memset(out,0,sizeof *out);out->count=1;out->end[0]=1ull<<32;return gate(8);}
int rpi5_fdt_reservation_plan(const void*b,size_t n,struct rpi5_reservation_plan*out){
    (void)b;(void)n;memset(out,0,sizeof *out);if(fail_stage==11){out->fixed.count=1;out->fixed.extent[0]=(struct rpi5_range){(uintptr_t)fdt,(uintptr_t)fdt+40};}return gate(9);
}
int rpi5_ranges_validate_live(const struct rpi5_range*a,size_t n,const struct rpi5_range*b,size_t m){(void)a;(void)b;assert(n==1&&m==2);return gate(10);}
uint64_t rpi5_psci_query(uint64_t fid,uint64_t query){
    if(fid==0x8400000a){assert(query==0xc4000004);return gate(13)?UINT64_MAX:0;}
    assert(fid==0xc4000004 && query>=256&&query<=768&&query%256==0);return gate(13+(unsigned)(query/256))?0:1;
}
/* ACTUAL_SOURCE */
int main(int argc,char**argv){
    assert(argc==2);fail_stage=(unsigned)strtoul(argv[1],NULL,10);assert(fail_stage<=17);
    int stopped_early=setjmp(stopped);if(!stopped_early)probe_main((uintptr_t)fdt);
    if(fail_stage){assert(stopped_early&&!admitted);assert(stage==fail_stage);assert(strstr(output,"NO_RELOAD OBSERVATION_INCOMPLETE"));}
    else {assert(!stopped_early&&admitted&&stage==17&&original_fdt==(uintptr_t)fdt&&original_size==40);assert(!strstr(output,"REJECT"));}
    assert(!strstr(output,"ARMED")&&!strstr(output,"RESULT")&&!strstr(output,"INVENTORY"));fputs(output,stdout);return 0;
}
