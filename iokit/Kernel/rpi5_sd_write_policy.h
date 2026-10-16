/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_SD_WRITE_POLICY_H
#define RPI5_SD_WRITE_POLICY_H
#include <stddef.h>
#include <stdint.h>

/* Offline foundation only: not linked into the current read-only provider.
 * The caller serializes EVERY operation with its request/ownership mutex.
 * Zero-initialize once per device lifetime; never reset a quarantined policy
 * while a request can retain an epoch. A lease is not a security capability
 * against privileged kernel code, or a cryptographic card identity.
 */
struct rpi5_sd_write_profile {
    uint64_t sectors, start, blocks;
    uint32_t max_request_blocks, mbr_signature;
    uint32_t boot_start, boot_blocks;
    uint32_t hfs_block_size, hfs_total_blocks;
    uint8_t cid[15], csd[16];
};
struct rpi5_sd_write_policy {
    uint64_t epoch, start, blocks;
    uint32_t max_request_blocks, state;
};
enum { RPI5_SD_WRITE_DISABLED=0, RPI5_SD_WRITE_ENABLED=1, RPI5_SD_WRITE_QUARANTINED=2 };
#define RPI5_SD_WRITE_START UINT64_C(1050624)
#define RPI5_SD_WRITE_BLOCKS UINT64_C(262144)
#define RPI5_SD_WRITE_MAX_REQUEST_BLOCKS UINT64_C(32)

/* The historical card remains the default so prior evidence and packages keep
 * their exact behavior. A future candidate can instead compile a generated,
 * hash-pinned profile and call the explicit profile entry point. Profiles are
 * expected media, not proof of live identity, cache state or durability. */
extern const struct rpi5_sd_write_profile rpi5_sd_write_default_profile;
int rpi5_sd_write_profile_valid(const struct rpi5_sd_write_profile *);
const struct rpi5_sd_write_profile *rpi5_sd_write_selected_profile(void);

/* Initial clean fixture admission, BEFORE mounting HFS read/write. Requires
 * fresh controller/card observations, not FDT declarations or user assertions.
 * CID is canonical 128-bit R2 layout; its final CRC/end byte is not compared
 * because SDHCI omits it. CSD, capacity, MBR layout and both HFS headers must
 * match the deliberately narrow disposable-media profile. Geometry/clean bits
 * do not substitute for full-image hashes, fsck, backups or the prior RO trial.
 * Every attempt first revokes any previous lease. Failure remains disabled;
 * an I/O ambiguity must separately call quarantine, which cannot be rearmed.
 */
int rpi5_sd_write_authorize(struct rpi5_sd_write_policy *, uint64_t sectors,
    const void *cid, size_t cid_bytes, const void *csd, size_t csd_bytes,
    const void *mbr, size_t mbr_bytes, const void *primary, size_t primary_bytes,
    const void *alternate, size_t alternate_bytes);
int rpi5_sd_write_authorize_profile(struct rpi5_sd_write_policy *,
    const struct rpi5_sd_write_profile *, uint64_t sectors,
    const void *cid, size_t cid_bytes, const void *csd, size_t csd_bytes,
    const void *mbr, size_t mbr_bytes, const void *primary, size_t primary_bytes,
    const void *alternate, size_t alternate_bytes);
int rpi5_sd_write_request_valid(const struct rpi5_sd_write_policy *, uint64_t epoch,
    uint64_t block, uint64_t count, uint64_t bytes);
void rpi5_sd_write_revoke(struct rpi5_sd_write_policy *);
void rpi5_sd_write_quarantine(struct rpi5_sd_write_policy *);
#endif
