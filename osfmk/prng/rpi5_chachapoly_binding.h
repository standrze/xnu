/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_CHACHAPOLY_BINDING_H
#define RPI5_CHACHAPOLY_BINDING_H
#include <libkern/crypto/register_crypto.h>
/* Candidate only. incnonce reports unsupported, matching the audited API. */
extern const struct ccchacha20poly1305_fns rpi5_chachapoly_functions;
#endif
