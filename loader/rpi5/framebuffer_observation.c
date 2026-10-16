/* SPDX-License-Identifier: BSD-2-Clause */
#include "framebuffer_observation.h"
static uint32_t word(const uint8_t *p)
{ return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3]; }
static int eq(const uint8_t *p,size_t n,const char *s)
{
    size_t i=0;while(s[i])i++;
    if(n!=i+1)return 0;
    for(size_t j=0;j<=i;j++)if(p[j]!=(uint8_t)s[j])return 0;
    return 1;
}
static int member(const uint8_t *p,size_t n,const char *s)
{
    size_t i=0;int found=0;
    while(i<n){size_t end=i;while(end<n && p[end])end++;
        if(end==n || end==i)return -1;
        found|=eq(p+i,end-i+1,s);i=end+1;}
    return found;
}
static int prop(const void *b,size_t n,const char *path,const char *name,struct rpi5_fdt_property *p)
{ return rpi5_fdt_property(b,n,path,name,p); }
static uint32_t cell(const void *b,size_t n,const char *path,const char *name)
{
    struct rpi5_fdt_property p;int rc=prop(b,n,path,name,&p);
    if(rc==-2)return 0;
    return rc || p.length!=4?UINT32_MAX:word((const uint8_t *)b+p.offset);
}
static int overlap(struct rpi5_range a,struct rpi5_range b)
{ return a.start<b.end && b.start<a.end; }
static int node(const void *b,size_t n,const char *path,uint32_t kind,
    const struct rpi5_range *live,size_t live_count,struct rpi5_fb_observation *out)
{
    if(out->count==RPI5_FB_OBSERVE_NODES)return -1;
    struct rpi5_fb_observed_node *v=&out->node[out->count++];
    size_t j=0;do{v->path[j]=path[j];}while(path[j++]);
    v->kind=kind;v->descriptor_rc=-1;v->plan_rc=-1;
    const char *names[]={"width","height","stride","format","reg","status","firmware"};
    uint32_t *scalars[]={&v->width,&v->height,&v->stride};
    for(unsigned i=0;i<7;i++){
        struct rpi5_fdt_property p;int rc=prop(b,n,path,names[i],&p);
        if(rc==-2)continue;
        if(rc){v->malformed|=1u<<i;continue;}
        v->present|=1u<<i;const uint8_t *raw=(const uint8_t *)b+p.offset;
        if(i<3 || i==6){
            if(p.length!=4){v->malformed|=1u<<i;continue;}
            if(i<3)*scalars[i]=word(raw);else v->firmware=word(raw);
        }else if(i==3){
            const char *formats[]={"x8r8g8b8","a8r8g8b8","x8b8g8r8","a8b8g8r8"};
            for(unsigned k=0;k<4;k++)if(eq(raw,p.length,formats[k]))v->format=k+1;
            if(!v->format)v->malformed|=1u<<i;
        }else if(i==4){
            if(!p.length || p.length>16 || p.length%4){v->malformed|=1u<<i;continue;}
            v->reg_words=p.length/4;for(unsigned k=0;k<v->reg_words;k++)v->reg[k]=word(raw+4*k);
        }else{
            if(eq(raw,p.length,"okay") || eq(raw,p.length,"ok"))v->status=1;
            else if(eq(raw,p.length,"disabled"))v->status=2;
            else {v->status=3;v->malformed|=1u<<i;}
        }
    }
    if(kind!=1)return 0;
    struct rpi5_fb_descriptor descriptor;
    v->descriptor_rc=rpi5_fb_from_fdt(b,n,path,&descriptor);
    if(v->descriptor_rc)return 0;
    v->apple_compatible=(uint32_t)rpi5_fb_apple_text_compatible(&descriptor);
    if(out->memory_rc)return 0;
    struct rpi5_range ram[8];
    for(unsigned i=0;i<out->memory.count;i++)ram[i]=(struct rpi5_range){out->memory.start[i],out->memory.end[i]};
    /* No exclusions here: report facts separately. A firmware reservation may
     * intentionally cover its own scanout buffer; never relabel it 'free'. */
    v->plan_rc=rpi5_fb_plan(&descriptor,ram,out->memory.count,NULL,0,&v->plan);
    if(v->plan_rc)return 0;
    for(size_t i=0;i<live_count;i++)v->overlaps_live|=(uint32_t)overlap(v->plan.retained_pages,live[i]);
    if(!out->reservations_rc)for(size_t i=0;i<out->reservations.fixed.count;i++)
        v->overlaps_fixed|=(uint32_t)overlap(v->plan.retained_pages,out->reservations.fixed.extent[i]);
    return 0;
}
static int span_overlap(const void *a,size_t an,const void *b,size_t bn)
{
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    if(x>UINTPTR_MAX-an || y>UINTPTR_MAX-bn)return 1;
    return x<y+bn && y<x+an;
}
int rpi5_fb_observe_with_scratch(const void *b,size_t n,const struct rpi5_range *live,size_t live_count,
    struct rpi5_fb_observation *output,struct rpi5_fb_observation *out)
{
    if(!b || !output || !out || n>1048576 || live_count>64 || (live_count && !live) ||
        span_overlap(out,sizeof(*out),output,sizeof(*output)) || span_overlap(out,sizeof(*out),b,n) ||
        span_overlap(output,sizeof(*output),b,n) ||
        (live_count && (span_overlap(out,sizeof(*out),live,live_count*sizeof(*live)) ||
            span_overlap(output,sizeof(*output),live,live_count*sizeof(*live)))))return -1;
    for(size_t i=0;i<live_count;i++)if(live[i].end<=live[i].start || live[i].end>(1ull<<40))return -1;
    struct rpi5_fdt_layout l;
    if(rpi5_fdt_structure(b,n) || rpi5_fdt_layout(b,n,&l))return -1;
    struct rpi5_fdt_property compatible;
    if(prop(b,n,"/","compatible",&compatible) ||
        member((const uint8_t *)b+compatible.offset,compatible.length,"raspberrypi,5-model-b")!=1 ||
        member((const uint8_t *)b+compatible.offset,compatible.length,"brcm,bcm2712")!=1)return -1;
    *out=(struct rpi5_fb_observation){0};out->total_bytes=l.total;
    if(rpi5_fdt_compatible_count(b,n,"simple-framebuffer",&out->simplefb_declarations) ||
        rpi5_fdt_compatible_count(b,n,"brcm,bcm2708-fb",&out->mailbox_fb_declarations))return -1;
    out->root_ac=cell(b,n,"/","#address-cells");out->root_sc=cell(b,n,"/","#size-cells");
    out->chosen_ac=cell(b,n,"/chosen","#address-cells");out->chosen_sc=cell(b,n,"/chosen","#size-cells");
    out->memory_rc=rpi5_fdt_memory(b,n,&out->memory);
    out->reservations_rc=rpi5_fdt_reservation_plan(b,n,&out->reservations);
    const uint8_t *raw=b;uint32_t pos=l.structure,end=l.structure+l.structure_size;
    char path[RPI5_FB_OBSERVE_PATH]={0};size_t lengths[32],length=0;unsigned depth=0;
    while(pos<end){uint32_t token=word(raw+pos);pos+=4;
        if(token==1){
            if(depth==32)return -1;
            size_t name=pos;while(raw[pos])pos++;
            size_t size=pos-name;lengths[depth]=length;
            if(!depth){if(size)return -1;path[0]='/';length=1;}
            else{
                if(!size || length+(length>1)+size>=sizeof(path))return -1;
                if(length>1)path[length++]='/';
                for(size_t k=0;k<size;k++){
                    uint8_t c=raw[name+k];
                    if(!((c>='a'&&c<='z') || (c>='A'&&c<='Z') || (c>='0'&&c<='9') ||
                        c=='@' || c==',' || c=='.' || c=='_' || c=='-' || c=='+'))return -1;
                    path[length++]=(char)c;
                }
            }
            path[length]=0;depth++;pos=(pos+4)&~3u;
        }else if(token==2){if(!depth)return -1;length=lengths[--depth];path[length]=0;}
        else if(token==3){
            uint32_t size=word(raw+pos),name=l.strings+word(raw+pos+4);pos+=8;
            size_t len=0;while(raw[name+len])len++;
            if(eq(raw+name,len+1,"compatible")){
                int simple=member(raw+pos,size,"simple-framebuffer");
                int mailbox=member(raw+pos,size,"brcm,bcm2708-fb");
                if(simple<0 || mailbox<0 || (simple && mailbox))return -1;
                if((simple || mailbox) && node(b,n,path,simple?1u:2u,live,live_count,out))return -1;
            }
            pos=(pos+size+3)&~3u;
        }else if(token==9){*output=*out;return 0;}
        else if(token!=4)return -1;
    }
    return -1;
}
int rpi5_fb_observe(const void *b,size_t n,const struct rpi5_range *live,size_t live_count,
    struct rpi5_fb_observation *output)
{ struct rpi5_fb_observation scratch;return rpi5_fb_observe_with_scratch(b,n,live,live_count,output,&scratch); }
int rpi5_fb_observation_log(const struct rpi5_fb_observation *o,
    int (*text)(const char *),int (*hex)(uint64_t))
{
    if(!o || !text || !hex || o->count>4 || o->memory.count>8 ||
       o->reservations.fixed.count>32 || o->reservations.count>8)return -1;
    /* Validate all caller-provided array/string bounds before any output. The
     * observer supplies these invariants; the public formatter still refuses
     * a forged object instead of leaking adjacent memory or partial records. */
    for(unsigned i=0;i<o->reservations.count;i++)
        if(o->reservations.request[i].window_count>8)return -1;
    for(unsigned i=0;i<o->count;i++){
        const struct rpi5_fb_observed_node *v=&o->node[i];size_t j=0;
        if(v->kind<1 || v->kind>2 || v->reg_words>4 || v->path[0]!='/')return -1;
        while(j<sizeof(v->path) && v->path[j]){
            unsigned char c=(unsigned char)v->path[j++];
            if(!((c>='a'&&c<='z') || (c>='A'&&c<='Z') || (c>='0'&&c<='9') ||
                c=='/' || c=='@' || c==',' || c=='.' || c=='_' || c=='-' || c=='+'))return -1;
        }
        if(j==sizeof(v->path))return -1;
    }
#define T(s) do{if(!text(s))return -1;}while(0)
#define H(s,v) do{T(s);if(!hex((uint64_t)(v)))return -1;}while(0)
    T("RPI5XNU:FBOBS:INVENTORY");H(" BYTES=",o->total_bytes);
    H(" SIMPLE=",o->simplefb_declarations);H(" MAILBOX_FB=",o->mailbox_fb_declarations);
    H(" NODES=",o->count);H(" ROOT_AC=",o->root_ac);H(" ROOT_SC=",o->root_sc);
    H(" CHOSEN_AC=",o->chosen_ac);H(" CHOSEN_SC=",o->chosen_sc);T("\r\n");
    T("RPI5XNU:FBOBS:MEMORY");H(" RC=",(int64_t)o->memory_rc);H(" BANKS=",o->memory.count);
    H(" RES_RC=",(int64_t)o->reservations_rc);H(" FIXED=",o->reservations.fixed.count);
    H(" DYNAMIC=",o->reservations.count);T(" OWNERSHIP_PROVEN=0 CACHE_CONTRACT_PROVEN=0\r\n");
    for(unsigned i=0;i<o->memory.count;i++){
        T("RPI5XNU:FBOBS:RAM");H(" INDEX=",i);H(" START=",o->memory.start[i]);H(" END=",o->memory.end[i]);T("\r\n");
    }
    for(size_t i=0;i<o->reservations.fixed.count;i++){
        T("RPI5XNU:FBOBS:FIXED");H(" INDEX=",i);H(" START=",o->reservations.fixed.extent[i].start);
        H(" END=",o->reservations.fixed.extent[i].end);T("\r\n");
    }
    for(unsigned i=0;i<o->reservations.count;i++){
        const struct rpi5_dynamic_reservation *r=&o->reservations.request[i];
        T("RPI5XNU:FBOBS:DYNAMIC");H(" INDEX=",i);H(" SIZE=",r->size);H(" ALIGN=",r->alignment);
        H(" WINDOWS=",r->window_count);H(" NO_MAP=",r->no_map);T(" NOT_ALLOCATED\r\n");
        for(unsigned j=0;j<r->window_count;j++){
            T("RPI5XNU:FBOBS:WINDOW");H(" INDEX=",i);H(" WINDOW=",j);H(" START=",r->window[j].start);
            H(" END=",r->window[j].end);T("\r\n");
        }
    }
    for(unsigned i=0;i<o->count;i++){
        const struct rpi5_fb_observed_node *v=&o->node[i];
        T("RPI5XNU:FBOBS:NODE");H(" INDEX=",i);H(" KIND=",v->kind);T(" PATH=");T(v->path);
        H(" PRESENT=",v->present);H(" MALFORMED=",v->malformed);T("\r\n");
        T("RPI5XNU:FBOBS:PROPERTIES");H(" INDEX=",i);H(" WIDTH=",v->width);H(" HEIGHT=",v->height);
        H(" STRIDE=",v->stride);H(" FORMAT=",v->format);H(" STATUS=",v->status);H(" FIRMWARE=",v->firmware);T("\r\n");
        T("RPI5XNU:FBOBS:REG");H(" INDEX=",i);H(" WORDS=",v->reg_words);
        H(" W0=",v->reg[0]);H(" W1=",v->reg[1]);H(" W2=",v->reg[2]);H(" W3=",v->reg[3]);T(" RAW_CELLS_NOT_GUESSED_PA\r\n");
        T("RPI5XNU:FBOBS:DESCRIPTOR");H(" INDEX=",i);H(" RC=",(int64_t)v->descriptor_rc);
        H(" PLAN_RC=",(int64_t)v->plan_rc);H(" APPLE_XRGB=",v->apple_compatible);
        H(" LIVE_OVERLAP=",v->overlaps_live);H(" FIXED_OVERLAP=",v->overlaps_fixed);T("\r\n");
        if(!v->descriptor_rc && !v->plan_rc){
            T("RPI5XNU:FBOBS:GEOMETRY");H(" INDEX=",i);H(" START=",v->plan.framebuffer.allocation.start);
            H(" END=",v->plan.framebuffer.allocation.end);H(" VISIBLE=",v->plan.framebuffer.visible_bytes);
            H(" RETAIN_START=",v->plan.retained_pages.start);H(" RETAIN_END=",v->plan.retained_pages.end);
            T(" NO_MAPPING NO_DRAW NO_OWNERSHIP_CLAIM\r\n");
        }
    }
    return 0;
#undef H
#undef T
}
