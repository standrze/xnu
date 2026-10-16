/* SPDX-License-Identifier: BSD-2-Clause
 * Focused native fixture for the actual VM network split-ring transport.
 * Does not prove a virtual NIC, BSD attachment or real network traffic.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "virtio_net.h"
struct used_element { uint32_t id, length; };
struct used_ring { uint16_t flags, index; struct used_element ring[8]; };
static unsigned char dma[VZ_NET_DMA_BYTES] __attribute__((aligned(16384)));
static unsigned char notify[8], common[64];
int main(void)
{
    struct vz_net_queue q={.dma=dma,.notify=notify,.common=common};
    unsigned char frame[VZ_NET_FRAME_MAX], output[VZ_NET_FRAME_MAX];size_t n=0;
    for(unsigned i=0;i<sizeof(frame);i++) frame[i]=(unsigned char)i;
    for(unsigned i=0;i<VZ_NET_QUEUE_SIZE;i++) assert(vz_net_send(&q,frame,sizeof(frame))==0);
    assert(vz_net_send(&q,frame,sizeof(frame))==1);
    assert(vz_net_send(&q,frame,sizeof(frame)+1)==-1);
    struct used_ring *tx=(struct used_ring *)(dma+VZ_NET_QUEUE_BYTES+0x200);
    tx->ring[0]=(struct used_element){.id=3};tx->index=1;
    assert(vz_net_send(&q,frame,14)==0);
    /* Short ARP frames are padded in the owned TX buffer, not caller memory. */
    struct descriptor { uint64_t address; uint32_t length; uint16_t flags,next; };
    struct descriptor *descriptors=(struct descriptor *)(dma+VZ_NET_QUEUE_BYTES);
    assert(descriptors[3].length==VZ_NET_HEADER_BYTES+60);
    struct used_ring *rx=(struct used_ring *)(dma+0x200);
    memcpy(dma+VZ_NET_BUFFER_OFFSET+VZ_NET_HEADER_BYTES,frame,sizeof(frame));
    rx->ring[0]=(struct used_element){.id=0,.length=VZ_NET_HEADER_BYTES+sizeof(frame)};rx->index=1;
    assert(vz_net_receive(&q,output,&n)==1 && n==sizeof(frame) && !memcmp(frame,output,n));
    rx->ring[1]=(struct used_element){.id=1,.length=0};rx->index=2;
    assert(vz_net_receive(&q,output,&n)==2 && !q.failed);
    unsigned char *partial=dma+VZ_NET_BUFFER_OFFSET+2*VZ_NET_BUFFER_BYTES;
    partial[0]=1;partial[6]=14;partial[8]=2;
    partial[VZ_NET_HEADER_BYTES+14]=1;partial[VZ_NET_HEADER_BYTES+15]=2;
    partial[VZ_NET_HEADER_BYTES+18]=3;partial[VZ_NET_HEADER_BYTES+19]=4;
    rx->ring[2]=(struct used_element){.id=2,.length=VZ_NET_HEADER_BYTES+20};rx->index=3;
    assert(vz_net_receive(&q,output,&n)==1 && output[16]==0xfb && output[17]==0xf9);
    unsigned char *rsc=dma+VZ_NET_BUFFER_OFFSET+3*VZ_NET_BUFFER_BYTES;
    rsc[0]=6;rsc[6]=25;
    memcpy(rsc+VZ_NET_HEADER_BYTES,frame,sizeof(frame));
    rx->ring[3]=(struct used_element){.id=3,.length=VZ_NET_HEADER_BYTES+sizeof(frame)};rx->index=4;
    assert(vz_net_receive(&q,output,&n)==1 && n==sizeof(frame) && !memcmp(frame,output,n));
    unsigned char *invalid=dma+VZ_NET_BUFFER_OFFSET+4*VZ_NET_BUFFER_BYTES;
    invalid[0]=5;
    rx->ring[4]=(struct used_element){.id=4,.length=VZ_NET_HEADER_BYTES+60};rx->index=5;
    assert(vz_net_receive(&q,output,&n)==2 && !q.failed && q.last_rejected);
    rx->ring[5]=(struct used_element){.id=8,.length=14};rx->index=6;
    assert(vz_net_receive(&q,output,&n)==-1 && q.failed && common[20]==0);
    puts("VM net rings: TX bounds/padding/reclaim, RX bytes/checksum/RSC flags, empty and invalid descriptors passed");
    return 0;
}
