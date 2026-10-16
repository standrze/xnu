/* SPDX-License-Identifier: BSD-2-Clause
 * Adapter around original Apple's source-built libresolv wire parser. This is
 * not res_nquery, resolver configuration, DNSSEC or mDNSResponder emulation.
 */
#include "runtime.h"
#include <arpa/nameser.h>
/* Only this bootstrap executable is single-threaded; do not reuse this errno
 * adapter for pthread userland. zsh keeps its real Apple errno/TSD runtime. */
static int parser_errno;
int *__error(void) { return &parser_errno; }

static int wire_equal(const unsigned char *a, const unsigned char *b, size_t n)
{ for(size_t i=0;i<n;i++) if(a[i]!=b[i]) return 0;return 1; }

int apple_dns_answer(const unsigned char *query, size_t query_size,
                     const unsigned char *reply, size_t reply_size, uint32_t *address)
{
    if(query_size<17 || query_size>512 || reply_size<12 || reply_size>512) return -1;
    ns_msg message;
    if(ns_initparse(reply,(int)reply_size,&message)<0 || ns_msg_id(message)!=ns_get16(query) ||
       !ns_msg_getflag(message,ns_f_qr) || ns_msg_getflag(message,ns_f_opcode)!=ns_o_query ||
       ns_msg_getflag(message,ns_f_tc) || ns_msg_getflag(message,ns_f_rcode)!=ns_r_noerror ||
       ns_msg_count(message,ns_s_qd)!=1 || ns_msg_count(message,ns_s_an)!=1) return -1;
    unsigned char name[NS_MAXNNAME];size_t name_size=0;
    if(ns_name_unpack2(query,query+query_size,query+12,name,sizeof(name),&name_size)<0) return -1;
    ns_rr2 question,answer;
    if(ns_parserr2(&message,ns_s_qd,0,&question)<0 || ns_parserr2(&message,ns_s_an,0,&answer)<0 ||
       question.type!=ns_t_a || question.rr_class!=ns_c_in || answer.type!=ns_t_a ||
       answer.rr_class!=ns_c_in || answer.rdlength!=4 || question.nnamel!=name_size ||
       answer.nnamel!=name_size || !wire_equal(question.nname,name,name_size) ||
       !wire_equal(answer.nname,name,name_size)) return -1;
    unsigned char *out=(unsigned char *)address;
    for(unsigned i=0;i<4;i++) out[i]=answer.rdata[i];
    return 0;
}
