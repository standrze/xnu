/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_bar1_probe.h"

int rpi5_rp1_bar1_write_allowed(const struct rpi5_rp1_bar1_probe *s,
    const struct rpi5_pcie_config_request *r)
{
    if (!s || !r || r->bus!=1 || r->device || r->function || r->offset!=0x14 ||
        r->width!=4 || r->write!=1) return 0;
    return (s->state==RPI5_RP1_BAR1_PROBING && s->writes_started==1 && r->value==UINT32_MAX) ||
        (s->state==RPI5_RP1_BAR1_RESTORING && s->writes_started==2 && r->value==s->original_bar1);
}
static int read_config(struct rpi5_rp1_bar1_probe *s,struct rpi5_pcie_config *c,
    uint32_t offset,uint32_t *out)
{
    const struct rpi5_pcie_config_request r={1,0,0,offset,4,0,0};
    s->transactions++;
    return rpi5_pcie_config_transfer(c,&r,out);
}
static int write_config(struct rpi5_rp1_bar1_probe *s,struct rpi5_pcie_config *c,uint32_t value)
{
    const struct rpi5_pcie_config_request r={1,0,0,0x14,4,1,value};
    s->writes_started++;s->transactions++;
    return rpi5_rp1_bar1_write_allowed(s,&r) ? rpi5_pcie_config_transfer(c,&r,0) : -1;
}
int rpi5_rp1_bar1_probe(struct rpi5_rp1_bar1_probe *s,struct rpi5_pcie_config *c,
    const struct rpi5_rp1_config_snapshot *snapshot,struct rpi5_rp1_bar1_size *out)
{
    if (!s || !c || !snapshot || !out) return -1;
    if (s->state!=RPI5_RP1_BAR1_EMPTY) return -2;
    s->state=RPI5_RP1_BAR1_CHECKING;s->transactions=s->writes_started=0;
    int rc=-3;uint32_t value,command=0,mask=0,size=0;
    if (snapshot->header[0]!=UINT32_C(0x00011de4) || snapshot->header[3]&0x00ff0000 ||
        snapshot->header[4]&15 || snapshot->header[5]&15 || snapshot->command&7 ||
        snapshot->command!=(snapshot->header[1]&0xffff) ||
        snapshot->bar1_pci_base!=snapshot->header[5]) goto failed;
    s->original_bar1=snapshot->bar1_pci_base;
#define READ(off) do { if(read_config(s,c,(off),&value)){rc=-4;goto failed;} } while(0)
#define EXPECT(off,mask,want) do {READ(off);if((value&(mask))!=(want)){rc=-5;goto failed;}} while(0)
    EXPECT(0,UINT32_MAX,snapshot->header[0]);
    EXPECT(4,0xffff,snapshot->command);command=value&0xffff;
    EXPECT(0xc,0x00ff0000,0);
    EXPECT(0x10,UINT32_MAX,snapshot->header[4]);
    EXPECT(0x14,UINT32_MAX,s->original_bar1);
    /* PCI mask-write/read/restore sequence, also used by Apple's unchanged
     * IOPCIConfigurator; the first diagnostic supports only BAR1 MEM32. */
    s->state=RPI5_RP1_BAR1_PROBING;
    if(write_config(s,c,UINT32_MAX)){rc=-4;goto failed;}
    READ(0x14);mask=value;
    if (!mask || (mask&15)) {rc=-6;goto failed;}
    size=~mask+1u;
    if(size<16 || (size&(size-1)) || (s->original_bar1&(size-1))) {rc=-6;goto failed;}
    EXPECT(4,0xffff,command);
    s->state=RPI5_RP1_BAR1_RESTORING;
    if(write_config(s,c,s->original_bar1)){rc=-4;goto failed;}
    s->state=RPI5_RP1_BAR1_VERIFYING;
    EXPECT(0x14,UINT32_MAX,s->original_bar1);
    EXPECT(4,0xffff,command);
    EXPECT(0,UINT32_MAX,snapshot->header[0]);
    EXPECT(0x10,UINT32_MAX,snapshot->header[4]);
    {
        const struct rpi5_rp1_bar1_size result={s->original_bar1,mask,size,command,s->transactions};
        *out=result;
    }
    s->state=RPI5_RP1_BAR1_COMPLETE;return 0;
failed:
    s->state=RPI5_RP1_BAR1_FAILED;return rc;
#undef EXPECT
#undef READ
}
