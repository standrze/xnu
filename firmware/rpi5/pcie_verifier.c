/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_verifier.h"
#define GIC UINT64_C(0x107fff9000)
#define PM UINT64_C(0x107d200000)
#define RESET UINT64_C(0x1001504338)
#define RESCAL UINT64_C(0x1000119500)
enum { EMPTY, BUSY, OWNED, QUARANTINED };
static struct {
    uint64_t owner, frequency, start, deadline, last_counter;
    uint32_t first_count, last_count, sequence, state;
} verifier;

static int groups(uint32_t *facts)
{
    uint32_t typer=rpi5_fw_load32(GIC+4);
    /* GICv2 SecurityExtn plus at least 288 INTIDs for bank 8/ID 266.
     * Without security extensions this secure-view contract is unsupported. */
    if (typer==UINT32_MAX || !(typer&0x400) || (typer&0x1f)<8) return RPI5_FW_HARDWARE;
    static const uint32_t banks[3]={5,6,8};
    static const uint32_t masks[3]={UINT32_MAX,UINT32_MAX,0x7e0};
    uint32_t enabled=0;
    for (unsigned i=0;i<3;i++) {
        uint32_t group=rpi5_fw_load32(GIC+0x80+4*banks[i]);
        uint32_t enable=rpi5_fw_load32(GIC+0x100+4*banks[i]);
        uint32_t active=rpi5_fw_load32(GIC+0x300+4*banks[i]);
        /* IGROUPR=all ones is EXPECTED for all-NS SPIs in the EL3 view,
         * unlike an all-ones device status. Reject active/enable all-ones;
         * do not interpret NS RAZ/WI as evidence of secure-group ownership. */
        if ((group&masks[i])!=masks[i] || enable==UINT32_MAX || active==UINT32_MAX || (active&masks[i]))
            return RPI5_FW_HARDWARE;
        enabled |= enable&masks[i];
    }
    *facts=RPI5_FW_GROUP1 | (enabled ? 0 : RPI5_FW_MASKED);
    return RPI5_FW_OK;
}
static int sample(struct rpi5_fw_observation *out, int claiming)
{
    uint64_t before=rpi5_fw_counter();
    if (before<verifier.last_counter || before>=verifier.deadline) return RPI5_FW_CLOCK;
    uint32_t facts;
    int rc=groups(&facts);
    if (rc) return rc;
    if (!(facts&RPI5_FW_MASKED)) return RPI5_FW_HARDWARE;
    uint32_t reset=rpi5_fw_load32(RESET);
    if (reset==UINT32_MAX || (reset&(1u<<11))) return RPI5_FW_HARDWARE;
    /* Controller 1/reset43 is retained for shared RESCAL. Never write either
     * reset; reset44 may change during the separately owned initial sequence. */
    facts |= RPI5_FW_C1_RELEASED;
    uint32_t rescal=rpi5_fw_load32(RESCAL), status=rpi5_fw_load32(RESCAL+8);
    if (rescal==UINT32_MAX || status==UINT32_MAX || (claiming && (rescal&1))) return RPI5_FW_HARDWARE;
    /* After claim our caller may legitimately have calibration in flight. */
    facts |= RPI5_FW_RESCAL_READ;
    uint32_t route=rpi5_fw_load32(PM+0x1c), count=rpi5_fw_load32(PM+0x24);
    if (route==UINT32_MAX || (route&0x30)!=0x20 || count==UINT32_MAX) return RPI5_FW_HARDWARE;
    count &= 0xfffff;
    if (count<=(2u<<16) || (claiming ? count<(13u<<16) : count>verifier.last_count)) return RPI5_FW_HARDWARE;
    if (!claiming && before-verifier.start>=(verifier.frequency+999)/1000 && count>=verifier.first_count)
        return RPI5_FW_CLOCK;
    uint64_t after=rpi5_fw_counter();
    if (after<before || after>=verifier.deadline || after-before>verifier.frequency) return RPI5_FW_CLOCK;
    facts |= RPI5_FW_WATCHDOG;
    verifier.last_count=count;verifier.last_counter=after;
    if (claiming) verifier.first_count=count;
    out->counter=after;out->facts=facts;out->sequence=++verifier.sequence;
    return RPI5_FW_OK;
}
int rpi5_fw_verifier_call(uint32_t fid, uint64_t owner, struct rpi5_fw_observation *out)
{
    if (!out || (fid!=RPI5_FW_PCIE_QUERY && fid!=RPI5_FW_PCIE_CLAIM && fid!=RPI5_FW_PCIE_CHECK))
        return RPI5_FW_ARGUMENT;
    struct rpi5_fw_observation result={0};
    if (fid==RPI5_FW_PCIE_QUERY) {
        if (owner || verifier.state!=EMPTY) return RPI5_FW_STATE;
        verifier.state=BUSY;
        int rc=groups(&result.facts);
        if (rc) {verifier.state=EMPTY;return rc;} /* Observations, not admission. */
        result.counter=rpi5_fw_counter();result.sequence=RPI5_FW_PCIE_ABI;
        verifier.state=EMPTY;
        *out=result;return RPI5_FW_OK;
    }
    if (!owner) return RPI5_FW_ARGUMENT;
    if (fid==RPI5_FW_PCIE_CLAIM) {
        if (verifier.state!=EMPTY) return RPI5_FW_STATE;
        verifier.state=BUSY;verifier.owner=owner; /* Irreversible attempt. */
        verifier.frequency=rpi5_fw_frequency();verifier.start=rpi5_fw_counter();
        if (verifier.frequency<1000000 || verifier.frequency>1000000000 ||
                verifier.start>UINT64_MAX-10*verifier.frequency) goto clock_failure;
        verifier.deadline=verifier.start+10*verifier.frequency;verifier.last_counter=verifier.start;
    } else {
        if (verifier.state!=OWNED || verifier.owner!=owner) return RPI5_FW_STATE;
        verifier.state=BUSY;
        if (verifier.sequence>=65536) goto clock_failure;
        if (rpi5_fw_frequency()!=verifier.frequency) goto clock_failure;
    }
    int rc=sample(&result,fid==RPI5_FW_PCIE_CLAIM);
    if (rc) {verifier.state=QUARANTINED;return rc;}
    verifier.state=OWNED;*out=result;return RPI5_FW_OK;
clock_failure:
    verifier.state=QUARANTINED;return RPI5_FW_CLOCK;
}
