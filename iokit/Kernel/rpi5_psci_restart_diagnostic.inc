/* SPDX-License-Identifier: BSD-2-Clause
 * Distinct diagnostic composition. The original candidate callback and its
 * Apple shutdown/permission routing are included unchanged. Panic enum modes
 * are excluded there, not every possible panic context.
 */
#include "iokit/Kernel/rpi5_psci_restart_candidate.inc"
extern "C" {
#include "loader/rpi5/psci_restart_diagnostic.h"
void rpi5_restart_diagnostic_boot_ready(void)
{
    int enabled = 0;
    if (!PE_parse_boot_argn("rpi5_psci_restart", &enabled, sizeof(enabled)) || enabled != 1) return;
    const void *tree = NULL;
    size_t bytes = 0;
    if (!rpi5_firmware_fdt_view(&tree, &bytes)) return;
    (void)rpi5_restart_diagnostic_ready(tree, bytes);
}
}
