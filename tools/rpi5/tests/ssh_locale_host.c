/* SPDX-License-Identifier: BSD-2-Clause
 * Namespaced unchanged Apple locale sources, host pthread/allocator services.
 * The one explicit boundary maps Apple's reserved key registration to a fresh
 * host dynamic key. Never overwrite the host libSystem's reserved locale slot.
 */
#include "xlocale_private.h"
#include "mblocal.h"
#include <ctype.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>

static int registrations;
static atomic_int destroyed;
static int deliberately_wrong;

int fixture_key_init_np(int key, void (*destructor)(void *))
{
    if (key != __LIBC_PTHREAD_KEY_XLOCALE || !destructor || registrations++) abort();
    pthread_key_t host_key;
    if (pthread_key_create(&host_key, destructor)) abort();
    __locale_key = host_key;
    return 0;
}

struct conversion { const char *text; int base; long long value; int error; size_t end; };
static const struct conversion vectors[] = {
    {"0",0,0,0,1}, {"42",10,42,0,2}, {" \t\n-42tail",10,-42,0,6},
    {"+17",10,17,0,3}, {"077",0,63,0,3}, {"09",0,0,0,1},
    {"0x1f",0,31,0,4}, {"-0XFF!",16,-255,0,5}, {"0x",0,0,0,1},
    {"z",36,35,0,1}, {"101011",2,43,0,6}, {"123",1,0,EINVAL,0},
    {"123",37,0,EINVAL,0}, {"",10,0,EINVAL,0}, {"+",10,0,EINVAL,0},
    {"none",10,0,EINVAL,0}, {"9223372036854775807",10,LLONG_MAX,0,19},
    {"-9223372036854775808",10,LLONG_MIN,0,20},
    {"9223372036854775808xyz",10,LLONG_MAX,ERANGE,19},
    {"-9223372036854775809xyz",10,LLONG_MIN,ERANGE,20},
    {"999999999999999999999999999999z",10,LLONG_MAX,ERANGE,30},
    {"-8000000000000000",16,LLONG_MIN,0,17},
    {"8000000000000000",16,LLONG_MAX,ERANGE,16},
};

static int conversions(void)
{
    for (size_t i=0; i<sizeof(vectors)/sizeof(vectors[0]); i++) {
        const struct conversion *v=&vectors[i]; char *end=0;
        errno=0;
        long long result=strtoll(v->text,&end,v->base);
        if (result!=v->value+(deliberately_wrong && i==1) || errno!=v->error ||
            end!=v->text+v->end) return 1;
        errno=0;
        result=strtoll_l(v->text,&end,v->base,LC_C_LOCALE);
        if (result!=v->value || errno!=v->error || end!=v->text+v->end) return 2;
        errno=0;
        result=strtoll_l(v->text,0,v->base,LC_GLOBAL_LOCALE);
        if (result!=v->value || errno!=v->error) return 3;
    }
    return 0;
}

struct custom_ctype { struct xlocale_ctype ctype; _RuneLocale runes; };
static void dispose_ctype(void *raw)
{
    atomic_fetch_add(&destroyed,1);
    free(raw);
}

static void *worker(void *raw)
{
    uintptr_t index=(uintptr_t)raw;
    if (uselocale(0)!=LC_GLOBAL_LOCALE || __current_locale()!=&__global_locale)
        return (void *)1;
    locale_t local=duplocale(LC_GLOBAL_LOCALE);
    struct custom_ctype *custom=malloc(sizeof(*custom));
    if (!local || !custom) abort();
    custom->ctype=_DefaultRuneXLocale;
    custom->runes=*custom->ctype._CurrentRuneLocale;
    custom->ctype._CurrentRuneLocale=&custom->runes;
    custom->ctype.header.header.retain_count=1;
    custom->ctype.header.header.destructor=dispose_ctype;
    custom->runes.__runetype[128]=(index&1) ? _CTYPE_S : 0;
    xlocale_release(local->components[XLC_CTYPE]);
    local->components[XLC_CTYPE]=(struct xlocale_component *)custom;
    if (uselocale(local)!=LC_GLOBAL_LOCALE || __current_locale()!=local) return (void *)2;
    if (freelocale(local)) return (void *)3; /* TSD owns the remaining reference. */
    for (unsigned j=0;j<512;j++) {
        const char input[]={(char)128,'4','2',0}; char *end=0;
        errno=0; long long value=strtoll(input,&end,10);
        if ((index&1) ? (value!=42 || errno!=0 || end!=input+3)
                      : (value!=0 || errno!=EINVAL || end!=input)) return (void *)4;
        if (conversions()) return (void *)5;
    }
    /* Actual original __xlocale_release and destruct_locale run on thread exit. */
    return 0;
}

int main(int argc,char **argv)
{
    deliberately_wrong=argc>1 && strcmp(argv[1],"bad-expected")==0;
    if (__locale_key!=(pthread_key_t)-1) return 10;
    __xlocale_init(); __xlocale_init();
    if (registrations!=1 || __current_locale()!=&__global_locale || conversions()) return 11;
    pthread_t threads[4];
    for (uintptr_t i=0;i<4;i++) if(pthread_create(&threads[i],0,worker,(void *)i)) return 12;
    for (unsigned i=0;i<4;i++) {
        void *result=0;
        if(pthread_join(threads[i],&result) || result) return 13;
    }
    if(atomic_load(&destroyed)!=4 || __current_locale()!=&__global_locale ||
       uselocale(0)!=LC_GLOBAL_LOCALE || _DefaultRuneLocale.__runetype[128]!=0) return 14;
    puts("APPLE_LOCALE PASS VECTORS=23 MODES=3 THREADS=4 ITERATIONS=2048 DESTRUCTORS=4 HOST_KEY_MAPPING_ONLY");
    return 0;
}
