/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_CTS_H
#define RPI5_CTS_H
#include <corecrypto/ccmode_impl.h>
size_t rpi5_cts3_encrypt(const struct ccmode_cbc *,cccbc_ctx *,cccbc_iv *,size_t,const void *,void *);
size_t rpi5_cts3_decrypt(const struct ccmode_cbc *,cccbc_ctx *,cccbc_iv *,size_t,const void *,void *);
#endif
