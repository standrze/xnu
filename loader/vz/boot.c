/* SPDX-License-Identifier: BSD-2-Clause
 * Source-built ARM64 EFI -> generic VZ XNU bootstrap. One vCPU initially.
 */
#include "efi.h"
#include "virtio_console.h"
#if VZ_NETWORK
#include "virtio_net.h"
#endif
#if VZ_WRITABLE_STORAGE
#include "virtio_block.h"
#endif
#ifndef VZ_CONSOLE_ONLY
#define VZ_CONSOLE_ONLY 1
#endif
#if !VZ_CONSOLE_ONLY
#include "../rpi5/macho.h"
#include "../rpi5/boot_args.h"
#include "../rpi5/apple_dt.h"
extern const uint8_t vz_kernel_start[], vz_kernel_end[], vz_ramroot_start[], vz_ramroot_end[];
extern uint8_t vz_boot_seed[], vz_boot_seed_end[];
static uint64_t arena_base, arena_size, kernel_entry, args_pa;
static uint64_t ram_base, ram_end;
struct physical_range { uint64_t start, end; };
static struct physical_range normal[60];
static unsigned normal_count;
#endif

static const struct efi_guid acpi2_guid = {0x8868e871, 0xe4f1, 0x11d3,
    {0xbc, 0x22, 0x00, 0x80, 0xc7, 0x3c, 0x88, 0x81}};
static uint8_t memory_map[65536] __attribute__((aligned(16)));
static uint64_t map_length, descriptor_size, map_key;
static uint32_t descriptor_version;
static struct efi_system_table *firmware;
static struct vz_console_shared *console;
static struct vz_console_binding binding;
static uint64_t ecam, gicd, gicr, gicr_size;
static unsigned ecam_start, ecam_end;
static uint32_t psci_hvc, timer_irq;
static int firmware_exited;

extern __attribute__((noreturn)) void vz_leave_firmware(void);
extern __attribute__((noreturn)) void vz_enter_xnu(uint64_t, uint64_t, uint64_t);
static uint32_t u32(const void *p) { const uint8_t *b=p; return b[0] | (uint32_t)b[1]<<8 | (uint32_t)b[2]<<16 | (uint32_t)b[3]<<24; }
static uint64_t u64(const void *p) { return u32(p) | (uint64_t)u32((const uint8_t *)p+4)<<32; }
static int equal(const void *a, const void *b, size_t n) { const uint8_t *x=a,*y=b; for(size_t i=0;i<n;i++) if(x[i]!=y[i]) return 0; return 1; }
static int checksum(const void *p, size_t n) { const uint8_t *b=p; uint8_t sum=0; for(size_t i=0;i<n;i++) sum+=b[i]; return sum==0; }
void *memcpy(void *d, const void *s, size_t n) { uint8_t *x=d; const uint8_t *y=s; for(size_t i=0;i<n;i++) x[i]=y[i]; return d; }
void *memset(void *d, int value, size_t n) { uint8_t *x=d; for(size_t i=0;i<n;i++) x[i]=(uint8_t)value; return d; }

static void text(const char *s) { while(*s) { if(vz_console_putc(&binding,(uint8_t)*s++)) break; } }
static void hex(uint64_t value) { static const char digits[]="0123456789abcdef"; for(int i=60;i>=0;i-=4) { (void)vz_console_putc(&binding,digits[(value>>i)&15]); } }
static __attribute__((noreturn)) void off(void)
{
    register uint64_t x0 __asm__("x0")=UINT64_C(0x84000008);
    if(psci_hvc) __asm__ volatile("hvc #0" : "+r"(x0) :: "x1","x2","x3","memory");
    else __asm__ volatile("smc #0" : "+r"(x0) :: "x1","x2","x3","memory");
    for(;;) __asm__ volatile("wfe");
}
static __attribute__((noreturn)) void fail(const char *message)
{
    if(binding.shared) { text("VZ:LOADER:FAIL "); text(message); text("\n"); off(); }
    if(!firmware_exited && firmware && firmware->console_out) {
        uint16_t line[128]; unsigned i=0;
        while(message[i] && i<126) { line[i]=(uint8_t)message[i]; i++; }
        line[i++]='\n'; line[i]=0;
        (void)firmware->console_out->output(firmware->console_out,line);
    }
    if(!firmware_exited && firmware && firmware->runtime) firmware->runtime->reset_system(2,1,0,0);
    for(;;) __asm__ volatile("wfe");
}

static int inventory(void)
{
    const uint8_t *rsdp=0;
    if(firmware->table_count>128) return -1;
    for(uint64_t i=0;i<firmware->table_count;i++)
        if(equal(&firmware->tables[i].guid,&acpi2_guid,sizeof acpi2_guid)) rsdp=firmware->tables[i].table;
    if(!rsdp || !equal(rsdp,"RSD PTR ",8) || !checksum(rsdp,20) ||
        rsdp[15]<2 || u32(rsdp+20)<36 || u32(rsdp+20)>4096 || !checksum(rsdp,u32(rsdp+20))) return -1;
    const uint8_t *xsdt=(const uint8_t *)(uintptr_t)u64(rsdp+24);
    if(!xsdt || !equal(xsdt,"XSDT",4) || u32(xsdt+4)<36 || u32(xsdt+4)>4096 ||
        (u32(xsdt+4)-36)%8 || !checksum(xsdt,u32(xsdt+4))) return -1;
    for(uint32_t i=36;i<u32(xsdt+4);i+=8) {
        const uint8_t *table=(const uint8_t *)(uintptr_t)u64(xsdt+i);
        if(!table || u32(table+4)<36 || u32(table+4)>65536 || !checksum(table,u32(table+4))) return -1;
        uint32_t length=u32(table+4);
        if(equal(table,"MCFG",4) && length>=60 && table[52]==0 && table[53]==0 && table[54]==0) {
            ecam=u64(table+44); ecam_start=table[54]; ecam_end=table[55];
        }
        if(equal(table,"FACP",4) && length>=131) {
            uint16_t flags=(uint16_t)(table[129] | table[130]<<8);
            if(!(flags&1)) return -1;
            psci_hvc=(flags>>1)&1;
        }
        if(equal(table,"GTDT",4) && length>=76) timer_irq=u32(table+64);
        if(equal(table,"APIC",4)) {
            for(uint32_t pos=44;pos+2<=length;) {
                uint32_t bytes=table[pos+1];
                if(bytes<2 || bytes>length-pos) return -1;
                if(table[pos]==12 && bytes>=24 && table[pos+20]==3) gicd=u64(table+pos+8);
                if(table[pos]==14 && bytes>=16) { gicr=u64(table+pos+4); gicr_size=u32(table+pos+12); }
                pos+=bytes;
            }
        }
    }
    return ecam && ecam_start==0 && ecam_end==255 && gicd && gicr &&
        gicr_size==0x20000 && timer_irq==27 && psci_hvc ? 0 : -1;
}

static int get_map(void)
{
    map_length=sizeof memory_map;
    efi_status result=firmware->boot->get_memory_map(&map_length,memory_map,&map_key,&descriptor_size,&descriptor_version);
    return result || map_length>sizeof memory_map || descriptor_size<40 ||
        descriptor_size>256 || !map_length || map_length%descriptor_size ? -1 : 0;
}

#if !VZ_CONSOLE_ONLY
static uint64_t align16(uint64_t n) { return (n+0x3fff)&~UINT64_C(0x3fff); }
static void le(void *destination, uint64_t value, unsigned bytes)
{
    uint8_t *p=destination;
    for(unsigned i=0;i<bytes;i++) p[i]=(uint8_t)(value>>(8*i));
}
static void collect_ram(void)
{
    normal_count=0;
    for(uint64_t pos=0;pos<map_length;pos+=descriptor_size) {
        const uint8_t *d=memory_map+pos;
        uint32_t type=u32(d); uint64_t start=u64(d+8), pages=u64(d+24), attributes=u64(d+32);
        /* EFI write-back RAM includes reserved RAM; ownership is established
         * separately by AllocateAddress, never by this type classification. */
        if(type>10 || !(attributes&8) || !pages) continue;
        if(pages>UINT64_MAX/4096 || start>UINT64_MAX-pages*4096) fail("EFI RAM overflow");
        /* Merge at EFI 4-KiB granularity before requiring XNU 16-KiB boundaries. */
        if(normal_count==60) fail("too many EFI RAM descriptors");
        unsigned at=normal_count;
        while(at && normal[at-1].start>start) { normal[at]=normal[at-1]; at--; }
        normal[at]=(struct physical_range){start,start+pages*4096}; normal_count++;
    }
    unsigned count=0;
    for(unsigned i=0;i<normal_count;i++) {
        if(count && normal[i].start<normal[count-1].end) fail("overlapping EFI RAM descriptors");
        if(count && normal[i].start==normal[count-1].end) normal[count-1].end=normal[i].end;
        else normal[count++]=normal[i];
    }
    normal_count=count;
    if(!normal_count) fail("no EFI RAM");
    for(unsigned i=0;i<normal_count;i++)
        if((normal[i].start|normal[i].end)&0x3fff) fail("unaligned EFI RAM envelope");
    ram_base=normal[0].start; ram_end=normal[normal_count-1].end;
}
static void allocate_arena(void)
{
    /* Selection uses a fresh map and only ConventionalMemory with WB RAM
     * attributes. Allocation itself is the authority for exclusive ownership. */
    if(get_map()) fail("arena memory map failed");
    collect_ram();
    for(uint64_t size=UINT64_C(320)<<20;size>=(UINT64_C(256)<<20);size-=UINT64_C(32)<<20) {
        for(uint64_t pos=0;pos<map_length;pos+=descriptor_size) {
            const uint8_t *d=memory_map+pos;
            uint64_t start=u64(d+8), pages=u64(d+24);
            if(u32(d)!=7 || !(u64(d+32)&8) || pages>UINT64_MAX/4096 ||
                start>UINT64_MAX-pages*4096 || start>UINT64_MAX-0x1ffffff) continue;
            uint64_t end=start+pages*4096, candidate=(start+0x1ffffff)&~UINT64_C(0x1ffffff);
            if(candidate>=end || size>end-candidate) continue;
            uint64_t address=candidate;
            if(!firmware->boot->allocate_pages(2,2,size/4096,&address)) {
                if(address!=candidate) fail("AllocateAddress changed arena location");
                arena_base=address; arena_size=size;
                return;
            }
        }
    }
    fail("cannot reserve at least 256 MiB aligned kernel arena");
}
static void prepare_xnu(void)
{
    const size_t kernel_size=(size_t)(vz_kernel_end-vz_kernel_start);
    const size_t root_size=(size_t)(vz_ramroot_end-vz_ramroot_start);
    struct rpi5_macho_commands commands;
    struct rpi5_macho_placement placement;
    if((size_t)(vz_boot_seed_end-vz_boot_seed)!=256 || !root_size || (root_size&0x3fff) ||
        root_size>0x4000000 || rpi5_macho_commands(vz_kernel_start,kernel_size,&commands) ||
        rpi5_macho_symbols(vz_kernel_start,kernel_size)) fail("invalid embedded kernel/ramroot/seed");
    unsigned seed_present=0;
    for(unsigned i=0;i<256;i++) seed_present|=vz_boot_seed[i];
    if(!seed_present) fail("boot entropy has not been provisioned");
    uint32_t relocations=0;
    for(size_t pos=32, i=0;i<commands.count;i++) {
        if(u32(vz_kernel_start+pos)==0xb) relocations=u32(vz_kernel_start+pos+76);
        pos+=u32(vz_kernel_start+pos+4);
    }
    if(relocations>0x100000) fail("relocation scratch limit");
    size_t scratch_capacity=1;
    while(scratch_capacity<(size_t)relocations*2) scratch_capacity*=2;
    uint64_t scratch_bytes=(scratch_capacity*4+4095)&~UINT64_C(4095), scratch_pa=0;
    if(firmware->boot->allocate_pages(0,2,scratch_bytes/4096,&scratch_pa)) fail("relocation scratch allocation failed");
    allocate_arena();
    uint64_t header=arena_base+0x1004000, arena_end=arena_base+arena_size;
    if(rpi5_macho_placement(vz_kernel_start,kernel_size,header,arena_base,arena_end,&placement) ||
        rpi5_macho_materialize(vz_kernel_start,kernel_size,(void *)(uintptr_t)header,
            (size_t)(placement.end-header),header,(uint32_t *)(uintptr_t)scratch_pa,scratch_capacity,&placement) ||
        rpi5_macho_verify_materialized(vz_kernel_start,kernel_size,(void *)(uintptr_t)header,
            (size_t)(placement.end-header),header)) fail("Mach-O materialization rejected");
    if(firmware->boot->free_pages(scratch_pa,scratch_bytes/4096)) fail("scratch release failed");
    kernel_entry=placement.entry;
    uint64_t tree_pa=align16(placement.end), tree_capacity=0x10000;
    args_pa=tree_pa+tree_capacity;
    uint64_t root_pa=args_pa+0x4000;
    uint64_t console_pa=root_pa+root_size, top=console_pa+0x10000;
    if(top<console_pa || top>arena_end) fail("retained boot data exceeds arena");
    memset((void *)(uintptr_t)tree_pa,0,(size_t)(top-tree_pa));
    memcpy((void *)(uintptr_t)root_pa,vz_ramroot_start,root_size);
    console=(struct vz_console_shared *)(uintptr_t)console_pa;
    if(vz_console_discover(ecam,ecam_start,ecam_end,console)) fail("no modern virtio PCI console");
#if VZ_WRITABLE_STORAGE
    struct vz_block_device block={0};
    if(vz_block_discover(ecam,ecam_start,ecam_end,&block)) fail("expected exactly one writable virtio block disk");
    uint64_t block_bar=block.common_pa&~UINT64_C(0xffff);
    if ((block.notify_pa&~UINT64_C(0xffff))!=block_bar ||
        (block.config_pa&~UINT64_C(0xffff))!=block_bar || block.notify_length>65536 ||
        (block.notify_pa&0xffff)+block.notify_length>65536 || (block.config_pa&0xffff)>65528 ||
        (block.common_pa&0xffff)>65480) fail("unsupported block MMIO aperture");
#endif

    /* Explicit discovered RAM + initial VZ device windows, sorted by class.
     * The 32-bit PCI MMIO aperture adjacent to ECAM is an observed VZ profile;
     * do not silently apply it to a different generic EFI platform. */
    if(ecam!=0x40000000 || gicd!=0x10000000 || gicr!=0x10010000 ||
        (console->common_pa&~UINT64_C(0xffff))!=(console->notify_pa&~UINT64_C(0xffff)))
        fail("unsupported initial VZ MMIO profile");
    uint64_t bar=console->common_pa&~UINT64_C(0xffff);
    struct physical_range device[5]={{gicd,gicr+gicr_size},{ecam,ecam+0x20000000},{bar,bar+0x10000},{0,0},{0,0}};
    unsigned device_count=3;
#if VZ_WRITABLE_STORAGE
    if (block_bar!=bar) device[device_count++]=(struct physical_range){block_bar,block_bar+0x10000};
#endif
#if VZ_NETWORK
    struct vz_net_device net={0};
    if(vz_net_discover(ecam,ecam_start,ecam_end,&net)) fail("expected exactly one virtio network device");
    uint64_t net_bar=net.common_pa&~UINT64_C(0xffff);
    if ((net.notify_pa&~UINT64_C(0xffff))!=net_bar ||
        (net.config_pa&~UINT64_C(0xffff))!=net_bar || net.notify_length>65536 ||
        (net.notify_pa&0xffff)+net.notify_length>65536 || (net.config_pa&0xffff)>65524 ||
        (net.common_pa&0xffff)>65480) fail("unsupported network MMIO aperture");
    int net_bar_present=0;
    for(unsigned i=0;i<device_count;i++) if(device[i].start==net_bar) net_bar_present=1;
    if(!net_bar_present) device[device_count++]=(struct physical_range){net_bar,net_bar+0x10000};
#endif
    for (unsigned i=0;i<device_count;i++) for (unsigned j=i+1;j<device_count;j++) {
        if (device[j].start<device[i].start) { struct physical_range tmp=device[i]; device[i]=device[j]; device[j]=tmp; }
    }
    for(unsigned i=0;i<device_count;i++) {
        if(device[i].start>=device[i].end || ((device[i].start|device[i].end)&0x3fff) ||
            (i && device[i].start<device[i-1].end)) fail("overlapping VZ device ranges");
        for(unsigned j=0;j<normal_count;j++)
            if(device[i].start<normal[j].end && normal[j].start<device[i].end) fail("device overlaps Normal RAM");
    }
    uint8_t typed_map[8+64*24]={0};
    le(typed_map,1,4); le(typed_map+4,normal_count+device_count,4);
    for(unsigned i=0;i<normal_count+device_count;i++) {
        struct physical_range r=i<normal_count ? normal[i] : device[i-normal_count];
        le(typed_map+8+i*24,i<normal_count?1:2,8);
        le(typed_map+16+i*24,r.start,8); le(typed_map+24+i*24,r.end,8);
    }
    uint64_t frequency, mpidr;
    __asm__ volatile("mrs %0, CNTFRQ_EL0" : "=r"(frequency));
    __asm__ volatile("mrs %0, MPIDR_EL1" : "=r"(mpidr));
    if(frequency!=24000000 || (mpidr&UINT64_C(0xff00ffffff))) fail("unsupported CPU/timebase");
    uint32_t cpu_id=0, timebase=(uint32_t)frequency, phandle=1;
    /* Virtual compatibility profile, not a physical CPU/bus measurement.
     * These match XNU's existing fallback rates and avoid zero divisors. */
    uint32_t bus_frequency=100000000, cpu_frequency=400000000;
    uint64_t dram_size=ram_end-ram_base, console_pointer=console_pa;
    uint64_t ramdisk_record[2]={root_pa,root_size};
    uint64_t gic_reg[4]={gicd,0x10000,gicr,gicr_size};
    uint64_t bus_ranges[3]={0,gicd,0x100000000};
    const struct rpi5_adt_property root_props[]={{"compatible","apple,vz-generic",17}};
    const struct rpi5_adt_property cpu_props[]={
        {"reg",&cpu_id,4},{"state","running",8},{"timebase-frequency",&timebase,4},{"device_type","cpu",4},
        {"bus-frequency",&bus_frequency,4},{"clock-frequency",&cpu_frequency,4}};
    const struct rpi5_adt_node cpu={"cpu0",cpu_props,0,6,0};
    const struct rpi5_adt_node *cpu_children[]={&cpu};
    const struct rpi5_adt_node cpus={"cpus",0,cpu_children,0,1};
    const struct rpi5_adt_property gic_props[]={
        {"compatible","arm,gic-v3",11},{"reg",gic_reg,sizeof gic_reg}};
    const struct rpi5_adt_node interrupt={"interrupt-controller",gic_props,0,2,0};
    const struct rpi5_adt_property serial_props[]={
        {"compatible","virtio,pci-console",19},{"AAPL,phandle",&phandle,4}};
    const struct rpi5_adt_node serial={"serial",serial_props,0,2,0};
#if VZ_WRITABLE_STORAGE
    const struct rpi5_adt_property block_props[]={
        {"compatible","virtio,pci-block",17},{"vz-block",&block,sizeof block}};
    const struct rpi5_adt_node block_node={"virtio-block",block_props,0,2,0};
#endif
#if VZ_NETWORK
    const struct rpi5_adt_property net_props[]={
        {"compatible","virtio,pci-net",sizeof("virtio,pci-net")},{"vz-net",&net,sizeof net}};
    const struct rpi5_adt_node net_node={"virtio-net",net_props,0,2,0};
#endif
    const struct rpi5_adt_node *io_children[]={&interrupt,&serial,
#if VZ_WRITABLE_STORAGE
        &block_node,
#endif
#if VZ_NETWORK
        &net_node,
#endif
    };
    const struct rpi5_adt_property io_props[]={{"device_type","soc",4},{"ranges",bus_ranges,sizeof bus_ranges}};
    const struct rpi5_adt_node arm_io={"arm-io",io_props,io_children,2,sizeof io_children/sizeof io_children[0]};
    const struct rpi5_adt_property default_props[]={{"serial-device",&phandle,4}};
    const struct rpi5_adt_node defaults={"defaults",default_props,0,1,0};
    const struct rpi5_adt_property map_props[]={{"RAMDisk",ramdisk_record,sizeof ramdisk_record}};
    const struct rpi5_adt_node image_map={"memory-map",map_props,0,1,0};
    const struct rpi5_adt_node *chosen_children[]={&image_map};
    const struct rpi5_adt_property chosen_props[]={
        {"dram-base",&ram_base,8},{"dram-size",&dram_size,8},
        {"vz-memory-map",typed_map,8+(normal_count+device_count)*24},{"vz-console",&console_pointer,8},
        {"vz-psci-hvc",&psci_hvc,4},{"random-seed",vz_boot_seed,256}};
    const struct rpi5_adt_node chosen={"chosen",chosen_props,chosen_children,6,1};
    const struct rpi5_adt_node *children[]={&chosen,&cpus,&arm_io,&defaults};
    const struct rpi5_adt_node tree={"device-tree",root_props,children,1,4};
    size_t tree_size=0;
    if(rpi5_adt_encode(&tree,(void *)(uintptr_t)tree_pa,tree_capacity,&tree_size)) fail("Apple DT encoding failed");
    for(unsigned i=0;i<256;i++) ((volatile uint8_t *)vz_boot_seed)[i]=0;
    const char command[]="serial=3 debug=0xa -enable_kprintf_spam -noprogress rd=md0 launchdsuffix=release"
#if VZ_WRITABLE_STORAGE
        " vz_hfs=1"
#endif
        ;
    const struct rpi5_boot_args_input args={
        .virt_base=UINT64_C(0xfffffe0007004000)-(header-arena_base),
        .phys_base=arena_base,.mem_size=arena_size,.top=top,.tree_pa=tree_pa,
        .kernel_end=placement.end,.mem_actual=dram_size,.tree_length=(uint32_t)tree_size};
    if(rpi5_boot_args_encode(&args,command,sizeof command-1,(void *)(uintptr_t)args_pa,0x4000))
        fail("boot arguments rejected");
}
#endif

/* Small console-only build proves native virtio transport and firmware exit
 * before substituting an XNU payload. It never emits a Darwin shell marker.
 */
__attribute__((noreturn)) void vz_after_firmware(void)
{
    if(vz_console_start(console,(uintptr_t)console+0x4000,(uintptr_t)console+0x8000,&binding)) off();
    text("VZ:VIRTIO:READY EL1 MMU_OFF GICD="); hex(gicd); text(" GICR="); hex(gicr); text("\n");
#if VZ_CONSOLE_ONLY
    text("VZ:VIRTIO:CONSOLE_ONLY PSCI_HVC_SHUTDOWN\n");
    off();
#else
    text("VZ:XNU:HANDOFF ARGS="); hex(args_pa); text(" ENTRY="); hex(kernel_entry);
    text(" ARENA="); hex(arena_base); text(" SIZE="); hex(arena_size); text("\n");
    vz_enter_xnu(args_pa,kernel_entry,(uintptr_t)console);
#endif
}

efi_status efi_main(efi_handle image, struct efi_system_table *system)
{
    firmware=system;
    uint64_t el; __asm__ volatile("mrs %0, CurrentEL" : "=r"(el));
    if(el!=4 || !system || !system->boot || inventory()) fail("unsupported EFI/ACPI platform");
#if VZ_CONSOLE_ONLY
    uint64_t allocation=0;
    if(system->boot->allocate_pages(0,2,16,&allocation)) fail("console RAM allocation failed");
    allocation=(allocation+0x3fff)&~UINT64_C(0x3fff);
    console=(struct vz_console_shared *)(uintptr_t)allocation;
    memset(console,0,sizeof *console);
    if(vz_console_discover(ecam,ecam_start,ecam_end,console)) fail("no modern virtio PCI console");
#else
    prepare_xnu();
#endif
    /* GetMemoryMap immediately precedes ExitBootServices. On a changed key,
     * retry the map+exit pair only; do not allocate or invoke console protocols.
     */
    for(unsigned attempt=0;attempt<2;attempt++) {
        if(get_map()) fail("GetMemoryMap failed");
        if(!system->boot->exit_boot_services(image,map_key)) { firmware_exited=1; vz_leave_firmware(); }
    }
    fail("ExitBootServices refused current memory map");
}
