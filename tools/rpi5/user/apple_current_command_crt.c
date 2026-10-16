/* SPDX-License-Identifier: BSD-2-Clause */
/* Static startup initializes this from the actual kernel-provided argv[0].
 * Match Apple's CRT accessor ABI; do not fabricate a process name. */
extern char *__progname;
char **_NSGetProgname(void)
{
    return &__progname;
}
