/* SPDX-License-Identifier: BSD-2-Clause */
/* Included ONLY by the distinct arm_init overlay; no accepted source edited. */
#include "loader/rpi5/display_xnu_record.h"
#include "arm64/rpi5_display_xnu_api.h"
static SECURITY_READ_ONLY_LATE(struct rpi5_display_xnu_record) rpi5_display_contract;
static SECURITY_READ_ONLY_LATE(unsigned) rpi5_display_contract_ready;
int rpi5_display_xnu_map_admit(uint64_t start,uint64_t end,unsigned wcomb,unsigned nx,unsigned early)
{
    if(!rpi5_display_contract_ready)return -1;
    return rpi5_display_xnu_map_policy(&rpi5_display_contract,start,end,wcomb,nx,early);
}
int rpi5_display_xnu_video_admit(uint64_t base,uint64_t width,uint64_t height,uint64_t stride,uint64_t depth,
    uint64_t offset,uint64_t length,uint64_t rotate,uint64_t scale)
{
    return rpi5_display_contract_ready?rpi5_display_xnu_video_valid(&rpi5_display_contract,base,width,height,stride,depth,offset,length,rotate,scale):-1;
}
int rpi5_display_xnu_geometry(uint64_t base,uint64_t width,uint64_t height,uint64_t stride,uint64_t depth,uint64_t length)
{
    return rpi5_display_contract_ready&&base==rpi5_display_contract.base&&width==1920&&height==1080&&stride==7680&&depth==32&&
        length==rpi5_display_contract.reserve_end-rpi5_display_contract.reserve_start?0:-1;
}
