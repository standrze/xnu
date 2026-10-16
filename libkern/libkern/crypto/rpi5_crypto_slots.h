/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_CRYPTO_SLOTS_H
#define RPI5_CRYPTO_SLOTS_H
#include <libkern/crypto/register_crypto.h>
/* Structural precondition only: not proof of nested methods or semantics. */
static inline bool rpi5_crypto_slots_present(const struct crypto_functions *f)
{
    return f != NULL &&
        f->ccdigest_init_fn != NULL &&
        f->ccdigest_update_fn != NULL &&
        f->ccdigest_final_fn != NULL &&
        f->ccdigest_fn != NULL &&
        f->ccmd5_di != NULL &&
        f->ccsha1_di != NULL &&
        f->ccsha256_di != NULL &&
        f->ccsha384_di != NULL &&
        f->ccsha512_di != NULL &&
        f->cchmac_init_fn != NULL &&
        f->cchmac_update_fn != NULL &&
        f->cchmac_final_fn != NULL &&
        f->cchmac_fn != NULL &&
        f->ccaes_ecb_encrypt != NULL &&
        f->ccaes_ecb_decrypt != NULL &&
        f->ccaes_cbc_encrypt != NULL &&
        f->ccaes_cbc_decrypt != NULL &&
        f->ccaes_ctr_crypt != NULL &&
        f->ccaes_xts_encrypt != NULL &&
        f->ccaes_xts_decrypt != NULL &&
        f->ccaes_gcm_encrypt != NULL &&
        f->ccaes_gcm_decrypt != NULL &&
        f->ccgcm_init_with_iv_fn != NULL &&
        f->ccgcm_inc_iv_fn != NULL &&
        f->ccchacha20poly1305_fns != NULL &&
        f->ccdes_ecb_encrypt != NULL &&
        f->ccdes_ecb_decrypt != NULL &&
        f->ccdes_cbc_encrypt != NULL &&
        f->ccdes_cbc_decrypt != NULL &&
        f->cctdes_ecb_encrypt != NULL &&
        f->cctdes_ecb_decrypt != NULL &&
        f->cctdes_cbc_encrypt != NULL &&
        f->cctdes_cbc_decrypt != NULL &&
        f->ccdes_key_is_weak_fn != NULL &&
        f->ccdes_key_set_odd_parity_fn != NULL &&
        f->ccpad_cts3_encrypt_fn != NULL &&
        f->ccpad_cts3_decrypt_fn != NULL &&
        f->ccrng_fn != NULL &&
        f->ccrsa_make_pub_fn != NULL &&
        f->ccrsa_verify_pkcs1v15_fn != NULL &&
        f->random_generate_fn != NULL &&
        f->random_uniform_fn != NULL &&
        f->random_kmem_ctx_size_fn != NULL &&
        f->random_kmem_init_fn != NULL &&
        f->digest_ctx_size_fn != NULL &&
        f->digest_init_fn != NULL &&
        f->digest_update_fn != NULL &&
        f->digest_final_fn != NULL &&
        f->digest_fn != NULL &&
        f->hmac_ctx_size_fn != NULL &&
        f->hmac_init_fn != NULL &&
        f->hmac_update_fn != NULL &&
        f->hmac_final_generate_fn != NULL &&
        f->hmac_final_verify_fn != NULL &&
        f->hmac_generate_fn != NULL &&
        f->hmac_verify_fn != NULL;
}
#endif

