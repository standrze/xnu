/* SPDX-License-Identifier: BSD-2-Clause */
#include "runtime.h"

/* XNU bsd/sys/reboot.h has RB_HALT, not RB_POWERDOWN. For this VM's
 * platform expert, halt_all_cpus(false) -> kPEHaltCPU -> PSCI SYSTEM_OFF.
 * Do not import a POWERDOWN constant from another BSD or Linux ABI.
 */
enum { DARWIN_SYS_REBOOT = 55, DARWIN_RB_HALT = 0x08 };

int poweroff_main(int argc)
{
    if (argc != 1) { rt_put(2, "usage: poweroff\n"); return 2; }
    rt_put(1, "DARWIN:POWEROFF:REQUEST\n");
    long result = rt_call(DARWIN_SYS_REBOOT, DARWIN_RB_HALT, 0, 0, 0, 0, 0);
    if (result < 0) rt_error("poweroff/reboot", result);
    else rt_put(2, "poweroff: reboot returned without stopping the VM\n");
    /* A returned syscall is not evidence of shutdown, even if it returned 0. */
    return 1;
}
