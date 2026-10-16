/* SPDX-License-Identifier: BSD-2-Clause */
/* Pure admission/range/epoch checks. No MMIO, storage commands or allocation. */
#include "rpi5_sd_write_policy.h"

static uint32_t le32(const uint8_t *p)
{
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static uint32_t be32(const uint8_t *p)
{
    return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static int same(const uint8_t *a, const uint8_t *b, size_t length)
{
    for (size_t i=0;i<length;i++) if (a[i]!=b[i]) return 0;
    return 1;
}
const struct rpi5_sd_write_profile rpi5_sd_write_default_profile={
    .sectors=UINT64_C(250347520), .start=RPI5_SD_WRITE_START,
    .blocks=RPI5_SD_WRITE_BLOCKS,
    .max_request_blocks=RPI5_SD_WRITE_MAX_REQUEST_BLOCKS,
    .mbr_signature=UINT32_C(0x5ae1f07e),
    .boot_start=2048, .boot_blocks=1048576,
    .hfs_block_size=4096, .hfs_total_blocks=32768,
    .cid={0x1b,0x53,0x4d,0x47,0x44,0x32,0x53,0x35,
        0x30,0x65,0x4f,0x68,0xd1,0xa1,0x61},
    .csd={0x40,0x0e,0x00,0x32,0xdb,0x79,0x00,0x03,
        0xba,0xff,0x7f,0x80,0x0a,0x40,0x00,0x00}
};
#if RPI5_SD_WRITE_EXTERNAL_PROFILE
extern const struct rpi5_sd_write_profile rpi5_sd_write_external_profile;
#endif
const struct rpi5_sd_write_profile *rpi5_sd_write_selected_profile(void)
{
#if RPI5_SD_WRITE_EXTERNAL_PROFILE
    return &rpi5_sd_write_external_profile;
#else
    return &rpi5_sd_write_default_profile;
#endif
}
int rpi5_sd_write_profile_valid(const struct rpi5_sd_write_profile *p)
{
    if (!p || !p->sectors || !p->start || !p->blocks ||
        !p->max_request_blocks || p->max_request_blocks>32 ||
        p->start>=p->sectors || p->blocks>p->sectors-p->start ||
        !p->boot_start || !p->boot_blocks ||
        p->boot_start>=p->sectors || p->boot_blocks>p->sectors-p->boot_start ||
        p->boot_start>=p->start || p->boot_blocks>p->start-p->boot_start ||
        p->start>UINT32_MAX || p->blocks>UINT32_MAX ||
        p->hfs_block_size<512 || (p->hfs_block_size&(p->hfs_block_size-1)) ||
        !p->hfs_total_blocks ||
        p->blocks>UINT64_MAX/512 || p->blocks*512!=
            (uint64_t)p->hfs_block_size*p->hfs_total_blocks) return 0;
    return 1;
}
static int header(const uint8_t *p, const struct rpi5_sd_write_profile *profile)
{
    /* Pinned Apple hfs_format.h: H+ v4, clean unmounted, no journal,
     * software/hardware lock, inconsistency, content protection or expanded
     * timestamps. The harmless unused-node-fix bit is allowed. Restrict the
     * first write trial to the actual 4096 * 32768-byte standalone fixture.
     */
    uint32_t attributes=be32(p+4);
    return p[0]==0x48 && p[1]==0x2b && p[2]==0 && p[3]==4 &&
        (attributes==UINT32_C(0x100) || attributes==UINT32_C(0x80000100)) &&
        !be32(p+12) && be32(p+40)==profile->hfs_block_size &&
        be32(p+44)==profile->hfs_total_blocks &&
        be32(p+48)<=profile->hfs_total_blocks &&
        be32(p+52)<profile->hfs_total_blocks;
}
int rpi5_sd_write_authorize_profile(struct rpi5_sd_write_policy *p,
    const struct rpi5_sd_write_profile *profile, uint64_t sectors,
    const void *cid, size_t cid_bytes, const void *csd, size_t csd_bytes,
    const void *mbr, size_t mbr_bytes, const void *primary, size_t primary_bytes,
    const void *alternate, size_t alternate_bytes)
{
    if (!p) return -1;
    if (p->state>RPI5_SD_WRITE_ENABLED || p->epoch==UINT64_MAX) {
        p->state=RPI5_SD_WRITE_QUARANTINED;
        return -1;
    }
    p->state=RPI5_SD_WRITE_DISABLED;
    p->start=0; p->blocks=0; p->max_request_blocks=0;
    p->epoch++; /* Even a failed re-admission invalidates every prior lease. */
    if (!rpi5_sd_write_profile_valid(profile) || !cid || cid_bytes!=16 ||
        !csd || csd_bytes!=16 || !mbr || mbr_bytes!=512 ||
        !primary || primary_bytes!=512 || !alternate || alternate_bytes!=512 ||
        sectors!=profile->sectors) return -1;
    if (!same(cid,profile->cid,sizeof profile->cid) ||
        !same(csd,profile->csd,sizeof profile->csd)) return -1;
    const uint8_t *table=mbr;
    if (le32(table+440)!=profile->mbr_signature || table[510]!=0x55 || table[511]!=0xaa ||
        table[446]!=0x80 || table[450]!=0x0c || le32(table+454)!=profile->boot_start ||
        le32(table+458)!=profile->boot_blocks || table[462]!=0 || table[466]!=0xaf ||
        le32(table+470)!=profile->start || le32(table+474)!=profile->blocks) return -1;
    for (unsigned i=478;i<510;i++) if (table[i]) return -1;
    const uint8_t *a=primary,*b=alternate;
    if (!header(a,profile) || !header(b,profile) || be32(a+4)!=be32(b+4)) return -1;
    p->start=profile->start; p->blocks=profile->blocks;
    p->max_request_blocks=profile->max_request_blocks;
    p->state=RPI5_SD_WRITE_ENABLED;
    return 0;
}
int rpi5_sd_write_authorize(struct rpi5_sd_write_policy *p, uint64_t sectors,
    const void *cid, size_t cid_bytes, const void *csd, size_t csd_bytes,
    const void *mbr, size_t mbr_bytes, const void *primary, size_t primary_bytes,
    const void *alternate, size_t alternate_bytes)
{
    return rpi5_sd_write_authorize_profile(p,&rpi5_sd_write_default_profile,sectors,
        cid,cid_bytes,csd,csd_bytes,mbr,mbr_bytes,primary,primary_bytes,
        alternate,alternate_bytes);
}
int rpi5_sd_write_request_valid(const struct rpi5_sd_write_policy *p, uint64_t epoch,
    uint64_t block, uint64_t count, uint64_t bytes)
{
    if (!p || p->blocks>UINT64_MAX-p->start) return 0;
    const uint64_t end=p->start+p->blocks;
    return p && p->state==RPI5_SD_WRITE_ENABLED && epoch && epoch==p->epoch &&
        block>=p->start && block<end && count &&
        count<=p->max_request_blocks && count<=end-block &&
        count<=UINT64_MAX/512 && bytes==count*512;
}
void rpi5_sd_write_revoke(struct rpi5_sd_write_policy *p)
{
    if (p && p->state==RPI5_SD_WRITE_ENABLED) {
        p->state=RPI5_SD_WRITE_DISABLED;
        p->start=0; p->blocks=0; p->max_request_blocks=0;
    }
}
void rpi5_sd_write_quarantine(struct rpi5_sd_write_policy *p)
{
    if (p) {
        p->state=RPI5_SD_WRITE_QUARANTINED;
        p->start=0; p->blocks=0; p->max_request_blocks=0;
    }
}
