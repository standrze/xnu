/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RSA_H
#define RPI5_RSA_H
#include <corecrypto/ccrsa.h>
/* Candidate paired-provider representation: not a general cczp context. */
int rpi5_rsa_make_pub(ccrsa_pub_ctx_t, size_t, const uint8_t *, size_t, const uint8_t *);
/* valid must be writable and disjoint from key and all input buffers. */
int rpi5_rsa_verify_pkcs1v15(ccrsa_pub_ctx_t, const uint8_t *, size_t,
    const uint8_t *, size_t, const uint8_t *, bool *);
#endif
