/* SPDX-License-Identifier: BSD-2-Clause */
/* Isolated compile screen of the actual decmpfs implementation. Included
 * AFTER the reference kernel's meta_features.h, which disables this feature.
 * The final storage kernel must enable FS_COMPRESSION globally through its
 * configuration, not link an enabled object into a mismatched kernel.
 */
#if !defined(ARM64_BOARD_CONFIG_BCM2712) || !defined(DEVELOPMENT)
#error "Gate 4 compression screen is only for BCM2712 DEVELOPMENT"
#endif
#undef FS_COMPRESSION
#define FS_COMPRESSION 1
