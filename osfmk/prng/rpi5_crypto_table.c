/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_crypto_table.h"
#include "rpi5_digest_abi.h"
#include "rpi5_crypto_digest.h"
#include "rpi5_crypto_hmac.h"
#include "rpi5_aes_ecb.h"
#include "rpi5_aes_gcm.h"
#include "rpi5_des.h"
#include "rpi5_cts.h"
#include "rpi5_ccrng.h"
#include "rpi5_crypto_random.h"
#include "rpi5_rsa.h"
#include "rpi5_chachapoly_binding.h"
/* Candidate aggregate only. No registration or STARTUP hook: dependency,
 * whole-provider semantics and first-consumer ordering remain to be closed. */
struct crypto_functions rpi5_crypto_functions = {
    .ccdigest_init_fn=rpi5_digest_init,
    .ccdigest_update_fn=rpi5_digest_update,
    .ccdigest_final_fn=rpi5_digest_final,
    .ccdigest_fn=rpi5_digest,
    .ccmd5_di=&rpi5_md5_di,
    .ccsha1_di=&rpi5_sha1_di,
    .ccsha256_di=&rpi5_sha256_di,
    .ccsha384_di=&rpi5_sha384_di,
    .ccsha512_di=&rpi5_sha512_di,
    .cchmac_init_fn=rpi5_hmac_init,
    .cchmac_update_fn=rpi5_hmac_update,
    .cchmac_final_fn=rpi5_hmac_final,
    .cchmac_fn=rpi5_hmac,
    .ccgcm_init_with_iv_fn=rpi5_gcm_init_with_iv,
    .ccgcm_inc_iv_fn=rpi5_gcm_inc_iv,
    .ccchacha20poly1305_fns=&rpi5_chachapoly_functions,
    .ccdes_key_is_weak_fn=rpi5_des_key_is_weak,
    .ccdes_key_set_odd_parity_fn=rpi5_des_key_set_odd_parity,
    .ccpad_cts3_encrypt_fn=rpi5_cts3_encrypt,
    .ccpad_cts3_decrypt_fn=rpi5_cts3_decrypt,
    .ccrng_fn=rpi5_ccrng,
    .ccrsa_make_pub_fn=rpi5_rsa_make_pub,
    .ccrsa_verify_pkcs1v15_fn=rpi5_rsa_verify_pkcs1v15,
    .ccaes_ecb_encrypt=&rpi5_aes_ecb_encrypt,
    .ccaes_ecb_decrypt=&rpi5_aes_ecb_decrypt,
    .ccaes_cbc_encrypt=&rpi5_aes_cbc_encrypt,
    .ccaes_cbc_decrypt=&rpi5_aes_cbc_decrypt,
    .ccaes_xts_encrypt=&rpi5_aes_xts_encrypt,
    .ccaes_xts_decrypt=&rpi5_aes_xts_decrypt,
    .ccaes_gcm_encrypt=&rpi5_aes_gcm_encrypt,
    .ccaes_gcm_decrypt=&rpi5_aes_gcm_decrypt,
    .ccaes_ctr_crypt=&rpi5_aes_ctr,
    .ccdes_ecb_encrypt=&rpi5_des_ecb_encrypt,
    .ccdes_ecb_decrypt=&rpi5_des_ecb_decrypt,
    .ccdes_cbc_encrypt=&rpi5_des_cbc_encrypt,
    .ccdes_cbc_decrypt=&rpi5_des_cbc_decrypt,
    .cctdes_ecb_encrypt=&rpi5_tdes_ecb_encrypt,
    .cctdes_ecb_decrypt=&rpi5_tdes_ecb_decrypt,
    .cctdes_cbc_encrypt=&rpi5_tdes_cbc_encrypt,
    .cctdes_cbc_decrypt=&rpi5_tdes_cbc_decrypt,
    .random_generate_fn=rpi5_crypto_random_generate,
    .random_uniform_fn=rpi5_crypto_random_uniform,
    .random_kmem_ctx_size_fn=rpi5_crypto_random_kmem_ctx_size,
    .random_kmem_init_fn=rpi5_crypto_random_kmem_init,
    .digest_ctx_size_fn=rpi5_crypto_digest_ctx_size,
    .digest_init_fn=rpi5_crypto_digest_init,
    .digest_update_fn=rpi5_crypto_digest_update,
    .digest_final_fn=rpi5_crypto_digest_final,
    .digest_fn=rpi5_crypto_digest,
    .hmac_ctx_size_fn=rpi5_crypto_hmac_ctx_size,
    .hmac_init_fn=rpi5_crypto_hmac_init,
    .hmac_update_fn=rpi5_crypto_hmac_update,
    .hmac_final_generate_fn=rpi5_crypto_hmac_final_generate,
    .hmac_final_verify_fn=rpi5_crypto_hmac_final_verify,
    .hmac_generate_fn=rpi5_crypto_hmac_generate,
    .hmac_verify_fn=rpi5_crypto_hmac_verify,
};

