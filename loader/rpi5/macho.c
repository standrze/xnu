/* SPDX-License-Identifier: BSD-2-Clause */
#include "macho.h"
static uint32_t le32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
}
static uint64_t le64(const uint8_t *p) { return le32(p) | (uint64_t)le32(p+4)<<32; }
int rpi5_macho_verify_materialized(const void *image, size_t size,
    const volatile void *destination, size_t destination_size, uint64_t header_pa)
{
    uintptr_t src=(uintptr_t)image, dst=(uintptr_t)destination;
    if (!image || !destination || !size || !destination_size ||
        size>UINTPTR_MAX-src || destination_size>UINTPTR_MAX-dst ||
        (src<dst+destination_size && dst<src+size) ||
        header_pa>=(1ull<<40) || destination_size>(1ull<<40)-header_pa) return -1;
    struct rpi5_macho_placement placement;
    struct rpi5_macho_segments segments;
    if (rpi5_macho_placement(image,size,header_pa,header_pa,
            header_pa+destination_size,&placement) ||
        rpi5_macho_segments(image,size,&segments)) return -1;
    const volatile uint8_t *target=destination;
    const uint8_t *source=image;
    size_t cursor=0, used=(size_t)(placement.end-header_pa);
    /* Command order need not be address order. Select the next nonempty
     * segment; validated segments cannot overlap. Each byte is read once. */
    while (cursor<used) {
        size_t next=used;
        const struct rpi5_macho_segment *chosen=0;
        for (uint32_t i=0;i<segments.count;i++) {
            size_t offset=(size_t)(placement.destination[i]-header_pa);
            if (segments.segment[i].vmsize && offset>=cursor && offset<next) {
                next=offset; chosen=&segments.segment[i];
            }
        }
        while (cursor<next) if (target[cursor++]!=0) return -1;
        if (!chosen) break;
        for (size_t j=0;j<chosen->filesize;j++)
            if (target[cursor+j]!=source[chosen->fileoff+j]) return -1;
        cursor+=(size_t)chosen->filesize;
        size_t end=next+(size_t)chosen->vmsize;
        while (cursor<end) if (target[cursor++]!=0) return -1;
    }
    return 0;
}
int rpi5_macho_materialize(const void *image, size_t size, void *destination,
    size_t destination_size, uint64_t header_pa, uint32_t *scratch,
    size_t capacity, struct rpi5_macho_placement *out)
{
    if (!image || !size || !destination || !destination_size || !scratch ||
        !capacity || capacity>SIZE_MAX/sizeof(*scratch) || !out ||
        header_pa>=(1ull<<40) || destination_size>(1ull<<40)-header_pa) return -1;
    /* Check all aliases before even the relocation hash scratch is cleared. */
    uintptr_t starts[4]={(uintptr_t)image,(uintptr_t)destination,(uintptr_t)scratch,(uintptr_t)out};
    size_t sizes[4]={size,destination_size,capacity*sizeof(*scratch),sizeof(*out)};
    for (size_t i=0;i<4;i++) {
        if (sizes[i]>UINTPTR_MAX-starts[i]) return -1;
        for (size_t j=0;j<i;j++)
            if (starts[i]<starts[j]+sizes[j] && starts[j]<starts[i]+sizes[i]) return -1;
    }
    struct rpi5_macho_placement placement;
    struct rpi5_macho_segments segments;
    uint32_t count;
    if (rpi5_macho_relocations(image,size,scratch,capacity,&count) ||
        rpi5_macho_placement(image,size,header_pa,header_pa,header_pa+destination_size,&placement) ||
        rpi5_macho_segments(image,size,&segments)) return -1;
    /* The caller-proven arena is not published until copying completes. Clear
     * holes and rounded tail too, so uninitialized host/firmware bytes cannot
     * leak through the kernel's reserved physical envelope. */
    uint8_t *target=destination;
    const uint8_t *source=image;
    size_t used=(size_t)(placement.end-header_pa);
    for (size_t i=0;i<used;i++) target[i]=0;
    for (uint32_t i=0;i<segments.count;i++) {
        const struct rpi5_macho_segment *s=&segments.segment[i];
        if (!s->filesize) continue;
        size_t offset=(size_t)(placement.destination[i]-header_pa);
        for (size_t j=0;j<s->filesize;j++) target[offset+j]=source[s->fileoff+j];
    }
    *out=placement;
    return 0;
}
int rpi5_macho_symbols(const void *image, size_t size)
{
    struct rpi5_macho_commands commands;
    if (rpi5_macho_commands(image,size,&commands)) return -1;
    const uint8_t *p=image, *sym=0, *dyn=0;
    size_t pos=32;
    for (uint32_t i=0;i<commands.count;i++) {
        uint32_t cmd=le32(p+pos);
        if (cmd==2) sym=p+pos+8;
        if (cmd==0xb) dyn=p+pos+8;
        pos+=le32(p+pos+4);
    }
    if (!sym || !dyn) return -1;
    uint32_t off=le32(sym), count=le32(sym+4), strings=le32(sym+8), bytes=le32(sym+12);
    if (off>size || (uint64_t)count*16>size-off || strings>size || bytes>size-strings) return -1;
    for (size_t i=0;i<6;i+=2) {
        uint32_t begin=le32(dyn+i*4), number=le32(dyn+(i+1)*4);
        if (begin>count || number>count-begin) return -1;
    }
    if (le32(dyn+20)) return -1;
    for (size_t i=6;i<14;i++) if (le32(dyn+i*4)) return -1;
    if (le32(dyn+60)) return -1; /* External relocations need provider resolution. */
    uint32_t reloc=le32(dyn+64), nr=le32(dyn+68);
    if (reloc>size || (uint64_t)nr*8>size-reloc) return -1;
    /* A string starting at/before the last NUL is bounded. Scan once rather
     * than rescanning long shared suffixes for every symbol. */
    size_t last_nul=0;
    int has_nul=0;
    for (size_t i=0;i<bytes;i++)
        if (!p[strings+i]) { last_nul=i; has_nul=1; }
    for (uint32_t i=0;i<count;i++) {
        const uint8_t *symbol=p+off+(size_t)i*16;
        uint32_t string=le32(symbol);
        uint8_t type=symbol[4];
        if (!has_nul || string>last_nul || (!(type&0xe0) && !(type&0x0e))) return -1;
    }
    return 0;
}
static int same_name(const uint8_t *a, const uint8_t *b)
{
    for (size_t i=0;i<16;i++) {
        if (a[i]!=b[i]) return 0;
        if (!a[i]) return 1;
    }
    return 1;
}

int rpi5_macho_placement(const void *image, size_t size, uint64_t header_pa,
    uint64_t free_start, uint64_t free_end, struct rpi5_macho_placement *out)
{
    const uint64_t link=0xfffffe0007004000ull, page=0x4000, block=0x2000000;
    struct rpi5_macho_segments segments;
    if (!out || rpi5_macho_segments(image,size,&segments) ||
        (le32((const uint8_t *)image+24)&0x80000000u) ||
        free_start>=free_end || free_end>(1ull<<40) || header_pa<free_start || header_pa>=free_end ||
        (header_pa&(page-1)) || (header_pa&(block-1))!=(link&(block-1))) return -1;
    struct rpi5_macho_placement result={0};
    result.header=header_pa;
    result.end=header_pa;
    result.count=segments.count;
    int header_backed=0;
    for (uint32_t i=0;i<segments.count;i++) {
        const struct rpi5_macho_segment *s=&segments.segment[i];
        if (!s->vmsize) continue; /* Empty metadata segments require no copy. */
        if (s->vmaddr<link || (s->vmaddr&(page-1))) return -1;
        uint64_t delta=s->vmaddr-link;
        if (delta>free_end-header_pa || s->vmsize>free_end-header_pa-delta) return -1;
        uint64_t dest=header_pa+delta, end=dest+s->vmsize;
        result.destination[i]=dest;
        if (end>result.end) result.end=end;
        if (s->vmaddr==link && !s->fileoff && s->filesize>=32ull+le32((const uint8_t *)image+20)) header_backed=1;
    }
    if (!header_backed || segments.entry<link || segments.entry-link>=free_end-header_pa) return -1;
    result.entry=header_pa+(segments.entry-link);
    if (result.end>UINT64_MAX-(page-1)) return -1;
    result.end=(result.end+page-1)&~(page-1);
    if (result.end>free_end) return -1;
    *out=result;
    return 0;
}

int rpi5_macho_relocations(const void *image, size_t size, uint32_t *scratch,
    size_t capacity, uint32_t *out_count)
{
    struct rpi5_macho_segments segments;
    struct rpi5_macho_commands commands;
    if (!out_count || rpi5_macho_symbols(image,size) ||
        rpi5_macho_segments(image,size,&segments) || rpi5_macho_commands(image,size,&commands)) return -1;
    const uint8_t *p=image;
    size_t pos=32;
    uint32_t offset=0, count=0;
    for (uint32_t i=0;i<commands.count;i++) {
        if (le32(p+pos)==0xb) { offset=le32(p+pos+72); count=le32(p+pos+76); }
        pos+=le32(p+pos+4);
    }
    if (count) {
        if (!scratch || !capacity || (capacity&(capacity-1)) ||
            capacity>SIZE_MAX/sizeof(*scratch) || count>capacity/2) return -1;
        uintptr_t begin=(uintptr_t)image, work=(uintptr_t)scratch;
        size_t bytes=capacity*sizeof(*scratch);
        if ((work&3) || size>UINTPTR_MAX-begin || bytes>UINTPTR_MAX-work ||
            (begin<work+bytes && work<begin+size)) return -1;
        for (size_t i=0;i<capacity;i++) scratch[i]=UINT32_MAX;
    }
    for (uint32_t i=0;i<count;i++) {
        uint32_t address=le32(p+offset+(size_t)i*8), bits=le32(p+offset+(size_t)i*8+4);
        if ((address&0x80000000u) || bits>>24!=6 || address>UINT64_MAX-segments.segment[0].vmaddr) return -1;
        size_t slot=((uint64_t)address*2654435761u)&(capacity-1);
        while (scratch[slot]!=UINT32_MAX) {
            if (scratch[slot]==address) return -1;
            slot=(slot+1)&(capacity-1);
        }
        scratch[slot]=address;
        uint64_t site=segments.segment[0].vmaddr+address;
        int backed=0;
        for (uint32_t j=0;j<segments.count;j++) {
            const struct rpi5_macho_segment *s=&segments.segment[j];
            if (site>=s->vmaddr && site-s->vmaddr<=s->filesize &&
                s->filesize-(site-s->vmaddr)>=8) backed++;
        }
        if (backed!=1) return -1;
    }
    *out_count=count;
    return 0;
}

int rpi5_macho_segments(const void *image, size_t size, struct rpi5_macho_segments *out)
{
    struct rpi5_macho_commands commands;
    if (!out || rpi5_macho_commands(image,size,&commands)) return -1;
    const uint8_t *p=image;
    struct rpi5_macho_segments result={0};
    size_t pos=32;
    int has_entry=0;
    for (uint32_t c=0;c<commands.count;c++) {
        uint32_t cmd=le32(p+pos), length=le32(p+pos+4);
        if (cmd==5) { result.entry=le64(p+pos+272); has_entry=1; }
        if (cmd==0x19) {
            if (result.count==32) return -1;
            struct rpi5_macho_segment s={
                le64(p+pos+24),le64(p+pos+32),le64(p+pos+40),le64(p+pos+48),
                le32(p+pos+56),le32(p+pos+60),{0}};
            for (size_t n=0;n<16;n++) s.name[n]=p[pos+8+n];
            if (s.vmsize>UINT64_MAX-s.vmaddr || s.filesize>s.vmsize ||
                s.fileoff>size || s.filesize>size-s.fileoff ||
                (s.maxprot&~7u) || (s.initprot&~s.maxprot)) return -1;
            for (uint32_t j=0;j<result.count;j++) {
                const struct rpi5_macho_segment *t=&result.segment[j];
                if (same_name(s.name,t->name) ||
                    (s.vmsize && t->vmsize && s.vmaddr<t->vmaddr+t->vmsize && t->vmaddr<s.vmaddr+s.vmsize) ||
                    (s.filesize && t->filesize && s.fileoff<t->fileoff+t->filesize && t->fileoff<s.fileoff+s.filesize)) return -1;
            }
            uint32_t ns=le32(p+pos+64);
            for (uint32_t j=0;j<ns;j++) {
                const uint8_t *section=p+pos+72+(size_t)j*80;
                uint64_t addr=le64(section+32), bytes=le64(section+40);
                static const uint8_t threaded[16]="__thread_starts";
                if (bytes && same_name(section,threaded)) return -1;
                uint32_t off=le32(section+48), align=le32(section+52);
                uint32_t reloc=le32(section+56), nr=le32(section+60), kind=le32(section+64)&255;
                if (!same_name(section+16,s.name) || addr<s.vmaddr || addr>s.vmaddr+s.vmsize ||
                    bytes>s.vmaddr+s.vmsize-addr || align>=64 || (addr&((1ull<<align)-1)) ||
                    reloc>size || (uint64_t)nr*8>size-reloc) return -1;
                if (kind!=1 && kind!=12 && kind!=18 &&
                    (off<s.fileoff || off>s.fileoff+s.filesize || bytes>s.fileoff+s.filesize-off)) return -1;
            }
            result.segment[result.count++]=s;
        }
        pos+=length;
    }
    if (!result.count || !has_entry || (result.entry&3)) return -1;
    int executable=0;
    for (uint32_t i=0;i<result.count;i++) {
        const struct rpi5_macho_segment *s=&result.segment[i];
        if ((s->initprot&4) && result.entry>=s->vmaddr &&
            result.entry-s->vmaddr<=s->filesize &&
            s->filesize-(result.entry-s->vmaddr)>=4)
            executable=1;
    }
    if (!executable) return -1;
    *out=result;
    return 0;
}
int rpi5_macho_commands(const void *image, size_t size, struct rpi5_macho_commands *out)
{
    if (!image || !out || size < 32) return -1;
    const uint8_t *p = image;
    if (le32(p)!=0xfeedfacf || le32(p+4)!=0x100000c || le32(p+8)!=0 ||
        le32(p+12)!=2 || le32(p+28)!=0) return -1;
    uint32_t count=le32(p+16), bytes=le32(p+20), seen=0;
    if (!count || bytes>size-32 || count>bytes/8) return -1;
    size_t pos=32, end=32+(size_t)bytes;
    for (uint32_t i=0;i<count;i++) {
        if (end-pos<8) return -1;
        uint32_t command=le32(p+pos), length=le32(p+pos+4), bit=0;
        if (length<8 || (length&7) || length>end-pos) return -1;
        switch (command) {
        case 0x19:
            if (length<72 || le32(p+pos+64)!=(length-72)/80 || (length-72)%80) return -1;
            break;
        case 2: bit=1; if (length!=24) return -1; break;
        case 0xb: bit=2; if (length!=80) return -1; break;
        case 0x1b: bit=4; if (length!=24) return -1; break;
        case 0x32:
            bit=8;
            if (length<24 || le32(p+pos+20)!=(length-24)/8) return -1;
            break;
        case 0x2a: bit=16; if (length!=16) return -1; break;
        case 5:
            bit=32;
            if (length!=288 || le32(p+pos+8)!=6 || le32(p+pos+12)!=68) return -1;
            break;
        case 0x1e: bit=64; if (length!=16) return -1; break;
        case 0x26: bit=128; if (length!=16) return -1; break;
        default: return -1;
        }
        if (seen&bit) return -1;
        seen|=bit;
        pos+=length;
    }
    if (pos!=end) return -1;
    *out=(struct rpi5_macho_commands){count,bytes,le32(p+24)};
    return 0;
}
