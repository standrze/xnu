/* SPDX-License-Identifier: BSD-2-Clause */
#include "container.h"
#include "hash.h"
static uint32_t le32(const uint8_t *p)
{
    return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
static uint64_t le64(const uint8_t *p) { return le32(p)|(uint64_t)le32(p+4)<<32; }
static int matches(const uint8_t *a, const uint8_t *b, size_t n)
{
    unsigned difference=0;
    for (size_t i=0;i<n;i++) difference|=a[i]^b[i];
    return !difference;
}
int rpi5_container_parse(const void *buffer, size_t size, struct rpi5_container *out)
{
    static const uint8_t magic[8]={'R','P','I','5','X','N','U',0};
    if (!buffer || !out || size<128 || size>(512u<<20)) return -1;
    const uint8_t *b=buffer;
    uint32_t count=le32(b+24);
    if (!matches(b,magic,8) || le32(b+8)!=1 || le32(b+12)!=64 ||
        le64(b+16)!=size || !count || count>2 || le32(b+28)) return -1;
    size_t table=64*(size_t)count;
    if (table>size-64) return -1;
    uint8_t digest[32];
    if (rpi5_sha256(b+64,table,digest) || !matches(digest,b+32,32)) return -1;
    struct rpi5_container result={0};
    uint64_t cursor=64+table;
    for (uint32_t i=0;i<count;i++) {
        const uint8_t *entry=b+64+(size_t)i*64;
        uint64_t offset=le64(entry+8), length=le64(entry+16);
        uint64_t aligned=(cursor+63)&~63ull;
        if (le32(entry)!=i+1 || le32(entry+4) || le64(entry+56) || offset!=aligned ||
            !length || length>(256u<<20) || offset>size || length>size-offset) return -1;
        for (uint64_t j=cursor;j<offset;j++) if (b[j]) return -1;
        if (rpi5_sha256(b+offset,(size_t)length,digest) || !matches(digest,entry+24,32)) return -1;
        struct rpi5_payload payload={offset,length};
        if (i==0) result.kernel=payload; else result.init=payload;
        cursor=offset+length;
    }
    if (cursor!=size) return -1;
    result.count=count;
    *out=result;
    return 0;
}
