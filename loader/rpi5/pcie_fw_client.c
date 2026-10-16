/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_fw_client.h"
#include <stddef.h>
static int disjoint(const void *a,size_t n,const void *b,size_t m)
{
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    return x<=UINTPTR_MAX-n && y<=UINTPTR_MAX-m && (x+n<=y || y+m<=x);
}
static int fail(struct rpi5_pcie_fw_client *s)
{s->state=RPI5_FW_CLIENT_QUARANTINED;return -1;}
static int rpc(struct rpi5_pcie_fw_client *s,uint32_t fid,uint64_t token,uint64_t raw[4])
{
    return s->io.owner(s->io.context) || s->io.rpc(s->io.context,fid,token,raw) ||
        s->io.owner(s->io.context) || s->state!=RPI5_FW_CLIENT_BUSY ? -1:0;
}
int rpi5_pcie_fw_client_init(struct rpi5_pcie_fw_client *s,const struct rpi5_pcie_fw_io *io,
    uint64_t token,uint64_t frequency)
{
    if(!s || !io || !io->owner || !io->rpc || !token || frequency<1000000 || frequency>1000000000 ||
        s->state!=RPI5_FW_CLIENT_EMPTY || !disjoint(s,sizeof(*s),io,sizeof(*io)))return -1;
    s->io=*io;s->token=token;s->frequency=frequency;s->deadline=s->last_counter=0;s->sequence=0;
    s->state=RPI5_FW_CLIENT_READY;return 0;
}
int rpi5_pcie_fw_client_begin(struct rpi5_pcie_fw_client *s,struct rpi5_fw_observation *out)
{
    if(!s || !out || !disjoint(s,sizeof(*s),out,sizeof(*out)) || s->state!=RPI5_FW_CLIENT_READY)return -1;
    s->state=RPI5_FW_CLIENT_BUSY;
    uint64_t query[4]={0},claim[4]={0};
    if(rpc(s,RPI5_FW_PCIE_QUERY,0,query) || query[0] || query[1]!=RPI5_FW_PCIE_ABI || !query[2] ||
        query[3]!=(RPI5_FW_GROUP1|RPI5_FW_MASKED) || rpc(s,RPI5_FW_PCIE_CLAIM,s->token,claim) ||
        claim[0] || claim[1]!=1 || claim[2]<=query[2] || claim[3]!=31 ||
        claim[2]>UINT64_MAX-9*s->frequency)return fail(s);
    s->last_counter=claim[2];s->deadline=claim[2]+9*s->frequency;s->sequence=1;s->state=RPI5_FW_CLIENT_OWNED;
    *out=(struct rpi5_fw_observation){claim[2],1,31};return 0;
}
int rpi5_pcie_fw_client_check(struct rpi5_pcie_fw_client *s,struct rpi5_fw_observation *out)
{
    if(!s || !out || !disjoint(s,sizeof(*s),out,sizeof(*out)) || s->state!=RPI5_FW_CLIENT_OWNED)return -1;
    s->state=RPI5_FW_CLIENT_BUSY;
    if(s->sequence>=65536)return fail(s);
    uint64_t raw[4]={0};
    if(rpc(s,RPI5_FW_PCIE_CHECK,s->token,raw) || raw[0] || raw[1]!=(uint64_t)s->sequence+1 ||
        raw[2]<=s->last_counter || raw[2]>=s->deadline || raw[3]!=31)return fail(s);
    s->sequence++;s->last_counter=raw[2];s->state=RPI5_FW_CLIENT_OWNED;
    *out=(struct rpi5_fw_observation){raw[2],s->sequence,31};return 0;
}
