/* SPDX-License-Identifier: BSD-2-Clause
 * Typed source-buildable Darwin guest client. Not a Metal compatibility layer.
 */
#include "runtime.h"
#include "gpu_client.h"
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/time.h>
static int exchange(unsigned operation, const float *a, const float *b, size_t count, float *out)
{
    if(count>GPU_VECTOR_MAX || (count && (!a || !b || !out))) return -22;
    unsigned char request[12+GPU_VECTOR_MAX*8]={'D','G','C','1',0,0,0,0,0,0,0,0};
    request[8]=(unsigned char)(operation>>8);request[9]=(unsigned char)operation;request[11]=(unsigned char)count;
    for(size_t i=0;i<count;i++) {
        union {float f;uint32_t u;} left={.f=a[i]},right={.f=b[i]};
        gpu_set_word(request+12+4*i,left.u);gpu_set_word(request+12+count*4+4*i,right.u);
    }
    struct sockaddr_un own={0},server={0};
    own.sun_len=server.sun_len=sizeof(own);own.sun_family=server.sun_family=AF_UNIX;
    (void)rt_copy(server.sun_path,sizeof(server.sun_path),GPU_SOCKET_PATH);
    const char *prefix="/data/.darwin-gpu-";size_t pos=0;
    while(*prefix) own.sun_path[pos++]=*prefix++;
    unsigned long pid=(unsigned long)rt_getpid();char digits[24];size_t length=0;
    do { digits[length++]=(char)('0'+pid%10);pid/=10; } while(pid);
    while(length) own.sun_path[pos++]=digits[--length];
    long fd=rt_call(97,AF_UNIX,SOCK_DGRAM,0,0,0,0);if(fd<0) return (int)fd;
    int owned=0,result=-5;
    long r=rt_call(104,fd,(long)&own,sizeof(own),0,0,0);if(r<0) {result=(int)r;goto done;}
    owned=1;
    r=rt_call(15,(long)own.sun_path,0600,0,0,0,0);if(r<0) {result=(int)r;goto done;}
    struct timeval timeout={5,0};
    r=rt_call(105,fd,SOL_SOCKET,SO_RCVTIMEO,(long)&timeout,sizeof(timeout),0);if(r<0) {result=(int)r;goto done;}
    r=rt_call(105,fd,SOL_SOCKET,SO_SNDTIMEO,(long)&timeout,sizeof(timeout),0);if(r<0) {result=(int)r;goto done;}
    r=rt_call(98,fd,(long)&server,sizeof(server),0,0,0);if(r<0) {result=(int)r;goto done;}
    do {r=rt_write((int)fd,request,12+count*8);} while(r==-4);
    if(r!=(long)(12+count*8)) {result=r<0 ? (int)r : -5;goto done;}
    unsigned char reply[257];
    do {r=rt_read((int)fd,reply,sizeof(reply));} while(r==-4);
    if(r<0) {result=(int)r;goto done;}
    if(r<12 || reply[0]!='D' || reply[1]!='G' || reply[2]!='R' || reply[3]!='1' || gpu_word(reply+4)) goto done;
    unsigned status=((unsigned)reply[8]<<8)|reply[9],n=((unsigned)reply[10]<<8)|reply[11];
    if(status>5 || (status && (n || r!=12))) goto done;
    if(status) {result=(int)status;goto done;}
    if(n!=count || r!=(long)(12+4*count)) goto done;
    for(size_t i=0;i<count;i++) {union {uint32_t u;float f;} value={.u=gpu_word(reply+12+4*i)};out[i]=value.f;}
    result=0;
done:
    rt_close((int)fd);
    if(owned) (void)rt_call(10,(long)own.sun_path,0,0,0,0,0);
    return result;
}
int gpu_client_add(const float *a, const float *b, size_t count, float *result)
{ if(!count) return -22;return exchange(1,a,b,count,result); }
int gpu_main(int argc, char **argv)
{
    if(argc==2 && rt_equal(argv[1],"unsupported")) {
        int status=exchange(65535,0,0,0,0);
        if(status!=1) {rt_error("gpuctl unsupported",status);return 1;}
        rt_put(1,"DARWIN:GPU:UNSUPPORTED status=1\n");return 0;
    }
    if(argc!=3 || !rt_equal(argv[1],"selftest")) {rt_put(2,"gpuctl selftest SEED | unsupported\n");return 2;}
    unsigned seed=0;
    for(const char *p=argv[2];*p;p++) {if(*p<'0' || *p>'9' || seed>6553) return 2;seed=seed*10+(unsigned)(*p-'0');}
    if(!seed || seed>65535) return 2;
    float a[GPU_VECTOR_MAX],b[GPU_VECTOR_MAX],out[GPU_VECTOR_MAX];
    for(unsigned i=0;i<GPU_VECTOR_MAX;i++) {a[i]=(float)(seed+i)*0.5f;b[i]=-(float)i*0.25f;out[i]=-1;}
    int status=gpu_client_add(a,b,GPU_VECTOR_MAX,out);
    if(status) {rt_error("gpuctl add",status);return 1;}
    for(unsigned i=0;i<GPU_VECTOR_MAX;i++) if(out[i]!=a[i]+b[i]) {rt_put(2,"gpuctl wrong returned result\n");return 1;}
    rt_put(1,"DARWIN:GPU:ADD OK seed=");rt_number(1,seed);rt_put(1," count=16\n");return 0;
}
