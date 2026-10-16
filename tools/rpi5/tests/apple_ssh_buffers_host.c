/* SPDX-License-Identifier: BSD-2-Clause */
/* Exercise actual unchanged Apple-distributed OpenSSH objects. Native host
 * libc/signals/logging and ASan/UBSan, not the Pi runtime or SSH transport. */
#include "includes.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sshbuf.h"
#include "ssherr.h"
int main(int argc,char **argv)
{
    if(argc==2 && !strcmp(argv[1],"--low-max-reset")){
        struct sshbuf *limited=sshbuf_new();assert(limited);
        assert(!sshbuf_set_max_size(limited,16));
        sshbuf_reset(limited);
        /* Preserve the original reset/max-size invariant failure separately.
         * This should trip its real ssh_signal/raise fatal path, not a stub. */
        (void)sshbuf_len(limited);sshbuf_free(limited);return 7;
    }
    struct sshbuf *b=sshbuf_new();assert(b && !sshbuf_len(b));
    assert(!sshbuf_put_u8(b,0x5a));assert(!sshbuf_put_u16(b,0x1234));
    assert(!sshbuf_put_u32(b,0x89abcdef));assert(!sshbuf_put_u64(b,UINT64_C(0x0123456789abcdef)));
    assert(sshbuf_len(b)==15);
    const unsigned char encoded[]={0x5a,0x12,0x34,0x89,0xab,0xcd,0xef,1,0x23,0x45,0x67,0x89,0xab,0xcd,0xef};
    assert(!memcmp(sshbuf_ptr(b),encoded,sizeof(encoded)));
    uint8_t a;uint16_t c;uint32_t d;uint64_t e;
    assert(!sshbuf_get_u8(b,&a) && a==0x5a);assert(!sshbuf_get_u16(b,&c) && c==0x1234);
    assert(!sshbuf_get_u32(b,&d) && d==0x89abcdef);assert(!sshbuf_get_u64(b,&e) && e==UINT64_C(0x0123456789abcdef));
    assert(!sshbuf_len(b));a=0xa5;assert(sshbuf_get_u8(b,&a)==SSH_ERR_MESSAGE_INCOMPLETE && a==0xa5);
    assert(!sshbuf_put_cstring(b,"original Apple-distributed OpenSSH"));
    char *text=NULL;size_t length=0;
    assert(!sshbuf_get_cstring(b,&text,&length) && length==strlen(text));
    assert(!strcmp(text,"original Apple-distributed OpenSSH"));free(text);
    sshbuf_reset(b);assert(!sshbuf_put_u32(b,8));assert(!sshbuf_put(b,"short",5));
    size_t before=sshbuf_len(b);unsigned char *bytes=(void *)(uintptr_t)1;length=99;
    assert(sshbuf_get_string(b,&bytes,&length)==SSH_ERR_MESSAGE_INCOMPLETE && sshbuf_len(b)==before);
    assert(bytes==NULL && length==0);
    sshbuf_reset(b);assert(!sshbuf_set_max_size(b,16));
    assert(!sshbuf_put(b,"1234567890123456",16));
    assert(sshbuf_put_u8(b,1)==SSH_ERR_NO_BUFFER_SPACE && sshbuf_len(b)==16);
    assert(sshbuf_consume(b,17)==SSH_ERR_MESSAGE_INCOMPLETE && sshbuf_len(b)==16);
    sshbuf_free(b);b=sshbuf_new();assert(b);
    assert(!sshbuf_put_string(b,"a\0b",3));text=(void *)(uintptr_t)1;length=99;
    assert(sshbuf_get_cstring(b,&text,&length)==SSH_ERR_INVALID_FORMAT && text==NULL && length==0);
    sshbuf_free(b);
    b=sshbuf_from(encoded,sizeof(encoded));assert(b && sshbuf_len(b)==sizeof(encoded));
    assert(sshbuf_put_u8(b,1)==SSH_ERR_BUFFER_READ_ONLY);
    struct sshbuf *child=sshbuf_fromb(b);assert(child);sshbuf_free(b);
    assert(!sshbuf_get_u8(child,&a) && a==0x5a);sshbuf_free(child);
    assert(strstr(ssh_err(SSH_ERR_MESSAGE_INCOMPLETE),"incomplete")!=NULL);
    assert(ssh_err(-999999)!=NULL);
    puts("APPLE_OPENSSH_BUFFERS_HOST_PASS ORIGINAL_SIGNAL_LOG_ALLOC_COMPAT_LINKED=1 NO_NETWORK=1");return 0;
}
