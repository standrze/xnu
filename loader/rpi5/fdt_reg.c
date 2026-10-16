/* SPDX-License-Identifier: BSD-2-Clause */
#include "fdt.h"
static uint64_t cells(const uint8_t *p, unsigned n)
{
    uint64_t v=0;
    for (unsigned i=0;i<n*4;i++) v=(v<<8)|p[i];
    return v;
}
static int compatible(const void *buffer, size_t size, const char *path, const char *want)
{
    struct rpi5_fdt_property prop;
    if (rpi5_fdt_property(buffer,size,path,"compatible",&prop)) return 0;
    const uint8_t *data=(const uint8_t *)buffer+prop.offset;
    size_t pos=0, wanted=0;
    while (want[wanted]) wanted++;
    int matched=0;
    while (pos<prop.length) {
        size_t start=pos;
        while (pos<prop.length && data[pos]) pos++;
        if (pos==prop.length || pos==start) return 0;
        if (pos-start==wanted) {
            int same=1;
            for (size_t i=0;i<wanted;i++) if (data[start+i]!=(uint8_t)want[i]) same=0;
            matched|=same;
        }
        pos++;
    }
    return matched;
}
int rpi5_fdt_probe_mmio(const void *buffer, size_t available)
{
    const char *uart="/soc@107c000000/serial@7d001000";
    const char *gic="/soc@107c000000/interrupt-controller@7fff9000";
    struct rpi5_ranges ranges;
    if (!compatible(buffer,available,uart,"arm,pl011") ||
        !compatible(buffer,available,gic,"arm,gic-400") ||
        rpi5_fdt_reg(buffer,available,uart,&ranges) || ranges.count!=1 ||
        ranges.extent[0].start!=0x107d001000ull || ranges.extent[0].end!=0x107d001200ull) return -1;
    if (rpi5_fdt_reg(buffer,available,gic,&ranges) || ranges.count!=4) return -1;
    const struct rpi5_range expected[4]={
        {0x107fff9000ull,0x107fffa000ull}, {0x107fffa000ull,0x107fffc000ull},
        {0x107fffc000ull,0x107fffe000ull}, {0x107fffe000ull,0x1080000000ull},
    };
    for (size_t i=0;i<4;i++)
        if (ranges.extent[i].start!=expected[i].start || ranges.extent[i].end!=expected[i].end) return -1;
    return 0;
}
static int width(const void *b, size_t size, const char *path, const char *name)
{
    struct rpi5_fdt_property p;
    if (rpi5_fdt_property(b,size,path,name,&p) || p.length!=4) return -1;
    uint64_t n=cells((const uint8_t *)b+p.offset,1);
    return n==1 || n==2 ? (int)n : -1;
}
static int fits(uint64_t base, uint64_t size, unsigned n)
{
    if (!size || size>UINT64_MAX-base) return 0;
    return n==2 || base+size<=(1ull<<32);
}
static int enabled(const void *b, size_t size, const char *path)
{
    struct rpi5_fdt_property p;
    int rc=rpi5_fdt_property(b,size,path,"status",&p);
    if (rc==-2) return 1;
    if (rc) return 0;
    const uint8_t *v=(const uint8_t *)b+p.offset;
    return (p.length==3 && v[0]=='o' && v[1]=='k' && !v[2]) ||
        (p.length==5 && v[0]=='o' && v[1]=='k' && v[2]=='a' && v[3]=='y' && !v[4]);
}
static int u32_property(const void *b, size_t size, const char *path,
    const char *name, uint32_t *value)
{
    struct rpi5_fdt_property p;
    if (rpi5_fdt_property(b,size,path,name,&p) || p.length!=4) return -1;
    *value=(uint32_t)cells((const uint8_t *)b+p.offset,1);
    return 0;
}
static int exact_property(const void *b, size_t size, const char *path,
    const char *name, const void *wanted, size_t length)
{
    struct rpi5_fdt_property p;
    if (rpi5_fdt_property(b,size,path,name,&p) || p.length!=length) return 0;
    const uint8_t *data=(const uint8_t *)b+p.offset, *value=wanted;
    for (size_t i=0;i<length;i++) if (data[i]!=value[i]) return 0;
    return 1;
}
static int exact_cells(const void *b, size_t size, const char *path,
    const char *name, const uint32_t *wanted, unsigned count)
{
    struct rpi5_fdt_property p;
    if (rpi5_fdt_property(b,size,path,name,&p) || p.length!=(uint64_t)count*4) return 0;
    for (unsigned i=0;i<count;i++)
        if (cells((const uint8_t *)b+p.offset+i*4,1)!=wanted[i]) return 0;
    return 1;
}
int rpi5_fdt_sd_power(const void *b, size_t size, struct rpi5_fdt_sd_power *out)
{
    const char *slot="/soc@107c000000/mmc@fff000";
    const char *gpio="/soc@107c000000/gpio@7d517c00";
    const char *pins="/soc@107c000000/pinctrl@7d504100";
    const char *aon="/soc@107c000000/pinctrl@7d510700";
    const char *pulls="/soc@107c000000/pinctrl@7d504100/emmc_sd_pulls";
    const char *cd="/soc@107c000000/pinctrl@7d510700/emmc_aon_cd_pins";
    const char *vcc="/sd-vcc-reg", *vio="/sd-io-1v8-reg";
    struct rpi5_fdt_sd_power result={0};
    struct rpi5_fdt_sdhci sd;
    struct rpi5_ranges ranges;
    struct rpi5_fdt_property p;
    uint32_t gh, ph, ch, n;
    if (!out || rpi5_fdt_sdhci(b,size,&sd) ||
        !compatible(b,size,gpio,"brcm,brcmstb-gpio") ||
        rpi5_fdt_reg(b,size,gpio,&ranges) || ranges.count!=1 ||
        ranges.extent[0].start!=0x107d517c00ull || ranges.extent[0].end!=0x107d517c40ull)
        return -1;
    result.gpio=ranges.extent[0];
    /* The firmware monitors PMIC interrupts here. Never claim its controller. */
    if (!exact_property(b,size,gpio,"gpio-controller",0,0) ||
        !exact_property(b,size,gpio,"brcm,gpio-direct",0,0) ||
        rpi5_fdt_property(b,size,gpio,"interrupt-controller",&p)!=-2 ||
        rpi5_fdt_property(b,size,gpio,"#interrupt-cells",&p)!=-2 ||
        u32_property(b,size,gpio,"#gpio-cells",&n) || n!=2 ||
        u32_property(b,size,gpio,"phandle",&gh) || !gh ||
        !exact_cells(b,size,gpio,"brcm,gpio-bank-widths",(uint32_t[]){17,6},2)) return -1;
    if (rpi5_fdt_reg(b,size,pins,&ranges) || ranges.count!=1 ||
        ranges.extent[0].start!=0x107d504100ull || ranges.extent[0].end!=0x107d504130ull)
        return -1;
    result.pins=ranges.extent[0];
    if (rpi5_fdt_reg(b,size,aon,&ranges) || ranges.count!=1 ||
        ranges.extent[0].start!=0x107d510700ull || ranges.extent[0].end!=0x107d510720ull)
        return -1;
    result.aon_pins=ranges.extent[0];
    /* Exact strings, not overlapping compatible lists: pad layouts differ. */
    static const char c0[]="brcm,bcm2712c0-pinctrl", ca0[]="brcm,bcm2712c0-aon-pinctrl";
    static const char d0[]="brcm,bcm2712d0-pinctrl", da0[]="brcm,bcm2712d0-aon-pinctrl";
    if (exact_property(b,size,pins,"compatible",c0,sizeof c0) &&
        exact_property(b,size,aon,"compatible",ca0,sizeof ca0)) result.variant=0;
    else if (exact_property(b,size,pins,"compatible",d0,sizeof d0) &&
        exact_property(b,size,aon,"compatible",da0,sizeof da0)) result.variant=1;
    else return -1;
    if (!enabled(b,size,pulls) || !enabled(b,size,cd) ||
        u32_property(b,size,pulls,"phandle",&ph) || !ph ||
        u32_property(b,size,cd,"phandle",&ch) || !ch ||
        !exact_cells(b,size,slot,"pinctrl-0",(uint32_t[]){ph,ch},2) ||
        !exact_property(b,size,slot,"pinctrl-names","default",sizeof "default") ||
        !exact_property(b,size,pulls,"pins","emmc_cmd\0emmc_dat0\0emmc_dat1\0emmc_dat2\0emmc_dat3",
            sizeof "emmc_cmd\0emmc_dat0\0emmc_dat1\0emmc_dat2\0emmc_dat3") ||
        !exact_property(b,size,pulls,"bias-pull-up",0,0) ||
        !exact_property(b,size,cd,"pins","aon_gpio5",sizeof "aon_gpio5") ||
        !exact_property(b,size,cd,"function","sd_card_g",sizeof "sd_card_g") ||
        !exact_property(b,size,cd,"bias-pull-up",0,0) ||
        !exact_cells(b,size,slot,"cd-gpios",(uint32_t[]){gh,5,1},3)) return -1;
    if (!exact_cells(b,size,vcc,"gpios",(uint32_t[]){gh,4,0},3) ||
        !exact_property(b,size,vcc,"enable-active-high",0,0) ||
        !exact_cells(b,size,vcc,"regulator-min-microvolt",(uint32_t[]){3300000},1) ||
        !exact_cells(b,size,vcc,"regulator-max-microvolt",(uint32_t[]){3300000},1) ||
        !exact_cells(b,size,vio,"gpios",(uint32_t[]){gh,3,0},3) ||
        !exact_cells(b,size,vio,"states",(uint32_t[]){1800000,1,3300000,0},4) ||
        !exact_cells(b,size,vio,"regulator-min-microvolt",(uint32_t[]){1800000},1) ||
        !exact_cells(b,size,vio,"regulator-max-microvolt",(uint32_t[]){3300000},1) ||
        u32_property(b,size,vio,"regulator-settling-time-us",&result.settling_us) ||
        result.settling_us!=5000) return -1;
    /* Alternative enable GPIOs, parent supply control and extra pin states
     * require a reviewed sequence rather than silently ignored declarations. */
    const char *regs[2]={vcc,vio};
    const char *extras[]={"gpio","enable-gpios","enable-gpio","vin-supply","pinctrl-0","gpio-open-drain"};
    for (unsigned i=0;i<2;i++) for (unsigned j=0;j<sizeof extras/sizeof extras[0];j++)
        if (rpi5_fdt_property(b,size,regs[i],extras[j],&p)!=-2) return -1;
    if (rpi5_fdt_property(b,size,vio,"enable-active-high",&p)!=-2 ||
        rpi5_fdt_property(b,size,pulls,"function",&p)!=-2 ||
        rpi5_fdt_property(b,size,pulls,"bias-disable",&p)!=-2 ||
        rpi5_fdt_property(b,size,pulls,"bias-pull-down",&p)!=-2 ||
        rpi5_fdt_property(b,size,cd,"bias-disable",&p)!=-2 ||
        rpi5_fdt_property(b,size,cd,"bias-pull-down",&p)!=-2) return -1;
    *out=result;
    return 0;
}
int rpi5_fdt_sdhci(const void *buffer, size_t available, struct rpi5_fdt_sdhci *out)
{
    const char *slot="/soc@107c000000/mmc@fff000";
    const char *soc="/soc@107c000000";
    const char *gic="/soc@107c000000/interrupt-controller@7fff9000";
    const char *clock="/clocks/clk-emmc2";
    struct rpi5_fdt_sdhci result={0};
    struct rpi5_ranges ranges;
    struct rpi5_fdt_property p;
    uint32_t handle, parent_handle, n, clock_handle, supply_handle;
    if (!buffer || !out || rpi5_fdt_phandles(buffer,available) ||
        !compatible(buffer,available,"/","raspberrypi,5-model-b") ||
        !compatible(buffer,available,"/","brcm,bcm2712") ||
        !compatible(buffer,available,slot,"brcm,bcm2712-sdhci") ||
        !compatible(buffer,available,gic,"arm,gic-400") ||
        !enabled(buffer,available,gic) ||
        rpi5_fdt_reg(buffer,available,slot,&ranges) || ranges.count!=2 ||
        ranges.extent[0].start!=0x1000fff000ull || ranges.extent[0].end!=0x1000fff260ull ||
        ranges.extent[1].start!=0x1000fff400ull || ranges.extent[1].end!=0x1000fff600ull)
        return -1;
    result.host=ranges.extent[0]; result.cfg=ranges.extent[1];
    static const char names[]="host\0cfg";
    if (rpi5_fdt_property(buffer,available,slot,"reg-names",&p) ||
        p.length!=sizeof names) return -1;
    const uint8_t *b=buffer;
    for (unsigned i=0;i<sizeof names;i++) if (b[p.offset+i]!=(uint8_t)names[i]) return -1;
    /* Do not let an explicit ancestor override silently reroute the binding. */
    if (u32_property(buffer,available,gic,"phandle",&handle) || !handle ||
        u32_property(buffer,available,"/","interrupt-parent",&parent_handle) ||
        parent_handle!=handle ||
        u32_property(buffer,available,gic,"#interrupt-cells",&n) || n!=3 ||
        rpi5_fdt_property(buffer,available,gic,"interrupt-controller",&p) || p.length)
        return -1;
    const char *paths[2]={soc,slot};
    for (unsigned i=0;i<2;i++) {
        int rc=rpi5_fdt_property(buffer,available,paths[i],"interrupt-parent",&p);
        if (rc==-2) continue;
        if (rc || p.length!=4 || cells(b+p.offset,1)!=handle) return -1;
    }
    if (rpi5_fdt_property(buffer,available,slot,"interrupts-extended",&p)!=-2 ||
        rpi5_fdt_property(buffer,available,slot,"interrupts",&p) || p.length!=12 ||
        cells(b+p.offset,1)!=0 || cells(b+p.offset+4,1)!=273 ||
        cells(b+p.offset+8,1)!=4) return -1;
    result.irq=273+32;
    if (!enabled(buffer,available,"/clocks") || !enabled(buffer,available,clock) ||
        !compatible(buffer,available,clock,"fixed-clock") ||
        u32_property(buffer,available,clock,"phandle",&clock_handle) || !clock_handle ||
        u32_property(buffer,available,clock,"#clock-cells",&n) || n ||
        u32_property(buffer,available,slot,"clocks",&n) || n!=clock_handle ||
        u32_property(buffer,available,clock,"clock-frequency",&result.source_hz) ||
        result.source_hz!=200000000 ||
        u32_property(buffer,available,slot,"bus-width",&result.bus_width) || result.bus_width!=4 ||
        rpi5_fdt_property(buffer,available,slot,"non-removable",&p)!=-2 ||
        rpi5_fdt_property(buffer,available,slot,"mmc-pwrseq",&p)!=-2)
        return -1;
    if (u32_property(buffer,available,slot,"vmmc-supply",&result.vmmc) ||
        u32_property(buffer,available,slot,"vqmmc-supply",&result.vqmmc) ||
        !enabled(buffer,available,"/sd-vcc-reg") || !enabled(buffer,available,"/sd-io-1v8-reg") ||
        !compatible(buffer,available,"/sd-vcc-reg","regulator-fixed") ||
        !compatible(buffer,available,"/sd-io-1v8-reg","regulator-gpio") ||
        u32_property(buffer,available,"/sd-vcc-reg","phandle",&supply_handle) ||
        !supply_handle || supply_handle!=result.vmmc ||
        u32_property(buffer,available,"/sd-io-1v8-reg","phandle",&supply_handle) ||
        !supply_handle || supply_handle!=result.vqmmc)
        return -1;
    *out=result;
    return 0;
}
int rpi5_fdt_uart_irq(const void *buffer, size_t available)
{
    const char *uart="/soc@107c000000/serial@7d001000";
    const char *soc="/soc@107c000000";
    const char *gic="/soc@107c000000/interrupt-controller@7fff9000";
    struct rpi5_fdt_property root_parent, gic_handle, gic_cells, irq, override;
    if (!buffer || !enabled(buffer,available,uart) || !enabled(buffer,available,gic) ||
        !compatible(buffer,available,uart,"arm,pl011") ||
        !compatible(buffer,available,gic,"arm,gic-400") ||
        rpi5_fdt_property(buffer,available,"/","interrupt-parent",&root_parent) ||
        rpi5_fdt_property(buffer,available,gic,"phandle",&gic_handle) ||
        rpi5_fdt_property(buffer,available,gic,"#interrupt-cells",&gic_cells) ||
        rpi5_fdt_property(buffer,available,uart,"interrupts",&irq) ||
        root_parent.length!=4 || gic_handle.length!=4 || gic_cells.length!=4 ||
        irq.length!=12) return -1;
    const uint8_t *b=buffer;
    uint64_t handle=cells(b+gic_handle.offset,1);
    if (!handle || handle!=cells(b+root_parent.offset,1) ||
        cells(b+gic_cells.offset,1)!=3 || cells(b+irq.offset,1)!=0 ||
        cells(b+irq.offset+4,1)!=121 || cells(b+irq.offset+8,1)!=4) return -1;
    /* An explicit override at either ancestor must not silently reroute RX. */
    const char *paths[2]={soc,uart};
    for (unsigned i=0;i<2;i++) {
        int rc=rpi5_fdt_property(buffer,available,paths[i],"interrupt-parent",&override);
        if (rc==-2) continue;
        if (rc || override.length!=4 || cells(b+override.offset,1)!=handle) return -1;
    }
    return 0;
}
static void parent(char *path)
{
    size_t n=0;
    while (path[n]) n++;
    while (n>1 && path[n-1]!='/') n--;
    path[n==1?1:n-1]=0;
}
int rpi5_fdt_reg(const void *buffer, size_t available, const char *path,
    struct rpi5_ranges *out)
{
    if (!buffer || !path || !out || path[0]!='/' || !path[1]) return -1;
    char bus[1025]; size_t n=0;
    do { if (n==sizeof(bus)) return -1; bus[n]=path[n]; } while (path[n++]);
    if (!enabled(buffer,available,bus)) return -1;
    struct rpi5_fdt_property prop;
    if (rpi5_fdt_property(buffer,available,bus,"reg",&prop)) return -1;
    parent(bus);
    int ac=width(buffer,available,bus,"#address-cells"), sc=width(buffer,available,bus,"#size-cells");
    if (ac<0 || sc<0) return -1;
    unsigned stride=(unsigned)(ac+sc)*4;
    if (!prop.length || prop.length%stride || prop.length/stride>8) return -1;
    struct rpi5_ranges result={0};
    const uint8_t *b=buffer;
    for (uint32_t pos=0;pos<prop.length;pos+=stride) {
        uint64_t start=cells(b+prop.offset+pos,(unsigned)ac), size=cells(b+prop.offset+pos+ac*4,(unsigned)sc);
        if (!fits(start,size,(unsigned)ac)) return -1;
        result.extent[result.count++]=(struct rpi5_range){start,start+size};
    }
    for (;;) {
        if (!enabled(buffer,available,bus)) return -1;
        if (!bus[1]) break;
        ac=width(buffer,available,bus,"#address-cells"); sc=width(buffer,available,bus,"#size-cells");
        if (ac<0 || sc<0 || rpi5_fdt_property(buffer,available,bus,"ranges",&prop)) return -1;
        parent(bus);
        int pc=width(buffer,available,bus,"#address-cells");
        if (pc<0) return -1;
        stride=(unsigned)(ac+pc+sc)*4;
        if (prop.length%stride || prop.length/stride>32) return -1;
        for (size_t i=0;i<result.count;i++) {
            uint64_t start=result.extent[i].start, size=result.extent[i].end-start, translated=start;
            unsigned matches=prop.length?0:1;
            for (uint32_t pos=0;pos<prop.length;pos+=stride) {
                const uint8_t *row=b+prop.offset+pos;
                uint64_t child=cells(row,(unsigned)ac), host=cells(row+ac*4,(unsigned)pc);
                uint64_t span=cells(row+(ac+pc)*4,(unsigned)sc);
                if (!fits(child,span,(unsigned)ac) || !fits(host,span,(unsigned)pc)) return -1;
                if (start>=child && start-child<=span && size<=span-(start-child)) {
                    translated=host+(start-child); matches++;
                }
            }
            if (matches!=1 || !fits(translated,size,(unsigned)pc)) return -1;
            result.extent[i]=(struct rpi5_range){translated,translated+size};
        }
    }
    for (size_t i=0;i<result.count;i++) if (result.extent[i].end>(1ull<<40)) return -1;
    *out=result;
    return 0;
}

int rpi5_fdt_probe_timer(const void *buffer, size_t available)
{
    const char *gic="/soc@107c000000/interrupt-controller@7fff9000";
    const uint8_t *b=buffer;
    struct rpi5_fdt_property prop;
    if (!compatible(buffer,available,"/timer","arm,armv8-timer") ||
        !enabled(buffer,available,"/timer")) return -1;
    /* Named/extended interrupt forms need their own decoding, never guess. */
    if (rpi5_fdt_property(buffer,available,"/timer","interrupt-names",&prop)!=-2 ||
        rpi5_fdt_property(buffer,available,"/timer","interrupts-extended",&prop)!=-2) return -1;
    if (rpi5_fdt_property(buffer,available,gic,"#interrupt-cells",&prop) ||
        prop.length!=4 || cells(b+prop.offset,1)!=3) return -1;
    if (rpi5_fdt_property(buffer,available,gic,"interrupt-controller",&prop) || prop.length) return -1;
    if (rpi5_fdt_property(buffer,available,gic,"phandle",&prop) || prop.length!=4) return -1;
    uint64_t phandle=cells(b+prop.offset,1);
    if (!phandle || phandle==UINT32_MAX) return -1;
    int rc=rpi5_fdt_property(buffer,available,"/timer","interrupt-parent",&prop);
    if (rc==-2) rc=rpi5_fdt_property(buffer,available,"/","interrupt-parent",&prop);
    if (rc || prop.length!=4 || cells(b+prop.offset,1)!=phandle) return -1;
    /* ARM timer binding permits a fifth (EL2 virtual) interrupt. Accept only
     * the observed Pi profile; this does not enable VHE or use that timer. */
    if (rpi5_fdt_property(buffer,available,"/timer","interrupts",&prop) ||
        (prop.length!=48 && prop.length!=60)) return -1;
    const uint32_t ppi[5]={13,14,11,10,12};
    for (size_t i=0;i<prop.length/12;i++) {
        const uint8_t *row=b+prop.offset+i*12;
        if (cells(row,1)!=1 || cells(row+4,1)!=ppi[i] || cells(row+8,1)!=0xf08) return -1;
    }
    return 0;
}

int rpi5_fdt_uart_clocks(const void *buffer, size_t available, struct rpi5_uart_clocks *out)
{
    if (!out) return -1;
    const char *uart="/soc@107c000000/serial@7d001000";
    const char *providers[2]={"/clocks/clk-uart","/clocks/clk-vpu"};
    const uint8_t *b=buffer;
    struct rpi5_fdt_property prop;
    static const uint8_t names[]="uartclk\0apb_pclk";
    if (!enabled(buffer,available,"/") || !enabled(buffer,available,"/clocks") ||
        !enabled(buffer,available,"/soc@107c000000") || !enabled(buffer,available,uart) ||
        rpi5_fdt_property(buffer,available,uart,"clock-names",&prop) || prop.length!=sizeof(names)) return -1;
    for (size_t i=0;i<sizeof(names);i++) if (b[prop.offset+i]!=names[i]) return -1;
    if (rpi5_fdt_property(buffer,available,uart,"clocks",&prop) || prop.length!=8) return -1;
    uint64_t handles[2]={cells(b+prop.offset,1),cells(b+prop.offset+4,1)};
    if (!handles[0] || !handles[1] || handles[0]==UINT32_MAX || handles[1]==UINT32_MAX || handles[0]==handles[1]) return -1;
    uint32_t rates[2];
    for (size_t i=0;i<2;i++) {
        const char *path=providers[i];
        if (!enabled(buffer,available,path) || !compatible(buffer,available,path,"fixed-clock") ||
            rpi5_fdt_property(buffer,available,path,"phandle",&prop) || prop.length!=4 || cells(b+prop.offset,1)!=handles[i]) return -1;
        if (rpi5_fdt_property(buffer,available,path,"#clock-cells",&prop) || prop.length!=4 || cells(b+prop.offset,1)) return -1;
        if (rpi5_fdt_property(buffer,available,path,"clock-frequency",&prop) || prop.length!=4 || !cells(b+prop.offset,1)) return -1;
        rates[i]=(uint32_t)cells(b+prop.offset,1);
    }
    *out=(struct rpi5_uart_clocks){rates[0],rates[1]};
    return 0;
}

int rpi5_fdt_rng200(const void *buffer, size_t available, struct rpi5_range *out)
{
    const char *path="/soc@107c000000/rng@7d208000";
    struct rpi5_ranges ranges;
    if (!out || !compatible(buffer,available,path,"brcm,bcm2711-rng200") ||
        rpi5_fdt_reg(buffer,available,path,&ranges) || ranges.count!=1 ||
        ranges.extent[0].start!=0x107d208000ull || ranges.extent[0].end!=0x107d208028ull) return -1;
    *out=ranges.extent[0];
    return 0;
}

int rpi5_fdt_watchdog(const void *buffer, size_t available, struct rpi5_range *out)
{
    const char *path="/soc@107c000000/watchdog@7d200000";
    struct rpi5_ranges ranges;
    if (!out || !compatible(buffer,available,path,"brcm,bcm2712-pm") ||
        rpi5_fdt_reg(buffer,available,path,&ranges) || ranges.count!=1 ||
        ranges.extent[0].start!=0x107d200000ull ||
        ranges.extent[0].end!=0x107d200308ull) return -1;
    *out=ranges.extent[0];
    return 0;
}
