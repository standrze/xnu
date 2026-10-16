/* SPDX-License-Identifier: BSD-2-Clause
 * Public original lookup and real file/cache/TSD semantics. Only effective uid
 * is a test-controlled boundary; all fixture file I/O/stat and synchronization
 * are genuine host services. No host account database or DNS is consulted.
 */
#include <assert.h>
#include <arpa/inet.h>
#include <errno.h>
#include <grp.h>
#include <netdb.h>
#include <pthread.h>
#include <pwd.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include "si_module.h"

static _Thread_local uid_t effective_uid;
uid_t rpi5_fixture_geteuid(void) { return effective_uid; }

static void account_checks(unsigned index)
{
    effective_uid=(index&1) ? 501 : 0;
    for (unsigned i=0;i!=128;++i) {
        struct passwd *p=getpwnam("root"); assert(p && p->pw_uid==0 && p->pw_gid==0);
        assert(!strcmp(p->pw_passwd,"*") && !strcmp(p->pw_dir,"/var/root") && !strcmp(p->pw_shell,"/bin/zsh"));
        p=getpwuid(501); assert(p && !strcmp(p->pw_name,"sandrzej") && !strcmp(p->pw_dir,"/Users/sandrzej"));
        assert(!strcmp(p->pw_shell,"/bin/zsh") && !strcmp(p->pw_passwd,"*"));
        struct group *g=getgrnam("wheel"); assert(g && g->gr_gid==0 && !strcmp(g->gr_mem[0],"root"));
        g=getgrgid(20); assert(g && !strcmp(g->gr_name,"staff") && !strcmp(g->gr_mem[0],"sandrzej"));
        assert(getpwnam("unavailable")==NULL && getpwuid(65000)==NULL);
        assert(getgrnam("unavailable")==NULL && getgrgid(65000)==NULL);
    }
}
static void *worker(void *arg) { account_checks((unsigned)(uintptr_t)arg); return arg; }

int main(void)
{
    assert(setenv("SYSINFO_CONF_ENABLE","1",1)==0);
    errno=0; assert(!si_module_with_name("mdns") && errno==ENOTSUP);
    errno=0; assert(!si_module_with_name("ds") && errno==ENOTSUP);
    errno=0; assert(!si_module_with_name("darwin_directory") && errno==ENOTSUP);
    pthread_t threads[4];
    for(uintptr_t i=0;i!=4;++i)assert(!pthread_create(&threads[i],NULL,worker,(void *)i));
    for(uintptr_t i=0;i!=4;++i){void *result=NULL;assert(!pthread_join(threads[i],&result) && result==(void *)i);}
    effective_uid=0;
    int groups[8],count=8;
    assert(!getgrouplist("sandrzej",20,groups,&count) && count>=2);
    int found20=0,found80=0;for(int i=0;i<count;++i){found20|=groups[i]==20;found80|=groups[i]==80;}assert(found20&&found80);
    struct servent *serv=getservbyname("ssh","tcp");assert(serv && ntohs(serv->s_port)==22);
    assert(!getservbyname("not-installed","tcp"));
    struct addrinfo hints={.ai_family=AF_INET,.ai_socktype=SOCK_STREAM,.ai_flags=AI_NUMERICHOST|AI_NUMERICSERV},*a=NULL;
    assert(!getaddrinfo("192.0.2.23","22",&hints,&a) && a && !a->ai_next);
    char node[NI_MAXHOST],service[NI_MAXSERV];
    assert(!getnameinfo(a->ai_addr,a->ai_addrlen,node,sizeof(node),service,sizeof(service),NI_NUMERICHOST|NI_NUMERICSERV));
    assert(!strcmp(node,"192.0.2.23") && !strcmp(service,"22"));freeaddrinfo(a);
    hints.ai_flags=0;a=NULL;assert(!getaddrinfo("pi-fixture.example","ssh",&hints,&a) && a);freeaddrinfo(a);
    a=NULL;assert(getaddrinfo("not-installed.example","22",&hints,&a)!=0 && a==NULL);
    struct passwd *pw=getpwnam("sandrzej");assert(pw);
    const char *master=FIXTURE_DIRECTORY "/master.passwd",*backup=FIXTURE_DIRECTORY "/master.passwd.saved";
    assert(!rename(master,backup));assert(!getpwnam("sandrzej"));assert(!rename(backup,master));
    pw=getpwnam("sandrzej");assert(pw && pw->pw_uid==501);
    puts("PI_LIBINFO_FILES PASS THREADS=4 ACCOUNT_ITERATIONS=512 UID_MODES=2 GROUPLIST=1 SERVICE=1 NUMERIC=1 HOST_FILE=1 MISSING_FILE=1 UNAVAILABLE_MODULES=3 NO_DNS");
    return 0;
}
