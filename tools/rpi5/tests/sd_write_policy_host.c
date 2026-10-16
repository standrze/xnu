/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_sd_write_policy.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static uint8_t cid[16]={0x1b,0x53,0x4d,0x47,0x44,0x32,0x53,0x35,0x30,0x65,0x4f,0x68,0xd1,0xa1,0x61,0};
static uint8_t csd[16]={0x40,0x0e,0x00,0x32,0xdb,0x79,0x00,0x03,0xba,0xff,0x7f,0x80,0x0a,0x40,0,0};
static uint8_t mbr[512],primary[512],alternate[512];
static void le(uint8_t *p, uint32_t value)
{
    for (unsigned i=0;i<4;i++) p[i]=(uint8_t)(value>>(8*i));
}
static void be(uint8_t *p, uint32_t value)
{
    for (unsigned i=0;i<4;i++) p[i]=(uint8_t)(value>>(24-8*i));
}
#define AUTHORIZE(p) rpi5_sd_write_authorize(p,250347520,cid,16,csd,16,mbr,512,primary,512,alternate,512)
#define VALID(p,e,b,c,n) rpi5_sd_write_request_valid(p,e,b,c,n)
int main(int argc, char **argv)
{
    le(mbr+440,0x5ae1f07e); mbr[510]=0x55; mbr[511]=0xaa;
    mbr[446]=0x80; mbr[450]=0x0c; le(mbr+454,2048); le(mbr+458,1048576);
    mbr[466]=0xaf; le(mbr+470,1050624); le(mbr+474,262144);
    primary[0]=0x48; primary[1]=0x2b; primary[3]=4;
    be(primary+4,0x80000100); be(primary+40,4096); be(primary+44,32768);
    be(primary+48,31977); be(primary+52,4); memcpy(alternate,primary,512);
    if (argc==2) {
        FILE *image=fopen(argv[1],"rb"); assert(image);
        assert(!fseek(image,1024,SEEK_SET) && fread(primary,1,512,image)==512);
        assert(!fseek(image,134217728-1024,SEEK_SET) && fread(alternate,1,512,image)==512);
        assert(!fclose(image));
    } else assert(argc==1);
    struct rpi5_sd_write_policy p={0};
    assert(!VALID(&p,1,1050624,1,512)); assert(!AUTHORIZE(&p));
    uint64_t epoch=p.epoch;
    assert(rpi5_sd_write_profile_valid(&rpi5_sd_write_default_profile));
    {
        struct rpi5_sd_write_profile profile=rpi5_sd_write_default_profile;
        uint8_t custom_cid[16],custom_csd[16],custom_mbr[512];
        memcpy(custom_cid,cid,sizeof custom_cid); memcpy(custom_csd,csd,sizeof custom_csd);
        memcpy(custom_mbr,mbr,sizeof custom_mbr);
        profile.sectors=UINT64_C(300000000); profile.mbr_signature=UINT32_C(0x12345678);
        profile.cid[0]^=0x40; profile.csd[1]^=0x20;
        custom_cid[0]^=0x40; custom_csd[1]^=0x20; le(custom_mbr+440,profile.mbr_signature);
        struct rpi5_sd_write_policy custom={0};
        assert(!rpi5_sd_write_authorize_profile(&custom,&profile,profile.sectors,
            custom_cid,16,custom_csd,16,custom_mbr,512,primary,512,alternate,512));
        assert(custom.start==profile.start && custom.blocks==profile.blocks &&
            custom.max_request_blocks==profile.max_request_blocks);
        assert(rpi5_sd_write_request_valid(&custom,custom.epoch,profile.start,1,512));
        assert(!rpi5_sd_write_request_valid(&custom,custom.epoch,profile.start-1,1,512));
        profile.max_request_blocks=0;
        assert(!rpi5_sd_write_profile_valid(&profile));
        assert(rpi5_sd_write_authorize_profile(&custom,&profile,profile.sectors,
            custom_cid,16,custom_csd,16,custom_mbr,512,primary,512,alternate,512)==-1);
        assert(custom.state==RPI5_SD_WRITE_DISABLED && !custom.start && !custom.blocks);
    }
    assert(VALID(&p,epoch,1050624,1,512)); assert(VALID(&p,epoch,1312767,1,512));
    assert(VALID(&p,epoch,1312736,32,16384));
    const uint64_t bad[][3]={{0,1,512},{2048,1,512},{1050623,2,1024},{1312768,1,512},
        {1312767,2,1024},{1050624,0,0},{1050624,33,16896},{1050624,1,511},
        {UINT64_MAX,UINT64_MAX,UINT64_MAX},{250347519,1,512}};
    for (unsigned i=0;i<sizeof bad/sizeof bad[0];i++) assert(!VALID(&p,epoch,bad[i][0],bad[i][1],bad[i][2]));
    assert(!VALID(&p,0,1050624,1,512)); assert(!VALID(&p,epoch+1,1050624,1,512));
    rpi5_sd_write_revoke(&p); assert(!VALID(&p,epoch,1050624,1,512));
    assert(!AUTHORIZE(&p) && p.epoch>epoch); assert(!VALID(&p,epoch,1050624,1,512));
    struct {uint8_t *bytes; unsigned length;} identity[]={{cid,15},{csd,16}};
    for (unsigned item=0;item<2;item++) for (unsigned i=0;i<identity[item].length;i++) {
        identity[item].bytes[i]^=1; assert(AUTHORIZE(&p)==-1 && !p.state); identity[item].bytes[i]^=1;
    }
    cid[15]^=0xff; assert(!AUTHORIZE(&p)); cid[15]^=0xff; /* Omitted CRC/end byte, NOT identity. */
    const unsigned offsets[]={440,441,442,443,446,450,454,455,456,457,458,459,460,461,
        462,466,470,471,472,473,474,475,476,477,478,494,509,510,511};
    for (unsigned i=0;i<sizeof offsets/sizeof offsets[0];i++) {
        mbr[offsets[i]]^=1; assert(AUTHORIZE(&p)==-1 && !p.state); mbr[offsets[i]]^=1;
    }
    for (unsigned which=0;which<2;which++) {
        uint8_t *header=which ? alternate : primary;
        const unsigned critical[]={0,1,2,3,12,13,14,15,40,41,42,43,44,45,46,47};
        for (unsigned i=0;i<sizeof critical/sizeof critical[0];i++) {
            header[critical[i]]^=1; assert(AUTHORIZE(&p)==-1 && !p.state); header[critical[i]]^=1;
        }
        uint32_t saved=((uint32_t)header[4]<<24)|((uint32_t)header[5]<<16)|((uint32_t)header[6]<<8)|header[7];
        for (unsigned bit=0;bit<31;bit++) {
            be(header+4,saved^(UINT32_C(1)<<bit)); assert(AUTHORIZE(&p)==-1 && !p.state);
        }
        be(header+4,saved); uint8_t saved_free[4],saved_next[4];
        memcpy(saved_free,header+48,4); memcpy(saved_next,header+52,4);
        be(header+48,32769); assert(AUTHORIZE(&p)==-1 && !p.state); memcpy(header+48,saved_free,4);
        be(header+52,32768); assert(AUTHORIZE(&p)==-1 && !p.state); memcpy(header+52,saved_next,4);
    }
    assert(!AUTHORIZE(&p)); epoch=p.epoch;
    be(primary+4,0x100); be(alternate+4,0x100); assert(!AUTHORIZE(&p));
    be(primary+4,0x80000100); assert(AUTHORIZE(&p)==-1 && !p.state);
    be(alternate+4,0x80000100); assert(!AUTHORIZE(&p));
    assert(rpi5_sd_write_authorize(&p,250347519,cid,16,csd,16,mbr,512,primary,512,alternate,512)==-1 && !p.state);
    assert(!VALID(&p,epoch,1050624,1,512));
    for (unsigned length=0;length<16;length++) {
        assert(rpi5_sd_write_authorize(&p,250347520,cid,length,csd,16,mbr,512,primary,512,alternate,512)==-1);
        assert(rpi5_sd_write_authorize(&p,250347520,cid,16,csd,length,mbr,512,primary,512,alternate,512)==-1);
    }
    assert(rpi5_sd_write_authorize(&p,250347520,0,16,csd,16,mbr,512,primary,512,alternate,512)==-1);
    assert(rpi5_sd_write_authorize(&p,250347520,cid,16,0,16,mbr,512,primary,512,alternate,512)==-1);
    assert(rpi5_sd_write_authorize(&p,250347520,cid,16,csd,16,0,512,primary,512,alternate,512)==-1);
    assert(rpi5_sd_write_authorize(&p,250347520,cid,16,csd,16,mbr,512,0,512,alternate,512)==-1);
    assert(rpi5_sd_write_authorize(&p,250347520,cid,16,csd,16,mbr,512,primary,512,0,512)==-1);
    for (unsigned length=0;length<512;length++) {
        assert(rpi5_sd_write_authorize(&p,250347520,cid,16,csd,16,mbr,length,primary,512,alternate,512)==-1);
        assert(rpi5_sd_write_authorize(&p,250347520,cid,16,csd,16,mbr,512,primary,length,alternate,512)==-1);
        assert(rpi5_sd_write_authorize(&p,250347520,cid,16,csd,16,mbr,512,primary,512,alternate,length)==-1);
    }
    assert(!AUTHORIZE(&p)); rpi5_sd_write_quarantine(&p);
    assert(AUTHORIZE(&p)==-1 && p.state==RPI5_SD_WRITE_QUARANTINED);
    rpi5_sd_write_revoke(&p); assert(p.state==RPI5_SD_WRITE_QUARANTINED);
    p=(struct rpi5_sd_write_policy){.epoch=UINT64_MAX};
    assert(AUTHORIZE(&p)==-1 && p.state==RPI5_SD_WRITE_QUARANTINED);
    assert(!VALID(0,1,1050624,1,512)); assert(AUTHORIZE(0)==-1);
    assert(!rpi5_sd_write_profile_valid(0));
    rpi5_sd_write_revoke(0); rpi5_sd_write_quarantine(0);
    puts("SD_WRITE_POLICY_PASS");
    return 0;
}
