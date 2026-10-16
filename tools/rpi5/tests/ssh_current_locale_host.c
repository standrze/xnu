/* SPDX-License-Identifier: BSD-2-Clause
 * Actual current locale group. Host-only services remain explicit.
 */
#define main original_locale_contract_main
#include "ssh_locale_host.c"
#undef main
#include <langinfo.h>
#include <wchar.h>

static int current_api_contract(void)
{
    int (* volatile classifiers[])(int) = {
        isalnum,isalpha,isblank,iscntrl,isdigit,isgraph,
        islower,isprint,ispunct,isspace,isupper,isxdigit
    };
    const unsigned masks[] = {
        _CTYPE_A|_CTYPE_D,_CTYPE_A,_CTYPE_B,_CTYPE_C,_CTYPE_D,_CTYPE_G,
        _CTYPE_L,_CTYPE_R,_CTYPE_P,_CTYPE_S,_CTYPE_U,_CTYPE_X
    };
    for (int c=-1;c<256;c++) {
        unsigned flags=c<0?0:_DefaultRuneLocale.__runetype[c];
        for (unsigned i=0;i<12;i++) {
            if (!!classifiers[i](c) != !!(flags&masks[i])) return 20;
        }
        int upper=c<0?c:(int)_DefaultRuneLocale.__mapupper[c];
        int lower=c<0?c:(int)_DefaultRuneLocale.__maplower[c];
        int (* volatile up)(int)=toupper,(* volatile down)(int)=tolower;
        if(up(c)!=upper || down(c)!=lower)return 21;
    }
    wchar_t wc=0;
    if(mbtowc(NULL,NULL,0)!=0 || mbtowc(&wc,"",1)!=0 || wc!=0 ||
       mbtowc(&wc,"A",1)!=1 || wc!='A' || mbtowc(&wc,"A",0)!=-1)return 22;
    const char high[]={ (char)128,0 };
    if(mbtowc(&wc,high,1)!=1 || wc!=128)return 23;
    if(wcwidth(0)!=0 || wcwidth(L' ')!=1 || wcwidth(L'\n')!=-1 || wcwidth(128)!=-1)
        return 24;
    if(strcmp(nl_langinfo(CODESET),"US-ASCII") || strcmp(nl_langinfo(RADIXCHAR),".") ||
       strcmp(nl_langinfo(THOUSEP),""))return 25;
    if(strcmp(setlocale(LC_ALL,NULL),"C") || strcmp(setlocale(LC_ALL,"C"),"C"))return 26;
    errno=0;
    if(setlocale(-1,"C") || errno!=EINVAL)return 27;
    errno=0;
    if(setlocale(LC_ALL,"invalid/") || errno!=EINVAL)return 28;
    if(strcmp(setlocale(LC_CTYPE,"POSIX"),"POSIX") ||
       strcmp(setlocale(LC_CTYPE,"C"),"C"))return 29;
    struct lconv *numeric=localeconv();
    if(!numeric || strcmp(numeric->decimal_point,".") || strcmp(numeric->thousands_sep,""))
        return 30;
    return 0;
}

int main(int argc,char **argv)
{
    int rc=original_locale_contract_main(argc,argv);
    if(rc)return rc;
    if((rc=current_api_contract()))return rc;
    if(argc>1 && strcmp(argv[1],"bad-api")==0)return 31;
    puts("APPLE_CURRENT_LOCALE PASS CTYPES=3084 CASEMAPS=514 MBTOWC=6 WCWIDTH=4 C_LOCALE_APIS=10 HOST_SERVICES_ONLY");
    return 0;
}
