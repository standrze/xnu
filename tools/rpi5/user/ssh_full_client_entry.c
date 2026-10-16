/* SPDX-License-Identifier: BSD-2-Clause
 * Link-only composition: original client main, real initialized pthread
 * prerequisite. This file does not create a version-only surrogate client.
 */
extern int rpi5_packet_pthread_prerequisite(int, char **);
extern int rpi5_original_ssh_main(int, char **);

int rpi5_pthread_smoke_main(int argc, char **argv)
{
    int status = rpi5_packet_pthread_prerequisite(argc, argv);
    if (status) return status;
    return rpi5_original_ssh_main(argc, argv);
}
