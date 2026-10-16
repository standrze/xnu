/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_AES_ECB_H
#define RPI5_AES_ECB_H
#include <corecrypto/ccmode_impl.h>
extern const struct ccmode_ecb rpi5_aes_ecb_encrypt,rpi5_aes_ecb_decrypt;
extern const struct ccmode_cbc rpi5_aes_cbc_encrypt,rpi5_aes_cbc_decrypt;
extern const struct ccmode_ctr rpi5_aes_ctr;
extern const struct ccmode_xts rpi5_aes_xts_encrypt,rpi5_aes_xts_decrypt;
#endif
