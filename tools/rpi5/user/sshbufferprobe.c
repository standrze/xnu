/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual OpenSSH buffer dependency diagnostic. No keys, sockets, transport,
 * interface/config mutation or persistent writes. Normal process exit only. */
#include "includes.h"
#include <errno.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include "sshbuf.h"
static int emit(const char *s)
{
    size_t length=0;while(s[length])length++;
    for(unsigned i=0;i<64 && length;i++){
        ssize_t n=write(1,s,length);
        if(n<0 && errno==EINTR)continue;
        if(n<=0 || (size_t)n>length)return -1;
        s+=n;length-=(size_t)n;
    }
    return length?-1:0;
}
int main(int argc,char **argv)
{
    (void)argc;(void)argv;
    if(emit("RPI5XNU:SSHBUFFER:BEGIN ORIGINAL_BUFFERS RESET_OVERLAY NO_NETWORK NO_KEYS\n"))return 2;
    struct sshbuf *b=sshbuf_new();if(!b)return 3;
    uint32_t a=0;uint64_t c=0;
    if(sshbuf_put_u32(b,UINT32_C(0x89abcdef)) || sshbuf_put_u64(b,UINT64_C(0x0123456789abcdef)) ||
        sshbuf_get_u32(b,&a) || sshbuf_get_u64(b,&c) || a!=UINT32_C(0x89abcdef) || c!=UINT64_C(0x0123456789abcdef))goto failed;
    sshbuf_reset(b);
    if(sshbuf_set_max_size(b,16))goto failed;
    for(unsigned i=0;i<3;i++){
        if(sshbuf_put(b,"limit-reset",11))goto failed;
        sshbuf_reset(b);
        if(sshbuf_len(b) || sshbuf_max_size(b)!=16 || sshbuf_put_u32(b,42) || sshbuf_get_u32(b,&a) || a!=42)goto failed;
        sshbuf_reset(b);
    }
    sshbuf_free(b);
    if(emit("RPI5XNU:SSHBUFFER:PASS ROUNDTRIP LOW_MAX_RESET REUSE NOT_SSH_OR_CRYPTO_PROOF\n"))return 2;
    return 0;
failed:
    sshbuf_free(b);(void)emit("RPI5XNU:SSHBUFFER:FAIL NO_SSH_CLAIM\n");return 1;
}
