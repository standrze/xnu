/* SPDX-License-Identifier: BSD-2-Clause */
/* Synthetic syscall adapter. It never opens or reads any host disk. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/disk.h>
#include "../user/runtime.h"
#include "../user/sdread.h"
_Static_assert(SDREAD_BLOCK_SIZE==DKIOCGETBLOCKSIZE,"block-size ABI");
_Static_assert(SDREAD_BLOCK_COUNT==DKIOCGETBLOCKCOUNT,"block-count ABI");
_Static_assert(SDREAD_WRITABLE==DKIOCISWRITABLE,"write-protection ABI");
static unsigned opens, closes, reads;
static const char *mode;
static int is(const char *value) { return mode && !strcmp(mode,value); }
long rt_open(const char *path, int flags)
{ assert(!strncmp(path,"/dev/rdisk",10) && flags==RT_RDONLY); opens++; return is("open") ? -6 : 77; }
long rt_close(int fd) { assert(fd==77); closes++; return is("close") ? -5 : 0; }
long rt_call(long n, long fd, long command, long data, long offset, long e, long f)
{
    assert(fd==77 && !e && !f);
    if (n==54) {
        assert(!offset);
        if (is("ioctl")) return -5;
        if ((unsigned long)command==SDREAD_BLOCK_SIZE) *(uint32_t *)data=is("size") ? 4096 : 512;
        else if ((unsigned long)command==SDREAD_BLOCK_COUNT) *(uint64_t *)data=UINT64_C(250347520);
        else { assert((unsigned long)command==SDREAD_WRITABLE); *(uint32_t *)data=is("writable"); }
        return 0;
    }
    assert(n==153 && data==512 && offset>=0 && !(offset%512));
    reads++;
    if (is("eintr")) return -4;
    if (is("error")) return -5;
    for (unsigned i=0;i<512;i++) ((unsigned char *)command)[i]=(unsigned char)(offset/512+i);
    return is("short") ? 511 : 512;
}
int rt_write_all(int fd, const void *p, size_t n) { return fwrite(p,1,n,fd==1 ? stdout : stderr)==n ? 0 : -1; }
void rt_put(int fd, const char *text) { (void)rt_write_all(fd,text,strlen(text)); }
void rt_number(int fd, unsigned long value) { fprintf(fd==1 ? stdout : stderr,"%lu",value); }
void rt_error(const char *operation, long result) { fprintf(stderr,"%s: errno %ld\n",operation,-result); }
int main(int argc, char **argv)
{
    mode=getenv("SDREAD_FIXTURE");
    int rc=sdread_main(argc,argv);
    fprintf(stderr,"FIXTURE OPENS=%u CLOSES=%u READS=%u\n",opens,closes,reads);
    return rc;
}
