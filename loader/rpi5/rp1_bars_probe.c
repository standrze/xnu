/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_bars_probe.h"

int rpi5_rp1_bars_write_allowed(const struct rpi5_rp1_bars_probe *s,
    const struct rpi5_pcie_config_request *r)
{
    if (!s || !r || s->selected>=6 || r->bus!=1 || r->device || r->function ||
        r->offset!=0x10+4*s->selected || r->width!=4 || r->write!=1) return 0;
    return (s->state==RPI5_RP1_BARS_PROBING &&
            s->writes_started==2*s->selected+1 && r->value==UINT32_MAX) ||
        (s->state==RPI5_RP1_BARS_RESTORING &&
            s->writes_started==2*s->selected+2 && r->value==s->originals[s->selected]);
}
static int read_config(struct rpi5_rp1_bars_probe *s,struct rpi5_pcie_config *c,
    uint32_t offset,uint32_t *out)
{
    const struct rpi5_pcie_config_request r={1,0,0,offset,4,0,0};
    s->transactions++;
    return rpi5_pcie_config_transfer(c,&r,out);
}
static int write_config(struct rpi5_rp1_bars_probe *s,struct rpi5_pcie_config *c,uint32_t value)
{
    const struct rpi5_pcie_config_request r={1,0,0,0x10+4*s->selected,4,1,value};
    s->writes_started++;s->transactions++;
    return rpi5_rp1_bars_write_allowed(s,&r) ? rpi5_pcie_config_transfer(c,&r,0) : -1;
}
int rpi5_rp1_bars_probe(struct rpi5_rp1_bars_probe *s,struct rpi5_pcie_config *c,
    const struct rpi5_rp1_config_snapshot *snapshot,struct rpi5_rp1_bars_size *out)
{
    if (!s || !c || !snapshot || !out) return -1;
    if (s->state!=RPI5_RP1_BARS_EMPTY) return -2;
    s->state=RPI5_RP1_BARS_CHECKING;s->transactions=s->writes_started=0;
    int rc=-3;uint32_t value;
    struct rpi5_rp1_bars_size result={0};
    if (snapshot->header[0]!=UINT32_C(0x00011de4) || snapshot->header[3]&0x00ff0000 ||
        snapshot->header[12]&1 || snapshot->command&7 ||
        snapshot->command!=(snapshot->header[1]&0xffff) ||
        snapshot->bar1_pci_base!=snapshot->header[5]) goto failed;
    for(unsigned i=0;i<6;i++) {
        if(snapshot->header[4+i]&15)goto failed;
        s->originals[i]=snapshot->header[4+i];
        result.bar[i].original=s->originals[i];
    }
#define READ(off) do { if(read_config(s,c,(off),&value)){rc=-4;goto failed;} } while(0)
#define EXPECT(off,mask,want) do {READ(off);if((value&(mask))!=(want)){rc=-5;goto failed;}} while(0)
    EXPECT(0,UINT32_MAX,snapshot->header[0]);
    EXPECT(4,0xffff,snapshot->command);result.command=value&0xffff;
    EXPECT(0xc,0x00ff0000,0);EXPECT(0x30,1,0);
    for(unsigned i=0;i<6;i++)EXPECT(0x10+4*i,UINT32_MAX,s->originals[i]);
    /* Standard size-mask/read/restore sequence; Apple's IOPCIConfigurator
     * follows this same PCI protocol. No upstream implementation copied. */
    for(unsigned i=0;i<6;i++) {
        s->selected=i;s->state=RPI5_RP1_BARS_PROBING;
        if(write_config(s,c,UINT32_MAX)){rc=-4;goto failed;}
        READ(0x10+4*i);result.bar[i].mask=value;
        if (!value) {
            if(s->originals[i] || i==1){rc=-6;goto failed;}
        } else {
            uint32_t size=~value+1u;
            if((value&15) || size<16 || (size&(size-1)) || (s->originals[i]&(size-1))) {
                rc=-6;goto failed;
            }
            result.bar[i].size=size;result.present|=1u<<i;
        }
        EXPECT(4,0xffff,result.command);
        s->state=RPI5_RP1_BARS_RESTORING;
        if(write_config(s,c,s->originals[i])){rc=-4;goto failed;}
        s->state=RPI5_RP1_BARS_VERIFYING;
        EXPECT(0x10+4*i,UINT32_MAX,s->originals[i]);
    }
    EXPECT(4,0xffff,result.command);EXPECT(0,UINT32_MAX,snapshot->header[0]);EXPECT(0x30,1,0);
    for(unsigned i=0;i<6;i++)EXPECT(0x10+4*i,UINT32_MAX,s->originals[i]);
    result.transactions=s->transactions;*out=result;
    s->state=RPI5_RP1_BARS_COMPLETE;return 0;
failed:
    s->state=RPI5_RP1_BARS_FAILED;return rc;
#undef EXPECT
#undef READ
}
