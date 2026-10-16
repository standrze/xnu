/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_CONSOLE_MIRROR_H
#define RPI5_CONSOLE_MIRROR_H
/* Kernel-private, one-way gate. These APIs prove no mapping or scanout.
 * Publish only after Apple video initialization and an independently verified,
 * permanently retained XRGB mapping/cache/scanout contract, on a quiescent setup
 * path. No current caller publishes it. The initial state is OFF.
 * Revoke permanently disables future mirror admissions; an already admitted
 * call can finish, so revocation does not authorize freeing/unmapping memory.
 * Output to the original UART always happens exactly once, before the mirror.
 * Polling/debugger output never enters Apple's video ticket lock.
 */
bool rpi5_console_mirror_publish(void);
void rpi5_console_mirror_revoke(void);
#endif
