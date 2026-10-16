/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_DES_H
#define RPI5_DES_H
#include <corecrypto/ccmode_impl.h>
extern const struct ccmode_ecb rpi5_des_ecb_encrypt,rpi5_des_ecb_decrypt;
extern const struct ccmode_ecb rpi5_tdes_ecb_encrypt,rpi5_tdes_ecb_decrypt;
extern const struct ccmode_cbc rpi5_des_cbc_encrypt,rpi5_des_cbc_decrypt;
extern const struct ccmode_cbc rpi5_tdes_cbc_encrypt,rpi5_tdes_cbc_decrypt;
int rpi5_des_key_is_weak(void *,unsigned long);
void rpi5_des_key_set_odd_parity(void *,unsigned long);
#endif
