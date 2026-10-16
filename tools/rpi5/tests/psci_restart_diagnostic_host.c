/* SPDX-License-Identifier: BSD-2-Clause -- actual policy, explicit host doubles. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "psci_restart_candidate.h"
#include "psci_restart_diagnostic.h"
#include "pexpert/arm/rpi5_restart_diag_api.h"
static struct rpi5_restart_once once;
static unsigned versions,features,snapshots,writes,resets,fail_snapshot,fail_write;
static uint64_t el=4,version=0x10001,feature,result;
static struct rpi5_restart_diag_snapshot value;
static char wire[1024];static size_t wire_bytes;
uint64_t rpi5_restart_current_el(void){return el;}
uint64_t rpi5_restart_psci_version(void){versions++;return version;}
uint64_t rpi5_restart_psci_feature(void){features++;return feature;}
uint64_t rpi5_restart_psci_reset(void){assert(writes==1&&snapshots==1);resets++;return result;}
int rpi5_restart_diag_snapshot(struct rpi5_restart_diag_snapshot *out){snapshots++;if(fail_snapshot)return -1;*out=value;return 0;}
int rpi5_restart_diag_uart(const char *text,size_t n){writes++;assert(n<=256&&wire_bytes+n<sizeof(wire));if(fail_write==writes)return -1;memcpy(wire+wire_bytes,text,n);wire_bytes+=n;wire[wire_bytes]=0;return 0;}
static void reset(void){
    memset(&once,0,sizeof(once));versions=features=snapshots=writes=resets=fail_snapshot=fail_write=0;
    el=4;version=0x10001;feature=result=0;wire_bytes=0;wire[0]=0;
    value=(struct rpi5_restart_diag_snapshot){.cntvct_before=100,.cntvct=102,.cntfrq=100,
        .terminal_deadline=18000,.watchdog_count_before=15u<<16,.watchdog_remaining_ticks=14u<<16,
        .full_reset_route=1,.watchdog_nominal_hz=65536,.watchdog_rate_bound_proven=0};
}
int main(int argc,char **argv){
    assert(argc==2);FILE*f=fopen(argv[1],"rb");assert(f&&!fseek(f,0,SEEK_END));long n=ftell(f);assert(n>0);
    rewind(f);void*tree=malloc((size_t)n);assert(tree&&fread(tree,1,(size_t)n,f)==(size_t)n);assert(!fclose(f));
    reset();assert(rpi5_restart_diagnostic_ready(tree,(size_t)n));assert(versions==1&&features==1&&writes==1&&!snapshots&&!resets&&!once.entered);
    assert(!strcmp(wire,"\nRPI5XNU:RESTART:READY OPTIN=1 PSCI=00010001 RESET_SUPPORTED=1 WATCHDOG_UNCHANGED\n"));
    for(unsigned fail=0;fail<4;fail++){
        reset();if(fail==0)el=8;if(fail==1)version=0x10002;if(fail==2)feature=1;if(fail==3)fail_write=1;
        assert(!rpi5_restart_diagnostic_ready(tree,(size_t)n));assert(!resets&&!snapshots&&!once.entered);
        if(fail<3)assert(!writes);
    }
    for(unsigned bad=0;bad<12;bad++){
        reset();switch(bad){
        case 0:fail_snapshot=1;break;case 1:value.cntvct=99;break;case 2:value.cntfrq=0;break;
        case 3:value.terminal_deadline=102;break;case 4:value.watchdog_count_before=0x100000;break;
        case 5:value.watchdog_remaining_ticks=0;break;case 6:value.watchdog_remaining_ticks=value.watchdog_count_before+1;break;
        case 7:value.full_reset_route=0;break;case 8:value.watchdog_nominal_hz=1;break;
        case 9:value.watchdog_rate_bound_proven=1;break;case 10:fail_write=1;break;case 11:feature=1;break;}
        assert(rpi5_restart_attempt(&once,tree,(size_t)n)<0&&!resets&&once.entered==1);
        assert(rpi5_restart_attempt(&once,tree,(size_t)n)==RPI5_RESTART_BUSY&&!resets);
        if(bad<10)assert(!writes);
    }
    for(unsigned returned=0;returned<3;returned++){
        reset();result=returned==0?0:returned==1?1:UINT64_MAX;
        assert(rpi5_restart_attempt(&once,tree,(size_t)n)==RPI5_RESTART_RETURNED&&resets==1&&writes==2);
        assert(!strcmp(wire,"\nRPI5XNU:RESTART:PRE_SMC COUNT=000e0000 COUNTER=0000000000000066 FREQ=0000000000000064 DEADLINE=0000000000004650 NOMINAL_HZ=00010000 RATE_BOUND=0\n\nRPI5XNU:RESTART:RETURNED NO_RESET_PROVEN\n"));
        assert(rpi5_restart_attempt(&once,tree,(size_t)n)==RPI5_RESTART_BUSY&&resets==1);
    }
    free(tree);puts("DIAGNOSTIC_POLICY PASS READY_NOT_RESET ACTUAL_POLICY_GATE SNAPSHOT_FAILURES RETURNED_REJECT NOMINAL_ONLY NO_HARDWARE");return 0;
}
