/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_prng_refresh.h"
enum rpi5_refresh_result
rpi5_prng_refresh(const struct rpi5_refresh_ops *ops,void *lock_context,
    void *entropy_context,void *generator_context)
{
    if(!ops || !ops->try_lock || !ops->unlock || !ops->entropy || !ops->reseed_locked ||
        !ops->failure_locked)
        return RPI5_REFRESH_INVALID;
    if(!ops->try_lock(lock_context)) return RPI5_REFRESH_BUSY;
    unsigned char seed[64]={0};
    size_t bytes=sizeof seed;
    int32_t samples=ops->entropy(&bytes,seed,entropy_context);
    enum rpi5_refresh_result result;
    if(samples<0) result=RPI5_REFRESH_HEALTH_FAILURE;
    else if(bytes>sizeof seed || (samples==0 && bytes!=0) || (samples>0 && bytes!=sizeof seed))
        result=RPI5_REFRESH_SOURCE_FAILURE;
    else if(samples==0) result=RPI5_REFRESH_EMPTY;
    else {
        result=ops->reseed_locked(generator_context,bytes,seed) ?
            RPI5_REFRESH_SOURCE_FAILURE : RPI5_REFRESH_RESEEDED;
    }
    if(result==RPI5_REFRESH_HEALTH_FAILURE || result==RPI5_REFRESH_SOURCE_FAILURE)
        ops->failure_locked(generator_context,result);
    /* Callback is trusted to respect the supplied capacity. Returned length
     * validation cannot undo a callback buffer overflow. */
    for(size_t i=0;i<sizeof seed;i++) ((volatile unsigned char *)seed)[i]=0;
    ops->unlock(lock_context);
    return result;
}
