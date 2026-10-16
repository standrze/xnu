/* SPDX-License-Identifier: BSD-2-Clause */
/* Physical trial utility through real /dev/rdiskN and IOStorageFamily.
 * Opens read-only, checks geometry/write protection, performs one bounded
 * pread, emits exact bytes for independent host SHA-256 comparison. */
#include "runtime.h"
#include "sdread.h"

static int number(const char *text, uint64_t *out)
{
    uint64_t value=0;
    if (!*text) return -1;
    for (; *text; text++) {
        if (*text<'0' || *text>'9' || value>(UINT32_MAX-(unsigned)(*text-'0'))/10)
            return -1;
        value=value*10+(unsigned)(*text-'0');
    }
    *out=value;
    return 0;
}
int sdread_main(int argc, char **argv)
{
    uint64_t lba, disk;
    static const char prefix[]="/dev/rdisk";
    if (argc!=3) goto usage;
    for (unsigned i=0;i<sizeof prefix-1;i++) if (argv[1][i]!=prefix[i]) goto usage;
    if (number(argv[1]+sizeof prefix-1,&disk) || disk>31 || number(argv[2],&lba)) goto usage;
    long fd=rt_open(argv[1],RT_RDONLY);
    if (fd<0) { rt_error("sdread open",fd); return 1; }
    uint32_t block_size=0, writable=1;
    uint64_t sectors=0;
    long rc=rt_call(54,fd,SDREAD_BLOCK_SIZE,(long)&block_size,0,0,0);
    if (!rc) rc=rt_call(54,fd,SDREAD_BLOCK_COUNT,(long)&sectors,0,0,0);
    if (!rc) rc=rt_call(54,fd,SDREAD_WRITABLE,(long)&writable,0,0,0);
    if (rc || block_size!=512 || !sectors || sectors>(UINT64_C(1)<<32) || writable || lba>=sectors) {
        rt_error("sdread geometry/read-only guard",rc ? rc : -22); rt_close((int)fd); return 1;
    }
    unsigned char sector[512];
    unsigned attempts=0;
    do { rc=rt_call(153,fd,(long)sector,sizeof sector,(long)(lba*512),0,0); }
    while (rc==-4 && ++attempts<8);
    long closed=rt_close((int)fd);
    if (rc!=sizeof sector || closed) {
        rt_error("sdread pread/close",rc<0 ? rc : closed ? closed : -5); return 1;
    }
    rt_put(1,"RPI5XNU:SDREAD:SECTOR LBA="); rt_number(1,(unsigned long)lba);
    rt_put(1," SECTORS="); rt_number(1,(unsigned long)sectors); rt_put(1," BLOCK=512 READONLY=1\n");
    /* Short lines reduce the chance that SMP diagnostic UART output tears a
     * complete sector. The receiver still rejects missing/duplicate rows. */
    static const char digits[]="0123456789abcdef";
    for (unsigned row=0;row<16;row++) {
        char line[65];
        for (unsigned i=0;i<32;i++) {
            unsigned char value=sector[row*32+i];
            line[i*2]=digits[value>>4]; line[i*2+1]=digits[value&15];
        }
        line[64]='\n';
        rt_put(1,"RPI5XNU:SDREAD:DATA ROW="); rt_number(1,row); rt_put(1," HEX=");
        if (rt_write_all(1,line,sizeof line)) return 1;
    }
    rt_put(1,"RPI5XNU:SDREAD:END\n");
    return 0;
usage:
    rt_put(2,"usage: sdread /dev/rdiskN LBA (whole disk 0..31, decimal LBA <= 2^32-1)\n");
    return 2;
}
