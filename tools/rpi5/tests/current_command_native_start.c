/* SPDX-License-Identifier: BSD-2-Clause */
/* Native test entry only. Target uses its already-audited _start and real
 * darwin_static_start; this adapter does not enter the Pi package. */
char *__progname;
extern int darwin_network_command_main(int, char **);
int main(int argc, char **argv)
{
    __progname = argc ? argv[0] : (char *)"command";
    return darwin_network_command_main(argc, argv);
}
