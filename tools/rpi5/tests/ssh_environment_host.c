/* SPDX-License-Identifier: BSD-2-Clause
 * Actual current Apple environment family, isolated from the host environment.
 * Only allocation, environment-pointer and lock entry points are test doubles.
 */
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <os/lock_private.h>

char *fixture_getenv(const char *);
char *fixture_getenv_copy_np(const char *);
int fixture_setenv(const char *,const char *,int);
int fixture_unsetenv(const char *);
int fixture_putenv(char *);
void fixture__environ_lock_fork_child(void);
void *fixture_allocenvstate(void);
int fixture_deallocenvstate(void *);
int fixture_setenvp(const char *,const char *,int,char ***,void *);
int fixture_unsetenvp(const char *,char ***,void *);
char *fixture_getenvp(const char *,char ***,void *);
extern void *fixture_env_owned;
void fixture_owned_ptr_free(void *);

static char *empty[]={NULL};
static char **environment=empty;
static pthread_mutex_t mutex=PTHREAD_MUTEX_INITIALIZER;
static _Thread_local unsigned held;
static atomic_uint locks;
static _Thread_local void *copy_allocation;
static _Thread_local unsigned copy_calls, fail_copy, mutate_copy;
static _Thread_local int hook_error;
static const char *growth="abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz";

char ***fixture_NSGetEnviron(void) { return &environment; }
void fixture_lock(os_unfair_lock_t lock, os_unfair_lock_options_t options) {
    if(!lock||options!=OS_UNFAIR_LOCK_DATA_SYNCHRONIZATION||held) abort();
    if(pthread_mutex_lock(&mutex)) abort();
    held=1;atomic_fetch_add(&locks,1);
}
void fixture_unlock(os_unfair_lock_t lock) {
    if(!lock||held!=1) abort(); held=0;
    if(pthread_mutex_unlock(&mutex)) abort();
}
void fixture_free(void *p) { if(p==copy_allocation)copy_allocation=NULL; free(p); }
void *fixture_reallocf(void *old,size_t bytes) {
    if(held)abort(); ++copy_calls;
    if(mutate_copy==1) { if(fixture_unsetenv("COPY"))hook_error=1; }
    if(mutate_copy==2) {
        size_t length=16u<<copy_calls; char text[1024];
        if(length>=sizeof(text))abort();
        memcpy(text,growth,length);text[length]=0;
        if(fixture_setenv("COPY",text,1))hook_error=1;
    }
    if(fail_copy==copy_calls) { fixture_free(old);errno=ENOMEM;return NULL; }
    void *p=realloc(old,bytes);
    if(!p) { fixture_free(old);return NULL; }
    copy_allocation=p;return p;
}

#define CHECK(x) do { if(!(x)) { fprintf(stderr,"environment line %d\n",__LINE__);return 31; } } while(0)
static void reset(void) {
    if(copy_allocation)fixture_free(copy_allocation);
    if(fixture_env_owned)fixture_owned_ptr_free(fixture_env_owned);
    fixture_env_owned=NULL;environment=empty;
    copy_calls=fail_copy=mutate_copy=0;hook_error=0;
}

static int basic(void) {
    CHECK(fixture_getenv(NULL)==NULL);
    errno=EDOM;CHECK(fixture_getenv_copy_np("absent")==NULL&&errno==EDOM);
    const char *invalid[]={"","A=B"};
    for(unsigned i=0;i<2;i++) {
        errno=0;CHECK(fixture_setenv(invalid[i],"x",1)==-1&&errno==EINVAL);
        errno=0;CHECK(fixture_unsetenv(invalid[i])==-1&&errno==EINVAL);
        errno=0;CHECK(fixture_putenv((char *)(i?"missing-equals":""))==-1&&errno==EINVAL);
    }
    CHECK(fixture_setenv("A","=initial",0)==0);
    CHECK(!strcmp(fixture_getenv("A"),"=initial"));
    CHECK(fixture_setenv("A","ignored",0)==0&&!strcmp(fixture_getenv("A"),"=initial"));
    CHECK(fixture_setenv("A","replacement longer than initial",1)==0);
    char *copy=fixture_getenv_copy_np("A");CHECK(copy&&!strcmp(copy,"replacement longer than initial"));fixture_free(copy);
    char borrowed[]="BORROWED=value";CHECK(fixture_putenv(borrowed)==0);borrowed[9]='V';
    CHECK(!strcmp(fixture_getenv("BORROWED"),"Value"));CHECK(fixture_unsetenv("BORROWED")==0);
    CHECK(fixture_getenv("BORROWED")==NULL);
    CHECK(fixture_setenv("EMPTY","",1)==0);copy=fixture_getenv_copy_np("EMPTY");CHECK(copy&&!*copy);fixture_free(copy);
    CHECK(fixture_unsetenv("A")==0&&fixture_getenv("A")==NULL);
    CHECK(fixture_unsetenv("absent")==0);
    void *state=fixture_allocenvstate();CHECK(state);char **private_env=empty;
    CHECK(fixture_setenvp("PRIVATE","yes",1,&private_env,state)==0);
    CHECK(!strcmp(fixture_getenvp("PRIVATE",&private_env,state),"yes"));
    CHECK(fixture_getenv("PRIVATE")==NULL);
    CHECK(fixture_unsetenvp("PRIVATE",&private_env,state)==0);
    CHECK(fixture_deallocenvstate(state)==0);
    errno=0;CHECK(fixture_deallocenvstate(NULL)==-1&&errno==EINVAL);
    reset();return 0;
}

static atomic_uint thread_fail;
static void *worker(void *arg) {
    uintptr_t id=(uintptr_t)arg;char name[16],value[32];snprintf(name,sizeof(name),"THREAD%u",(unsigned)id);
    for(unsigned i=0;i<128;i++) {
        snprintf(value,sizeof(value),"%u:%u",(unsigned)id,i);
        if(fixture_setenv(name,value,1))atomic_fetch_add(&thread_fail,1);
        /* All production APIs share the original lock. Each thread owns its
         * name; the callback accounting is thread-local, never target code. */
        const char *got=fixture_getenv(name);
        if(!got||strcmp(got,value))atomic_fetch_add(&thread_fail,1);
        char *copy=fixture_getenv_copy_np(name);
        if(!copy||strcmp(copy,value))atomic_fetch_add(&thread_fail,1);
        fixture_free(copy);
        if(fixture_unsetenv(name))atomic_fetch_add(&thread_fail,1);
    } return NULL;
}

int main(int argc,char **argv) {
    int original=argc==2&&!strcmp(argv[1],"original-leaks");
    if(basic())return 31;
    for(unsigned failure=1;failure<=2;failure++) {
        CHECK(fixture_setenv("COPY","a",1)==0);mutate_copy=2;fail_copy=failure;
        errno=0;CHECK(fixture_getenv_copy_np("COPY")==NULL&&errno==ENOMEM);
        CHECK(copy_allocation==NULL&&!hook_error);reset();
    }
    unsigned leaks=0;
    for(unsigned mode=1;mode<=2;mode++) {
        CHECK(fixture_setenv("COPY","a",1)==0);mutate_copy=mode;errno=EDOM;
        CHECK(fixture_getenv_copy_np("COPY")==NULL);
        CHECK(errno==(mode==1?EDOM:EAGAIN)&&copy_calls==(mode==1?1:5)&&!hook_error);
        leaks+=copy_allocation!=NULL;reset();
    }
    if((original&&leaks!=2)||(!original&&leaks))return 32;
    pthread_t threads[4];
    for(uintptr_t i=0;i<4;i++)CHECK(pthread_create(&threads[i],NULL,worker,(void *)i)==0);
    for(unsigned i=0;i<4;i++)CHECK(pthread_join(threads[i],NULL)==0);
    CHECK(atomic_load(&thread_fail)==0);reset();
    if(argc==2&&!strcmp(argv[1],"bad-expected"))return 37;
    puts(original?"APPLE_ENV ORIGINAL_LEAKS=2 ERROR_CONTRACT_PRESERVED THREADS=4 ITERATIONS=128 TEST_ONLY_ENVIRONMENT":"APPLE_ENV PASS LEAKS=0 ERROR_CONTRACT_PRESERVED THREADS=4 ITERATIONS=128 TEST_ONLY_ENVIRONMENT");
    return 0;
}
