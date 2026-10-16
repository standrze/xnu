/* SPDX-License-Identifier: BSD-2-Clause
 * One native split-ring fixture for the actual shared console transport.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "virtio_console.h"

struct used_element { uint32_t id, length; };
struct used { uint16_t flags, index; struct used_element ring[8]; };
static unsigned char receive[16384], notify[4096];

int main(void)
{
    struct vz_console_shared shared = {0};
    struct vz_console_binding binding = {.shared=&shared, .notify=notify, .queues={receive, 0}};
    struct used *used=(struct used *)(receive+0x200);
    assert(vz_console_rx_ready(&binding)==0);
    used->ring[0]=(struct used_element){.id=3, .length=0};
    used->ring[1]=(struct used_element){.id=1, .length=2};
    receive[0x400+256]=0x80; receive[0x400+257]=0xff;
    used->index=2;
    assert(vz_console_rx_ready(&binding)==1 && shared.received_used==1);
    assert(vz_console_getc(&binding)==0x80 && shared.received_offset==1);
    assert(vz_console_getc(&binding)==0xff && shared.received_used==2);
    assert(vz_console_getc(&binding)==-1);
    /* Used-index wraparound and descriptor identity are independent. */
    memset(receive, 0, sizeof receive);
    shared.received_used=UINT16_MAX; shared.received_offset=0;
    used->ring[7]=(struct used_element){.id=4, .length=1};
    receive[0x400+4*256]=42; used->index=0;
    assert(vz_console_getc(&binding)==42 && shared.received_used==0);
    used->ring[0]=(struct used_element){.id=8, .length=1}; used->index=1;
    assert(vz_console_rx_ready(&binding)==-3);
    used->ring[0]=(struct used_element){.id=0, .length=257};
    assert(vz_console_rx_ready(&binding)==-4);
    puts("console RX: empty completions, binary bytes, index wrap and invalid bounds passed");
    return 0;
}
