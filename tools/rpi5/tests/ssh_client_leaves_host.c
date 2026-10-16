/* SPDX-License-Identifier: BSD-2-Clause
 * Execute original Apple option/error providers under distinct host names.
 * Host errno/stdio/strtoll are real host services, not target execution.
 */
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
extern int fixture_getopt(int, char *const[], const char *);
extern int fixture_opterr, fixture_optind, fixture_optopt, fixture_optreset;
extern char *fixture_optarg;
extern long long fixture_strtonum(const char *, long long, long long, const char **);

static void reset(void) { fixture_optind=1; fixture_optreset=1; fixture_opterr=0; }
int main(void)
{
    char *version[]={"ssh", "-V", 0}; reset();
    assert(fixture_getopt(2, version, "Vp:")=='V');
    assert(fixture_optind==2 && fixture_optarg==0);
    assert(fixture_getopt(2, version, "Vp:")==-1);
    char *cluster[]={"ssh", "-vvp22", "host", 0}; reset();
    assert(fixture_getopt(3, cluster, "vp:")=='v');
    assert(fixture_getopt(3, cluster, "vp:")=='v');
    assert(fixture_getopt(3, cluster, "vp:")=='p');
    assert(!strcmp(fixture_optarg,"22") && fixture_optind==2);
    assert(fixture_getopt(3, cluster, "vp:")==-1);
    char *separate[]={"ssh", "-p", "2222", "--", "-V", 0}; reset();
    assert(fixture_getopt(5,separate,"p:")=='p' && !strcmp(fixture_optarg,"2222"));
    assert(fixture_getopt(5,separate,"p:")==-1 && fixture_optind==4);
    char *missing[]={"ssh","-p",0}; reset();
    assert(fixture_getopt(2,missing,":p:")==':' && fixture_optarg==0);
    assert(fixture_optind==3); /* Original Darwin UNIX03 required behavior. */
    char *bad[]={"ssh","-x",0}; reset();
    assert(fixture_getopt(2,bad,"V")=='?' && fixture_optopt=='x');
    char *optional[]={"ssh","-q",0}; reset();
    assert(fixture_getopt(2,optional,"q::")=='q' && !fixture_optarg);
    char *dash[]={"ssh","-",0}; reset();
    assert(fixture_getopt(2,dash,"V")==-1 && fixture_optind==1);
    reset(); assert(fixture_getopt(2,version,"V")=='V');

    struct row { const char *s; long long lo,hi,value; int error; const char *text; } rows[]={
        {"22",1,65535,22,0,0}, {"0",0,0,0,0,0},
        {"9223372036854775807",LLONG_MIN,LLONG_MAX,LLONG_MAX,0,0},
        {"-9223372036854775808",LLONG_MIN,LLONG_MAX,LLONG_MIN,0,0},
        {"9223372036854775808",LLONG_MIN,LLONG_MAX,0,ERANGE,"too large"},
        {"-9223372036854775809",LLONG_MIN,LLONG_MAX,0,ERANGE,"too small"},
        {"0",1,65535,0,ERANGE,"too small"}, {"65536",1,65535,0,ERANGE,"too large"},
        {"",0,100,0,EINVAL,"invalid"}, {"12x",0,100,0,EINVAL,"invalid"},
        {"10 ",0,100,0,EINVAL,"invalid"}, {"1",2,1,0,EINVAL,"invalid"},
        {" +10",0,100,10,0,0}, {"-0",0,100,0,0,0},
    };
    for(unsigned i=0;i<sizeof(rows)/sizeof(*rows);i++) {
        const char *why=(void *)1; errno=E2BIG;
        long long n=fixture_strtonum(rows[i].s,rows[i].lo,rows[i].hi,&why);
        assert(n==rows[i].value && errno==(rows[i].error?rows[i].error:E2BIG));
        assert(rows[i].text ? why && !strcmp(why,rows[i].text) : why==0);
    }
    errno=E2BIG; assert(fixture_strtonum("12",0,20,0)==12 && errno==E2BIG);
    puts("APPLE_SSH_CLIENT_LEAVES PASS GETOPT_GROUPS=8 STRTONUM_CASES=15 HOST_SERVICES_ONLY");
    return 0;
}
