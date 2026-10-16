/* SPDX-License-Identifier: BSD-2-Clause */
#include "fdt.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
    assert(argc==2);
    FILE *f=fopen(argv[1],"rb"); assert(f);
    assert(!fseek(f,0,SEEK_END)); long n=ftell(f); assert(n>0); rewind(f);
    unsigned char *b=malloc((size_t)n); assert(b);
    assert(fread(b,1,(size_t)n,f)==(size_t)n); fclose(f);
    struct rpi5_fdt_sdhci out, prior;
    memset(&prior,0xa5,sizeof prior);
    assert(!rpi5_fdt_sdhci(b,(size_t)n,&out));
    assert(out.host.start==0x1000fff000ull && out.host.end==0x1000fff260ull);
    assert(out.cfg.start==0x1000fff400ull && out.cfg.end==0x1000fff600ull);
    assert(out.source_hz==200000000 && out.irq==305 && out.bus_width==4);
    assert(out.vmmc && out.vqmmc && out.vmmc!=out.vqmmc);
    struct rpi5_fdt_sd_power power, power_prior;
    memset(&power_prior,0x5a,sizeof power_prior);
    assert(!rpi5_fdt_sd_power(b,(size_t)n,&power));
    assert(power.gpio.start==0x107d517c00ull && power.gpio.end==0x107d517c40ull);
    assert(power.pins.start==0x107d504100ull && power.pins.end==0x107d504130ull);
    assert(power.aon_pins.start==0x107d510700ull && power.aon_pins.end==0x107d510720ull);
    assert(power.variant==0 && power.settling_us==5000);
    assert(rpi5_fdt_sd_power(b,(size_t)n,0)==-1);
    assert(rpi5_fdt_sd_power(0,(size_t)n,&power)==-1);
    assert(rpi5_fdt_sdhci(b,(size_t)n,0)==-1);
    assert(rpi5_fdt_sdhci(0,(size_t)n,&out)==-1);
    const char *slot="/soc@107c000000/mmc@fff000";
    struct { const char *path, *name; } cases[]={
        {slot,"reg"},{slot,"reg-names"},{slot,"interrupts"},
        {slot,"clocks"},{slot,"bus-width"},{slot,"status"},
        {slot,"vmmc-supply"},{slot,"vqmmc-supply"},
        {"/clocks/clk-emmc2","clock-frequency"},
        {"/clocks/clk-emmc2","#clock-cells"},
        {"/clocks/clk-emmc2","phandle"},
        {"/","interrupt-parent"},
        {"/soc@107c000000/interrupt-controller@7fff9000","#interrupt-cells"},
        {"/sd-vcc-reg","phandle"},{"/sd-io-1v8-reg","phandle"},
    };
    for (unsigned i=0;i<sizeof cases/sizeof cases[0];i++) {
        struct rpi5_fdt_property p;
        assert(!rpi5_fdt_property(b,(size_t)n,cases[i].path,cases[i].name,&p));
        for (unsigned j=0;j<p.length;j++) {
            b[p.offset+j]^=1; out=prior;
            assert(rpi5_fdt_sdhci(b,(size_t)n,&out)==-1);
            assert(!memcmp(&out,&prior,sizeof out));
            b[p.offset+j]^=1;
        }
    }
    /* The other enabled BCM2712 controller must never substitute for the slot. */
    struct rpi5_fdt_property p;
    assert(!rpi5_fdt_property(b,(size_t)n,slot,"compatible",&p));
    b[p.offset]^=1; out=prior;
    assert(rpi5_fdt_sdhci(b,(size_t)n,&out)==-1);
    assert(!memcmp(&out,&prior,sizeof out));
    b[p.offset]^=1;
    assert(!rpi5_fdt_sdhci(b,(size_t)n,&out));
    for (unsigned cut=0;cut<40;cut++) {
        out=prior;
        assert(rpi5_fdt_sdhci(b,cut,&out)==-1);
        assert(!memcmp(&out,&prior,sizeof out));
    }
    const char *gpio="/soc@107c000000/gpio@7d517c00";
    const char *pins="/soc@107c000000/pinctrl@7d504100";
    const char *aon="/soc@107c000000/pinctrl@7d510700";
    const char *pulls="/soc@107c000000/pinctrl@7d504100/emmc_sd_pulls";
    const char *cd="/soc@107c000000/pinctrl@7d510700/emmc_aon_cd_pins";
    struct { const char *path,*name; } power_cases[]={
        {slot,"reg"},{slot,"pinctrl-0"},{slot,"pinctrl-names"},{slot,"cd-gpios"},
        {gpio,"reg"},{gpio,"phandle"},{gpio,"#gpio-cells"},{gpio,"brcm,gpio-bank-widths"},
        {pins,"reg"},{pins,"compatible"},{aon,"reg"},{aon,"compatible"},
        {pulls,"pins"},{pulls,"phandle"},{cd,"function"},{cd,"pins"},{cd,"phandle"},
        {"/sd-vcc-reg","gpios"},{"/sd-vcc-reg","regulator-min-microvolt"},
        {"/sd-vcc-reg","regulator-max-microvolt"},
        {"/sd-io-1v8-reg","gpios"},{"/sd-io-1v8-reg","states"},
        {"/sd-io-1v8-reg","regulator-min-microvolt"},
        {"/sd-io-1v8-reg","regulator-max-microvolt"},
        {"/sd-io-1v8-reg","regulator-settling-time-us"},
    };
    for (unsigned i=0;i<sizeof power_cases/sizeof power_cases[0];i++) {
        assert(!rpi5_fdt_property(b,(size_t)n,power_cases[i].path,power_cases[i].name,&p));
        for (unsigned j=0;j<p.length;j++) {
            b[p.offset+j]^=1; power=power_prior;
            assert(rpi5_fdt_sd_power(b,(size_t)n,&power)==-1);
            assert(!memcmp(&power,&power_prior,sizeof power));
            b[p.offset+j]^=1;
        }
    }
    /* D0 has different pad layout: accept only a matched pair, never mix. */
    struct rpi5_fdt_property pp,ap;
    assert(!rpi5_fdt_property(b,(size_t)n,pins,"compatible",&pp));
    assert(!rpi5_fdt_property(b,(size_t)n,aon,"compatible",&ap));
    assert(b[pp.offset+12]=='c' && b[ap.offset+12]=='c');
    b[pp.offset+12]='d';
    power=power_prior; assert(rpi5_fdt_sd_power(b,(size_t)n,&power)==-1);
    assert(!memcmp(&power,&power_prior,sizeof power));
    b[ap.offset+12]='d';
    assert(!rpi5_fdt_sd_power(b,(size_t)n,&power) && power.variant==1);
    b[pp.offset+12]='c'; b[ap.offset+12]='c';
    /* Required empty properties must still exist, not silently default. */
    struct {const char *path,*name;} flags[]={
        {gpio,"gpio-controller"},{gpio,"brcm,gpio-direct"},
        {pulls,"bias-pull-up"},{cd,"bias-pull-up"},{"/sd-vcc-reg","enable-active-high"},
    };
    for (unsigned i=0;i<sizeof flags/sizeof flags[0];i++) {
        assert(!rpi5_fdt_property(b,(size_t)n,flags[i].path,flags[i].name,&p));
        /* FDT_PROP token precedes length/name; turn it into NOP, preserving framing. */
        unsigned char saved[12]; memcpy(saved,b+p.offset-12,12);
        for (unsigned j=0;j<12;j+=4) { memset(b+p.offset-12+j,0,4); b[p.offset-12+j+3]=4; }
        power=power_prior; assert(rpi5_fdt_sd_power(b,(size_t)n,&power)==-1);
        assert(!memcmp(&power,&power_prior,sizeof power));
        memcpy(b+p.offset-12,saved,12);
    }
    assert(!rpi5_fdt_sd_power(b,(size_t)n,&power));
    free(b); puts("SDHCI_FDT_PASS"); return 0;
}
