/* SPDX-License-Identifier: BSD-2-Clause */
/* Real provider methods below; only Apple allocation, FDT retrieval/parser,
 * CPU translation and MMIO callbacks are explicit software doubles. */
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
#include <initializer_list>
#include "rpi5_gem_dma_route.h"
extern "C" {
#include "pcie_profile.h"
#include "pcie_released_windows.h"
}
using UInt64=uint64_t;using UInt32=uint32_t;using IOByteCount=uint64_t;
using ppnum_t=uint32_t;using boolean_t=int;
static constexpr uint64_t PAGE_SIZE=0x4000,PAGE_SHIFT=14;
static constexpr unsigned VM_WIMG_MASK=255,VM_WIMG_WCOMB=6;
static constexpr unsigned kIODirectionInOut=3,kIOMemoryPhysicallyContiguous=0x10,
    kIOMemoryMapperNone=0x100,kIOMapWriteCombineCache=0x200;
static constexpr int kIOReturnSuccess=0;
static void *kernel_task=(void *)0x1000;
static struct Model {
    unsigned calls,fail,complete,clear,releases,reads,owner_calls,mode,trigger,reservation_calls;
    bool intr=false,enabled=true;int preemption=0;
    void *thread=(void *)0x2000;
    uint64_t pa=0x100000000,gen=0x100000000,span=0x48000;
    uint32_t regs[0x5000/4]={};
    void (*hook)()=nullptr;
} model;
static bool event() { ++model.calls;if(model.hook && model.calls==model.trigger)model.hook();return model.calls==model.fail; }
static bool ml_at_interrupt_context(){return model.intr;}
static bool ml_get_interrupts_enabled(){return model.enabled;}
static int get_preemption_level(){return model.preemption;}
static void *current_thread(){return model.thread;}
static uint64_t ml_static_ptovirt(uint64_t p){return p+0xffff000000000000;}
static unsigned rpi5_physical_memory_type(uint64_t a,uint64_t b){assert(b-a==0x48000);return event() || a!=model.pa ? 0:1;}
static unsigned pmap_cache_attributes(ppnum_t){return event()?0:VM_WIMG_WCOMB;}
alignas(0x4000) static unsigned char allocation[0x48000];
class IOBufferMemoryDescriptor {
public:
    static IOBufferMemoryDescriptor *inTaskWithOptions(void *t,unsigned options,uint64_t n,uint64_t a) {
        assert(t==kernel_task && options==(kIODirectionInOut|kIOMemoryPhysicallyContiguous|kIOMemoryMapperNone|kIOMapWriteCombineCache));
        assert(n==sizeof allocation && a==0x4000);static IOBufferMemoryDescriptor b;return event()?nullptr:&b;
    }
    uint64_t getLength()const{return sizeof allocation;}
    uint64_t getCapacity()const{return sizeof allocation;}
    void *getBytesNoCopy()const{return allocation;}
    uint64_t getPhysicalSegment(uint64_t o,uint64_t *n,unsigned option)const {
        assert(!o && option==kIOMemoryMapperNone);*n=model.span;return event()?0:model.pa;
    }
    void release(){model.releases++;}
};
class IODMACommand {
public:
    enum MappingOptions{kUnmapped};
    struct Segment64 { uint64_t fIOVMAddr,fLength; };
    static IODMACommand *withSpecification(int fn,unsigned bits,uint64_t max,MappingOptions opt,uint64_t length,unsigned a,void *mapper,void *ref) {
        assert(fn==1 && bits==64 && max==sizeof allocation && opt==kUnmapped && length==max && a==0x4000 && !mapper && !ref);
        static IODMACommand c;return event()?nullptr:&c;
    }
    int setMemoryDescriptor(IOBufferMemoryDescriptor *b,bool automatic){assert(b && !automatic);return event()?-1:0;}
    int prepare(uint64_t offset,uint64_t n){assert(!offset && n==sizeof allocation);return event()?-1:0;}
    int gen64IOVMSegments(uint64_t *o,Segment64 *s,uint32_t *count) {
        assert(!*o && *count==1);*o=sizeof allocation;s->fIOVMAddr=model.gen;s->fLength=sizeof allocation;
        return event()?-1:0;
    }
    int complete(){model.complete++;return event()?-1:0;}
    int clearMemoryDescriptor(bool a){assert(!a);model.clear++;return event()?-1:0;}
    void release(){model.releases++;}
};
#define kIODMACommandOutputHost64 1
static rpi5_pcie_fdt fixture;
class OSData {
public:
    const void *getBytesNoCopy()const{return &fixture;}
    unsigned getLength()const{return sizeof fixture;}
    void release(){model.releases++;}
};
static OSData *rpi5_copy_boot_firmware_fdt(){static OSData d;return event()?nullptr:&d;}
extern "C" int rpi5_pcie_profile_decode(const void *p,size_t n,rpi5_pcie_fdt *f,rpi5_pcie_profile *profile) {
    assert(p==&fixture && n==sizeof fixture);*f=fixture;*profile={};return event()?-1:0;
}
extern "C" int rpi5_fdt_memory(const void *,size_t,struct rpi5_fdt_memory *ram) {
    *ram={};ram->count=1;ram->start[0]=0x40000000;ram->end[0]=0x200000000;return event()?-1:0;
}
extern "C" int rpi5_fdt_reservation_plan(const void *,size_t,rpi5_reservation_plan *p) {
    *p={};p->count=1;p->request[0].size=0x4000000;p->request[0].window_count=1;p->request[0].window[0]={0,0x40000000};return event()?-1:0;
}
extern "C" int rpi5_fdt_initrd(const void *,size_t,rpi5_range *){return event()?-1:1;}
static bool fake_translated_nc(uint64_t va,uint64_t pa) {
    assert(pa>=model.pa && pa<model.pa+sizeof allocation);
    assert(va==(uint64_t)allocation+(pa-model.pa) || va==ml_static_ptovirt(pa));
    return !event();
}
/*PROVIDER_HEADER*/
static rpi5_reservation_record reservation_record,alternate_reservation_record;
extern "C" const rpi5_reservation_record *rpi5_boot_reservation_record(void) {
    model.reservation_calls++;
    if (event() || model.mode==7) return nullptr;
    if (model.mode==8 && model.reservation_calls>1) return &alternate_reservation_record;
    return &reservation_record;
}
extern "C" int rpi5_reservation_record_validate_fdt(const rpi5_reservation_record *record,
    const void *bytes,size_t length) {
    assert(record==&reservation_record && bytes==&fixture && length==sizeof fixture);
    return event() || model.mode==9 ? -1:0;
}
extern "C" int rpi5_reservation_kernel_buffer(const rpi5_reservation_record *record,
    uint64_t physical,uint64_t bytes) {
    assert(record==&reservation_record && physical==model.pa && bytes==sizeof allocation);
    return event() || model.mode==5 ? -1:0;
}
/*PROVIDER_BODY*/
static BCM2712GEMDMAMemory *active;
static rpi5_pcie_released_windows *released;
static void reenter(){struct rpi5_gem_dma_route o;assert(!active->qualify(released,&o));}
static void change_thread(){model.thread=(void *)0x4000;}
static void mutate(){released->io.context=(void *)0x4444;}
static int owner(void *) {model.owner_calls++;return event()?-1:0;}
static int order(void *){return event()?-1:0;}
static int read32(void *,uint32_t off,uint32_t *value){assert(off<sizeof model.regs && !(off&3));model.reads++;*value=model.regs[off/4];return event()?-1:0;}
static void setup(rpi5_pcie_windows &w,rpi5_pcie_released_windows &r)
{
    model=Model{};fixture={};
    fixture.bridge_regs={0x1000120000,0x1000129310};fixture.mip_regs={0x1000130000,0x10001300c0};
    fixture.mip_target={0xfffffff000,0x10000000000};fixture.outbound_count=2;fixture.dma_count=3;fixture.rp1_dma_count=3;
    fixture.outbound[0]={0x02000000,0,0x1f00000000,0xfffffffc};fixture.outbound[1]={0x43000000,0x400000000,0x1c00000000,0x300000000};
    fixture.dma[0]={0x02000000,0,0x1f00000000,0x400000};fixture.dma[1]={0x43000000,0x1000000000,0,0x1000000000};
    fixture.dma[2]={0x03000000,0xfffffff000,0x1000130000,0x1000};
    fixture.rp1_dma[0]={0x43000000,0x1000000000,0x1000000000,0x1000000000};
    fixture.rp1_dma[1]={0x02000000,0xc040000000,0,0x410000};fixture.rp1_dma[2]={0x02000000,0,0x1000000000,0x1000000000};
    w={};assert(!rpi5_pcie_windows_plan(&fixture,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES,&w.plan));w.state=RPI5_PCIE_WINDOWS_COMPLETE;
    /* Match the real released board policy: preferred RAM remains enabled,
     * while device and MIP inbound decoders remain disabled. */
    w.plan.inbound[0].bar_lo&=~UINT32_C(31);
    w.plan.inbound[2].bar_lo&=~UINT32_C(31);
    w.io.physical_base=0x1000120000;w.io.mapped_bytes=0x9310;
    r={};rpi5_pcie_released_windows_io io{&model,0x1000120000,0x9310,owner,read32,order};
    assert(!rpi5_pcie_released_windows_init(&r,&w,&io));released=&r;
    model.regs[0x4068/4]=0x80;
    for(unsigned i=0;i<3;i++) {
        auto &p=w.plan.inbound[i];model.regs[(0x402c+8*i)/4]=p.bar_lo;model.regs[(0x4030+8*i)/4]=p.bar_hi;
        model.regs[(0x40ac+8*i)/4]=p.remap_lo;model.regs[(0x40b0+8*i)/4]=p.remap_hi;
    }
    for(unsigned i=0;i<2;i++) {
        auto &p=w.plan.outbound[i];model.regs[(0x400c+8*i)/4]=p.pci_lo;model.regs[(0x4010+8*i)/4]=p.pci_hi;
        model.regs[(0x4070+4*i)/4]=p.base_limit;model.regs[(0x4080+8*i)/4]=p.base_hi;model.regs[(0x4084+8*i)/4]=p.limit_hi;
    }
    model.regs[(0x4070+4*2)/4]=0xfff0;model.regs[(0x4070+4*3)/4]=0xfff0;
}
int main()
{
    rpi5_pcie_windows w;rpi5_pcie_released_windows r;setup(w,r);
    BCM2712GEMDMAMemory good;active=&good;assert(good.prepare());unsigned prepare_calls=model.calls;
    rpi5_gem_full_provider_observation unavailable,before_layout;
    memset(&unavailable,0xa5,sizeof unavailable);before_layout=unavailable;
    assert(!good.observeCPUOwnedLayout(&unavailable) &&
        !memcmp(&unavailable,&before_layout,sizeof unavailable));
    struct rpi5_gem_dma_route out,before;assert(good.qualify(&r,&out));unsigned all_calls=model.calls;
    assert(good.state()==BCM2712GEMDMAMemory::Held && good.qualificationStep()==13 &&
        good.qualificationError()==0 && out.rp1==0x1100000000 && model.reads==90);
    rpi5_gem_full_provider_observation layout{};
    assert(good.observeCPUOwnedLayout(&layout));
    assert(layout.version==RPI5_GEM_FULL_PROVIDER_VERSION && layout.provider_bytes==0x48000 &&
        layout.mapping_page_bytes==0x4000 && layout.mapping_pages==18 &&
        layout.normal_nc_page_bitmap==0x3ffff && layout.ring_pages==2 &&
        layout.packet_spans==128 && layout.packet_bytes==0x800 &&
        layout.packet_mapped_bytes==0x40000 && layout.packet_spans_cpu_owned==128);
    assert(layout.base_cpu_address==(uint64_t)allocation &&
        layout.base_physical_address==model.pa && layout.base_rp1_dma_address==0x1100000000);
    for(unsigned i=0;i<18;i++) {
        const auto &page=layout.page[i];uint64_t pa=model.pa+(uint64_t)i*0x4000;
        assert(page.index==i && page.cache_attribute==VM_WIMG_WCOMB &&
            page.retained_valid==1 && page.static_valid==1 &&
            page.retained_cpu_address==(uint64_t)allocation+(uint64_t)i*0x4000 &&
            page.static_cpu_address==ml_static_ptovirt(pa) && page.physical_address==pa &&
            (page.retained_read_par>>56)==0x44 && (page.retained_write_par>>56)==0x44 &&
            (page.static_read_par>>56)==0x44 && (page.static_write_par>>56)==0x44);
    }
    assert(layout.ring[0].cpu_address==(uint64_t)allocation &&
        layout.ring[0].dma_address==0x1100000000 && layout.ring[0].mapping_page==0 &&
        layout.ring[1].cpu_address==(uint64_t)allocation+0x4000 &&
        layout.ring[1].dma_address==0x1100004000 && layout.ring[1].mapping_page==1);
    for(unsigned i=0;i<128;i++) {
        const auto &span=layout.packet[i];uint64_t offset=0x8000+(uint64_t)i*0x800;
        assert(span.cpu_address==(uint64_t)allocation+offset &&
            span.dma_address==0x1100000000+offset && span.bytes==0x800 &&
            span.mapping_page==offset/0x4000 && span.owner==RPI5_GEM_FULL_PROVIDER_OWNER_CPU);
        if(i) assert(layout.packet[i-1].cpu_address+0x800==span.cpu_address &&
            layout.packet[i-1].dma_address+0x800==span.dma_address);
    }
    memset(&unavailable,0xa5,sizeof unavailable);before_layout=unavailable;
    model.fail=model.calls+1;
    assert(!good.observeCPUOwnedLayout(&unavailable) &&
        !memcmp(&unavailable,&before_layout,sizeof unavailable));
    model.fail=0;model.thread=(void *)0x4000;
    assert(!good.observeCPUOwnedLayout(&unavailable));
    model.thread=(void *)0x2000;
    assert(!good.observeCPUOwnedLayout(nullptr));
    assert(!good.discardBeforeAdmission() && !good.qualify(&r,&out) && !model.complete && !model.releases);
    setup(w,r);BCM2712GEMDMAMemory activeSideWindow;active=&activeSideWindow;
    assert(activeSideWindow.prepare());
    r.expected.inbound[0].bar_lo|=UINT32_C(31);
    memset(&out,0xa5,sizeof out);before=out;
    assert(!activeSideWindow.qualify(&r,&out) &&
        activeSideWindow.state()==BCM2712GEMDMAMemory::Quarantined &&
        activeSideWindow.qualificationStep()==4 && activeSideWindow.qualificationError()==-4 &&
        !model.reads && !memcmp(&out,&before,sizeof out));
    unsigned faults=1;
    for(unsigned fail=1;fail<=prepare_calls;fail++) {
        setup(w,r);BCM2712GEMDMAMemory m;active=&m;model.fail=fail;
        assert(!m.prepare());assert(!m.prepare());assert(!model.reads);
        if(m.state()==BCM2712GEMDMAMemory::Quarantined)assert(!m.discardBeforeAdmission());
        else {model.fail=0;assert(m.discardBeforeAdmission());}
        faults++;
    }
    for(unsigned fail=prepare_calls+1;fail<=all_calls;fail++) {
        setup(w,r);BCM2712GEMDMAMemory m;active=&m;assert(m.prepare());model.fail=fail;
        memset(&out,0xa5,sizeof out);before=out;bool qualified=m.qualify(&r,&out);
        if(qualified)fprintf(stderr,"UNEXPECTED_QUALIFY fail=%u prep=%u all=%u calls=%u\n",fail,prepare_calls,all_calls,model.calls);
        assert(!qualified);
        assert(m.state()==BCM2712GEMDMAMemory::Quarantined && !memcmp(&out,&before,sizeof out));
        assert(!m.discardBeforeAdmission() && !m.qualify(&r,&out));
        assert(!model.complete && !model.releases);faults++;
    }
    for(auto hook:{reenter,change_thread,mutate})for(unsigned position:{prepare_calls+1,
        prepare_calls+(all_calls-prepare_calls)/2,all_calls}) {
        setup(w,r);BCM2712GEMDMAMemory m;active=&m;assert(m.prepare());model.hook=hook;model.trigger=position;
        memset(&out,0xa5,sizeof out);before=out;assert(!m.qualify(&r,&out));
        assert(m.state()==BCM2712GEMDMAMemory::Quarantined && !memcmp(&out,&before,sizeof out));
        assert(!model.complete && !model.releases);faults++;
    }
    for(unsigned mode=0;mode<10;mode++) {
        setup(w,r);BCM2712GEMDMAMemory m;active=&m;
        if(mode==0)model.intr=true;if(mode==1)model.enabled=false;if(mode==2)model.preemption=1;
        if(mode==3)model.gen+=0x4000;if(mode==4)model.span-=0x4000;
        if(mode==5){model.mode=5;model.pa=model.gen=0x10000000;} /* actual resolved reservation */
        if(mode==6)model.pa=model.gen=0x1f00000000; /* device route */
        if(mode==7)model.mode=7; /* missing same-boot record */
        if(mode==8)model.mode=8; /* record identity changes */
        if(mode==9)model.mode=9; /* record/FDT binding invalid */
        assert(!m.prepare());assert(!model.reads);faults++;
    }
    setup(w,r);BCM2712GEMDMAMemory discard;assert(discard.prepare());assert(discard.discardBeforeAdmission());
    assert(model.complete==1 && model.clear==1 && model.releases==3);
    for(unsigned when=1;when<=2;when++)for(unsigned how=0;how<3;how++) {
        setup(w,r);BCM2712GEMDMAMemory m;active=&m;assert(m.prepare());
        if(how==0)model.fail=model.calls+when;
        else {model.trigger=model.calls+when;model.hook=how==1 ? reenter : change_thread;}
        assert(!m.discardBeforeAdmission());assert(m.state()==BCM2712GEMDMAMemory::Quarantined);
        assert(!model.releases && !m.discardBeforeAdmission());faults++;
    }
    printf("DMA_APPLE_PROVIDER_BODY_PASS faults=%u prep=%u total=%u live_reads=90 NO_HARDWARE_PROOF\n",faults,prepare_calls,all_calls);
}
