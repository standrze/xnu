/* SPDX-License-Identifier: BSD-2-Clause
 * Explicit experimental network bring-up diagnostic, not Apple ipconfig,
 * ifconfig or a replacement resolver. All traffic uses the guest BSD sockets.
 */
#include "runtime.h"
#include <sys/socket.h>
#include <sys/sockio.h>
#include <sys/sysctl.h>
#include <sys/time.h>
#include <net/if.h>
#include <net/if_dl.h>
#include <net/route.h>
#include <net/bpf.h>
#include <netinet/in.h>
/* Exact ioctl ABI from this XNU's bsd/sys/sockio_private.h, not SDK public API. */
#define VZ_SIOCPROTOATTACH _IOWR('i', 80, struct ifreq)
_Static_assert(sizeof(struct ifreq)==32, "XNU arm64 ifreq ABI");
void *memcpy(void *, const void *, size_t);
void *memset(void *, int, size_t);
void bzero(void *p, size_t n) { memset(p,0,n); }
#ifdef DARWIN_APPLE_DNS
int apple_dns_answer(const unsigned char *,size_t,const unsigned char *,size_t,uint32_t *);
#endif

static uint16_t be16(uint16_t n) { return __builtin_bswap16(n); }
static int same(const void *a, const void *b, size_t n)
{ const unsigned char *x=a,*y=b; for(size_t i=0;i<n;i++) if(x[i]!=y[i]) return 0; return 1; }
static void ip_print(uint32_t value)
{ const unsigned char *p=(const unsigned char *)&value; for(unsigned i=0;i<4;i++) { if(i) rt_put(1,"."); rt_number(1,p[i]); } }
static int ip_parse(const char *s, uint32_t *ip)
{
    unsigned char bytes[4];
    for(unsigned i=0;i<4;i++) {
        unsigned value=0, digits=0;
        while(*s>='0' && *s<='9') { if(++digits>3) return -1; value=value*10+(unsigned)(*s++-'0'); }
        if(!digits || value>255 || (i<3 ? *s++!='.' : *s!=0)) return -1;
        bytes[i]=(unsigned char)value;
    }
    memcpy(ip,bytes,4); return 0;
}
static long socket_open(int type)
{
    long fd=rt_call(97,AF_INET,type,0,0,0,0);
    if(fd<0) return fd;
    struct timeval timeout={4,0};
    long receive=rt_call(105,fd,SOL_SOCKET,SO_RCVTIMEO,(long)&timeout,sizeof(timeout),0);
    if(receive<0) { rt_close((int)fd); return receive; }
    long r=rt_call(105,fd,SOL_SOCKET,SO_SNDTIMEO,(long)&timeout,sizeof(timeout),0);
    if(r<0) { rt_close((int)fd); return r; }
    return fd;
}
static struct sockaddr_in address(uint32_t ip, unsigned port)
{
    struct sockaddr_in a={0}; a.sin_len=sizeof(a); a.sin_family=AF_INET;
    a.sin_port=be16((uint16_t)port); a.sin_addr.s_addr=ip; return a;
}
static long send_packet(int fd, const void *p, size_t n, const struct sockaddr_in *to)
{ return rt_call(133,fd,(long)p,(long)n,0,(long)to,sizeof(*to)); }
static int identity(unsigned char mac[6], unsigned *index)
{
    int mib[]={CTL_NET,PF_ROUTE,0,AF_LINK,NET_RT_IFLIST,0};
    unsigned char bytes[16384]; size_t size=sizeof(bytes);
    long r=rt_call(202,(long)mib,6,(long)bytes,(long)&size,0,0);
    if(r<0) { rt_error("netctl/iflist",r); return -1; }
    if(size>sizeof(bytes)) return -1;
    for(size_t pos=0;pos<size;) {
        if(size-pos<4) return -1;
        struct if_msghdr header;
        unsigned len=bytes[pos]|((unsigned)bytes[pos+1]<<8);
        if(len<4 || len>size-pos) return -1;
        if(bytes[pos+2]==RTM_VERSION && bytes[pos+3]==RTM_IFINFO && len>=sizeof(header)) {
            memcpy(&header,bytes+pos,sizeof(header));
            size_t cursor=sizeof(header);
            for(unsigned slot=0;slot<RTAX_MAX;slot++) if(header.ifm_addrs&(1U<<slot)) {
                if(cursor+2>len) return -1;
                const unsigned char *sa=bytes+pos+cursor;
                size_t length=sa[0], rounded=length ? (length+3)&~(size_t)3 : 4;
                if(length<2 || rounded>len-cursor) return -1;
                if(slot==RTAX_IFP && sa[1]==AF_LINK && length>=8) {
                    unsigned nlen=sa[5], alen=sa[6];
                    if(nlen==3 && alen==6 && 8+nlen+alen<=length && same(sa+8,"en0",3)) {
                        memcpy(mac,sa+8+nlen,6); *index=header.ifm_index; return 0;
                    }
                }
                cursor+=rounded;
            }
        }
        pos+=len;
    }
    rt_put(2,"netctl: en0 not attached\n"); return -1;
}
static int configure(int fd, uint32_t ip, uint32_t mask)
{
    struct ifaliasreq request={0};
    rt_copy(request.ifra_name,sizeof(request.ifra_name),"en0");
    struct sockaddr_in a=address(ip,0), m=address(mask,0), b=address(ip|~mask,0);
    memcpy(&request.ifra_addr,&a,sizeof(a)); memcpy(&request.ifra_mask,&m,sizeof(m));
    memcpy(&request.ifra_broadaddr,&b,sizeof(b));
    long r=rt_call(54,fd,SIOCAIFADDR,(long)&request,0,0,0);
    if(r<0) { rt_error("netctl/address",r); return -1; }
    return 0;
}
static int default_route(uint32_t gateway)
{
    struct { struct rt_msghdr header; struct sockaddr_in dst, gateway, mask; } message={0};
    message.header.rtm_msglen=sizeof(message); message.header.rtm_version=RTM_VERSION;
    message.header.rtm_type=RTM_ADD; message.header.rtm_flags=RTF_UP|RTF_GATEWAY|RTF_STATIC;
    message.header.rtm_addrs=RTA_DST|RTA_GATEWAY|RTA_NETMASK;
    message.header.rtm_pid=(int)rt_getpid(); message.header.rtm_seq=1;
    message.dst=address(0,0); message.gateway=address(gateway,0); message.mask=address(0,0);
    long fd=rt_call(97,PF_ROUTE,SOCK_RAW,0,0,0,0);
    if(fd<0) { rt_error("netctl/route-socket",fd); return -1; }
    long result=rt_write((int)fd,&message,sizeof(message)); rt_close((int)fd);
    if(result!=(long)sizeof(message)) { rt_error("netctl/default-route",result); return -1; }
    return 0;
}
static long dhcp_send(int bpf, const unsigned char mac[6], const unsigned char *payload, size_t n)
{
    if(n>576) return -22;
    unsigned char frame[618]={0};
    for(unsigned i=0;i<6;i++) frame[i]=255;
    memcpy(frame+6,mac,6);frame[12]=8;
    unsigned char *ip=frame+14;
    ip[0]=0x45;ip[2]=(unsigned char)((n+28)>>8);ip[3]=(unsigned char)(n+28);ip[8]=64;ip[9]=17;
    ip[16]=255;ip[17]=255;ip[18]=255;ip[19]=255;
    unsigned sum=0;for(unsigned i=0;i<20;i+=2)sum+=((unsigned)ip[i]<<8)+ip[i+1];
    while(sum>>16)sum=(sum&65535)+(sum>>16);
    sum=(~sum)&65535;ip[10]=(unsigned char)(sum>>8);ip[11]=(unsigned char)sum;
    unsigned char *udp=ip+20;udp[1]=68;udp[3]=67;udp[4]=(unsigned char)((n+8)>>8);udp[5]=(unsigned char)(n+8);
    memcpy(udp+8,payload,n);
    return rt_write(bpf,frame,n+42);
}
struct lease { uint32_t ip, mask, router, dns, server; };
static int dhcp_reply(const unsigned char *p, size_t n, const unsigned char mac[6], unsigned type, struct lease *lease)
{
    static const unsigned char transaction[]={0x58,0x4e,0x55,0x31}, cookie[]={99,130,83,99};
    if(n<240 || p[0]!=2 || p[1]!=1 || p[2]!=6 || !same(p+4,transaction,4) ||
        !same(p+28,mac,6) || !same(p+236,cookie,4)) return 0;
    struct lease candidate={0}; memcpy(&candidate.ip,p+16,4);
    unsigned message_type=0;
    for(size_t i=240;i<n;) {
        unsigned tag=p[i++]; if(tag==255) break; if(!tag) continue;
        if(i>=n) return 0;
        unsigned count=p[i++]; if(count>n-i) return 0;
        if(tag==53 && count==1) message_type=p[i];
        if(tag==1 && count==4) memcpy(&candidate.mask,p+i,4);
        if(tag==3 && count>=4) memcpy(&candidate.router,p+i,4);
        if(tag==6 && count>=4) memcpy(&candidate.dns,p+i,4);
        if(tag==54 && count==4) memcpy(&candidate.server,p+i,4);
        i+=count;
    }
    if(message_type!=type || !candidate.ip || !candidate.server) return 0;
    if(type==5 && (candidate.ip!=lease->ip || candidate.server!=lease->server)) return 0;
    *lease=candidate; return 1;
}
static int dhcp(void)
{
    unsigned char mac[6]; unsigned index=0;
    if(identity(mac,&index)) return 1;
    long fd=socket_open(SOCK_DGRAM); if(fd<0) { rt_error("netctl/socket",fd); return 1; }
    long bpf=-1;
    int yes=1; long r=rt_call(105,fd,SOL_SOCKET,SO_BROADCAST,(long)&yes,sizeof(yes),0);
    if(!r) r=rt_call(105,fd,IPPROTO_IP,IP_BOUND_IF,(long)&index,sizeof(index),0);
    if(r<0) goto error;
    struct ifreq request={0};rt_copy(request.ifr_name,sizeof(request.ifr_name),"en0");
    r=rt_call(54,fd,VZ_SIOCPROTOATTACH,(long)&request,0,0,0);if(r<0 && r!=-17)goto error;
    r=rt_call(54,fd,SIOCGIFFLAGS,(long)&request,0,0,0);if(r<0)goto error;
    request.ifr_flags|=IFF_UP;
    r=rt_call(54,fd,SIOCSIFFLAGS,(long)&request,0,0,0);if(r<0)goto error;
    request.ifr_intval=1;
    r=rt_call(54,fd,SIOCAUTOADDR,(long)&request,0,0,0);if(r<0)goto error;
    bpf=rt_open("/dev/bpf0",RT_RDWR);if(bpf<0){r=bpf;goto error;}
    r=rt_call(54,bpf,BIOCSETIF,(long)&request,0,0,0);if(r<0)goto error;
    r=rt_call(54,bpf,BIOCSHDRCMPLT,(long)&yes,0,0,0);if(r<0)goto error;
    struct bpf_insn drop=BPF_STMT(BPF_RET|BPF_K,0);
    struct bpf_program filter={1,&drop};
    r=rt_call(54,bpf,BIOCSETF,(long)&filter,0,0,0);if(r<0)goto error;
    struct sockaddr_in local=address(0,68);
    r=rt_call(104,fd,(long)&local,sizeof(local),0,0,0); if(r<0) goto error;
    unsigned char packet[576]={0}, response[1024]; struct lease lease={0};
    packet[0]=1; packet[1]=1; packet[2]=6; packet[4]=0x58;packet[5]=0x4e;packet[6]=0x55;packet[7]=0x31;
    packet[10]=0x80; memcpy(packet+28,mac,6);
    packet[236]=99;packet[237]=130;packet[238]=83;packet[239]=99;
    for(unsigned stage=0;stage<2;stage++) {
        size_t n=240; packet[n++]=53;packet[n++]=1;packet[n++]=(unsigned char)(stage?3:1);
        packet[n++]=61;packet[n++]=7;packet[n++]=1; memcpy(packet+n,mac,6);n+=6;
        if(stage) {
            packet[n++]=50;packet[n++]=4;memcpy(packet+n,&lease.ip,4);n+=4;
            packet[n++]=54;packet[n++]=4;memcpy(packet+n,&lease.server,4);n+=4;
        }
        packet[n++]=55;packet[n++]=4;packet[n++]=1;packet[n++]=3;packet[n++]=6;packet[n++]=51;packet[n++]=255;
        int accepted=0;
        for(unsigned retry=0;retry<3 && !accepted;retry++) {
            size_t bytes=n<300?300:n;
            r=dhcp_send((int)bpf,mac,packet,bytes); if(r!=(long)(bytes+42)) goto error;
            for(unsigned receive=0;receive<4;receive++) {
                struct sockaddr_in from={0}; socklen_t length=sizeof(from);
                r=rt_call(29,fd,(long)response,sizeof(response),0,(long)&from,(long)&length);
                if(r<0) break;
                if(from.sin_family!=AF_INET || from.sin_port!=be16(67)) continue;
                if(dhcp_reply(response,(size_t)r,mac,stage?5:2,&lease)) { accepted=1;break; }
            }
        }
        if(!accepted) { rt_put(2,stage?"netctl: DHCP ACK timeout\n":"netctl: DHCP OFFER timeout\n"); goto fail; }
    }
    if(!lease.mask || !lease.router || configure((int)fd,lease.ip,lease.mask) || default_route(lease.router)) goto fail;
    request.ifr_intval=0;
    r=rt_call(54,fd,SIOCAUTOADDR,(long)&request,0,0,0);if(r<0)goto error;
    rt_put(1,"DARWIN:NET:DHCP IP=");ip_print(lease.ip);rt_put(1," MASK=");ip_print(lease.mask);
    rt_put(1," ROUTER=");ip_print(lease.router);rt_put(1," DNS=");ip_print(lease.dns);rt_put(1,"\n");
    rt_close((int)bpf);rt_close((int)fd);return 0;
error:
    rt_error("netctl/dhcp",r);
fail:
    if(bpf>=0)rt_close((int)bpf);
    rt_close((int)fd);return 1;
}

static unsigned port_parse(const char *s)
{
    unsigned n=0;
    if(!*s) return 0;
    while(*s) { if(*s<'0' || *s>'9' || n>6553) return 0; n=n*10+(unsigned)(*s++-'0'); }
    return n && n<=65535 ? n : 0;
}
static long arp_monitor(void)
{
    long fd=rt_open("/dev/bpf0",RT_RDWR);if(fd<0)return fd;
    struct ifreq req={0};rt_copy(req.ifr_name,sizeof(req.ifr_name),"en0");int yes=1;
    struct bpf_insn rules[]={BPF_STMT(BPF_LD|BPF_H|BPF_ABS,12),BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,0x806,1,0),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,0x800,0,1),BPF_STMT(BPF_RET|BPF_K,2048),BPF_STMT(BPF_RET|BPF_K,0)};
    struct bpf_program filter={5,rules};
    if(rt_call(54,fd,BIOCSETIF,(long)&req,0,0,0)<0 || rt_call(54,fd,BIOCIMMEDIATE,(long)&yes,0,0,0)<0 ||
        rt_call(54,fd,BIOCSETF,(long)&filter,0,0,0)<0 || rt_call(92,fd,4,4,0,0,0)<0) {
        rt_close((int)fd);return -1;
    }
    return fd;
}
static void arp_observation(int fd)
{
    static unsigned char records[4096];long count=rt_read(fd,records,sizeof(records));
    if(count<=0){rt_error("netctl/packet-observation",count);return;}
    const size_t minimum=offsetof(struct bpf_hdr,bh_hdrlen)+sizeof(((struct bpf_hdr *)0)->bh_hdrlen);
    for(size_t offset=0;offset+minimum<=(size_t)count;) {
        struct bpf_hdr header={0};memcpy(&header,records+offset,minimum);
        if(header.bh_hdrlen<minimum || header.bh_hdrlen>(size_t)count-offset ||
            header.bh_caplen>(size_t)count-offset-header.bh_hdrlen)break;
        const unsigned char *p=records+offset+header.bh_hdrlen;
        if(header.bh_caplen>=42 && p[12]==8 && p[13]==6) {
            rt_put(1,"DARWIN:NET:ARP OP=");rt_number(1,p[21]);rt_put(1," FROM=");
            uint32_t ip;memcpy(&ip,p+28,4);ip_print(ip);rt_put(1," TO=");memcpy(&ip,p+38,4);ip_print(ip);rt_put(1,"\n");
        } else if(header.bh_caplen>=42 && p[12]==8 && p[13]==0 && p[23]==17) {
            unsigned ihl=(p[14]&15)*4,total=((unsigned)p[16]<<8)+p[17];
            if(ihl<20 || total<ihl+8 || total+14>header.bh_caplen)break;
            unsigned sum=0;
            for(unsigned i=26;i<34;i+=2)sum+=((unsigned)p[i]<<8)+p[i+1];
            unsigned udp=14+ihl,udplen=((unsigned)p[udp+4]<<8)+p[udp+5];
            if(udplen<8 || udplen>total-ihl)break;
            sum+=17+udplen;
            for(unsigned i=udp;i<udp+udplen;i+=2)sum+=((unsigned)p[i]<<8)+(i+1<udp+udplen?p[i+1]:0);
            while(sum>>16)sum=(sum&65535)+(sum>>16);
            rt_put(1,"DARWIN:NET:UDP FROM=");uint32_t ip;memcpy(&ip,p+26,4);ip_print(ip);
            rt_put(1," PORT=");rt_number(1,((unsigned)p[udp]<<8)+p[udp+1]);
            rt_put(1," CHECKSUM_SUM=");rt_number(1,sum);rt_put(1,"\n");
        }
        size_t span=BPF_WORDALIGN(header.bh_hdrlen+header.bh_caplen);if(!span || span>(size_t)count-offset)break;
        offset+=span;
    }
}
static void rejected_observation(void)
{
    int query[]={0,3},oid[16];size_t size=sizeof(oid);
    const char name[]="debug.vznet_rx_rejected";
    if(rt_call(202,(long)query,2,(long)oid,(long)&size,(long)name,sizeof(name)-1)<0 ||
        !size || size>sizeof(oid) || size%sizeof(int)) return;
    uint64_t value=0;size_t length=sizeof(value);
    if(rt_call(202,(long)oid,(long)(size/sizeof(int)),(long)&value,(long)&length,0,0)<0 || length!=sizeof(value))return;
    rt_put(1,"DARWIN:NET:REJECTED LEN=");rt_number(1,value>>48);
    rt_put(1," FLAGS=");rt_number(1,(value>>40)&255);rt_put(1," GSO=");rt_number(1,(value>>32)&255);
    rt_put(1," CSUM_START=");rt_number(1,(value>>16)&65535);rt_put(1," CSUM_OFFSET=");rt_number(1,value&65535);rt_put(1,"\n");
}
static int exchange(char **argv)
{
    uint32_t host=0;
    unsigned dns_port=port_parse(argv[3]), tcp_port=port_parse(argv[4]);
    size_t token_size=rt_len(argv[5]);
    if(ip_parse(argv[2],&host) || !dns_port || !tcp_port || !token_size || token_size>40) return 2;
    for(size_t i=0;i<token_size;i++) if(!((argv[5][i]>='a' && argv[5][i]<='z') ||
        (argv[5][i]>='0' && argv[5][i]<='9'))) return 2;
    unsigned char query[128]={0x58,0x4e,1,0,0,1}, reply[256];
    size_t n=12; query[n++]=(unsigned char)token_size;
    memcpy(query+n,argv[5],token_size); n+=token_size;
    query[n++]=6;memcpy(query+n,"darwin",6);n+=6;
    query[n++]=4;memcpy(query+n,"test",4);n+=4;
    query[n++]=0;query[n++]=0;query[n++]=1;query[n++]=0;query[n++]=1;
    long monitor=arp_monitor();
    if(monitor<0)rt_error("netctl/monitor-open",monitor);
    long fd=socket_open(SOCK_DGRAM), result=fd;
    if(fd<0) goto error;
    struct sockaddr_in resolver=address(host,dns_port), from={0};socklen_t length=sizeof(from);
    result=send_packet((int)fd,query,n,&resolver);if(result!=(long)n) goto close_error;
    result=rt_call(29,fd,(long)reply,sizeof(reply),0,(long)&from,(long)&length);
    if(result<0)goto close_error;
    uint32_t resolved=0;
#ifdef DARWIN_APPLE_DNS
    if(from.sin_family!=AF_INET || from.sin_port!=resolver.sin_port || from.sin_addr.s_addr!=host ||
       apple_dns_answer(query,n,reply,(size_t)result,&resolved)) {result=-22;goto close_error;}
    rt_put(1,"DARWIN:NET:APPLE_DNS_WIRE libresolv-96\n");
#else
    if(result!=(long)(n+16) || from.sin_family!=AF_INET || from.sin_port!=resolver.sin_port ||
        from.sin_addr.s_addr!=host || reply[0]!=query[0] || reply[1]!=query[1] ||
        reply[2]!=0x81 || reply[3]!=0x80 || reply[4]!=0 || reply[5]!=1 ||
        reply[6]!=0 || reply[7]!=1 || reply[8] || reply[9] || reply[10] || reply[11] ||
        !same(reply+12,query+12,n-12) || reply[n]!=0xc0 || reply[n+1]!=12 ||
        reply[n+2] || reply[n+3]!=1 || reply[n+4] || reply[n+5]!=1 ||
        reply[n+10] || reply[n+11]!=4) {
        rt_put(2,"netctl: DNS response validation failed length=");rt_number(2,(unsigned long)result);
        rt_put(2," expected=");rt_number(2,n+16);rt_put(2,"\n");
        result=-22;goto close_error;
    }
    memcpy(&resolved,reply+n+12,4);
#endif
    if(resolved!=host) { result=-22;goto close_error; }
    rt_close((int)fd);
    rt_put(1,"DARWIN:NET:DNS ");rt_put(1,argv[5]);rt_put(1,".darwin.test A=");ip_print(resolved);rt_put(1,"\n");
    fd=socket_open(SOCK_STREAM); result=fd;if(fd<0) goto error;
    /* Nonblocking connect + select caps the connection establishment wait. */
    result=rt_call(92,fd,4,4,0,0,0);if(result<0)goto close_error; /* F_SETFL/O_NONBLOCK */
    struct sockaddr_in peer=address(resolved,tcp_port);
    result=rt_call(98,fd,(long)&peer,sizeof(peer),0,0,0);
    if(result==-36) {
        if(fd>=32) { result=-24;goto close_error; }
        uint32_t writable=1U<<fd;struct timeval wait={4,0};
        result=rt_call(93,fd+1,0,(long)&writable,0,(long)&wait,0);
        if(result<=0) { result=-60;goto close_error; }
        int socket_error=0;socklen_t size=sizeof(socket_error);
        result=rt_call(118,fd,SOL_SOCKET,SO_ERROR,(long)&socket_error,(long)&size,0);
        if(result<0 || socket_error) { if(socket_error)result=-socket_error;goto close_error; }
    } else if(result<0) goto close_error;
    result=rt_call(92,fd,4,0,0,0,0);if(result<0)goto close_error;
    if(rt_write_all((int)fd,argv[5],token_size)) { result=-5;goto close_error; }
    size_t received=0;
    for(unsigned attempt=0;attempt<4 && received<token_size;attempt++) {
        result=rt_read((int)fd,reply+received,token_size-received);
        if(result<=0)goto close_error;
        received+=(size_t)result;
    }
    if(received!=token_size || !same(reply,argv[5],token_size)) { result=-22;goto close_error; }
    rt_put(1,"DARWIN:NET:TCP ECHO=");rt_write_all(1,reply,received);rt_put(1,"\n");
    if(monitor>=0)rt_close((int)monitor);
    rt_close((int)fd);return 0;
close_error:
    rt_close((int)fd);
error:
    if(monitor>=0){arp_observation((int)monitor);rt_close((int)monitor);}
    rejected_observation();
    rt_error("netctl/exchange",result);return 1;
}

int network_main(int argc, char **argv)
{
    if(argc==2 && rt_equal(argv[1],"dhcp")) return dhcp();
    if(argc==6 && rt_equal(argv[1],"exchange")) return exchange(argv);
    if(argc==2 && rt_equal(argv[1],"info")) {
        unsigned char mac[6];unsigned index=0;
        if(identity(mac,&index)) return 1;
        rt_put(1,"DARWIN:NET:INTERFACE en0 INDEX=");rt_number(1,index);rt_put(1," MAC=");
        static const char hex[]="0123456789abcdef";
        for(unsigned i=0;i<6;i++) { char b[]={hex[mac[i]>>4],hex[mac[i]&15]};if(i)rt_put(1,":");rt_write_all(1,b,2); }
        rt_put(1,"\n");return 0;
    }
    rt_put(2,"usage: netctl info|dhcp|exchange HOST DNSPORT TCPPORT TOKEN\n");return 2;
}
