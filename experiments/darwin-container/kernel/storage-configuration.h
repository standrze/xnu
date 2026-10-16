/* SPDX-License-Identifier: BSD-2-Clause
 * Provider is compiled against the frozen VZ ABI headers. Its final kernel
 * MUST enable FS_COMPRESSION globally through MASTER.arm64.vzgeneric.
 */
#if !defined(ARM64_BOARD_CONFIG_VZGENERIC) || !defined(DEVELOPMENT)
#error "VZ storage provider requires VZGENERIC DEVELOPMENT"
#endif
#undef FS_COMPRESSION
#define FS_COMPRESSION 1
