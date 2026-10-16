/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ils.h"

int main(void)
{
    char prefix[65], *strings[]={"one","second",NULL};
    uint32_t a=0x11223344,b=0x55667788;char *four[]={(char *)&a,(char *)&b,NULL};
    uint64_t c=UINT64_C(0x1122334455667788),d=UINT64_C(0x7766554433221100);char *eight[]={(char *)&c,(char *)&d,NULL};
    unsigned char e[16]={1,2,3},f[16]={4,5,6};char *sixteen[]={(char *)e,(char *)f,NULL};
    unsigned cases=0;
    for(unsigned n=0;n!=64;++n) {
        memset(prefix,'p',n);prefix[n]=0;
        struct string_list {char *prefix;char **values;};
        const char *formats[]={"s*","sa","sb","sc"};
        char **inputs[]={strings,four,eight,sixteen};
        const size_t lengths[]={0,4,8,16};
        for(unsigned k=0;k!=4;++k) {
            struct string_list *v=LI_ils_create((char *)formats[k],prefix,inputs[k]);assert(v);
            assert(!strcmp(v->prefix,prefix) && ((uintptr_t)v->values&7)==0);
            assert(v->values[0]&&v->values[1]&&!v->values[2]);
            for(unsigned i=0;i!=2;++i) {
                if(k) { assert(((uintptr_t)v->values[i] & (k==1 ? 3:7))==0);assert(!memcmp(v->values[i],inputs[k][i],lengths[k])); }
                else assert(!strcmp(v->values[i],inputs[k][i]));
            }
            free(v);++cases;
        }
        struct buffer {char *prefix;uint32_t count;uint32_t *value;};
        struct buffer *v=LI_ils_create("s@",prefix,(uint32_t)sizeof(a),(char *)&a);assert(v);
        assert(((uintptr_t)v->value&7)==0 && v->count==sizeof(a) && *v->value==a);free(v);++cases;
    }
    printf("LIBINFO_PAYLOAD_ALIGNMENT PASS CASES=%u PREFIX_LENGTHS=64 FORMATS=5\n",cases);
    return 0;
}
