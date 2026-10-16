/* SPDX-License-Identifier: BSD-2-Clause
 * PID1-owned local datagram endpoint. Only its framed VM console reaches host
 * Metal. No guest network port or host listener is opened by this bridge.
 */
#include "runtime.h"
#include "gpu_relay.h"
#include <fcntl.h>
#include <sys/time.h>
_Static_assert(sizeof(struct sockaddr_un)==106, "Darwin arm64 local socket ABI");
static int64_t now(void)
{
    struct timeval value={0};
    return rt_call(116,(long)&value,0,0,0,0,0)<0 ? -1 : value.tv_sec;
}
int gpu_relay_open(struct gpu_relay *r)
{
    r->fd=-1;r->owned=r->pending=0;r->sequence=0;
    long fd=rt_call(97,AF_UNIX,SOCK_DGRAM,0,0,0,0);
    if(fd<0 || fd>=32) { if(fd>=0) rt_close((int)fd); return -1; }
    r->fd=(int)fd;
    struct sockaddr_un address={0};address.sun_len=sizeof(address);address.sun_family=AF_UNIX;
    (void)rt_copy(address.sun_path,sizeof(address.sun_path),GPU_SOCKET_PATH);
    if(rt_call(104,fd,(long)&address,sizeof(address),0,0,0)<0) goto fail;
    r->owned=1;
    if(rt_call(15,(long)GPU_SOCKET_PATH,0600,0,0,0,0)<0) goto fail;
    int buffer=4096;
    if(rt_call(105,fd,SOL_SOCKET,SO_RCVBUF,(long)&buffer,sizeof(buffer),0)<0) goto fail;
    long flags=rt_call(92,fd,F_GETFL,0,0,0,0);
    if(flags<0 || rt_call(92,fd,F_SETFL,flags|O_NONBLOCK,0,0,0)<0) goto fail;
    return 0;
fail:
    gpu_relay_close(r);return -1;
}
void gpu_relay_close(struct gpu_relay *r)
{
    if(r->fd>=0) rt_close(r->fd);
    if(r->owned) (void)rt_call(10,(long)GPU_SOCKET_PATH,0,0,0,0,0);
    r->fd=-1;r->owned=r->pending=0;
}
int gpu_relay_request(struct gpu_relay *r, unsigned char payload[256], size_t *size)
{
    if(r->pending) return -1;
    unsigned char bytes[257];
    r->peer_size=sizeof(r->peer);
    long n=rt_call(29,r->fd,(long)bytes,sizeof(bytes),0,(long)&r->peer,(long)&r->peer_size);
    if(n==-4 || n==-35) return 0;
    /* The sender must have a real named local endpoint. Bad guest-local packets
     * are dropped without involving Metal or damaging the shell transport. */
    if(n<12 || n>256 || r->peer_size<3 || r->peer_size>sizeof(r->peer) ||
       r->peer.sun_family!=AF_UNIX || !r->peer.sun_path[0]) return 0;
    if(r->sequence==UINT32_MAX) return -1;
    for(long i=0;i<n;i++) payload[i]=bytes[i];
    gpu_set_word(payload+4,++r->sequence);
    int64_t time=now();if(time<0) return -1;
    r->deadline=time+10;r->pending=1;*size=(size_t)n;
    return 1;
}
int gpu_relay_reply(struct gpu_relay *r, const unsigned char *p, size_t size)
{
    if(!r->pending || size<12 || size>12+GPU_VECTOR_MAX*4 ||
       p[0]!='D' || p[1]!='G' || p[2]!='R' || p[3]!='1' || gpu_word(p+4)!=r->sequence) return -1;
    /* The local API never exposes the wire ID: it belongs to this PID1 session. */
    unsigned char bytes[256];for(size_t i=0;i<size;i++) bytes[i]=p[i];
    gpu_set_word(bytes+4,0);
    long n=rt_call(133,r->fd,(long)bytes,(long)size,0,(long)&r->peer,r->peer_size);
    r->pending=0;
    /* A client can exit before completion; dropping its reply is not VM failure. */
    return n==(long)size || n==-2 || n==-35 || n==-61 || n==-57 ? 0 : -1;
}
int gpu_relay_expired(struct gpu_relay *r)
{ int64_t time=now();return time<0 || (r->pending && time>=r->deadline); }
