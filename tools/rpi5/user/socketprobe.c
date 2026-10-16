/* SPDX-License-Identifier: BSD-2-Clause */
/* Raw Darwin socket ABI diagnosis, not an ifconfig/route/SSH replacement.
 * Only Unix socketpair or literal 127.0.0.1 with ephemeral ports. No interface
 * changes, DNS, filesystem sockets, fork, threads, external traffic or retries.
 */
#include "runtime.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <sys/socket.h>
#include <netinet/in.h>

_Static_assert(sizeof(struct sockaddr_in) == 16, "Darwin IPv4 sockaddr ABI");
_Static_assert(sizeof(socklen_t) == 4, "Darwin socklen ABI");
_Static_assert(sizeof(struct pollfd) == 8, "Darwin poll ABI");
_Static_assert(AF_UNIX == 1 && AF_INET == 2, "Darwin address families");
_Static_assert(EAGAIN == 35 && EINPROGRESS == 36, "Darwin socket errno ABI");

#define MESSAGE_BYTES 32
#define POLL_MS 200
#define IO_STEPS 16
static unsigned operation_count;
struct guarded_length { unsigned before; socklen_t value; unsigned after; };
#define LENGTH_INITIAL(n) {0xc3c3c3c3,(n),0x3c3c3c3c}

static int length_intact(const struct guarded_length *p, unsigned expected)
{
    return p->before==0xc3c3c3c3 && p->after==0x3c3c3c3c && p->value==expected;
}

static void result(const char *name, long value)
{
    rt_put(1,"SOCKETPROBE:"); rt_put(1,name); rt_put(1,"=");
    if (value < 0) { rt_put(1,"-"); rt_number(1,0UL-(unsigned long)value); }
    else rt_number(1,(unsigned long)value);
    rt_put(1,"\n");
}

static long call(const char *name, long number, long a, long b, long c, long d, long e, long f)
{
    /* Excludes output writes. All data-path loops and syscall counts are finite;
     * a broken/hung kernel syscall itself still needs independent containment. */
    if (++operation_count > 256) { result("CALL_BOUND",-1); return -EIO; }
    long value = rt_call(number,a,b,c,d,e,f);
    result(name,value); return value;
}

static int own(long fd) { return fd >= 3 && fd <= INT_MAX; }

static int close_fd(int *fd)
{
    if (*fd < 0) return 0;
    int value = *fd; *fd = -1; /* Never retry close, including EINTR. */
    return call("CLOSE",6,value,0,0,0,0,0) == 0 ? 0 : -1;
}

static int prepare_fd(int fd)
{
    long flags = call("GETFL",92,fd,F_GETFL,0,0,0,0);
    if (flags < 0 || flags > INT_MAX) return -1;
    if (call("SETFL_NONBLOCK",92,fd,F_SETFL,flags|O_NONBLOCK,0,0,0) != 0) return -1;
    flags = call("GETFL_VERIFY",92,fd,F_GETFL,0,0,0,0);
    if (flags < 0 || !(flags&O_NONBLOCK)) return -1;
    int yes = 1;
    return call("NOSIGPIPE",105,fd,SOL_SOCKET,SO_NOSIGPIPE,(long)&yes,sizeof(yes),0) == 0 ? 0 : -1;
}

static int ready(int fd, short events, int eof_ok)
{
    struct pollfd p = {fd,events,0};
    long rc = call("POLL",230,(long)&p,1,POLL_MS,0,0,0);
    if (rc != 1 || (p.revents&(POLLERR|POLLNVAL)) ||
        (p.revents&~(events|POLLHUP)) || !(p.revents&(events|(eof_ok?POLLHUP:0))) ||
        (!eof_ok && (p.revents&POLLHUP))) return -1;
    return 0;
}

struct guarded_message {
    unsigned char before[16], data[MESSAGE_BYTES+1], after[16];
};

static void fill(struct guarded_message *value)
{
    for (unsigned i=0;i<16;i++) { value->before[i]=0xc3; value->after[i]=0x3c; }
    for (unsigned i=0;i<sizeof(value->data);i++) value->data[i]=0xa5;
}

static int intact(const struct guarded_message *value)
{
    for (unsigned i=0;i<16;i++) if (value->before[i]!=0xc3 || value->after[i]!=0x3c) return 0;
    return 1;
}

static void message(unsigned char bytes[MESSAGE_BYTES], unsigned tag)
{
    for (unsigned i=0;i<MESSAGE_BYTES;i++) bytes[i]=(unsigned char)(i^tag);
}

static int same(const unsigned char *a, const unsigned char *b, unsigned length)
{
    for (unsigned i=0;i<length;i++) if (a[i]!=b[i]) return 0;
    return 1;
}

static int stream_transfer(int from, int to, unsigned tag)
{
    unsigned char bytes[MESSAGE_BYTES]; struct guarded_message received;
    message(bytes,tag); fill(&received);
    unsigned sent=0,got=0;
    for (unsigned step=0; sent<MESSAGE_BYTES && step<IO_STEPS; step++) {
        if (ready(from,POLLOUT,0)) return -1;
        long n = call("STREAM_WRITE",4,from,(long)(bytes+sent),MESSAGE_BYTES-sent,0,0,0);
        if (n <= 0 || (unsigned long)n > MESSAGE_BYTES-sent) return -1;
        sent+=(unsigned)n;
    }
    if (sent!=MESSAGE_BYTES) return -1;
    for (unsigned step=0; got<MESSAGE_BYTES && step<IO_STEPS; step++) {
        if (ready(to,POLLIN,0)) return -1;
        long n = call("STREAM_READ",3,to,(long)(received.data+got),MESSAGE_BYTES-got,0,0,0);
        if (!intact(&received) || n <= 0 || (unsigned long)n > MESSAGE_BYTES-got) return -1;
        got+=(unsigned)n;
    }
    if (got!=MESSAGE_BYTES || received.data[MESSAGE_BYTES]!=0xa5 || !same(bytes,received.data,MESSAGE_BYTES)) return -1;
    result("STREAM_PAYLOAD_MATCH",MESSAGE_BYTES); return 0;
}

static int half_close(int from, int to)
{
    if (call("SHUT_WR",134,from,SHUT_WR,0,0,0,0) != 0 || ready(to,POLLIN,1)) return -1;
    struct guarded_message value; fill(&value);
    long n=call("STREAM_EOF",3,to,(long)value.data,sizeof(value.data),0,0,0);
    if (n!=0 || !intact(&value)) return -1;
    for (unsigned i=0;i<sizeof(value.data);i++) if (value.data[i]!=0xa5) return -1;
    return 0;
}

static int unix_pair(void)
{
    struct { unsigned before; int fd[2]; unsigned after; } pair = {0xc3c3c3c3,{-1,-1},0x3c3c3c3c};
    int a=-1,b=-1,ok=0;
    long rc=call("UNIX_SOCKETPAIR",135,AF_UNIX,SOCK_STREAM,0,(long)pair.fd,0,0);
    if (rc!=0) return -1;
    if (pair.before!=0xc3c3c3c3 || pair.after!=0x3c3c3c3c) {
        result("DESCRIPTOR_BUFFER_DAMAGE",1); return -1;
    }
    if (!own(pair.fd[0]) || !own(pair.fd[1]) || pair.fd[0]==pair.fd[1]) {
        /* Do not close stdio, duplicate an ownership claim or retry anything. */
        if (own(pair.fd[0])) a=pair.fd[0];
        if (own(pair.fd[1]) && pair.fd[1]!=a) b=pair.fd[1];
        goto done;
    }
    a=pair.fd[0]; b=pair.fd[1];
    if (prepare_fd(a) || prepare_fd(b) || stream_transfer(a,b,0x51) ||
        stream_transfer(b,a,0xa2) || half_close(a,b)) goto done;
    /* EOF in one direction must not disable the reverse direction. */
    if (stream_transfer(b,a,0x13)) goto done;
    ok=1;
done:
    if (close_fd(&b)) ok=0;
    if (close_fd(&a)) ok=0;
    return ok?0:-1;
}

static struct sockaddr_in loopback(void)
{
    struct sockaddr_in address={0};
    address.sin_len=sizeof(address); address.sin_family=AF_INET;
    address.sin_addr.s_addr=__builtin_bswap32(UINT32_C(0x7f000001));
    return address;
}

static int bound_address(int fd, struct sockaddr_in *address)
{
    struct { unsigned before; struct sockaddr_in value; unsigned after; } out = {0xc3c3c3c3,{0},0x3c3c3c3c};
    struct guarded_length size=LENGTH_INITIAL(sizeof(out.value));
    if (call("GETSOCKNAME",32,fd,(long)&out.value,(long)&size.value,0,0,0) != 0 ||
        out.before!=0xc3c3c3c3 || out.after!=0x3c3c3c3c || !length_intact(&size,sizeof(out.value)) ||
        out.value.sin_len!=sizeof(out.value) || out.value.sin_family!=AF_INET ||
        out.value.sin_addr.s_addr!=__builtin_bswap32(UINT32_C(0x7f000001)) || !out.value.sin_port) return -1;
    *address=out.value; return 0;
}

static int socket_fd(int type, int existing)
{
    long fd=call("SOCKET",97,AF_INET,type,0,0,0,0);
    if (!own(fd) || fd==existing) return -1;
    int result_fd=(int)fd;
    if (prepare_fd(result_fd)) { (void)close_fd(&result_fd); return -1; }
    return result_fd;
}

static int udp(void)
{
    int a=-1,b=-1,ok=0; struct sockaddr_in aa=loopback(),ba=loopback();
    a=socket_fd(SOCK_DGRAM,-1); if (a<0) goto done;
    b=socket_fd(SOCK_DGRAM,a); if (b<0) goto done;
    if (call("UDP_BIND_A",104,a,(long)&aa,sizeof(aa),0,0,0) != 0 ||
        call("UDP_BIND_B",104,b,(long)&ba,sizeof(ba),0,0,0) != 0 ||
        bound_address(a,&aa) || bound_address(b,&ba) || aa.sin_port==ba.sin_port) goto done;
    for (unsigned direction=0;direction<2;direction++) {
        unsigned char bytes[MESSAGE_BYTES]; struct guarded_message value;
        message(bytes,direction?0x29:0x62); fill(&value);
        int from=direction?b:a,to=direction?a:b;
        struct sockaddr_in *dest=direction?&aa:&ba,*source=direction?&ba:&aa;
        struct { unsigned before; struct sockaddr_in value; unsigned after; } peer={0xc3c3c3c3,{0},0x3c3c3c3c};
        struct guarded_length size=LENGTH_INITIAL(sizeof(peer.value));
        if (call("UDP_SENDTO",133,from,(long)bytes,sizeof(bytes),MSG_DONTWAIT,(long)dest,sizeof(*dest)) != MESSAGE_BYTES ||
            ready(to,POLLIN,0)) goto done;
        long n=call("UDP_RECVFROM",29,to,(long)value.data,sizeof(value.data),MSG_DONTWAIT,(long)&peer.value,(long)&size.value);
        if (n!=MESSAGE_BYTES || !intact(&value) || value.data[MESSAGE_BYTES]!=0xa5 ||
            !same(bytes,value.data,MESSAGE_BYTES) || peer.before!=0xc3c3c3c3 || peer.after!=0x3c3c3c3c ||
            !length_intact(&size,sizeof(peer.value)) || peer.value.sin_len!=sizeof(peer.value) || peer.value.sin_family!=AF_INET ||
            peer.value.sin_addr.s_addr!=source->sin_addr.s_addr || peer.value.sin_port!=source->sin_port) goto done;
        result("UDP_PAYLOAD_AND_PEER_MATCH",MESSAGE_BYTES);
    }
    ok=1;
done:
    if (close_fd(&b)) ok=0;
    if (close_fd(&a)) ok=0;
    return ok?0:-1;
}

static int tcp(void)
{
    int listener=-1,client=-1,server=-1,ok=0; struct sockaddr_in address=loopback();
    listener=socket_fd(SOCK_STREAM,-1); if (listener<0) goto done;
    if (call("TCP_BIND",104,listener,(long)&address,sizeof(address),0,0,0) != 0 ||
        bound_address(listener,&address) || call("LISTEN",106,listener,1,0,0,0,0) != 0) goto done;
    client=socket_fd(SOCK_STREAM,listener); if (client<0) goto done;
    long rc=call("CONNECT",98,client,(long)&address,sizeof(address),0,0,0);
    if ((rc!=0 && rc!=-EINPROGRESS) || ready(client,POLLOUT,0)) goto done;
    struct { unsigned before; int value; unsigned after; } error={0xc3c3c3c3,-1,0x3c3c3c3c};
    struct guarded_length size=LENGTH_INITIAL(sizeof(error.value));
    if (call("SO_ERROR",118,client,SOL_SOCKET,SO_ERROR,(long)&error.value,(long)&size.value,0) != 0 ||
        error.before!=0xc3c3c3c3 || error.after!=0x3c3c3c3c || !length_intact(&size,sizeof(error.value)) || error.value!=0 ||
        ready(listener,POLLIN,0)) goto done;
    long accepted=call("ACCEPT",30,listener,0,0,0,0,0);
    if (!own(accepted) || accepted==client || accepted==listener) goto done;
    server=(int)accepted;
    if (prepare_fd(server) || stream_transfer(client,server,0x73) ||
        stream_transfer(server,client,0xb4) || half_close(client,server) ||
        stream_transfer(server,client,0xe5)) goto done;
    ok=1;
done:
    if (close_fd(&server)) ok=0;
    if (close_fd(&client)) ok=0;
    if (close_fd(&listener)) ok=0;
    return ok?0:-1;
}

int socketprobe_main(int argc, char **argv)
{
    operation_count=0;
    if (argc!=2 || !argv || !argv[1] || (!rt_equal(argv[1],"unix") && !rt_equal(argv[1],"inet"))) return 2;
    rt_put(1,"SOCKETPROBE:BEGIN:RAW_DARWIN_V1\n");
    int rc;
    if (rt_equal(argv[1],"unix")) { rt_put(1,"SOCKETPROBE:MODE=unix\n"); rc=unix_pair(); }
    else {
        rt_put(1,"SOCKETPROBE:MODE=inet_LOOPBACK_ONLY\n");
        rc=udp(); if (!rc) { rt_put(1,"SOCKETPROBE:UDP_PASS\n"); rc=tcp(); }
        if (!rc) rt_put(1,"SOCKETPROBE:TCP_PASS\n");
    }
    result("OPERATIONS",operation_count);
    rt_put(1,rc?"SOCKETPROBE:FAIL\n":"SOCKETPROBE:PASS\n");
    rt_put(1,"SOCKETPROBE:END:NOT_ETHERNET_OR_SSH_PROOF\n");
    return rc?1:0;
}

#ifndef RPI5_SOCKETPROBE_HOST_TEST
_Noreturn void user_start(uintptr_t *stack)
{
    if (stack[0]!=2 || !((char **) (stack+1))[0]) rt_exit(2);
    rt_exit(socketprobe_main((int)stack[0],(char **)(stack+1)));
}
#endif
