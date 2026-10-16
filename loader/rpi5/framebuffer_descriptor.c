/* SPDX-License-Identifier: BSD-2-Clause */
#include "framebuffer_descriptor.h"

static uint64_t big(const uint8_t *p, unsigned n)
{
    uint64_t v=0;
    for(unsigned i=0;i<n;i++)v=(v<<8)|p[i];
    return v;
}
static int equal(const uint8_t *p,size_t size,const char *s)
{
    size_t n=0;
    while(s[n])n++;
    if(size!=n+1)return 0;
    for(size_t i=0;i<=n;i++)if(p[i]!=(uint8_t)s[i])return 0;
    return 1;
}
static int property(const void *b,size_t n,const char *path,const char *name,
    struct rpi5_fdt_property *p)
{ return rpi5_fdt_property(b,n,path,name,p); }
static int word(const void *b,size_t n,const char *path,const char *name,uint32_t *out)
{
    struct rpi5_fdt_property p;
    if(property(b,n,path,name,&p) || p.length!=4)return -1;
    *out=(uint32_t)big((const uint8_t *)b+p.offset,4);
    return 0;
}
static int enabled(const void *b,size_t n,const char *path)
{
    struct rpi5_fdt_property p;
    int rc=property(b,n,path,"status",&p);
    return rc==-2 || (!rc && (equal((const uint8_t *)b+p.offset,p.length,"okay") ||
                             equal((const uint8_t *)b+p.offset,p.length,"ok")));
}
static int compatible(const void *b,size_t n,const char *path,const char *wanted)
{
    struct rpi5_fdt_property p;
    if(property(b,n,path,"compatible",&p))return 0;
    const uint8_t *raw=(const uint8_t *)b+p.offset;
    size_t pos=0;int found=0;
    while(pos<p.length){
        size_t end=pos;
        while(end<p.length && raw[end])end++;
        if(end==p.length || end==pos)return 0;
        found|=equal(raw+pos,end-pos+1,wanted);pos=end+1;
    }
    return found;
}
static int geometry(const struct rpi5_fb_descriptor *d)
{
    if(!d || !d->width || d->width>1920 || !d->height || d->height>1080 ||
       d->stride<d->width*4 || d->stride>8192 || (d->stride&3) ||
       d->format<RPI5_FB_XRGB8888 || d->format>RPI5_FB_ABGR8888 ||
       !d->allocation.start || (d->allocation.start&3) ||
       d->allocation.end<=d->allocation.start || d->allocation.end>(1ull<<40) ||
       d->allocation.end-d->allocation.start>16*1024*1024)return -1;
    uint64_t bytes=(uint64_t)d->stride*d->height;
    if(d->visible_bytes!=bytes || bytes>d->allocation.end-d->allocation.start)return -1;
    return 0;
}
/* Called only after full structural validation on stable bytes. Reject every
 * unhandled node property (including arbitrary *-supply resource owners) and
 * child, rather than guessing all names of possible binding extensions. */
static int narrow_node(const void *b,size_t n,uint32_t offset)
{
    struct rpi5_fdt_layout l;
    if(rpi5_fdt_layout(b,n,&l))return -1;
    const uint8_t *raw=b;
    uint32_t pos=offset+4,seen=0;
    while(raw[pos])pos++;
    pos=(pos+4)&~3u;
    for(;;){
        uint32_t token=(uint32_t)big(raw+pos,4);pos+=4;
        if(token==2)return 0;
        if(token==4)continue;
        if(token!=3)return -1;
        uint32_t length=(uint32_t)big(raw+pos,4);
        uint32_t name=l.strings+(uint32_t)big(raw+pos+4,4);pos+=8;
        size_t size=0;while(raw[name+size])size++;
        static const char *allowed[]={"compatible","reg","width","height","stride",
            "format","status","display","phandle","linux,phandle"};
        unsigned i=0;
        for(;i<sizeof allowed/sizeof allowed[0];i++)if(equal(raw+name,size+1,allowed[i]))break;
        if(i==sizeof allowed/sizeof allowed[0] || (seen&(1u<<i)))return -1;
        seen|=1u<<i;
        if(i>=7 && (length!=4 || !big(raw+pos,4)))return -1;
        pos=(pos+length+3)&~3u;
    }
}
int rpi5_fb_from_fdt(const void *b,size_t n,const char *path,struct rpi5_fb_descriptor *out)
{
    static const char prefix[]="/chosen/framebuffer@";
    if(!b || !path || !out || n>1024*1024 || rpi5_fdt_structure(b,n))return -1;
    for(size_t i=0;i<sizeof prefix-1;i++)if(path[i]!=prefix[i])return -1;
    uint64_t named=0;unsigned digits=0;
    const char *s=path+sizeof prefix-1;
    for(;*s;s++){
        unsigned value;
        if(*s>='0' && *s<='9')value=(unsigned)(*s-'0');
        else if(*s>='a' && *s<='f')value=(unsigned)(*s-'a'+10);
        else return -1;
        if(++digits>10 || (digits>1 && path[sizeof prefix-1]=='0'))return -1;
        named=(named<<4)|value;
    }
    if(!digits || !named || !compatible(b,n,"/","raspberrypi,5-model-b") ||
       !compatible(b,n,"/","brcm,bcm2712") || !enabled(b,n,"/") ||
       !enabled(b,n,"/chosen") || !enabled(b,n,path))return -1;
    uint32_t count=0,ac=0,sc=0;
    struct rpi5_fdt_property p;
    if(rpi5_fdt_compatible_count(b,n,"simple-framebuffer",&count) || count!=1 ||
       property(b,n,path,"compatible",&p) ||
       !equal((const uint8_t *)b+p.offset,p.length,"simple-framebuffer") ||
       narrow_node(b,n,p.node_offset) ||
       word(b,n,"/chosen","#address-cells",&ac) || (ac!=1 && ac!=2) ||
       word(b,n,"/chosen","#size-cells",&sc) || (sc!=1 && sc!=2))return -1;
    /* A memory-region overrides reg. Resource-managed/simple-bus variants
     * need distinct ownership work, not a silently ignored declaration. */
    const char *unsupported[]={"memory-region","clocks","power-domains"};
    for(unsigned i=0;i<sizeof unsupported/sizeof unsupported[0];i++)
        if(property(b,n,path,unsupported[i],&p)!=-2)return -1;
    int ranges=property(b,n,"/chosen","ranges",&p);
    if(ranges!=-2 && (ranges || p.length))return -1;
    if(property(b,n,path,"reg",&p) || p.length!=(ac+sc)*4)return -1;
    struct rpi5_fb_descriptor result={0};
    uint64_t start=big((const uint8_t *)b+p.offset,ac*4);
    uint64_t size=big((const uint8_t *)b+p.offset+ac*4,sc*4);
    if(start!=named || size>UINT64_MAX-start)return -1;
    result.allocation=(struct rpi5_range){start,start+size};
    if(word(b,n,path,"width",&result.width) || word(b,n,path,"height",&result.height) ||
       word(b,n,path,"stride",&result.stride) || property(b,n,path,"format",&p))return -1;
    const char *formats[]={"x8r8g8b8","a8r8g8b8","x8b8g8r8","a8b8g8r8"};
    for(unsigned i=0;i<4;i++)if(equal((const uint8_t *)b+p.offset,p.length,formats[i]))result.format=i+1;
    result.visible_bytes=(uint64_t)result.stride*result.height;
    if(geometry(&result))return -1;
    *out=result;return 0;
}
int rpi5_fb_plan(const struct rpi5_fb_descriptor *d,const struct rpi5_range *ram,size_t nr,
    const struct rpi5_range *occupied,size_t no,struct rpi5_fb_plan *out)
{
    if(!out || geometry(d) || !ram || !nr || nr>32 || no>64 || (!occupied && no))return -1;
    struct rpi5_fb_plan result={.framebuffer=*d};
    result.retained_pages=(struct rpi5_range){d->allocation.start&~0x3fffull,
        (d->allocation.end+0x3fffull)&~0x3fffull};
    if(rpi5_ranges_validate_live(ram,nr,&result.retained_pages,1))return -1;
    for(size_t i=0;i<no;i++){
        if(occupied[i].end<=occupied[i].start || occupied[i].end>(1ull<<40) ||
           (occupied[i].start<result.retained_pages.end &&
            result.retained_pages.start<occupied[i].end))return -1;
    }
    *out=result;return 0;
}
int rpi5_fb_apple_text_compatible(const struct rpi5_fb_descriptor *d)
{
    /* At least one complete 8x16 text cell; still no mapping/scanout proof. */
    return !geometry(d) && d->width>=8 && d->height>=16 && d->format==RPI5_FB_XRGB8888;
}
