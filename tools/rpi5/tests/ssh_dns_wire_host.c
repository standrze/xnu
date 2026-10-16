/* SPDX-License-Identifier: BSD-2-Clause */
/* Whole Apple parser units, host libc only; no DNS/socket/service doubles. */
#include <arpa/nameser.h>
#include <resolv.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned cases;
#define CHECK(c) do { ++cases; if (!(c)) { fprintf(stderr,"DNS line %u case %u\n",__LINE__,cases); exit(37); } } while (0)

static int boundary(const char *which)
{
    unsigned char root[1] = {0}, byte = 0xa5;
    unsigned char empty[1] = {0}, truncated[2] = {1, 'x'};
    unsigned char ext[1] = {0x41};
    const unsigned char *p;
    char dst[8];
    memset(dst,0xa5,sizeof dst); errno=0;
    if (!strcmp(which,"zero-unpack"))
        return ns_name_unpack(root,root+1,root,&byte,0)==-1 && byte==0xa5 && errno==EMSGSIZE;
    if (!strcmp(which,"negative-expand"))
        return dn_expand(root,root+1,root,dst,-1)==-1 && (unsigned char)dst[0]==0xa5 && errno==EMSGSIZE;
    if (!strcmp(which,"empty-skip")) {
        p=empty;
        return ns_name_skip(&p,empty)==-1 && p==empty && errno==EMSGSIZE;
    }
    if (!strcmp(which,"unterminated-skip")) {
        p=truncated;
        return ns_name_skip(&p,truncated+2)==-1 && p==truncated && errno==EMSGSIZE;
    }
    if (!strcmp(which,"short-extended-skip")) {
        p=ext;
        return ns_name_skip(&p,ext+1)==-1 && p==ext && errno==EMSGSIZE;
    }
    if (!strcmp(which,"short-extended-unpack")) {
        unsigned char *exact=malloc(1); CHECK(exact!=NULL); exact[0]=0x41;
        int result=ns_name_unpack(exact,exact+1,exact,&byte,1);
        free(exact);
        return result==-1 && byte==0xa5 && errno==EMSGSIZE;
    }
    return 0;
}

static void roundtrips(void)
{
    const char *names[]={".","example.com","www.example.com.","a\\.b.example",
        "a\\032b.example","under_score.example","a\\255b.example"};
    unsigned char wire[1024], packed[1024]; char text[2048];
    for (size_t i=0;i<sizeof names/sizeof names[0];i++) {
        int absolute=ns_name_pton(names[i],wire,sizeof wire); CHECK(absolute>=0);
        int n=ns_name_ntop(wire,text,sizeof text); CHECK(n>0);
        CHECK(ns_name_pton(text,packed,sizeof packed)>=0);
        int length=dn_skipname(wire,wire+sizeof wire); CHECK(length>0);
        CHECK(!memcmp(wire,packed,(size_t)length));
        for (int capacity=0;capacity<=n;capacity++) {
            memset(text,0xa5,sizeof text);
            int r=ns_name_ntop(wire,text,(size_t)capacity);
            CHECK((capacity<n && r==-1) || (capacity==n && r==n));
            CHECK((unsigned char)text[capacity]==0xa5);
        }
    }
    const unsigned char compressed[]={3,'w','w','w',7,'e','x','a','m','p','l','e',3,'c','o','m',0,
        4,'m','a','i','l',0xc0,4};
    CHECK(dn_expand(compressed,compressed+sizeof compressed,compressed+17,text,sizeof text)==7);
    CHECK(!strcmp(text,"mail.example.com"));
    const unsigned char *ptrs[20]={packed,NULL};
    int a=ns_name_compress("www.example.com",packed,sizeof packed,ptrs,ptrs+20); CHECK(a==17);
    int b=ns_name_compress("mail.example.com",packed+a,sizeof packed-a,ptrs,ptrs+20); CHECK(b==7);
    CHECK(packed[a+5]==0xc0 && packed[a+6]==4);
    CHECK(dn_expand(packed,packed+a+b,packed+a,text,sizeof text)==7);
    CHECK(!strcmp(text,"mail.example.com"));
    for (size_t end=0;end<sizeof compressed;end++) {
        errno=0;
        int r=dn_expand(compressed,compressed+end,compressed+17,text,sizeof text);
        CHECK(r==-1 && errno==EMSGSIZE);
    }
    unsigned char loop[]={0xc0,0}, bad[]={0xc0,0xff}, invalid[]={0x80,0};
    CHECK(dn_expand(loop,loop+2,loop,text,sizeof text)==-1);
    CHECK(dn_expand(bad,bad+2,bad,text,sizeof text)==-1);
    CHECK(dn_expand(invalid,invalid+2,invalid,text,sizeof text)==-1);
    CHECK(res_hnok("valid-name.example") && !res_hnok("-bad.example"));
    CHECK(res_ownok("*.example") && res_mailok("a.example") && res_dnok("a.example"));
    /* Preserve the original extended-label feature, including the 0=>256-bit
     * encoding. The new guards reject truncation, not valid bitstring names. */
    for (unsigned bits=0;bits<=256;bits++) {
        unsigned payload=((bits?bits:256)+7)/8;
        unsigned char bitname[35], unpacked[35];
        bitname[0]=0x41;bitname[1]=(unsigned char)bits;
        memset(bitname+2,0xa0,payload);bitname[payload+2]=0;
        const unsigned char *p=bitname;
        CHECK(ns_name_skip(&p,bitname+payload+3)==0 && p==bitname+payload+3);
        CHECK(ns_name_unpack(bitname,bitname+payload+3,bitname,unpacked,sizeof unpacked)==(int)payload+3);
        CHECK(!memcmp(bitname,unpacked,payload+3));
        for (unsigned length=0;length<payload+3;length++) {
            p=bitname;errno=0;
            CHECK(ns_name_skip(&p,bitname+length)==-1 && p==bitname && errno==EMSGSIZE);
        }
    }
    for (unsigned value=0;value<65536;value+=257) {
        ns_put16((uint16_t)value,wire+1); CHECK(ns_get16(wire+1)==value);
        uint32_t v=(uint32_t)value*65537U;
        ns_put32(v,wire+3); CHECK(ns_get32(wire+3)==v);
    }
}

static void messages(void)
{
    unsigned char msg[]={0x12,0x34,0x81,0x80,0,1,0,1,0,0,0,0,
        7,'e','x','a','m','p','l','e',3,'c','o','m',0,0,1,0,1,
        0xc0,12,0,1,0,1,0,0,0,60,0,4,192,0,2,1};
    ns_msg parsed; ns_rr rr; ns_rr2 rr2;
    CHECK(ns_initparse(msg,sizeof msg,&parsed)==0);
    CHECK(ns_msg_id(parsed)==0x1234 && ns_msg_count(parsed,ns_s_an)==1);
    CHECK(ns_msg_getflag(parsed,ns_f_qr)==1 && ns_msg_getflag(parsed,ns_f_rcode)==0);
    CHECK(ns_parserr(&parsed,ns_s_qd,0,&rr)==0 && !strcmp(ns_rr_name(rr),"example.com"));
    CHECK(ns_parserr(&parsed,ns_s_an,0,&rr)==0 && !strcmp(ns_rr_name(rr),"example.com"));
    CHECK(ns_rr_type(rr)==ns_t_a && ns_rr_class(rr)==ns_c_in && ns_rr_ttl(rr)==60);
    CHECK(ns_rr_rdlen(rr)==4 && !memcmp(ns_rr_rdata(rr),"\300\000\002\001",4));
    CHECK(ns_parserr(&parsed,ns_s_an,-1,&rr)==-1);
    CHECK(ns_parserr(&parsed,ns_s_max,0,&rr)==-1);
    CHECK(ns_initparse(msg,sizeof msg,&parsed)==0);
    CHECK(ns_parserr2(&parsed,ns_s_an,0,&rr2)==0 && rr2.nnamel==13);
    for (size_t n=0;n<sizeof msg;n++) {
        unsigned char *copy=malloc(n?n:1); CHECK(copy!=NULL);
        memcpy(copy,msg,n); errno=0;
        CHECK(ns_initparse(copy,(int)n,&parsed)==-1 && errno==EMSGSIZE);
        free(copy);
    }
    unsigned char copy[sizeof msg+1]; memcpy(copy,msg,sizeof msg); copy[sizeof msg]=0;
    CHECK(ns_initparse(copy,sizeof copy,&parsed)==-1);
    copy[6]=0xff;copy[7]=0xff;
    CHECK(ns_initparse(copy,sizeof msg,&parsed)==-1);
}

int main(int argc,char **argv)
{
    if (argc>1 && strcmp(argv[1],"bad-expectation")) {
        int safe=boundary(argv[1]);
        printf("APPLE_DNS_BOUNDARY %s SAFE=%d\n",argv[1],safe);
        return safe?0:38;
    }
    const char *names[]={"zero-unpack","negative-expand","empty-skip","unterminated-skip",
        "short-extended-skip","short-extended-unpack"};
    for (unsigned i=0;i<6;i++) CHECK(boundary(names[i]));
    roundtrips();messages();
    if (argc>1) return 37;
    printf("APPLE_DNS_WIRE PASS CASES=%u WHOLE_UNITS=4 BOUNDARY_CORRECTIONS=6 NO_NETWORK TARGET_NOT_RUN\n",cases);
    return 0;
}
