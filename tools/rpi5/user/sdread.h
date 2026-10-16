/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_USER_SDREAD_H
#define RPI5_USER_SDREAD_H
/* Darwin ioctl encodings from this kernel's bsd/sys/{disk,ioccom}.h.
 * Kept header-free for the freestanding userspace build; native tests compare
 * them to the public headers. These queries never write media. */
#define SDREAD_BLOCK_SIZE  0x40046418UL
#define SDREAD_BLOCK_COUNT 0x40086419UL
#define SDREAD_WRITABLE    0x4004641dUL
int sdread_main(int argc, char **argv);
#endif
