/* SPDX-License-Identifier: BSD-2-Clause
 * Included only in a DISTINCT opt-in IOPlatformExpert translation unit.
 * The original platform callback remains first priority. This fallback is
 * reached only after Apple's existing privileged shutdown path. It never
 * handles panic, halt, poweroff or UPS modes. A failed attempt returns -1 to
 * the original halt_all_cpus loop; it does not claim or retry a reset.
 */
#if !defined(ARM64_BOARD_CONFIG_BCM2712) || !DEVELOPMENT || !RPI5_FIRMWARE_FDT_HANDOFF
#error "Restart candidate requires the BCM2712 DEVELOPMENT retained-FDT build"
#endif
extern "C" {
#include "loader/rpi5/psci_restart_candidate.h"
#include "osfmk/arm64/rpi5_firmware_fdt_api.h"
}
static struct rpi5_restart_once rpi5_restart_candidate_once;
static int rpi5_restart_candidate_platform(unsigned int type)
{
    if (type != kPERestartCPU) return -1;
    int enabled = 0;
    if (!PE_parse_boot_argn("rpi5_psci_restart", &enabled, sizeof(enabled)) || enabled != 1) return -1;
    const void *tree = NULL;
    size_t bytes = 0;
    if (!rpi5_firmware_fdt_view(&tree, &bytes)) return -1;
    (void)rpi5_restart_attempt(&rpi5_restart_candidate_once, tree, bytes);
    return -1;
}
