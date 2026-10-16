/* SPDX-License-Identifier: BSD-2-Clause */
/* Select only Apple OpenSSH's public-ABI localtime_r compatibility body. */
#include "includes.h"
#undef HAVE_LOCALTIME_R
/* bsd-misc.c already contributes these two definitions to the unchanged full
 * client. Give the provider copy private names; they are not forced or used. */
#define ssh_get_progname rpi5_openssh_unused_ssh_get_progname
#define pledge rpi5_openssh_unused_pledge
