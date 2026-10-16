/* SPDX-License-Identifier: BSD-2-Clause
 * Fixed public packet material only. Genuine pthread lifecycle is a required
 * prerequisite; this is not an SSH transport, key exchange, or entropy test.
 */
extern int rpi5_packet_pthread_prerequisite(int, char **);
extern int darwin_network_command_main(int, char **);

int rpi5_pthread_smoke_main(int argc, char **argv)
{
    int result = rpi5_packet_pthread_prerequisite(argc, argv);
    if (result) return result;
    return darwin_network_command_main(argc, argv);
}

#ifdef RPI5_PACKET_HOST
int main(int argc, char **argv) { return rpi5_pthread_smoke_main(argc, argv); }
#endif
