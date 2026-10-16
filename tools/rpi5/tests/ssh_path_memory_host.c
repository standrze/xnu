/* Original Apple pathname/memory semantics, no target or filesystem activity. */
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/param.h>
extern void *fixture_memmem(const void *,size_t,const void *,size_t);
extern char *fixture_dirname(char *);
extern char *fixture_dirname_r(const char *,char *);
static int fail_alloc;
void *fixture_malloc(size_t n) { if(fail_alloc) { errno=ENOMEM;return NULL; }return malloc(n); }
int main(int argc,char **argv) {
    if(argc==2&&strcmp(argv[1],"alloc-fail")==0) {
        fail_alloc=1;errno=0;assert(!fixture_dirname("a/b")&&errno==ENOMEM);
        puts("APPLE_SSH_PATH_MEMORY ALLOC_FAILURE PASS");return 0;
    }
    unsigned char hay[]={0,1,2,0,1,2,3,0};unsigned char needle[]={0,1,2};
    assert(fixture_memmem(hay,sizeof(hay),needle,sizeof(needle))==hay);
    assert(fixture_memmem(hay+1,sizeof(hay)-1,needle,sizeof(needle))==hay+3);
    assert(fixture_memmem(hay,3,needle,3)==hay);
    assert(!fixture_memmem(hay,2,needle,3));
    assert(fixture_memmem(hay,8,hay+6,1)==hay+6);
    assert(fixture_memmem(hay,8,hay+7,1)==hay);
    assert(!fixture_memmem(hay,0,needle,3));
    assert(!fixture_memmem(hay,8,needle,0)); /* Original Apple empty-needle policy. */
    unsigned char absent=9;assert(!fixture_memmem(hay,8,&absent,1));
    assert(!fixture_memmem(hay,6,hay+5,2));
    assert(fixture_memmem(hay,8,hay+5,3)==hay+5);
    assert(!fixture_memmem(NULL,0,NULL,0));
    const char *paths[]={NULL,"","a","a/b","a/b///","/","///","/a","/a/b","a//b","./a","../a"};
    const char *answers[]={".",".",".","a","a","/","/","/","/a","a",".",".."};
    char buffer[MAXPATHLEN];
    for(unsigned i=0;i<12;i++) {
        assert(fixture_dirname_r(paths[i],buffer)==buffer&&strcmp(buffer,answers[i])==0);
        assert(strcmp(fixture_dirname((char *)paths[i]),answers[i])==0);
    }
    char longpath[MAXPATHLEN+8];memset(longpath,'a',sizeof(longpath));
    longpath[MAXPATHLEN]='/';longpath[MAXPATHLEN+1]='x';longpath[MAXPATHLEN+2]=0;
    errno=0;assert(!fixture_dirname_r(longpath,buffer)&&errno==ENAMETOOLONG);
    longpath[MAXPATHLEN-1]='/';longpath[MAXPATHLEN]='x';longpath[MAXPATHLEN+1]=0;
    assert(fixture_dirname_r(longpath,buffer)==buffer&&strlen(buffer)==MAXPATHLEN-1);
    puts("APPLE_SSH_PATH_MEMORY PASS MEMMEM=12 DIRNAME=26 ORIGINAL_APPLE_POLICY");
    return 0;
}
