/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual original collection TUs. Only allocation fault injection and the
 * caller are test code; the native Blocks runtime is the original Apple one. */
#include <os/collections.h>
#include <assert.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

enum { N = 1024 };
static unsigned allocation_calls, fail_at;
void *fixture_calloc(size_t n, size_t size)
{
    allocation_calls++;
    return fail_at && allocation_calls == fail_at ? NULL : calloc(n, size);
}
static unsigned payload[N];
static uint32_t keys32[N];
static uint64_t keys64[N];
static char names[N][32];
static const char *strings[N];

#define MAP_CASE(TYPE, KEY_TYPE, KEY) do { \
    TYPE map; os_map_init(&map, NULL); \
    assert(os_map_count(&map) == 0); \
    for (unsigned i=0;i<N;i++) os_map_insert(&map, (KEY), &payload[i]); \
    assert(os_map_count(&map) == N); \
    for (unsigned i=0;i<N;i++) assert(os_map_find(&map, (KEY)) == &payload[i]); \
    __block unsigned visited=0; __block uint64_t sum=0; \
    os_map_foreach(&map, ^bool(KEY_TYPE key, void *value) { \
        (void)key; sum += *(unsigned *)value; visited++; return true; }); \
    assert(visited==N && sum==(uint64_t)N*(N-1)/2); \
    visited=0; os_map_foreach(&map, ^bool(KEY_TYPE key, void *value) { \
        (void)key; (void)value; visited++; return false; }); assert(visited==1); \
    for (unsigned i=0;i<N;i+=2) { assert(os_map_delete(&map, (KEY))==&payload[i]); \
        assert(!os_map_find(&map, (KEY))); assert(!os_map_delete(&map, (KEY))); } \
    assert(os_map_count(&map)==N/2); visited=0; \
    os_map_clear(&map, ^bool(KEY_TYPE key, void *value) { \
        (void)key; assert((*(unsigned *)value)&1); visited++; return false; }); \
    assert(visited==N/2 && !os_map_count(&map)); \
    for (unsigned i=0;i<N;i++) os_map_insert(&map, (KEY), &payload[i]); \
    os_map_clear(&map, NULL); assert(!os_map_count(&map)); os_map_destroy(&map); \
} while (0)

#define SET_CASE(TYPE, VALUE_TYPE, ADDRESS, KEY) do { \
    TYPE set; os_set_init(&set, NULL); \
    for (unsigned i=0;i<N;i++) os_set_insert(&set, (ADDRESS)); \
    assert(os_set_count(&set)==N); \
    for (unsigned i=0;i<N;i++) assert(os_set_find(&set,(KEY))==(ADDRESS)); \
    __block unsigned visited=0; \
    os_set_foreach(&set, ^bool(VALUE_TYPE value) {assert(value);visited++;return true;}); \
    assert(visited==N); visited=0; \
    os_set_foreach(&set, ^bool(VALUE_TYPE value) {(void)value;visited++;return false;}); assert(visited==1); \
    for (unsigned i=0;i<N;i+=2) {assert(os_set_delete(&set,(KEY))==(ADDRESS)); \
        assert(!os_set_find(&set,(KEY))); assert(!os_set_delete(&set,(KEY)));} \
    assert(os_set_count(&set)==N/2); visited=0; \
    os_set_clear(&set, ^bool(VALUE_TYPE value) {assert(value);visited++;return false;}); \
    assert(visited==N/2 && !os_set_count(&set)); \
    for (unsigned i=0;i<N;i++) os_set_insert(&set,(ADDRESS)); \
    os_set_clear(&set,NULL);assert(!os_set_count(&set));os_set_destroy(&set); \
} while (0)

static void fatal_case(unsigned kind)
{
    pid_t pid=fork(); assert(pid>=0);
    if (!pid) {
        struct rlimit lim={0,0};assert(!setrlimit(RLIMIT_CORE,&lim));
        assert(freopen("/dev/null","w",stderr));
        allocation_calls=0;fail_at=kind<2?1:2;
        if (!(kind&1)) {os_map_32_t map;os_map_init(&map,NULL);
            for(unsigned i=0;i<N;i++)os_map_insert(&map,i,&payload[i]);}
        else {os_set_64_ptr_t set;os_set_init(&set,NULL);
            for(unsigned i=0;i<N;i++)os_set_insert(&set,&keys64[i]);}
        _exit(77);
    }
    int status;assert(waitpid(pid,&status,0)==pid);
    assert(WIFSIGNALED(status) && WTERMSIG(status)==SIGABRT);
}

int main(int argc,char **argv)
{
    (void)argv;
    for(unsigned i=0;i<N;i++) {payload[i]=i;keys32[i]=i;keys64[i]=(uint64_t)i<<32;
        snprintf(names[i],sizeof names[i],"notify-collision-%u",i);strings[i]=names[i];}
    MAP_CASE(os_map_32_t,uint32_t,keys32[i]);
    MAP_CASE(os_map_64_t,uint64_t,keys64[i]);
    MAP_CASE(os_map_128_t,os_map_128_key_t,((os_map_128_key_t){{i,(uint64_t)i<<32}}));
    MAP_CASE(os_map_str_t,const char *,strings[i]);
    SET_CASE(os_set_32_ptr_t,uint32_t *,&keys32[i],keys32[i]);
    /* Every original 64-pointer hash sees the same low32bits: exercise real
     * Robin-Hood collision paths, deletion compaction and resize/shrink. */
    SET_CASE(os_set_64_ptr_t,uint64_t *,&keys64[i],keys64[i]);
    SET_CASE(os_set_str_ptr_t,const char **,&strings[i],strings[i]);
    os_map_str_t map;os_map_init(&map,NULL);os_map_insert(&map,strings[0],payload);
    char identical[32];strcpy(identical,strings[0]);
    assert(os_map_entry(&map,identical)==strings[0]);assert(!os_map_entry(&map,"absent"));
    os_map_destroy(&map);
    for(unsigned i=0;i<4;i++)fatal_case(i);
    if(argc!=1)return 37;
    puts("APPLE_COLLECTIONS PASS MAPS=4 SETS=3 ELEMENTS=1024 COLLISION_SET=1024 ALLOCATION_ABORTS=4 ORIGINAL_BLOCKS HOST_ONLY");
    return 0;
}
