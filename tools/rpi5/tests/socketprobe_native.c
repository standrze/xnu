/* SPDX-License-Identifier: BSD-2-Clause */
/* Native Darwin loopback adapter. This is not Pi/raw-SVC execution evidence. */
#include "../user/runtime.h"
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>

int socketprobe_main(int argc, char **argv);
static int owned[128], violations, calls, fail_at;
static const char *scenario;

static int is(const char *s) { return strcmp(scenario,s)==0; }
static long answer(long n) { return n<0?-errno:n; }
static long adopt(int fd)
{
    if (fd<0) return -errno;
    if (fd<3 || fd>=128 || owned[fd]) { violations++; return -EIO; }
    owned[fd]=1; return fd;
}
static int address_ok(const struct sockaddr_in *p, long size)
{
    return p && size==sizeof(*p) && p->sin_len==sizeof(*p) &&
        p->sin_family==AF_INET && p->sin_addr.s_addr==htonl(INADDR_LOOPBACK);
}
static int any_owned(void)
{
    for (int i=3;i<128;i++) if (owned[i]) return i;
    return -1;
}

long rt_call(long number,long a,long b,long c,long d,long e,long f)
{
    calls++;
    if (fail_at==calls && number!=6) return -EIO;
    if (number!=97 && number!=135 && number!=230 &&
        (a<3 || a>=128 || !owned[a])) { violations++; return -EBADF; }
    switch (number) {
    case 3: {
        size_t n=(size_t)c;
        if (is("partial-two") && n>2) n=2;
        if (is("partial-one") && n>1) n=1;
        long rc=answer(read((int)a,(void *)b,n));
        if (rc>0 && is("payload")) ((unsigned char *)b)[0]^=1;
        if (rc>0 && is("read-overrun")) ((unsigned char *)b)[c+1]^=1;
        if (rc==0 && is("bad-eof")) rc=1;
        return rc;
    }
    case 4: {
        size_t n=(size_t)c;
        if (is("partial-two") && n>2) n=2;
        if (is("partial-one") && n>1) n=1;
        return answer(write((int)a,(const void *)b,n));
    }
    case 6: {
        owned[a]=0;
        long rc=answer(close((int)a));
        /* Inject an uncertain close result after the native fd is released;
         * verifies no retry, not the kernel's close-on-error semantics. */
        return fail_at==calls?-EINTR:rc;
    }
    case 29: {
        long rc=answer(recvfrom((int)a,(void *)b,(size_t)c,(int)d,(struct sockaddr *)e,(socklen_t *)f));
        if (rc>=0 && is("udp-payload")) ((unsigned char *)b)[0]^=1;
        if (rc>=0 && is("udp-peer")) ((struct sockaddr_in *)e)->sin_addr.s_addr=0;
        if (rc>=0 && is("udp-length")) *(socklen_t *)f=0;
        if (rc>=0 && is("udp-overrun")) ((unsigned char *)b)[c]^=1;
        if (rc>=0 && is("length-overrun")) ((socklen_t *)f)[1]^=1;
        return rc;
    }
    case 30:
        if (b || c) { violations++; return -EINVAL; }
        if (is("accept-alias")) return a;
        return adopt(accept((int)a,NULL,NULL));
    case 32: {
        long rc=answer(getsockname((int)a,(struct sockaddr *)b,(socklen_t *)c));
        if (!rc && is("address")) ((struct sockaddr_in *)b)->sin_family=AF_UNIX;
        if (!rc && is("name-length")) *(socklen_t *)c=0;
        return rc;
    }
    case 92:
        if (b!=F_GETFL && b!=F_SETFL) { violations++; return -EINVAL; }
        if (b==F_SETFL && !(c&O_NONBLOCK)) { violations++; return -EINVAL; }
        if (is("nonblock") && b==F_GETFL) return 0;
        return answer(fcntl((int)a,(int)b,(int)c));
    case 97:
        if (a!=AF_INET || (b!=SOCK_STREAM && b!=SOCK_DGRAM) || c) { violations++; return -EINVAL; }
        if (is("socket-stdio")) return 1;
        if (is("socket-alias") && any_owned()>=0) return any_owned();
        return adopt(socket((int)a,(int)b,(int)c));
    case 98:
    case 104:
        if (!address_ok((struct sockaddr_in *)b,c) ||
            (number==104 && ((struct sockaddr_in *)b)->sin_port)) { violations++; return -EINVAL; }
        return number==98?answer(connect((int)a,(struct sockaddr *)b,(socklen_t)c)):
                          answer(bind((int)a,(struct sockaddr *)b,(socklen_t)c));
    case 105:
        if (b!=SOL_SOCKET || c!=SO_NOSIGPIPE || !d || e!=sizeof(int) || *(int *)d!=1) {
            violations++; return -EINVAL;
        }
        return answer(setsockopt((int)a,(int)b,(int)c,(const void *)d,(socklen_t)e));
    case 106:
        if (b!=1) { violations++; return -EINVAL; }
        return answer(listen((int)a,(int)b));
    case 118: {
        if (b!=SOL_SOCKET || c!=SO_ERROR) { violations++; return -EINVAL; }
        long rc=answer(getsockopt((int)a,(int)b,(int)c,(void *)d,(socklen_t *)e));
        if (!rc && is("so-error")) *(int *)d=ECONNREFUSED;
        if (!rc && is("so-error-length")) *(socklen_t *)e=0;
        return rc;
    }
    case 133:
        if (!address_ok((struct sockaddr_in *)e,f) || !((struct sockaddr_in *)e)->sin_port || d!=MSG_DONTWAIT) {
            violations++; return -EINVAL;
        }
        if (is("short-udp")) c--;
        return answer(sendto((int)a,(const void *)b,(size_t)c,(int)d,(const struct sockaddr *)e,(socklen_t)f));
    case 134:
        if (b!=SHUT_WR) { violations++; return -EINVAL; }
        return answer(shutdown((int)a,(int)b));
    case 135: {
        if (a!=AF_UNIX || b!=SOCK_STREAM || c) { violations++; return -EINVAL; }
        int *pair=(int *)d;
        long rc=answer(socketpair((int)a,(int)b,(int)c,pair));
        if (!rc) {
            adopt(pair[0]); adopt(pair[1]);
            if (is("pair-alias")) { owned[pair[1]]=0; close(pair[1]); pair[1]=pair[0]; }
            if (is("pair-stdio")) { owned[pair[1]]=0; close(pair[1]); pair[1]=1; }
        }
        return rc;
    }
    case 230: {
        struct pollfd *p=(struct pollfd *)a;
        if (!p || b!=1 || c!=200 || p->fd<3 || p->fd>=128 || !owned[p->fd] ||
            (p->events!=POLLIN && p->events!=POLLOUT)) { violations++; return -EINVAL; }
        if (is("poll-timeout")) return 0;
        if (is("poll-error")) { p->revents=POLLERR; return 1; }
        return answer(poll(p,(nfds_t)b,(int)c));
    }
    default: violations++; return -ENOSYS;
    }
}

int rt_equal(const char *a,const char *b) { return strcmp(a,b)==0; }
void rt_put(int fd,const char *s) { if (fd!=1) violations++; fputs(s,stdout); }
void rt_number(int fd,unsigned long n) { if (fd!=1) violations++; printf("%lu",n); }

int main(int argc,char **argv)
{
    if (argc<3 || argc>4) return 3;
    scenario=argv[2]; fail_at=argc==4?atoi(argv[3]):0;
    int rc=socketprobe_main(2,argv);
    int leaks=0;
    for (int i=3;i<128;i++) if (owned[i]) { leaks++; close(i); }
    printf("NATIVE:CALLS=%d:LEAKS=%d:VIOLATIONS=%d\n",calls,leaks,violations);
    return leaks || violations?4:rc;
}
