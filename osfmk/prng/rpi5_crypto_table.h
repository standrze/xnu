/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_CRYPTO_TABLE_H
#define RPI5_CRYPTO_TABLE_H
#include <libkern/crypto/register_crypto.h>
/* Unregistered candidate; mutable type matches the registration ABI. */
extern struct crypto_functions rpi5_crypto_functions;
#endif
