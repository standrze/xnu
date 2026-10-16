/* SPDX-License-Identifier: BSD-2-Clause
 * Original private numeric parsing and real address conversion, not DNS.
 * Source inclusion reaches private routines without replacing their code.
 */
#include TEST_NUMERIC_MODULE
#include <assert.h>
#include <errno.h>

int main(void)
{
    const char *services[] = {NULL, "0", "22", "65535", "", "65536", "-1", "ssh", "22x"};
    const int ok[] = {1,1,1,1,0,0,0,0,0};
    const unsigned ports[] = {0,0,22,65535};
    for (unsigned i=0; i != 9; ++i) {
        uint16_t port=1234; assert(_gai_numericserv(services[i], &port)==ok[i]);
        assert(port==(ok[i] ? ports[i] : 1234));
    }
    struct vector { const char *s; uint32_t family; int flags, result; uint32_t final_family; const char *text; } v[] = {
        {"192.0.2.1",AF_UNSPEC,0,1,AF_INET,"192.0.2.1"},
        {"127.1",AF_UNSPEC,0,1,AF_INET,"127.0.0.1"},
        {"0x7f000001",AF_INET,0,1,AF_INET,"127.0.0.1"},
        {"::1",AF_UNSPEC,0,1,AF_INET6,"::1"},
        {"2001:db8::1",AF_INET6,0,1,AF_INET6,"2001:db8::1"},
        {"192.0.2.1",AF_INET6,AI_V4MAPPED,1,AF_INET6,"::ffff:192.0.2.1"},
        {"192.0.2.1",AF_INET6,0,-1,AF_INET6,NULL},
        {"::1",AF_INET,0,-1,AF_INET,NULL},
        {"invalid.example",AF_UNSPEC,0,0,AF_UNSPEC,NULL},
        {"256.0.0.1",AF_UNSPEC,0,0,AF_UNSPEC,NULL},
        {"192.0.2.1 trailing",AF_UNSPEC,0,0,AF_UNSPEC,NULL},
        {"",AF_UNSPEC,0,0,AF_UNSPEC,NULL},
        {NULL,AF_INET,0,1,AF_INET,"127.0.0.1"},
        {NULL,AF_INET,AI_PASSIVE,1,AF_INET,"0.0.0.0"},
        {NULL,AF_INET6,0,1,AF_INET6,"::1"},
        {NULL,AF_INET6,AI_PASSIVE,1,AF_INET6,"::"},
    };
    for (unsigned i=0; i != sizeof(v)/sizeof(*v); ++i) {
        struct in_addr a4={0}; struct in6_addr a6={0}; int scope=0; uint32_t family=v[i].family;
        assert(_gai_numerichost(v[i].s,&family,v[i].flags,&a4,&a6,&scope)==v[i].result);
        assert(family==v[i].final_family);
        if (v[i].text) {
            char text[INET6_ADDRSTRLEN];
            assert(inet_ntop(family,family==AF_INET ? (void *)&a4 : (void *)&a6,text,sizeof(text)));
            assert(!strcmp(text,v[i].text));
        }
    }
    struct in_addr a4; assert(inet_pton(AF_INET,"192.0.2.1",&a4)==1);
    char small[3]; errno=0; assert(!inet_ntop(AF_INET,&a4,small,sizeof(small)) && errno==ENOSPC);
    assert(!strcmp(inet_ntoa(a4),"192.0.2.1"));
    assert(!strcmp(gai_strerror(EAI_NONAME),"nodename nor servname provided, or not known"));
    assert(!strcmp(gai_strerror(INT32_MAX),"Unknown error"));
    struct addrinfo *a=calloc(1,sizeof(*a)),*b=calloc(1,sizeof(*b)); assert(a && b);
    a->ai_next=b; a->ai_addr=calloc(1,sizeof(struct sockaddr_in)); b->ai_canonname=strdup("fixture");
    assert(a->ai_addr && b->ai_canonname); freeaddrinfo(a); freeaddrinfo(NULL);
    puts("LIBINFO_NUMERIC PASS SERVICES=9 HOSTS=16 SMALL_BUFFER=1 ERRORS=2 FREE_CHAIN=1 NO_DNS");
    return 0;
}
