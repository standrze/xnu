/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_AES_GCM_H
#define RPI5_AES_GCM_H
#include <corecrypto/ccmode_impl.h>
extern const struct ccmode_gcm rpi5_aes_gcm_encrypt,rpi5_aes_gcm_decrypt;
int rpi5_gcm_init_with_iv(const struct ccmode_gcm *,ccgcm_ctx *,size_t,const void *,const void *);
int rpi5_gcm_inc_iv(const struct ccmode_gcm *,ccgcm_ctx *,void *);
#endif
