/* SPDX-License-Identifier: BSD-2-Clause */
#include "uart.h"
#include "fdt.h"
#include "container.h"
#include "macho.h"
#include "hash.h"
#include "watchdog_budget.h"
#include "board_tree.h"
#include "tree_handoff.h"
#include "firmware_seed.h"
#include "firmware_seed_tree.h"
#include "boot_data.h"
#include "transfer.h"
#ifndef RPI5_XNU_TRANSFER
#define RPI5_XNU_TRANSFER 0
#endif
#ifndef RPI5_SERIAL_TERMINAL
#define RPI5_SERIAL_TERMINAL 0
#endif
#ifndef RPI5_GATE4_STORAGE
#define RPI5_GATE4_STORAGE 0
#endif
#ifndef RPI5_GATE5_PCIE_TOPOLOGY
#define RPI5_GATE5_PCIE_TOPOLOGY 0
#endif
#if RPI5_GATE5_PCIE_TOPOLOGY
#include "pcie_topology.h"
#if RPI5_GATE4_STORAGE
#error "PCIe topology diagnostic must remain separate from storage trials"
#endif
#endif
#ifndef RPI5_GATE4_SD_READONLY
#define RPI5_GATE4_SD_READONLY 0
#endif
#ifndef RPI5_GATE4_HFS_READONLY
#define RPI5_GATE4_HFS_READONLY 0
#endif
#ifndef RPI5_GATE4_HFS_WRITE_TRIAL
#define RPI5_GATE4_HFS_WRITE_TRIAL 0
#endif
#if RPI5_GATE4_HFS_WRITE_TRIAL && (!RPI5_GATE4_STORAGE || !RPI5_SERIAL_TERMINAL || RPI5_GATE4_SD_READONLY || RPI5_GATE4_HFS_READONLY)
#error "Write trial requires distinct storage/serial profile without read-only flags"
#endif
#if RPI5_GATE4_SD_READONLY && (!RPI5_GATE4_STORAGE || !RPI5_SERIAL_TERMINAL)
#error SD read-only trial requires the separate storage/serial recovery image
#endif
#if RPI5_GATE4_HFS_READONLY && !RPI5_GATE4_SD_READONLY
#error HFS read-only trial requires the separate SD read-only recovery image
#endif

/* Pi 5 UART10 translated from the pinned board DTB; runtime discovery pending. */
#define UART10_BASE ((uintptr_t)0x107d001000ull)
#define POLL_BUDGET ((size_t)1000000)

extern uint64_t rpi5_psci_query(uint64_t fid, uint64_t query);
extern uint64_t rpi5_psci_cpu_on(uint64_t affinity, uintptr_t entry, uint64_t context);
extern void probe_secondary_entry(void);
static int text(const char *s);
static int hex(uint64_t value);
static void timer_irq_probe(void);
static uint32_t gic_target_mask(void);
static volatile uint64_t console_owner;
static volatile uint32_t console_owner_valid;

static uint32_t read32(uintptr_t address) { return *(volatile uint32_t *)address; }
static void write32(uintptr_t address, uint32_t value) { *(volatile uint32_t *)address = value; }

/* Single-primary state, not an SMP synchronization protocol. */
volatile uint32_t probe_irq_count;
volatile uint32_t probe_irq_last_ack;
volatile uint32_t probe_irq_timer_status;
volatile uint32_t probe_irq_verified;

struct secondary_record {
    uint64_t mpidr, el, sctlr, daif, frequency, counter;
    uint64_t ready;
    uint64_t irq_verified, irq_ack, irq_count, irq_timer_status;
    uint64_t fault_slot, fault_el, fault_esr, fault_elr, fault_far, fault_spsr;
    uint64_t gic_target;
    uint64_t features[9];
};
volatile struct secondary_record probe_secondary_records[4];
static uint64_t primary_features[9];

static void capture_features(volatile uint64_t *values)
{
    uint64_t value;
#define CAPTURE_FEATURE(index, reg) \
    __asm__ volatile("mrs %0, " #reg : "=r"(value)); values[index] = value
    CAPTURE_FEATURE(0, id_aa64pfr0_el1);
    CAPTURE_FEATURE(1, id_aa64pfr1_el1);
    CAPTURE_FEATURE(2, id_aa64mmfr0_el1);
    CAPTURE_FEATURE(3, id_aa64mmfr1_el1);
    CAPTURE_FEATURE(4, id_aa64mmfr2_el1);
    CAPTURE_FEATURE(5, id_aa64isar0_el1);
    CAPTURE_FEATURE(6, id_aa64isar1_el1);
    CAPTURE_FEATURE(7, ctr_el0);
    CAPTURE_FEATURE(8, dczid_el0);
#undef CAPTURE_FEATURE
}

void probe_secondary_main(uint64_t slot)
{
    if (slot >= 4) return;
    uint64_t mpidr, el, sctlr, daif, frequency, counter;
    __asm__ volatile("mrs %0, mpidr_el1" : "=r"(mpidr));
    __asm__ volatile("mrs %0, CurrentEL" : "=r"(el));
    __asm__ volatile("mrs %0, sctlr_el1" : "=r"(sctlr));
    __asm__ volatile("mrs %0, daif" : "=r"(daif));
    __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(frequency));
    __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(counter));
    probe_secondary_records[slot].mpidr = mpidr;
    probe_secondary_records[slot].el = el;
    probe_secondary_records[slot].sctlr = sctlr;
    probe_secondary_records[slot].daif = daif;
    probe_secondary_records[slot].frequency = frequency;
    probe_secondary_records[slot].counter = counter;
    probe_secondary_records[slot].gic_target = gic_target_mask();
    capture_features(probe_secondary_records[slot].features);
    timer_irq_probe();
    probe_secondary_records[slot].irq_verified = probe_irq_verified;
    probe_secondary_records[slot].irq_ack = probe_irq_last_ack;
    probe_secondary_records[slot].irq_count = probe_irq_count;
    probe_secondary_records[slot].irq_timer_status = probe_irq_timer_status;
    /* Cache-disabled diagnostic publication, not a cacheable SMP protocol. */
    __asm__ volatile("dsb sy" ::: "memory");
    probe_secondary_records[slot].ready = 1;
    __asm__ volatile("dsb sy; sev" ::: "memory");
}

void probe_irq_handler(void)
{
    const uintptr_t cpu = 0x107fffa000ull;
    uint32_t ack = read32(cpu + 0xc);
    uint32_t id = ack & 0x3ff;
    probe_irq_last_ack = ack;
    if (id == 27) {
        uint64_t control;
        __asm__ volatile("mrs %0, cntv_ctl_el0" : "=r"(control));
        probe_irq_timer_status = (uint32_t)control;
        __asm__ volatile("msr cntv_ctl_el0, %0; isb" :: "r"((uint64_t)2) : "memory");
        ++probe_irq_count;
    }
    if (id < 1020) {
        /* Quiesce timer before EOI. Non-secure EOImodeNS is bit 9. */
        __asm__ volatile("dsb sy" ::: "memory");
        write32(cpu + 0x10, ack);
        if (read32(cpu) & (1u << 9)) {
            write32(cpu + 0x1000, ack);
        }
        __asm__ volatile("dsb sy" ::: "memory");
    }
    /* No logging here. Assembly masks IRQs on return for all outcomes. */
}

static void gic_inventory(void)
{
    /* Pinned Pi DTB simple-bus translation; runtime discovery still required.
     * Read-only: do not read IAR, which would acknowledge a pending interrupt. */
    const uintptr_t distributor = 0x107fff9000ull;
    const uintptr_t cpu = 0x107fffa000ull;
    uint32_t typer = *(volatile uint32_t *)(distributor + 4);
    uint32_t did = *(volatile uint32_t *)(distributor + 8);
    uint32_t cid = *(volatile uint32_t *)(cpu + 0xfc);
    uint32_t targets = gic_target_mask();
    if (!text("RPI5XNU:BL33:GIC TYPER=") || !hex(typer) ||
        !text(" GICD_IIDR=") || !hex(did) || !text(" GICC_IIDR=") || !hex(cid) ||
        !text(" CPU_TARGET_MASK=") || !hex(targets)) return;
    if (!targets || (targets & (targets - 1))) {
        (void)text(" INVALID_TARGET_NO_IRQ_SETUP\r\n");
    } else {
        (void)text(" INVENTORY_ONLY_NO_IRQ_PROOF\r\n");
    }
}

static uint32_t gic_target_mask(void)
{
    uint32_t mask = 0;
    for (size_t offset = 0x800; offset < 0x820; offset += 4) {
        uint32_t value = read32(0x107fff9000ull + offset);
        mask |= value | (value >> 8) | (value >> 16) | (value >> 24);
    }
    return mask & 0xff;
}

extern const uint8_t __probe_start[], __probe_end[];
extern const uint8_t __payload_start[], __payload_end[];
#ifndef RPI5_RELOCATION_CAPACITY
#define RPI5_RELOCATION_CAPACITY 2
#endif
/* Primary-only, inside the linker/BSS live extent. Never allocated from raw
 * firmware-advertised RAM. The parser rejects a larger-than-built workload. */
static uint32_t relocation_scratch[RPI5_RELOCATION_CAPACITY];
static uintptr_t hash_watchdog_base;
static struct rpi5_watchdog_budget hash_watchdog_budget;
static const void *validated_kernel;
static size_t validated_kernel_length;
static const uint8_t *validated_init;
static size_t validated_init_length;
static uintptr_t copy_watchdog_base;
static uintptr_t transfer_watchdog_base;
static struct rpi5_watchdog_budget copy_watchdog_budget;

static void copy_watchdog_checkpoint(size_t completed)
{
    uint64_t now;
    __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(now));
    if (copy_watchdog_base && completed==copy_watchdog_budget.completed+1 &&
        rpi5_watchdog_budget_step(&copy_watchdog_budget,now,completed,2) &&
        (read32(copy_watchdog_base+0x1c)&0x30u)==0x20u) {
        write32(copy_watchdog_base+0x24,0x5a000000u|(15u<<16));
        __asm__ volatile("dsb sy" ::: "memory");
    }
    if (completed==2) copy_watchdog_base=0;
}

static int payload_stage(const char *stage)
{
    uint64_t counter;
    __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(counter));
    return text("RPI5XNU:BL33:PAYLOAD_STAGE ") && text(stage) &&
        text(" CNTVCT=") && hex(counter) && text("\r\n");
}

static int seed_stack_selftest(void)
{
    /* Public deterministic test data only. Never a source for an XNU seed. */
    static uint8_t seed[64], output[256], consumed;
    static const uint8_t expected[32]={
        0xfa,0xc4,0x92,0xd9,0xc3,0xe1,0xc4,0x76,0x65,0x46,0x58,0xc8,0x29,0xc1,0x63,0x05,
        0x99,0x78,0x0e,0x89,0xbf,0x01,0xbb,0x1f,0xe7,0x09,0x9f,0x01,0x0f,0x94,0x9f,0x4f};
    if (consumed) return 0;
    for (size_t i=0;i<64;i++) seed[i]=(uint8_t)i;
    volatile uint8_t *stack=rpi5_seed_stack;
    for (size_t i=0;i<0x4000;i++) stack[i]=0xa5;
    if (rpi5_firmware_seed_consume_isolated(seed,64,rpi5_seed_stack,256,&consumed)!=-1 || consumed)
        return 0;
    for (size_t i=0;i<0x4000;i++) if (stack[i]!=0xa5) return 0;
    if (rpi5_firmware_seed_consume_isolated(seed,64,output,256,&consumed) || consumed!=1)
        return 0;
    for (size_t i=0;i<64;i++) if (seed[i]) return 0;
    for (size_t i=0;i<0x4000;i++) if (stack[i]) return 0;
    uint8_t digest[32];
    if (rpi5_sha256(output,sizeof output,digest)) return 0;
    for (size_t i=0;i<32;i++) if (digest[i]!=expected[i]) return 0;
    if (rpi5_firmware_seed_consume_isolated(seed,64,output,256,&consumed)!=-1) return 0;
    for (size_t i=0;i<0x4000;i++) if (stack[i]) return 0;
    for (size_t i=0;i<sizeof output;i++) ((volatile uint8_t *)output)[i]=0;
    return text("RPI5XNU:BL33:SEED_STACK_SELFTEST PASS SYNTHETIC_ONLY REAL_SEED_UNTOUCHED\r\n");
}

static int firmware_seed_diagnostic(uintptr_t pa,size_t total,
    struct rpi5_board_tree *tree,uint8_t *encoded,size_t capacity,
    const struct rpi5_handoff_plan *handoff,uintptr_t tree_pa)
{
    static uint8_t consumed;
    struct rpi5_fdt_property property;
    size_t expected=0, written=0;
    /* Called only after resolver-backed ownership and Normal-RAM checks:
     * entire FDT is retained, disjoint from the probe and kernel destination.
     * Tree, output, consumed state and scratch stack are separate probe BSS. */
    if (consumed || rpi5_firmware_seed_version((const void *)pa,total) ||
        rpi5_firmware_seed_select((const void *)pa,total,&property) ||
        rpi5_seed_tree_measure(&tree->root,capacity,&expected)) {
        (void)text("RPI5XNU:BL33:FIRMWARE_SEED PREFLIGHT_REJECTED_NO_CONSUMPTION\r\n");
        return 0;
    }
    uint8_t *source=(uint8_t *)(pa+property.offset);
    int status=rpi5_firmware_seed_tree(tree,source,&consumed,encoded,capacity,&written,
        rpi5_firmware_seed_consume_isolated);
    int cleared=consumed==1;
    for(size_t i=0;i<64;i++) if(((volatile uint8_t *)source)[i]) cleared=0;
    for(size_t i=0;i<sizeof rpi5_seed_stack;i++)
        if(((volatile uint8_t *)rpi5_seed_stack)[i]) cleared=0;
    int published=0;
    if(!status && written==expected && cleared) {
        volatile uint8_t *ad=(volatile uint8_t *)(uintptr_t)handoff->args_pa;
        volatile uint8_t *td=(volatile uint8_t *)tree_pa;
        if (RPI5_XNU_TRANSFER)
            published=rpi5_boot_data_commit(handoff->args,encoded,written,capacity,ad,td)==0;
        else
            published=rpi5_boot_data_publish(handoff->args,encoded,written,ad,td)==0;
        /* Diagnostic stop: do not retain usable boot data or secret tree. */
        if (!RPI5_XNU_TRANSFER) {
        for(size_t i=0;i<RPI5_BOOT_ARGS_SIZE;i++) ad[i]=0;
        for(size_t i=0;i<written;i++) td[i]=0;
        __asm__ volatile("dsb sy" ::: "memory");
        for(size_t i=0;i<RPI5_BOOT_ARGS_SIZE;i++) if(ad[i]) cleared=0;
        for(size_t i=0;i<written;i++) if(td[i]) cleared=0;
        }
    }
    /* This diagnostic does not hand off: erase encoded seed before reporting.
     * No digest or other seed-derived value is emitted. */
    for(size_t i=0;i<capacity;i++) ((volatile uint8_t *)encoded)[i]=0;
    __asm__ volatile("dsb sy" ::: "memory");
    for(size_t i=0;i<capacity;i++) if(((volatile uint8_t *)encoded)[i]) cleared=0;
    /* Report only fixed stage text, never seed contents or derived values.
     * On timeout the common failure path erases retained destinations. */
    if (RPI5_XNU_TRANSFER && !status && written==expected && cleared && published) {
        if (!text("RPI5XNU:BL33:BOOT_DATA_COMMITTED TRANSFER_NEXT\r\n") ||
            rpi5_uart_drain(UART10_BASE,POLL_BUDGET)!=RPI5_UART_OK) status=-1;
    }
    if (status || written!=expected || !cleared || !published) {
        if (RPI5_XNU_TRANSFER && published) {
            volatile uint8_t *ad=(volatile uint8_t *)(uintptr_t)handoff->args_pa;
            volatile uint8_t *td=(volatile uint8_t *)tree_pa;
            for(size_t i=0;i<RPI5_BOOT_ARGS_SIZE;i++) ad[i]=0;
            for(size_t i=0;i<written;i++) td[i]=0;
            __asm__ volatile("dsb sy" ::: "memory");
        }
        (void)text("RPI5XNU:BL33:FIRMWARE_SEED TRANSACTION_OR_ERASURE_FAILED_STOP\r\n");
        return 0;
    }
    /* All fallible checkpoint output completed, with cleanup on failure. */
    if (RPI5_XNU_TRANSFER) return 1;
    return text("RPI5XNU:BL33:FIRMWARE_SEED DERIVED_TREE_BYTES=") && hex(written) &&
        text(" SOURCE_AND_SCRATCH_ERASED BOOT_DATA_PUBLISHED_VERIFIED_THEN_ERASED NO_TRANSFER\r\n");
}

/* Prepared by the primary before CPU tests; consumed only after they pass.
 * All pointed-to storage is retained static probe BSS or the retained FDT.
 * No seed has been consumed and no boot arguments published at this stage. */
static struct {
    uintptr_t fdt_pa, tree_pa;
    size_t fdt_length, capacity;
    struct rpi5_board_tree *tree;
    uint8_t *encoded;
    const struct rpi5_handoff_plan *handoff;
    int ready;
} pending_boot_data;

static int board_tree_diagnostic(const struct rpi5_fdt_cpus *cpus,
    const struct rpi5_fdt_memory *memory, uint32_t frequency,
    uintptr_t fdt_pa, size_t fdt_length,
    const struct rpi5_resolved_reservations *resolved,
    const struct rpi5_range *watchdog)
{
    pending_boot_data.ready=0;
    /* Probe-owned BSS only; never a physical handoff destination. These
     * buffers contain no seed and are not passed to XNU. */
    static struct rpi5_board_tree tree;
    static uint8_t encoded[16384];
    if (cpus->count!=4 || cpus->enabled_mask!=15 || !memory->count ||
        memory->start[0]!=0 || memory->end[memory->count-1]!=0x200000000ull)
        return 0;
    size_t measured=0, written=0;
    if (rpi5_board_tree_init(cpus->affinity,cpus->count,console_owner,frequency,
        (struct rpi5_range){UART10_BASE,UART10_BASE+0x200},0,0x200000000ull,&tree)) return 0;
    if (!watchdog || rpi5_board_tree_watchdog(&tree,*watchdog)) return 0;
    /* Gate 4 starts with binding/snapshot evidence. It does not reset or issue
     * commands to a possibly 1.8-V firmware-configured card. */
#if RPI5_GATE4_STORAGE
    struct rpi5_fdt_sdhci sd;
    struct rpi5_fdt_sd_power sd_power;
    if (rpi5_fdt_sdhci((const void *)fdt_pa,fdt_length,&sd) ||
        rpi5_fdt_sd_power((const void *)fdt_pa,fdt_length,&sd_power) ||
        rpi5_board_tree_sdhci(&tree,&sd) || rpi5_board_tree_sd_power(&tree,&sd_power)) {
        (void)text("RPI5XNU:BL33:SDHCI_BINDING_REJECTED\r\n"); return 0;
    }
    if (!text("RPI5XNU:BL33:SDHCI_BINDING HOST=") || !hex(sd.host.start) ||
        !text(" CFG=") || !hex(sd.cfg.start) || !text(" SOURCE_HZ=") || !hex(sd.source_hz) ||
        !text(" INTID=") || !hex(sd.irq) || !text(" VOLTAGE_AND_CLOCK_UNVERIFIED NO_CARD_COMMANDS\r\n"))
        return 0;
    if (!text("RPI5XNU:BL33:SDHCI_SNAPSHOT PRESENT=") || !hex(read32(sd.host.start+0x24)) ||
        !text(" CONTROL=") || !hex(read32(sd.host.start+0x28)) ||
        !text(" CLOCK=") || !hex(read32(sd.host.start+0x2c)) ||
        !text(" CONTROL2=") || !hex(read32(sd.host.start+0x3c)) ||
        !text(" CAPS=") || !hex(read32(sd.host.start+0x40)) ||
        !text(" VERSION=") || !hex(read32(sd.host.start+0xfc)) ||
        !text(" CFG_PIN=") || !hex(read32(sd.cfg.start+0x44)) ||
        !text(" READ_ONLY_REGISTERS_NOT_BLOCK_IO\r\n")) return 0;
    if (!text("RPI5XNU:BL33:SD_POWER_SNAPSHOT VARIANT=") || !hex(sd_power.variant) ||
        !text(" GPIO_DATA=") || !hex(read32(sd_power.gpio.start+4)) ||
        !text(" GPIO_DIRECTION=") || !hex(read32(sd_power.gpio.start+8)) ||
        !text(" GPIO_ODEN=") || !hex(read32(sd_power.gpio.start)) ||
        !text(" AON_MUX=") || !hex(read32(sd_power.aon_pins.start+0xc)) ||
        !text(" CQ_VERSION=") || !hex(read32(sd.host.start+0x200)) ||
        !text(" CQ_CONFIG=") || !hex(read32(sd.host.start+0x208)) ||
        !text(" CQ_DOORBELL=") || !hex(read32(sd.host.start+0x228)) ||
        !text(" CQ_PENDING=") || !hex(read32(sd.host.start+0x234)) ||
        !text(" NO_RAIL_CHANGES NO_CARD_COMMANDS\r\n")) return 0;
#endif
    static struct rpi5_memory_types types;
    static struct rpi5_handoff_plan handoff;
    struct rpi5_macho_placement placement;
    if (!validated_kernel || memory->count>8) return 0;
    types.normal.count=memory->count;
    /* The PL011 consumer maps its 0x200-byte register window via ml_io_map,
     * which maps a complete 16 KiB page. Permit only that containing Device
     * page; this is not permission to access neighbouring register offsets.
     * No blanket peripheral-bus window or inferred RAM-hole mapping. */
    types.device.count=3;
    types.device.extent[0]=(struct rpi5_range){
        UART10_BASE&~0x3fffull,(UART10_BASE&~0x3fffull)+0x4000};
    /* Keep Device ranges in ascending order for memory-map validation. */
    types.device.extent[1]=(struct rpi5_range){0x107d200000ull,0x107d204000ull};
    /* GICD and GICC share this page after the runtime FDT profile check. */
    types.device.extent[2]=(struct rpi5_range){0x107fff8000ull,0x107fffc000ull};
#if RPI5_GATE4_STORAGE
    /* Insert the validated host+cfg containing page before the existing
     * sorted Device windows. It lies outside the actual arm-io bus range. */
    for (unsigned i=3;i>0;i--) types.device.extent[i]=types.device.extent[i-1];
    types.device.extent[0]=(struct rpi5_range){sd.host.start&~0x3fffull,
        (sd.host.start&~0x3fffull)+0x4000};
    types.device.extent[6]=types.device.extent[3]; /* GIC moves after pad/GPIO pages. */
    types.device.extent[3]=(struct rpi5_range){sd_power.pins.start&~0x3fffull,
        (sd_power.pins.start&~0x3fffull)+0x4000};
    types.device.extent[4]=(struct rpi5_range){sd_power.aon_pins.start&~0x3fffull,
        (sd_power.aon_pins.start&~0x3fffull)+0x4000};
    types.device.extent[5]=(struct rpi5_range){sd_power.gpio.start&~0x3fffull,
        (sd_power.gpio.start&~0x3fffull)+0x4000};
    types.device.count=7;
#endif
    for (size_t i=0;i<memory->count;i++)
        types.normal.extent[i]=(struct rpi5_range){memory->start[i],memory->end[i]};
    if (rpi5_board_tree_memory_map(&tree,&types)) return 0;
    /* Geometry first; resolved planner below proves reservation exclusion.
     * Firmware memory-node truth is the explicit DTSpec trust assumption. */
    if (rpi5_macho_placement(validated_kernel,validated_kernel_length,
            0x7004000,0x6000000,0x10000000,&placement)) return 0;
    uint64_t args=(placement.end+0x3fff)&~0x3fffull;
    /* Keep the RAM disk after the fixed-size tree window. The resolver
     * proves this extra retained range is DRAM, unreserved and disjoint. */
    uint64_t init_pa=args+0x8000;
    if (validated_init && (validated_init_length&0x3fff || !validated_init_length ||
        validated_init_length>0x4000000 || init_pa>0x10000000ull-validated_init_length ||
        rpi5_board_tree_ramdisk(&tree,init_pa,validated_init_length))) return 0;
    if (rpi5_adt_measure(&tree.root,sizeof encoded,&measured) ||
        rpi5_adt_encode(&tree.root,encoded,sizeof encoded,&written) ||
        written!=measured) return 0;
    if (!text("RPI5XNU:BL33:APPLE_TREE_DIAGNOSTIC BYTES=") || !hex(written) ||
        !text(" NO_SEED EXPLICIT_MEMORY_MAP XNU_CONSUMER_PENDING\r\n")) return 0;
    struct rpi5_range live[3]={
        {(uintptr_t)__probe_start,(uintptr_t)__probe_end},
        {fdt_pa,fdt_pa+fdt_length},
        {init_pa,init_pa+validated_init_length}
    };
    size_t live_count=validated_init ? 3 : 2;
    struct rpi5_handoff_input input={
        .header_pa=0x7004000,.phys_base=0x6000000,.mem_size=0xa000000,
        .mem_actual=0x200000000ull,.args_pa=args,.tree_pa=args+0x4000
    };
    /* DEVELOPMENT kprintf requires its own opt-in in addition to DB_KPRT.
     * serial=1 selects output only; do not require keyboard input/debugger.
     * kt=2 prints allocator policy statistics without changing that policy.
     * No framebuffer is supplied: disable graphical progress. Avoid verbose
     * startup enumeration; serial output is within the recovery deadline. */
    const char *command_line=RPI5_XNU_TRANSFER ?
        (validated_init ?
            "serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release" :
            "serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress") : "";
#define RPI5_STRINGIFY_INNER(value) #value
#define RPI5_STRINGIFY(value) RPI5_STRINGIFY_INNER(value)
#if RPI5_SERIAL_TERMINAL
#if RPI5_GATE4_HFS_WRITE_TRIAL
    command_line = "serial=3 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release bcm2712_register_secondaries=1 bcm2712_cpu_on_all=1 bcm2712_terminal_watchdog=1 bcm2712_hfs=1 bcm2712_sd_write_trial=1";
#elif RPI5_GATE4_SD_READONLY
#if RPI5_GATE4_HFS_READONLY
    command_line = "serial=3 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release bcm2712_register_secondaries=1 bcm2712_cpu_on_all=1 bcm2712_terminal_watchdog=1 bcm2712_hfs=1 bcm2712_sd_readonly=1";
#else
    command_line = "serial=3 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release bcm2712_register_secondaries=1 bcm2712_cpu_on_all=1 bcm2712_terminal_watchdog=1 bcm2712_sd_readonly=1";
#endif
#else
    command_line = "serial=3 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release bcm2712_register_secondaries=1 bcm2712_cpu_on_all=1 bcm2712_terminal_watchdog=1";
#endif
#elif RPI5_GATE3_QUALIFICATION_CONFIG_ENABLED
    command_line = "serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release bcm2712_register_secondaries=1 bcm2712_cpu_on_all=1 bcm2712_gate3_qualify=1 bcm2712_gate3_xnupost_suite=1 kernPOST=1 kernPOST_config=" RPI5_GATE3_QUALIFICATION_CONFIG;
#elif RPI5_GATE3_SOAK_SECONDS > 0
    command_line = "serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release bcm2712_register_secondaries=1 bcm2712_cpu_on_all=1 bcm2712_soak_seconds=" RPI5_STRINGIFY(RPI5_GATE3_SOAK_SECONDS);
#elif RPI5_GATE3_XNUPOST_CONFIG_ENABLED
    command_line = "serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release bcm2712_register_secondaries=1 bcm2712_cpu_on_all=1 bcm2712_gate3_xnupost_suite=1 kernPOST=1 kernPOST_config=" RPI5_GATE3_XNUPOST_CONFIG;
#elif RPI5_GATE3_XNUPOST_INDEX > 0
    command_line = "serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release bcm2712_register_secondaries=1 bcm2712_cpu_on_all=1 bcm2712_gate3_xnupost_suite=1 kernPOST=1 kernPOST_config=" RPI5_STRINGIFY(RPI5_GATE3_XNUPOST_INDEX) "_" RPI5_STRINGIFY(RPI5_GATE3_XNUPOST_INDEX);
#elif RPI5_GATE3_XNUPOST_INVENTORY
    command_line = "serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release bcm2712_register_secondaries=1 bcm2712_cpu_on_all=1 kernPOST=4";
#elif RPI5_GATE3_TLB_TRIAL
    command_line = "serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release bcm2712_register_secondaries=1 bcm2712_cpu_on_all=1 bcm2712_tlb_trial=1";
#elif RPI5_GATE3_USER_TLB_TRIAL
    command_line = "serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release bcm2712_register_secondaries=1 bcm2712_cpu_on_all=1 bcm2712_user_tlb_trial=1";
#elif RPI5_GATE3_CONCURRENCY_TRIAL
    command_line = "serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release bcm2712_register_secondaries=1 bcm2712_cpu_on_all=1 bcm2712_concurrency_trial=1";
#elif RPI5_GATE3_CPU_ON_ALL
    command_line = "serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release bcm2712_register_secondaries=1 bcm2712_cpu_on_all=1";
#elif RPI5_GATE3_CPU_ON_1
    command_line = "serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release bcm2712_register_secondaries=1 bcm2712_cpu_on_1=1";
#elif RPI5_GATE3_REGISTER_CPUS
    command_line = "serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release bcm2712_register_secondaries=1";
#elif RPI5_GATE3_REGISTER_BOOT_CPU
    command_line = "serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release bcm2712_register_boot_cpu=1";
#endif
    size_t command_length=0;
    while (command_line[command_length]) command_length++;
    if (rpi5_resolved_tree_handoff(validated_kernel,validated_kernel_length,
            &input,resolved,&types,&tree.root,sizeof encoded,live,live_count,command_line,command_length,&handoff)) {
        (void)text("RPI5XNU:BL33:LOAD_PLAN REJECTED_NO_WRITES\r\n"); return 0;
    }
    int reported=text("RPI5XNU:BL33:LOAD_PLAN HEADER=") && hex(handoff.kernel.header) &&
        text(" END=") && hex(handoff.kernel.end) && text(" ENTRY=") && hex(handoff.kernel.entry) &&
        text(" ARGS=") && hex(handoff.args_pa) && text(" TREE=") && hex(input.tree_pa) &&
        text(" TOP=") && hex(handoff.top) && text(" MAP_START=") && hex(handoff.mapping.physical_start) &&
        text(" MAP_END=") && hex(handoff.mapping.physical_end) &&
        text(" DTSPEC_TRUST NO_SEED NO_PHYSICAL_WRITES NO_TRANSFER\r\n");
    if (!reported || !payload_stage("PHYSICAL_COPY_BEGIN")) return 0;
    /* The successful resolver-backed plan excludes all retained live inputs
     * from this exact arena. No other core has been started at this point.
     * Output and relocation scratch remain within the reserved probe BSS. */
    static struct rpi5_macho_placement copied;
    size_t bytes=(size_t)(handoff.kernel.end-handoff.kernel.header);
    void *destination=(void *)(uintptr_t)handoff.kernel.header;
    if (rpi5_macho_materialize(validated_kernel,validated_kernel_length,
            destination,bytes,handoff.kernel.header,relocation_scratch,
            RPI5_RELOCATION_CAPACITY,&copied)) {
        (void)text("RPI5XNU:BL33:PHYSICAL_COPY FAILED_STOP\r\n"); return 0;
    }
    if (copied.header!=handoff.kernel.header || copied.end!=handoff.kernel.end ||
        copied.entry!=handoff.kernel.entry || copied.count!=handoff.kernel.count) return 0;
    for (uint32_t i=0;i<copied.count;i++)
        if (copied.destination[i]!=handoff.kernel.destination[i]) return 0;
    __asm__ volatile("dsb sy" ::: "memory");
    copy_watchdog_checkpoint(1);
    if (!payload_stage("PHYSICAL_READBACK_BEGIN")) return 0;
    if (rpi5_macho_verify_materialized(validated_kernel,validated_kernel_length,
            destination,bytes,handoff.kernel.header)) {
        (void)text("RPI5XNU:BL33:PHYSICAL_READBACK FAILED_STOP\r\n"); return 0;
    }
    if (validated_init) {
        volatile uint8_t *ramdisk=(volatile uint8_t *)(uintptr_t)init_pa;
        for (size_t i=0;i<validated_init_length;i++) ramdisk[i]=validated_init[i];
        __asm__ volatile("dsb sy" ::: "memory");
        for (size_t i=0;i<validated_init_length;i++)
            if (ramdisk[i]!=validated_init[i]) {
                (void)text("RPI5XNU:BL33:RAMDISK_READBACK FAILED_STOP\r\n"); return 0;
            }
        if (!text("RPI5XNU:BL33:RAMDISK_MATERIALIZED PA=") || !hex(init_pa) ||
            !text(" BYTES=") || !hex(validated_init_length) || !text(" VERIFIED\r\n")) return 0;
    }
    copy_watchdog_checkpoint(2);
    if (!(seed_stack_selftest() && payload_stage("PHYSICAL_READBACK_COMPLETE") &&
        text("RPI5XNU:BL33:KERNEL_MATERIALIZED BYTES=") && hex(bytes) &&
        text(" FULL_ENVELOPE_VERIFIED NO_BOOT_ARGS_WRITTEN NO_TRANSFER\r\n"))) return 0;
    pending_boot_data.fdt_pa=fdt_pa;
    pending_boot_data.fdt_length=fdt_length;
    pending_boot_data.tree=&tree;
    pending_boot_data.encoded=encoded;
    pending_boot_data.capacity=sizeof encoded;
    pending_boot_data.handoff=&handoff;
    pending_boot_data.tree_pa=input.tree_pa;
    pending_boot_data.ready=1;
    return 1;
}

void rpi5_hash_progress(size_t completed, size_t total)
{
    uint64_t counter;
    __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(counter));
    /* The container hashes its tiny 64/128-byte record table first. Do not
     * bind the sole renewal budget to that preliminary digest: the following
     * kernel digest is the long operation requiring service. Keep one large
     * payload only and the deadline established before hashing. */
    if (hash_watchdog_base && !hash_watchdog_budget.total && !completed &&
        total >= (1u<<20) &&
        total <= (uintptr_t)__payload_end-(uintptr_t)__payload_start)
        hash_watchdog_budget.total = total;
    if (hash_watchdog_base &&
        rpi5_watchdog_budget_step(&hash_watchdog_budget,counter,completed,total) &&
        (read32(hash_watchdog_base+0x1c) & 0x30u) == 0x20u) {
        /* Only reload an already-running full-reset watchdog. Leave reset
         * control, reset status and firmware's next-boot selection untouched. */
        write32(hash_watchdog_base+0x24,0x5a000000u | (15u << 16));
        __asm__ volatile("dsb sy" ::: "memory");
    }
    (void)(text("RPI5XNU:BL33:HASH_PROGRESS DONE=") && hex(completed) &&
        text(" TOTAL=") && hex(total) && text(" CNTVCT=") && hex(counter) &&
        text("\r\n"));
}

static int embedded_payload_inventory(void)
{
    validated_kernel=0;
    validated_kernel_length=0;
    validated_init=0;
    validated_init_length=0;
    size_t length=(uintptr_t)__payload_end-(uintptr_t)__payload_start;
    if (!length) return text("RPI5XNU:BL33:NO_EMBEDDED_PAYLOAD\r\n");
    struct rpi5_container container;
    struct rpi5_macho_segments kernel;
    if (!payload_stage("CONTAINER_HASH_BEGIN")) return 0;
    if (rpi5_container_parse(__payload_start,length,&container)) {
        (void)text("RPI5XNU:BL33:PAYLOAD_INTEGRITY_REJECTED\r\n"); return 0;
    }
    const void *image=__payload_start+container.kernel.offset;
    if (!payload_stage("SEGMENTS_BEGIN")) return 0;
    if (rpi5_macho_segments(image,(size_t)container.kernel.length,&kernel)) {
        (void)text("RPI5XNU:BL33:PAYLOAD_KERNEL_REJECTED\r\n"); return 0;
    }
    if (!payload_stage("SYMBOLS_BEGIN")) return 0;
    if (rpi5_macho_symbols(image,(size_t)container.kernel.length)) {
        (void)text("RPI5XNU:BL33:PAYLOAD_SYMBOLS_REJECTED\r\n"); return 0;
    }
    uint32_t relocations;
    if (!payload_stage("RELOCATIONS_BEGIN")) return 0;
    if (rpi5_macho_relocations(image,(size_t)container.kernel.length,relocation_scratch,
        RPI5_RELOCATION_CAPACITY,&relocations)) {
        (void)text("RPI5XNU:BL33:PAYLOAD_RELOCATIONS_REJECTED\r\n"); return 0;
    }
    validated_kernel=image;
    validated_kernel_length=(size_t)container.kernel.length;
    if (container.count==2) {
        validated_init=__payload_start+container.init.offset;
        validated_init_length=(size_t)container.init.length;
    }
    return payload_stage("COMPLETE") &&
        text("RPI5XNU:BL33:PAYLOAD_INTEGRITY_OBSERVED BYTES=") && hex(length) &&
        text(" KERNEL_BYTES=") && hex(container.kernel.length) &&
        text(" ENTRY_KVA=") && hex(kernel.entry) &&
        text(" LOCAL_RELOCATIONS=") && hex(relocations) &&
        text(" NOT_LOADED\r\n");
}

static int runtime_reservations(uintptr_t pa, uint32_t total,
    const struct rpi5_fdt_memory *memory, struct rpi5_resolved_reservations *out)
{
    /* Primary-only diagnostic scratch; no allocator consumes these results.
     * Keep bounded planning structures off the early exception-sensitive stack. */
    static struct rpi5_reservation_plan plan;
    static struct rpi5_resolved_reservations resolved;
    int status = rpi5_fdt_reservation_plan((const void *)pa, total, &plan);
    if (status) {
        (void)text(status == -2 ?
            "RPI5XNU:BL33:RESERVATIONS UNSUPPORTED_NO_ALLOCATION\r\n" :
            "RPI5XNU:BL33:RESERVATIONS MALFORMED_NO_ALLOCATION\r\n");
        return 0;
    }
    /* Firmware is not a loader-owned buffer: exclude it from BOTH views even
     * when FDT omits it. Refuse planning rather than drop a full-table entry. */
    if (plan.fixed.count >= 32) {
        (void)text("RPI5XNU:BL33:RESERVATIONS FIRMWARE_CAPACITY_NO_ALLOCATION\r\n");
        return 0;
    }
    plan.fixed.extent[plan.fixed.count++] = (struct rpi5_range){0, 0x80000};
    struct rpi5_range initrd;
    int initrd_status=rpi5_fdt_initrd((const void *)pa,total,&initrd);
    if (initrd_status<0) {
        (void)text("RPI5XNU:BL33:INITRD MALFORMED_NO_ALLOCATION\r\n");
        return 0;
    }
    if (!initrd_status) {
        struct rpi5_range ram[8];
        for (size_t i=0;i<memory->count;i++)
            ram[i]=(struct rpi5_range){memory->start[i],memory->end[i]};
        const struct rpi5_range inputs[]={
            {(uintptr_t)__probe_start,(uintptr_t)__probe_end},
            {pa,(uint64_t)pa+total},initrd
        };
        /* A reserved address is not necessarily readable RAM. No contents are
         * accessed here; reject conflicting firmware input before planning. */
        if (initrd.start<0x80000 ||
            rpi5_ranges_validate_live(ram,memory->count,inputs,3)) {
            (void)text("RPI5XNU:BL33:INITRD LIVE_RANGE_CONFLICT_NO_ALLOCATION\r\n");
            return 0;
        }
        if (plan.fixed.count>=32) {
            (void)text("RPI5XNU:BL33:INITRD CAPACITY_NO_ALLOCATION\r\n");
            return 0;
        }
        /* Preserve foreign boot input; no content read, reclaim or XNU use. */
        plan.fixed.extent[plan.fixed.count++]=initrd;
        if (!text("RPI5XNU:BL33:INITRD_PRESERVED START=") || !hex(initrd.start) ||
            !text(" END=") || !hex(initrd.end) || !text(" NOT_DARWIN_INIT\r\n")) return 0;
    }
    /* Probe range includes BSS and every primary/secondary/fault stack. */
    const struct rpi5_range live[] = {
        {(uintptr_t)__probe_start, (uintptr_t)__probe_end},
        {pa, (uint64_t)pa + total},
    };
    if (rpi5_resolve_reservations(memory, &plan, live, 2, &resolved)) {
        (void)text("RPI5XNU:BL33:RESERVATIONS NO_FIT_NO_ALLOCATION\r\n");
        return 0;
    }
    /* Subtraction can produce a valid free map even when firmware placed a
     * live image inside a foreign reservation. Do not continue to CPU_ON in
     * that case. Use reservation_free: available deliberately excludes us. */
    if (rpi5_ranges_validate_live(resolved.reservation_free.extent,
            resolved.reservation_free.count,live,2)) {
        (void)text("RPI5XNU:BL33:RESERVATIONS LIVE_FOREIGN_CONFLICT_STOP\r\n");
        return 0;
    }
    for (size_t i=0;i<2;i++)
        if (!text(i ? "RPI5XNU:BL33:LIVE_FDT START=" : "RPI5XNU:BL33:LIVE_PROBE START=") ||
            !hex(live[i].start) || !text(" END=") || !hex(live[i].end) ||
            !text(" FIRMWARE_RESERVATIONS_CHECKED_INVENTORY_INCOMPLETE\r\n")) return 0;
    for (size_t i = 0; i < plan.fixed.count; ++i)
        if (!text("RPI5XNU:BL33:RESERVED START=") || !hex(plan.fixed.extent[i].start) ||
            !text(" END=") || !hex(plan.fixed.extent[i].end) || !text("\r\n")) return 0;
    for (size_t i = 0; i < resolved.count; ++i)
        if (!text("RPI5XNU:BL33:RESERVATION_PROPOSED NODE_OFFSET=") ||
            !hex(plan.request[i].node_offset) || !text(" START=") ||
            !hex(resolved.allocation[i].start) || !text(" END=") ||
            !hex(resolved.allocation[i].end) || !text(" NOT_COMMITTED\r\n")) return 0;
    for (size_t i = 0; i < resolved.available.count; ++i)
        if (!text("RPI5XNU:BL33:RAM_CANDIDATE START=") ||
            !hex(resolved.available.extent[i].start) || !text(" END=") ||
            !hex(resolved.available.extent[i].end) ||
            !text(" LIVE_INVENTORY_INCOMPLETE_NOT_ALLOCATOR_INPUT\r\n")) return 0;
    if (out) *out=resolved;
    return 1;
}

static int runtime_seed_metadata(uintptr_t pa, size_t total)
{
    const char *names[]={"rng-seed","kaslr-seed","random-seed"};
    for (size_t i=0;i<3;i++) {
        struct rpi5_fdt_property property;
        int status=rpi5_fdt_property((const void *)pa,total,"/chosen",names[i],&property);
        if (status != 0 && status != -2) return 0;
        if (!text("RPI5XNU:BL33:SEED_METADATA NAME=") || !text(names[i]) ||
            !text(status == -2 ? " ABSENT" : " LENGTH=")) return 0;
        if (!status && !hex(property.length)) return 0;
        if (!text(" CONTENT_NOT_READ SOURCE_NOT_QUALIFIED\r\n")) return 0;
    }
    return 1;
}

static int runtime_cpus(uintptr_t pa, struct rpi5_fdt_cpus *cpus)
{
    /* Trusted firmware handoff, not fault-safe probing of arbitrary memory.
     * Match pinned TF-A's 32-bit pointer and 4 MiB mapping window. */
    if (pa < 0x80000 || pa > UINT32_MAX || (pa & 7)) {
        (void)text("RPI5XNU:BL33:FDT POINTER_REJECTED\r\n"); return 0;
    }
    uint64_t end = ((uint64_t)pa & ~0x1fffffull) + (4u << 20);
    if (end > (1ull << 32)) end = 1ull << 32;
    if (end - pa < 40) {
        (void)text("RPI5XNU:BL33:FDT HEADER_WINDOW_REJECTED\r\n"); return 0;
    }
    const volatile uint8_t *header = (const volatile uint8_t *)pa;
    uint32_t total = ((uint32_t)header[4] << 24) | ((uint32_t)header[5] << 16) |
        ((uint32_t)header[6] << 8) | header[7];
    if (!text("RPI5XNU:BL33:FDT HEADER_TOTAL=") || !hex(total) ||
        !text(" WINDOW_END=") || !hex(end) || !text("\r\n")) return 0;
    if (total < 40 || total > end - pa) {
        (void)text("RPI5XNU:BL33:FDT TOTAL_WINDOW_REJECTED\r\n"); return 0;
    }
    struct rpi5_fdt_layout layout;
    if (rpi5_fdt_layout((const void *)pa,total,&layout)) {
        (void)text("RPI5XNU:BL33:FDT LAYOUT_REJECTED\r\n"); return 0;
    }
    if (rpi5_fdt_structure((const void *)pa,total)) {
        (void)text("RPI5XNU:BL33:FDT STRUCTURE_REJECTED\r\n"); return 0;
    }
    if (!runtime_seed_metadata(pa,total)) return 0;
    uint32_t framebuffer_declarations;
    if (rpi5_fdt_compatible_count((const void *)pa,total,"simple-framebuffer",
        &framebuffer_declarations)) return 0;
    if (!text("RPI5XNU:BL33:FRAMEBUFFER_COMPATIBLE_DECLARATIONS=") ||
        !hex(framebuffer_declarations) ||
        !text(" INCLUDES_DISABLED NOT_ALLOCATION_INVENTORY\r\n")) return 0;
    struct rpi5_fdt_memory memory;
    if (rpi5_fdt_memory((const void *)pa, total, &memory)) {
        (void)text("RPI5XNU:BL33:FDT MEMORY_DECODE_REJECTED\r\n"); return 0;
    }
    const struct rpi5_range live[] = {
        {(uintptr_t)__probe_start, (uintptr_t)__probe_end},
        {pa, (uint64_t)pa + total},
    };
    struct rpi5_range ram[8];
    for (size_t i = 0; i < memory.count; ++i)
        ram[i] = (struct rpi5_range){memory.start[i], memory.end[i]};
    /* Firmware already loaded us: this catches inconsistency before CPU_ON,
     * not prior corruption during loading/BSS initialization. ATF may be
     * omitted from advertised nonsecure RAM, so test its boundary separately. */
    if (live[0].start < 0x80000 ||
        rpi5_ranges_validate_live(ram, memory.count, live, 2)) {
        (void)text("RPI5XNU:BL33:LIVE_RANGE_CONTRACT_REJECTED\r\n");
        return 0;
    }
    if (rpi5_fdt_phandles((const void *)pa, total)) {
        (void)text("RPI5XNU:BL33:FDT_PHANDLES_REJECTED\r\n");
        return 0;
    }
    if (rpi5_fdt_probe_mmio((const void *)pa, total)) {
        (void)text("RPI5XNU:BL33:RUNTIME_MMIO_PROFILE_REJECTED\r\n");
        return 0;
    }
    if (rpi5_fdt_probe_timer((const void *)pa, total)) {
        (void)text("RPI5XNU:BL33:RUNTIME_TIMER_BINDING_REJECTED\r\n");
        return 0;
    }
#if RPI5_SERIAL_TERMINAL
    if (rpi5_fdt_uart_irq((const void *)pa, total)) {
        (void)text("RPI5XNU:BL33:UART_IRQ_BINDING_REJECTED\r\n");
        return 0;
    }
    if (!text("RPI5XNU:BL33:UART_IRQ_BINDING SPI=121 INTID=153 NOT_ENABLED\r\n")) return 0;
#if RPI5_GATE4_SD_READONLY
    if (!text("RPI5XNU:BL33:SD_READONLY_TRIAL DMA=0 WRITES=0\r\n")) return 0;
#endif
#if RPI5_GATE4_HFS_READONLY
    if (!text("RPI5XNU:BL33:HFS_READONLY_TRIAL\r\n")) return 0;
#endif
#if RPI5_GATE4_HFS_WRITE_TRIAL
    if (!text("RPI5XNU:BL33:HFS_WRITE_TRIAL DMA=0 HFS_EXTENT_ONLY DURABILITY_VERIFIED=0\r\n")) return 0;
#endif
#endif
    if (!text("RPI5XNU:BL33:RUNTIME_MMIO_TIMER_PROFILE_MATCH DELIVERY_CLOCK_UNVERIFIED\r\n")) return 0;
    struct rpi5_uart_clocks clocks;
    if (rpi5_fdt_uart_clocks((const void *)pa, total, &clocks)) {
        (void)text("RPI5XNU:BL33:UART_CLOCK_BINDING_REJECTED\r\n");
        return 0;
    }
    if (!text("RPI5XNU:BL33:UART_CLOCK_DECLARED UART_HZ=") || !hex(clocks.uart_hz) ||
        !text(" APB_HZ=") || !hex(clocks.apb_hz) || !text(" NOT_MEASURED\r\n")) return 0;
    struct rpi5_uart_snapshot nominal_uart;
    /* Primary only, before CPU_ON; capture host is receive-only. Firmware has
     * handed off, and this probe owns UART10. Keep exact nominal policy rather
     * than accepting TF-A's 44 MHz assumption against the runtime declaration. */
    if (!text("RPI5XNU:BL33:UART_EXACT_CONFIGURE_FROM_DECLARED_CLOCK\r\n")) return 0;
    if (rpi5_uart_set_exact(UART10_BASE, clocks.uart_hz, 115200, POLL_BUDGET) != RPI5_UART_OK) {
        (void)text("RPI5XNU:BL33:UART_EXACT_CONFIGURE_REJECTED\r\n");
        return 0;
    }
    if (rpi5_uart_snapshot(UART10_BASE, &nominal_uart) != RPI5_UART_OK ||
        rpi5_uart_check_nominal(&nominal_uart, clocks.uart_hz, 115200) != RPI5_UART_OK) {
        (void)text("RPI5XNU:BL33:UART_NOMINAL_115200_8N1_REJECTED\r\n");
        return 0;
    }
    if (!text("RPI5XNU:BL33:UART_NOMINAL_115200_8N1_MATCH CLOCK_NOT_MEASURED\r\n")) return 0;
    struct rpi5_range rng;
    if (rpi5_fdt_rng200((const void *)pa, total, &rng)) {
        if (!text("RPI5XNU:BL33:RNG200_BINDING_UNSUPPORTED NO_ENTROPY_PROVIDER\r\n")) return 0;
    } else if (!text("RPI5XNU:BL33:RNG200_CANDIDATE START=") || !hex(rng.start) ||
        !text(" END=") || !hex(rng.end) || !text(" NOT_ACCESSED_NO_ENTROPY_PROVIDER\r\n")) return 0;
    /* Batch independent inspections after the common framing/live-range/MMIO
     * prerequisites. Payload and topology inspection do not allocate from the
     * FDT reservation plan. Complete these before reservation parsing, which
     * previously hid all their evidence behind its first failure or exception.
     * None of these results authorizes CPU_ON or handoff on its own. */
    int psci_ok = rpi5_fdt_psci_smc((const void *)pa, total) == 0;
    int cpus_ok = rpi5_fdt_cpus((const void *)pa, total, cpus) == 0;
    if (!text("RPI5XNU:BL33:TOPOLOGY_INVENTORY PSCI_BINDING=") || !hex(psci_ok) ||
        !text(" CPU_TOPOLOGY=") || !hex(cpus_ok) || !text("\r\n")) return 0;
    struct rpi5_range watchdog;
    uint64_t now, frequency;
    __asm__ volatile("isb; mrs %0, cntvct_el0; mrs %1, cntfrq_el0"
        : "=r"(now), "=r"(frequency));
    if (!rpi5_fdt_watchdog((const void *)pa,total,&watchdog) &&
        frequency && frequency <= UINT32_MAX && now <= UINT64_MAX-60*frequency &&
        (read32(watchdog.start+0x1c) & 0x30u) == 0x20u) {
        hash_watchdog_base=(uintptr_t)watchdog.start;
        hash_watchdog_budget=(struct rpi5_watchdog_budget){now+60*frequency,now,0,0,128};
        copy_watchdog_base=(uintptr_t)watchdog.start;
        transfer_watchdog_base=(uintptr_t)watchdog.start;
        copy_watchdog_budget=(struct rpi5_watchdog_budget){now+60*frequency,now,2,0,2};
        if (!text("RPI5XNU:BL33:WATCHDOG SHARED_DEADLINE_60S HASH_MAX_128 COPY_CHECKPOINT_MAX_2\r\n")) return 0;
    }
    int payload_ok = embedded_payload_inventory();
    hash_watchdog_base=0; /* Hash servicing ends; two copy checkpoints remain. */
    if (!text("RPI5XNU:BL33:INDEPENDENT_INVENTORY PAYLOAD=") || !hex(payload_ok) ||
        !text(" PSCI_BINDING=") || !hex(psci_ok) ||
        !text(" CPU_TOPOLOGY=") || !hex(cpus_ok) || !text("\r\n")) return 0;
    static struct rpi5_resolved_reservations resolved;
    int reservations_ok = runtime_reservations(pa, total, &memory, &resolved);
    for (uint32_t i = 0; i < memory.count; ++i) {
        if (!text("RPI5XNU:BL33:RAM_ADVERTISED START=") || !hex(memory.start[i]) ||
            !text(" END=") || !hex(memory.end[i]) || !text(" NOT_ALLOCATOR_INPUT\r\n")) return 0;
    }
    int tree_ok=0;
    if (payload_ok && cpus_ok && reservations_ok && frequency && frequency<=UINT32_MAX)
        tree_ok=board_tree_diagnostic(cpus,&memory,(uint32_t)frequency,pa,total,&resolved,
            transfer_watchdog_base ? &watchdog : 0);
    if (!tree_ok) (void)text("RPI5XNU:BL33:APPLE_TREE_DIAGNOSTIC_REJECTED_OR_SKIPPED\r\n");
    return payload_ok && psci_ok && cpus_ok && reservations_ok && tree_ok;
}

static int start_secondaries(const struct rpi5_fdt_cpus *cpus)
{
    uint64_t mpidr, frequency;
    __asm__ volatile("mrs %0, mpidr_el1" : "=r"(mpidr));
    __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(frequency));
    uint64_t self = mpidr & 0xff00ffffffull;
    int known = 0;
    if (!frequency || frequency > UINT32_MAX) return 0;
    for (uint32_t i = 0; i < cpus->count; ++i)
        known |= cpus->affinity[i] == self && (cpus->enabled_mask & (1u << i));
    if (!known) return 0;
    uint32_t used_targets = gic_target_mask();
    if (!used_targets || (used_targets & (used_targets - 1))) {
        (void)text("RPI5XNU:BL33:SECONDARY INVALID_PRIMARY_GIC_TARGET\r\n"); return 0;
    }
    for (uint32_t i = 0; i < cpus->count; ++i) {
        uint64_t target = cpus->affinity[i];
        if (target == self || !(cpus->enabled_mask & (1u << i))) continue;
        if (probe_secondary_records[i].ready || rpi5_psci_query(0xc4000004u, target) != 1) {
            (void)text("RPI5XNU:BL33:SECONDARY STOP_NOT_OFF_OR_SLOT_USED\r\n");
            return 0;
        }
        /* One attempt per slot. Never clear/recycle a slot after CPU_ON. */
        __asm__ volatile("dsb sy" ::: "memory");
        uint64_t result = rpi5_psci_cpu_on(target, (uintptr_t)probe_secondary_entry, i);
        if (result != 0) {
            if (text("RPI5XNU:BL33:CPU_ON ERROR_RAW=")) (void)hex(result);
            (void)text("\r\n"); return 0;
        }
        uint64_t begin, now;
        __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(begin));
        for (size_t poll = 0; poll < 10 * POLL_BUDGET && !probe_secondary_records[i].ready; ++poll) {
            __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(now));
            if (now - begin >= frequency) break;
            __asm__ volatile("yield" ::: "memory");
        }
        if (!probe_secondary_records[i].ready) {
            (void)text("RPI5XNU:BL33:SECONDARY TIMEOUT_NO_RETRY\r\n"); return 0;
        }
        __asm__ volatile("dsb sy" ::: "memory");
        volatile struct secondary_record *r = &probe_secondary_records[i];
        if (r->ready == 2) {
            if (text("RPI5XNU:BL33:SECONDARY_FAULT TARGET=") && hex(target) &&
                text(" SLOT=") && hex(r->fault_slot) && text(" EL=") && hex(r->fault_el) &&
                text(" ESR=") && hex(r->fault_esr) && text(" ELR=") && hex(r->fault_elr) &&
                text(" FAR_RAW=") && hex(r->fault_far) && text(" SPSR=") && hex(r->fault_spsr))
                (void)text("\r\n");
            return 0; /* Fault path cannot promise GIC cleanup; never continue. */
        }
        int valid = r->ready == 1 && (r->mpidr & 0xff00ffffffull) == target &&
            r->el == 4 && !(r->sctlr & 0x1005) && (r->daif & 0x3c0) == 0x3c0 && r->frequency == frequency &&
            r->irq_verified == 1 && r->irq_count == 1 && (r->irq_ack & 0x3ff) == 27 && (r->irq_timer_status & 7) == 5 &&
            r->gic_target && r->gic_target <= 0x80 && !(r->gic_target & (r->gic_target - 1)) &&
            !(used_targets & r->gic_target);
        if (!text("RPI5XNU:BL33:SECONDARY TARGET=") || !hex(target) ||
            !text(" MPIDR=") || !hex(r->mpidr) || !text(" EL=") || !hex(r->el) ||
            !text(" SCTLR=") || !hex(r->sctlr) || !text(" DAIF=") || !hex(r->daif) ||
            !text(" CNTFRQ=") || !hex(r->frequency) || !text(" CNTVCT=") || !hex(r->counter) ||
            !text(" IRQ_VERIFIED=") || !hex(r->irq_verified) || !text(" IRQ_ACK=") || !hex(r->irq_ack) ||
            !text(" IRQ_COUNT=") || !hex(r->irq_count) || !text(" TIMER_STATUS=") || !hex(r->irq_timer_status) ||
            !text(" GIC_TARGET=") || !hex(r->gic_target) ||
            !text(valid ? " EL1_AND_IRQ_RECORD_OBSERVED\r\n" : " INVALID_RECORD\r\n")) return 0;
        if (!valid) return 0;
        int matching_features = 1;
        if (!text("RPI5XNU:BL33:SECONDARY_FEATURES TARGET=") || !hex(target)) return 0;
        for (size_t f = 0; f < 9; ++f) {
            matching_features &= r->features[f] == primary_features[f];
            if (!text(" REG_INDEX=") || !hex(f) || !text(" VALUE=") || !hex(r->features[f])) return 0;
        }
        if (!text(matching_features ? " MATCH_PRIMARY_RAW\r\n" : " MISMATCH_STOP\r\n")) return 0;
        if (!matching_features) return 0;
        /* Publication is not proof of shutdown: query TF-A separately. */
        uint64_t off_state = 0;
        __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(begin));
        for (size_t poll = 0; poll < 10 * POLL_BUDGET; ++poll) {
            off_state = rpi5_psci_query(0xc4000004u, target);
            if (off_state == 1) break;
            if (off_state != 0 && off_state != 2) break;
            __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(now));
            if (now - begin >= frequency) break;
            __asm__ volatile("yield" ::: "memory");
        }
        if (!text("RPI5XNU:BL33:SECONDARY_OFF TARGET=") || !hex(target) ||
            !text(" AFFINITY_STATE=") || !hex(off_state) ||
            !text(off_state == 1 ? " OFF_OBSERVED\r\n" : " STOP_NOT_OFF\r\n")) return 0;
        if (off_state != 1) return 0;
        used_targets |= (uint32_t)r->gic_target;
    }
    return 1;
}

static int psci_affinity_inventory(const struct rpi5_fdt_cpus *cpus)
{
    uint64_t mpidr;
    __asm__ volatile("mrs %0, mpidr_el1" : "=r"(mpidr));
    uint64_t self = mpidr & 0xff00ffffffull;
    int known = 0;
    for (size_t i = 0; i < cpus->count; ++i)
        known |= self == cpus->affinity[i] && (cpus->enabled_mask & (1u << i));
    if (!known) {
        (void)text("RPI5XNU:BL33:PSCI SKIP_UNKNOWN_BOOT_AFFINITY\r\n");
        return 0;
    }
    for (size_t i = 0; i < cpus->count; ++i) {
        if (!(cpus->enabled_mask & (1u << i))) continue;
        uint64_t result = rpi5_psci_query(0xc4000004u, cpus->affinity[i]);
        if (!text("RPI5XNU:BL33:PSCI AFFINITY=") || !hex(cpus->affinity[i]) ||
            !text(" SELF=") || !hex(self == cpus->affinity[i]) ||
            !text(" STATE_RAW=") || !hex(result)) return 0;
        const char *state = result == 0 ? " ON" : result == 1 ? " OFF" :
            result == 2 ? " ON_PENDING" : " ERROR_OR_UNKNOWN";
        if (!text(state) || !text("\r\n")) return 0;
        if (result != (self == cpus->affinity[i] ? 0u : 1u)) {
            (void)text("RPI5XNU:BL33:PSCI INITIAL_AFFINITY_STATE_REJECTED\r\n");
            return 0;
        }
    }
    return 1;
}

static void timer_irq_probe(void)
{
    probe_irq_verified = 0;
    probe_irq_count = 0;
    probe_irq_last_ack = UINT32_MAX;
    probe_irq_timer_status = 0;
    const uintptr_t d = 0x107fff9000ull, c = 0x107fffa000ull;
    const uint32_t bit = 1u << 27;
    uint64_t frequency, now, daif;
    __asm__ volatile("mrs %0, cntfrq_el0; mrs %1, daif" : "=r"(frequency), "=r"(daif));
    uint32_t typer = read32(d + 4);
    if (!frequency || frequency > UINT32_MAX || !(daif & 0x80) ||
        ((read32(c + 0xfc) >> 16) & 15) != 2 || !(typer & (1u << 10))) {
        (void)text("RPI5XNU:BL33:IRQ SKIP_PROFILE\r\n");
        return;
    }
    /* No concurrent firmware/secondary users are supported. SGIs may be RAO
     * enabled, but pending/active SGIs and enabled PPIs/SPIs forbid this test. */
    for (uint32_t bank = 0; bank <= (typer & 31); ++bank) {
        uint32_t enabled = read32(d + 0x100 + 4 * bank);
        if ((!bank ? enabled & 0xffff0000u : enabled) ||
            read32(d + 0x200 + 4 * bank) || read32(d + 0x300 + 4 * bank)) {
            (void)text("RPI5XNU:BL33:IRQ SKIP_EXISTING_INTERRUPTS\r\n");
            return;
        }
    }
    if (read32(d + 0xc04) & (1u << 23)) {
        (void)text("RPI5XNU:BL33:IRQ SKIP_NONLEVEL_TIMER\r\n");
        return;
    }
    uint32_t old_dctl = read32(d), old_cctl = read32(c), old_pmr = read32(c + 4);
    uint8_t old_priority = *(volatile uint8_t *)(d + 0x400 + 27);
    probe_irq_count = 0;
    probe_irq_last_ack = UINT32_MAX;
    probe_irq_timer_status = 0;
    *(volatile uint8_t *)(d + 0x400 + 27) = 0x80;
    write32(c + 4, 0xff);
    write32(c, (old_cctl & ~(1u << 9)) | 1u); /* Combined EOI, NS Group 1. */
    write32(d, old_dctl | 1u);                /* NS view EnableGrp1 is bit 0. */
    write32(d + 0x100, bit);
    __asm__ volatile("dsb sy; isb" ::: "memory");
    int configured = (read32(d + 0x100) & bit) && (read32(d) & 1) &&
        (read32(c) & 1) && !(read32(c) & (1u << 9));
    if (configured) {
        __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(now));
        uint64_t ticks = (frequency + 999) / 1000;
        if (now <= UINT64_MAX - ticks) {
            uint64_t deadline = now + ticks;
            __asm__ volatile("msr cntv_cval_el0, %0; isb" :: "r"(deadline) : "memory");
            __asm__ volatile("msr cntv_ctl_el0, %0; isb" :: "r"((uint64_t)1) : "memory");
            __asm__ volatile("msr daifclr, #2; isb" ::: "memory");
            for (size_t i = 0; i < POLL_BUDGET && probe_irq_last_ack == UINT32_MAX; ++i) {
                __asm__ volatile("yield" ::: "memory");
            }
            __asm__ volatile("msr daifset, #2; isb" ::: "memory");
        } else configured = 0;
    }
    /* Keep IRQs masked and quiesce the owned source on every normal exit. */
    __asm__ volatile("msr cntv_ctl_el0, %0; isb; dsb sy" :: "r"((uint64_t)2) : "memory");
    write32(d + 0x180, bit);
    write32(d + 0x280, bit);
    __asm__ volatile("dsb sy" ::: "memory");
    *(volatile uint8_t *)(d + 0x400 + 27) = old_priority;
    write32(c + 4, old_pmr);
    write32(c, old_cctl);
    write32(d, old_dctl);
    __asm__ volatile("dsb sy; isb" ::: "memory");
    int cleaned = !(read32(d + 0x100) & bit) && !(read32(d + 0x200) & bit) &&
        !(read32(d + 0x300) & bit) && read32(c + 4) == old_pmr &&
        read32(c) == old_cctl && read32(d) == old_dctl &&
        *(volatile uint8_t *)(d + 0x400 + 27) == old_priority;
    probe_irq_verified = configured && cleaned && probe_irq_count == 1 &&
        (probe_irq_last_ack & 0x3ff) == 27 && (probe_irq_timer_status & 7) == 5;
    if (!text("RPI5XNU:BL33:IRQ CONFIGURED=") || !hex(configured) ||
        !text(" CLEANED=") || !hex(cleaned) ||
        !text(" ACK=") || !hex(probe_irq_last_ack) || !text(" COUNT=") || !hex(probe_irq_count) ||
        !text(" TIMER_STATUS=") || !hex(probe_irq_timer_status)) return;
    (void)text(configured && cleaned && probe_irq_count == 1 && (probe_irq_last_ack & 0x3ff) == 27 &&
        (probe_irq_timer_status & 7) == 5 ? " SINGLE_CPU_IRQ_OBSERVED\r\n" : " NOT_CONFIRMED\r\n");
}

/* Bounded iteration count also terminates if the architectural counter stalls.
 * This diagnostic owns CNTV; it neither enables IRQs nor touches the GIC. */
static int timer_probe(void)
{
    uint64_t frequency, begin, now, control = 0, deadline;
    __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(frequency));
    if (!frequency || frequency > UINT32_MAX) {
        (void)text("RPI5XNU:BL33:TIMER INVALID_FREQUENCY\r\n");
        return 0;
    }
    __asm__ volatile("msr cntv_ctl_el0, %0; isb" :: "r"((uint64_t)2) : "memory");
    __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(begin));
    uint64_t ticks = (frequency + 999) / 1000; /* Approximately 1 ms, rounded up. */
    if (begin > UINT64_MAX - ticks) {
        (void)text("RPI5XNU:BL33:TIMER COUNTER_WRAP\r\n");
        return 0;
    }
    deadline = begin + ticks;
    __asm__ volatile("msr cntv_cval_el0, %0; isb" :: "r"(deadline) : "memory");
    __asm__ volatile("msr cntv_ctl_el0, %0; isb" :: "r"((uint64_t)3) : "memory");
    now = begin;
    size_t polls;
    for (polls = 0; polls < POLL_BUDGET; ++polls) {
        __asm__ volatile("isb; mrs %0, cntv_ctl_el0; mrs %1, cntvct_el0"
            : "=r"(control), "=r"(now));
        if (control & 4) break;
    }
    /* Disable before serial output, including timeout/inconsistent outcomes. */
    __asm__ volatile("msr cntv_ctl_el0, %0; isb" :: "r"((uint64_t)2) : "memory");
    if (!text("RPI5XNU:BL33:TIMER MASKED_STATUS=") || !hex(control) ||
        !text(" BEGIN=") || !hex(begin) || !text(" DEADLINE=") || !hex(deadline) ||
        !text(" END=") || !hex(now) || !text(" POLLS=") || !hex(polls)) return 0;
    if ((control & 7) == 7 && now >= deadline && now > begin) {
        return text(" CONDITION_OBSERVED_NO_IRQ_PROOF\r\n");
    } else {
        (void)text(" TIMEOUT_OR_INCONSISTENT\r\n");
        return 0;
    }
}

static int owns_console(void)
{
    uint64_t mpidr;
    __asm__ volatile("mrs %0, mpidr_el1" : "=r"(mpidr));
    return !console_owner_valid || (mpidr & 0xff00ffffffull) == console_owner;
}

static int text(const char *s)
{
    if (!owns_console()) return 1;
    while (*s) {
        if (rpi5_uart_putc(UART10_BASE, (uint8_t)*s++, POLL_BUDGET) != RPI5_UART_OK) return 0;
    }
    return 1;
}

static int hex(uint64_t value)
{
    if (!owns_console()) return 1;
    static const char digits[] = "0123456789abcdef";
    for (int shift = 60; shift >= 0; shift -= 4) {
        if (rpi5_uart_putc(UART10_BASE, digits[(value >> shift) & 15], POLL_BUDGET) != RPI5_UART_OK) return 0;
    }
    return 1;
}

/* FAR is printed raw; its validity depends on the syndrome, not on this log. */
void probe_exception(uint64_t slot, uint64_t esr, uint64_t elr,
    uint64_t far, uint64_t spsr, uint64_t el)
{
    uint64_t owner;
    __asm__ volatile("mrs %0, tpidrro_el0" : "=r"(owner));
    if (owner) {
        if (owner > 4) return;
        volatile struct secondary_record *r = &probe_secondary_records[owner - 1];
        r->fault_slot = slot;
        r->fault_el = el;
        r->fault_esr = esr;
        r->fault_elr = elr;
        r->fault_far = far;
        r->fault_spsr = spsr;
        __asm__ volatile("dsb sy" ::: "memory");
        r->ready = 2;
        __asm__ volatile("dsb sy; sev" ::: "memory");
        return;
    }
    if (!text("RPI5XNU:BL33:FAULT SLOT=") || !hex(slot) ||
        !text(" EL=") || !hex(el) ||
        !text(" ESR=") || !hex(esr) || !text(" ELR=") || !hex(elr) ||
        !text(" FAR_RAW=") || !hex(far) || !text(" SPSR=") || !hex(spsr) ||
        !text("\r\n")) return;
    (void)rpi5_uart_drain(UART10_BASE, POLL_BUDGET);
}

void probe_main(uintptr_t fdt_pa)
{
    uint64_t midr, mpidr, el, frequency;
    __asm__ volatile("mrs %0, midr_el1" : "=r"(midr));
    __asm__ volatile("mrs %0, mpidr_el1" : "=r"(mpidr));
    __asm__ volatile("mrs %0, CurrentEL" : "=r"(el));
    __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(frequency));
    console_owner = mpidr & 0xff00ffffffull;
    console_owner_valid = 1;
    __asm__ volatile("dsb sy" ::: "memory");
    struct rpi5_uart_snapshot uart;
    if (rpi5_uart_snapshot(UART10_BASE, &uart) != RPI5_UART_OK) return;
    if (!text("RPI5XNU:BL33:UART BASE=") || !hex(UART10_BASE) ||
        !text(" CR=") || !hex(uart.control) || !text(" FR=") || !hex(uart.flags) ||
        !text(" IBRD=") || !hex(uart.integer_divisor) ||
        !text(" FBRD=") || !hex(uart.fractional_divisor) ||
        !text(" LCRH=") || !hex(uart.line_control) ||
        !text(" FIRMWARE_PRESERVED_CLOCK_UNVERIFIED\r\n")) return;
    if (!text("RPI5XNU:BL33:ENTRY EL=") || !hex(el) ||
        !text(" MIDR=") || !hex(midr) || !text(" MPIDR=") || !hex(mpidr) ||
        !text(" CNTFRQ=") || !hex(frequency) || !text(" FDT_PA=") || !hex(fdt_pa) ||
        !text("\r\nRPI5XNU:BL33:ENTERING EL1\r\n")) return;
    (void)rpi5_uart_drain(UART10_BASE, POLL_BUDGET);
}

static int primary_feature_inventory(void)
{
    capture_features(primary_features);
    /* Baseline AArch64 ID registers only: do not read optional SVE ID registers
     * on an A76. Raw values are evidence, not a claim of XNU compatibility. */
    uint64_t pfr0 = primary_features[0], pfr1 = primary_features[1];
    uint64_t mmfr0 = primary_features[2], mmfr1 = primary_features[3], mmfr2 = primary_features[4];
    uint64_t isar0 = primary_features[5], isar1 = primary_features[6];
    uint64_t ctr = primary_features[7], dczid = primary_features[8];
    return text("RPI5XNU:BL33:PRIMARY_FEATURES PFR0=") && hex(pfr0) &&
        text(" PFR1=") && hex(pfr1) && text(" MMFR0=") && hex(mmfr0) &&
        text(" MMFR1=") && hex(mmfr1) && text(" MMFR2=") && hex(mmfr2) &&
        text(" ISAR0=") && hex(isar0) && text(" ISAR1=") && hex(isar1) &&
        text(" CTR=") && hex(ctr) && text(" DCZID=") && hex(dczid) &&
        text(" RAW_NOT_COMPATIBILITY_PROOF\r\n");
}

/* Unsupported PSCI must not silently skip the secondary evidence requirement. */
static int psci_secondary_probe(const struct rpi5_fdt_cpus *cpus)
{
    uint32_t version = (uint32_t)rpi5_psci_query(0x84000000u, 0);
    if (!text("RPI5XNU:BL33:PSCI VERSION_RAW=") || !hex(version)) return 0;
    if (version == UINT32_MAX || (version >> 16) < 1 || (version & 0x80000000u)) {
        (void)text(" UNSUPPORTED_STOP\r\n"); return 0;
    }
    uint32_t cpu_on = (uint32_t)rpi5_psci_query(0x8400000au, 0xc4000003u);
    uint32_t affinity = (uint32_t)rpi5_psci_query(0x8400000au, 0xc4000004u);
    uint32_t cpu_off = (uint32_t)rpi5_psci_query(0x8400000au, 0x84000002u);
    if (!text(" CPU_ON_FEATURE_RAW=") || !hex(cpu_on) ||
        !text(" AFFINITY_INFO_FEATURE_RAW=") || !hex(affinity) ||
        !text(" CPU_OFF_FEATURE_RAW=") || !hex(cpu_off) || !text("\r\n")) return 0;
    if (affinity != 0 || cpu_on != 0 || cpu_off != 0) {
        (void)text("RPI5XNU:BL33:PSCI REQUIRED_FEATURE_UNSUPPORTED_STOP\r\n");
        return 0;
    }
    if (!psci_affinity_inventory(cpus)) return 0;
    return start_secondaries(cpus);
}

void probe_el1_main(uintptr_t fdt_pa)
{
    uint64_t el, sctlr, daif, counter;
    __asm__ volatile("mrs %0, CurrentEL" : "=r"(el));
    __asm__ volatile("mrs %0, sctlr_el1" : "=r"(sctlr));
    __asm__ volatile("mrs %0, daif" : "=r"(daif));
    __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(counter));
    if (!text("RPI5XNU:BL33:EL1 EL=") || !hex(el) ||
        !text(" SCTLR=") || !hex(sctlr) || !text(" DAIF=") || !hex(daif) ||
        !text(" CNTVCT=") || !hex(counter) || !text(" FDT_PA=") || !hex(fdt_pa) ||
        !text("\r\n")) return;
    if (el != 4 || (sctlr & 0x1005) || (daif & 0x3c0) != 0x3c0) {
        (void)text("RPI5XNU:BL33:PRIMARY EL1_STATE_REJECTED\r\n"); return;
    }
    struct rpi5_fdt_cpus cpus;
    if (!primary_feature_inventory()) return;
    if (!runtime_cpus(fdt_pa, &cpus)) {
        (void)text("RPI5XNU:BL33:FDT MEMORY_CPU_OR_PSCI_CONTRACT_REJECTED\r\n"); return;
    }
#if RPI5_GATE5_PCIE_TOPOLOGY
    /* runtime_cpus completed safe framing/window checks and returned: keep its
     * large frame off this decoder's call chain. No PCIe register access. */
    if (!pending_boot_data.ready || pending_boot_data.fdt_pa != fdt_pa ||
        rpi5_pcie_topology_log((const void *)fdt_pa, pending_boot_data.fdt_length, text, hex)) return;
#endif
    if (!psci_secondary_probe(&cpus)) return;
    gic_inventory();
    if (!timer_probe()) return;
    timer_irq_probe();
    if (!probe_irq_verified) {
        (void)text("RPI5XNU:BL33:PRIMARY IRQ_NOT_VERIFIED_STOP\r\n"); return;
    }
    if (!pending_boot_data.ready) return;
    pending_boot_data.ready=0;
    if (RPI5_XNU_TRANSFER) {
        /* One bounded observation window, no promise of XNU servicing it.
         * Require the already-armed firmware full-reset watchdog. Do not
         * change reset routing or enable a previously stopped watchdog. */
        if (!transfer_watchdog_base ||
            (read32(transfer_watchdog_base+0x1c)&0x30u)!=0x20u) return;
        if (!text("RPI5XNU:BL33:XNU_TRANSFER_PENDING WATCHDOG_15S SEED_COMMIT_NEXT\r\n") ||
            rpi5_uart_drain(UART10_BASE,POLL_BUDGET)!=RPI5_UART_OK) return;
        write32(transfer_watchdog_base+0x24,0x5a000000u|(15u<<16));
        __asm__ volatile("dsb sy" ::: "memory");
    }
    if (!firmware_seed_diagnostic(pending_boot_data.fdt_pa,pending_boot_data.fdt_length,
            pending_boot_data.tree,pending_boot_data.encoded,pending_boot_data.capacity,
            pending_boot_data.handoff,pending_boot_data.tree_pa)) return;
    if (RPI5_XNU_TRANSFER)
        rpi5_transfer(pending_boot_data.handoff->args_pa,pending_boot_data.handoff->kernel.entry);
    if (!text("RPI5XNU:BL33:STOP BEFORE XNU LOADER\r\n")) return;
    (void)rpi5_uart_drain(UART10_BASE, POLL_BUDGET);
}
