/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RSA_DIGEST_H
#define RPI5_RSA_DIGEST_H
#include <stddef.h>
#include <stdint.h>
/* Translate supported XNU DER OIDs to BearSSL length-prefixed OIDs.
 * Input must be a readable DER OID object. NULL selects legacy raw digest.
 * On rejection the result is NULL. No signature verification is done here. */
int rpi5_rsa_digest_oid(const uint8_t *, size_t, const unsigned char **);
#endif
