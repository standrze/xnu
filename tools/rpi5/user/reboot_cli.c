/* SPDX-License-Identifier: BSD-2-Clause
 * Project-owned front end, not Apple's launchd-integrated reboot utility.
 * The production reboot() implementation is the unchanged Apple wrapper.
 * Every return from reboot, including an unexpected zero, is a failure.
 */
#include <sys/reboot.h>
#include <unistd.h>
#include <string.h>

int rpi5_pthread_smoke_main(int argc, char **argv)
{
    static const char usage[] = "usage: /sbin/reboot [--help]\n"
        "Privileged normal restart; poweroff and quick modes unsupported.\n";
    static const char failed[] = "reboot: restart syscall returned; no reset proven\n";
    if (argc == 2 && !strcmp(argv[1], "--help")) {
        return write(1, usage, sizeof(usage)-1) == sizeof(usage)-1 ? 0 : 1;
    }
    if (argc != 1) {
        (void)write(2, usage, sizeof(usage)-1);
        return 64;
    }
    /* Kernel suser/MAC authorization and normal shutdown remain authoritative.
     * RB_AUTOBOOT is zero: no QUICK/NOSYNC/PANIC/HALT flags are exposed here. */
    (void)reboot(RB_AUTOBOOT);
    (void)write(2, failed, sizeof(failed)-1);
    return 1;
}
