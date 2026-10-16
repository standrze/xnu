/* SPDX-License-Identifier: BSD-2-Clause */
/* Host-only adapter into the unchanged actual secure implementation. */
#include <string.h>
#include "firmware/rpi5/pcie_verifier.c"
#include "firmware/rpi5/pcie_verifier_sip.c"
void model_secure_reset(void)
{
    memset(&verifier,0,sizeof verifier);verifier_lock=0;
}
void model_secure_call(uint64_t fid,uint64_t token,uint64_t out[4])
{
    struct host_context context={0};
    rpi5_pcie_sip((uint32_t)fid,token,0,0,0,NULL,&context,1);
    memcpy(out,context.regs,sizeof context.regs);
}
