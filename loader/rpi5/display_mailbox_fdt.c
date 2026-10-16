/* SPDX-License-Identifier: BSD-2-Clause */
#include "display_mailbox_fdt.h"

static uint32_t be32(const uint8_t *p)
{ return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3]; }
static size_t length(const char *s) { size_t n=0;while(s[n])n++;return n; }
static int eq(const uint8_t *v,size_t n,const char *s)
{ size_t z=length(s)+1;if(z!=n)return 0;for(size_t i=0;i<z;i++)if(v[i]!=(uint8_t)s[i])return 0;return 1; }
static int same(const char *a,const char *b)
{ return eq((const uint8_t *)a,length(a)+1,b); }
static int prefix(const uint8_t *v,const char *s)
{ while(*s)if(*v++!=(uint8_t)*s++)return 0;return 1; }
static int members(const uint8_t *v,size_t n,const char *wanted)
{
    size_t i=0;int count=0;if(!n)return -1;
    while(i<n){size_t end=i;while(end<n && v[end])end++;
        if(end==n || end==i)return -1;
        count+=eq(v+i,end-i+1,wanted);i=end+1;}
    return count;
}
static int property(const void *b,size_t n,const char *path,const char *key,
    struct rpi5_fdt_property *p)
{ return rpi5_fdt_property(b,n,path,key,p); }
static int exact(const void *b,size_t n,const char *path,const char *key,
    const void *value,size_t bytes)
{
    struct rpi5_fdt_property p;if(property(b,n,path,key,&p) || p.length!=bytes)return 0;
    const uint8_t *a=(const uint8_t *)b+p.offset,*v=value;
    for(size_t i=0;i<bytes;i++)if(a[i]!=v[i])return 0;return 1;
}
static int scalar(const void *b,size_t n,const char *path,const char *key,uint32_t *out)
{ struct rpi5_fdt_property p;if(property(b,n,path,key,&p) || p.length!=4)return -1;*out=be32((const uint8_t *)b+p.offset);return 0; }
static int scalar_is(const void *b,size_t n,const char *path,const char *key,uint32_t value)
{ uint32_t v;return !scalar(b,n,path,key,&v) && v==value; }
static int enabled(const void *b,size_t n,const char *path)
{
    struct rpi5_fdt_property p;int rc=property(b,n,path,"status",&p);
    if(rc==-2)return 1;if(rc)return 0;
    return eq((const uint8_t *)b+p.offset,p.length,"okay") || eq((const uint8_t *)b+p.offset,p.length,"ok");
}
static int handle(const void *b,size_t n,const char *path,uint32_t *out)
{
    struct rpi5_fdt_property p;uint32_t a=0,c=0;
    int rc=property(b,n,path,"phandle",&p);
    if(!rc){if(p.length!=4)return -1;a=be32((const uint8_t *)b+p.offset);}else if(rc!=-2)return -1;
    rc=property(b,n,path,"linux,phandle",&p);
    if(!rc){if(p.length!=4)return -1;c=be32((const uint8_t *)b+p.offset);}else if(rc!=-2)return -1;
    if((a && c && a!=c) || !(a|c) || a==UINT32_MAX || c==UINT32_MAX)return -1;
    *out=a?a:c;return 0;
}
static int disjoint(const void *a,size_t an,const void *b,size_t bn)
{
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    if(an>UINTPTR_MAX-x || bn>UINTPTR_MAX-y)return 0;
    return x+an<=y || y+bn<=x;
}
static int namechar(uint8_t c)
{ return (c>='a'&&c<='z') || (c>='A'&&c<='Z') || (c>='0'&&c<='9') || c=='@' || c==',' || c=='.' || c=='_' || c=='-' || c=='+'; }

/* Structural validation has already bounded all tokens, strings and values.
 * Inventory every matching declaration, including disabled/duplicate nodes;
 * aliases are not followed and multiple declarations are never selected. */
static int inventory(const uint8_t *b,const struct rpi5_fdt_layout *l,char paths[3][256])
{
    const char *wanted[]={"brcm,bcm2708-fb","raspberrypi,bcm2835-firmware","brcm,bcm2835-mbox"};
    unsigned found[3]={0};char path[256]={0};size_t old[32],used=0;unsigned depth=0;
    uint32_t p=l->structure,end=p+l->structure_size;
    while(p<end){uint32_t t=be32(b+p);p+=4;
        if(t==1){if(depth==32)return -1;size_t start=p;while(b[p])p++;
            size_t size=p-start;old[depth]=used;
            if(!depth){if(size)return -1;path[0]='/';used=1;}
            else{if(!size || used+(used>1)+size>=sizeof path)return -1;
                if(used>1)path[used++]='/';
                for(size_t i=0;i<size;i++){if(!namechar(b[start+i]))return -1;path[used++]=(char)b[start+i];}}
            path[used]=0;depth++;p=(p+4)&~3u;
        }else if(t==2){if(!depth)return -1;used=old[--depth];path[used]=0;
        }else if(t==3){uint32_t size=be32(b+p),key=l->strings+be32(b+p+4);p+=8;
            if(same((const char *)b+key,"compatible"))for(unsigned i=0;i<3;i++){
                int count=members(b+p,size,wanted[i]);if(count<0 || count>1)return -1;
                if(count){if(++found[i]!=1)return -1;for(size_t j=0;j<=used;j++)paths[i][j]=path[j];}}
            p=(p+size+3)&~3u;
        }else if(t==9)return found[0]==1 && found[1]==1 && found[2]==1?0:-1;
        else if(t!=4)return -1;
    }return -1;
}
static int parent_bus(const char *path,char bus[256])
{
    size_t n=length(path),last=0;for(size_t i=0;i<n;i++)if(path[i]=='/')last=i;
    if(!last)return -1;for(size_t i=0;i<last;i++)bus[i]=path[i];bus[last]=0;
    return same(bus,"/soc") || same(bus,"/soc@107c000000")?0:-1;
}
/* Reject topology overrides on every participating path. Other devices may
 * have DMA/IOMMU declarations: they are not ancestors of this controller.
 * Firmware's empty dma-ranges is recorded separately, never used to translate
 * the mailbox controller's request buffer. */
static int policy(const void *buffer,size_t n,const char *path,int kind)
{
    const uint8_t *b=buffer;struct rpi5_fdt_layout l;struct rpi5_fdt_property p;
    if(rpi5_fdt_layout(b,n,&l) || property(b,n,path,"compatible",&p))return -1;
    uint32_t pos=p.node_offset+4;while(b[pos])pos++;pos=(pos+4)&~3u;unsigned nested=0;
    const char *leaf[]={"compatible","status","phandle","linux,phandle","firmware",
        "mboxes","#address-cells","#size-cells","dma-ranges","reg","interrupts",
        "interrupt-parent","#mbox-cells"};
    uint32_t allowed=kind==2?0x1fu:kind==3?0x1efu:kind==4?0x1e0fu:UINT32_MAX;
    uint32_t seen=0;
    while(pos<l.structure+l.structure_size){uint32_t t=be32(b+pos);pos+=4;
        if(t==1){if(kind==2 || kind==4)return -1;nested++;while(b[pos])pos++;pos=(pos+4)&~3u;
        }else if(t==2){if(!nested)return 0;nested--;
        }else if(t==3){uint32_t size=be32(b+pos),key=l.strings+be32(b+pos+4);pos+=8;
            if(!nested){const uint8_t *k=b+key;
                int dma=prefix(k,"dma-") || prefix(k,"iommu") || prefix(k,"#iommu") ||
                    same((const char *)k,"memory-region") || same((const char *)k,"memory-region-names") ||
                    same((const char *)k,"interconnects") || same((const char *)k,"interconnect-names") ||
                    same((const char *)k,"secure-status");
                if(dma && !(kind==3 && same((const char *)k,"dma-ranges") && !size))return -1;
                unsigned i;for(i=0;i<13;i++)if(same((const char *)k,leaf[i]))break;
                if(kind>=2 && (i==13 || !(allowed&(1u<<i))))return -1;
                if(i<13){if(seen&(1u<<i))return -1;seen|=1u<<i;}
            }pos=(pos+size+3)&~3u;
        }else if(t!=4)return -1;
    }return -1;
}
int rpi5_display_mailbox_from_fdt(const void *buffer,size_t n,struct rpi5_display_mailbox_fdt *out)
{
    if(!buffer || !out || n>1048576 || !disjoint(buffer,n,out,sizeof(*out)))return -1;
    const uint8_t *b=buffer;struct rpi5_fdt_layout l;struct rpi5_fdt_property p;
    if(rpi5_fdt_structure(b,n) || rpi5_fdt_layout(b,n,&l) || rpi5_fdt_phandles(b,n) ||
        property(b,n,"/","compatible",&p) ||
        members(b+p.offset,p.length,"raspberrypi,5-model-b")!=1 ||
        members(b+p.offset,p.length,"brcm,bcm2712")!=1)return -1;
    char paths[3][256]={{0}},bus[256],other[256];
    if(inventory(b,&l,paths) || parent_bus(paths[0],bus))return -1;
    for(unsigned i=1;i<3;i++)if(parent_bus(paths[i],other) || !same(bus,other))return -1;
    const char *all[]={"/",bus,paths[0],paths[1],paths[2]};
    for(unsigned i=0;i<5;i++)if(!enabled(b,n,all[i]) || policy(b,n,all[i],(int)i))return -1;
    if(!exact(b,n,bus,"compatible","simple-bus",sizeof "simple-bus") ||
        !scalar_is(b,n,"/","#address-cells",2) || !scalar_is(b,n,"/","#size-cells",2) ||
        !scalar_is(b,n,bus,"#address-cells",1) || !scalar_is(b,n,bus,"#size-cells",1) ||
        !scalar_is(b,n,paths[1],"#address-cells",1) || !scalar_is(b,n,paths[1],"#size-cells",1) ||
        !exact(b,n,paths[0],"compatible","brcm,bcm2708-fb",sizeof "brcm,bcm2708-fb") ||
        !exact(b,n,paths[1],"compatible","raspberrypi,bcm2835-firmware\0simple-mfd",sizeof "raspberrypi,bcm2835-firmware\0simple-mfd") ||
        !exact(b,n,paths[2],"compatible","brcm,bcm2835-mbox",sizeof "brcm,bcm2835-mbox") ||
        !scalar_is(b,n,paths[2],"#mbox-cells",0) ||
        !exact(b,n,paths[1],"dma-ranges",0,0) || property(b,n,"/","ranges",&p)!=-2)return -1;
    struct rpi5_display_mailbox_fdt result={0};uint32_t fw,mbox;
    if(handle(b,n,paths[1],&fw) || handle(b,n,paths[2],&mbox) || fw==mbox ||
        !scalar_is(b,n,paths[0],"firmware",fw) || !scalar_is(b,n,paths[1],"mboxes",mbox))return -1;
    if(property(b,n,bus,"ranges",&p) || p.length!=16 || be32(b+p.offset)!=0 ||
        be32(b+p.offset+4)!=0x10 || be32(b+p.offset+8)!=0 || be32(b+p.offset+12)!=0x80000000)return -1;
    result.ranges_child=0;result.ranges_cpu=0x1000000000ull;result.ranges_bytes=0x80000000;
    if(property(b,n,paths[2],"reg",&p) || p.length!=8 || be32(b+p.offset)!=0x7c013880 ||
        be32(b+p.offset+4)!=0x40)return -1;
    struct rpi5_ranges translated;
    if(rpi5_fdt_reg(b,n,paths[2],&translated) || translated.count!=1 ||
        translated.extent[0].start!=0x107c013880ull || translated.extent[0].end!=0x107c0138c0ull)return -1;
    result.mmio=translated.extent[0];result.reg_bus_address=0x7c013880;result.reg_bytes=0x40;
    uint32_t *nodes[]={&result.fb_node,&result.firmware_node,&result.mailbox_node};
    for(unsigned i=0;i<3;i++){if(property(b,n,paths[i],"compatible",&p))return -1;*nodes[i]=p.node_offset;}
    result.fdt_bytes=l.total;result.firmware_phandle=fw;result.mailbox_phandle=mbox;
    result.dma_profile=RPI5_MAILBOX_DMA_PI5_NO_RANGES_DIRECT;
    result.firmware_dma_ranges=RPI5_MAILBOX_PROP_EMPTY;result.linux_default_dma_mask_bits=32;
    *out=result;return 0;
}
