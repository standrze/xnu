/* SPDX-License-Identifier: BSD-2-Clause
 * Host-only checks of the project adapter. Real host malloc zones/pthreads are
 * used; the target Apple scalable allocator and target startup are NOT run.
 */
#include <malloc/malloc.h>
#include <pthread.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "../user/pthread_static_entry_core.h"
extern void *rpi5_malloc(size_t), *rpi5_calloc(size_t,size_t);
extern void *rpi5_realloc(void *,size_t), *rpi5_valloc(size_t);
extern void rpi5_free(void *), rpi5_malloc_zone_register(malloc_zone_t *);
extern unsigned rpi5_malloc_num_zones;
extern malloc_zone_t **rpi5_malloc_zones;
static unsigned requests, gate, failure;

malloc_zone_t *fixture_create_scalable_zone(size_t size,unsigned flags)
{
    unsigned call = __atomic_add_fetch(&requests,1,__ATOMIC_RELAXED);
    /* A single explicit failure-injection case, then real host VM allocator. */
    if (call == 1) return 0;
    return malloc_create_zone(size,flags);
}

static void *worker(void *arg)
{
    unsigned char value=(unsigned char)(uintptr_t)arg;
    while (!__atomic_load_n(&gate,__ATOMIC_ACQUIRE)) {}
    for (unsigned i=0;i<512;i++) {
        unsigned char *p=rpi5_calloc(17,3);
        if (!p) return (void *)1;
        for (unsigned j=0;j<51;j++) if (p[j]) return (void *)2;
        memset(p,value,51);
        unsigned char *q=rpi5_realloc(p,137);
        if (!q) { rpi5_free(p);return (void *)3; }
        for (unsigned j=0;j<51;j++) if (q[j]!=value) return (void *)4;
        rpi5_free(q);
    }
    return 0;
}

static unsigned initialized;
static void init_one(void) { initialized = initialized*10+1; }
static void init_two(void) { initialized = initialized*10+2; }

static int vector_checks(void)
{
    char a[]="pthreadprobe",e[]="PATH=/usr/bin:/bin",k[]="th_port=0x103";
    uintptr_t input[]={1,(uintptr_t)a,0,(uintptr_t)e,0,(uintptr_t)k,0};
    struct rpi5_process_vectors out,original;
    memset(&out,0xa5,sizeof(out));original=out;
    for (size_t n=0;n<7;n++) {
        if (!rpi5_process_vectors_parse(input,n,&out)||memcmp(&out,&original,sizeof(out))) return 10;
    }
    if (rpi5_process_vectors_parse(input,7,&out)||out.argc!=1||out.argv[0]!=a||out.envp[0]!=e||out.apple[0]!=k) return 11;
    if (!rpi5_process_vectors_parse(0,7,&out)||!rpi5_process_vectors_parse(input,7,0)) return 12;
    input[0]=4097;if (!rpi5_process_vectors_parse(input,7,&out)) return 13;input[0]=1;
    input[1]=0;if (!rpi5_process_vectors_parse(input,7,&out)) return 14;input[1]=(uintptr_t)a;
    input[2]=1;if (!rpi5_process_vectors_parse(input,7,&out)) return 15;input[2]=0;
    rpi5_initializer functions[]={init_one,init_two},bad[]={init_one,0};
    if (!rpi5_run_initializers(bad,bad+2)||initialized) return 16;
    if (rpi5_run_initializers(functions,functions+2)||initialized!=12) return 17;
    if (!rpi5_run_initializers(functions,(rpi5_initializer *)((uintptr_t)functions-1))) return 18;
    rpi5_initializer long_list[65]={0};
    if (!rpi5_run_initializers(long_list,long_list+65)||initialized!=12) return 19;
    return 0;
}

int main(void)
{
    int check=vector_checks();if(check)return check;
    errno=0;if(rpi5_malloc(16)||errno!=ENOMEM||requests!=1||rpi5_malloc_num_zones)return 20;
    pthread_t threads[8];
    for(unsigned i=0;i<8;i++)if(pthread_create(&threads[i],0,worker,(void *)(uintptr_t)(i+1)))return 21;
    __atomic_store_n(&gate,1,__ATOMIC_RELEASE);
    for(unsigned i=0;i<8;i++){void *r=0;if(pthread_join(threads[i],&r)||r)failure=1;}
    if(failure||requests!=2||rpi5_malloc_num_zones!=1)return 22;
    errno=0;if(rpi5_calloc(SIZE_MAX,2)||errno!=ENOMEM)return 23;
    void *p=rpi5_valloc(99);if(!p||(uintptr_t)p%(size_t)getpagesize())return 24;rpi5_free(p);
    p=rpi5_realloc(0,15);if(!p)return 25;p=rpi5_realloc(p,0);if(!p)return 26;rpi5_free(p);
    rpi5_free(0);
    errno=0;rpi5_malloc_zone_register(0);if(errno!=EINVAL)return 27;
    malloc_zone_t *zone=rpi5_malloc_zones[0];
    rpi5_malloc_zone_register(zone);if(rpi5_malloc_num_zones!=1)return 28;
    malloc_destroy_zone(zone);
    puts("PTHREAD_ADAPTER PASS VECTOR=16 CTOR_ATOMIC=1 THREADS=8 ALLOC=4096 FIRST_FAILURE=1 ZONE_CREATES=1 HOST_ZONE_ONLY");
    return 0;
}
