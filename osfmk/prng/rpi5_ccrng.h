/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_CCRNG_H
#define RPI5_CCRNG_H
#include <corecrypto/ccrng.h>
/* Candidate only: usable after ordinary kernel PRNG registration. */
struct ccrng_state *rpi5_ccrng(int *error);
#endif
