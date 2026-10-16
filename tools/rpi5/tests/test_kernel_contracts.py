# SPDX-License-Identifier: BSD-2-Clause
"""Compile exact changed kernel fragments in small native regression harnesses.

This checks arithmetic and disabled-feature contracts; it does not simulate XNU.
"""
import platform
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def function_text(relative, name, return_type):
    text = (ROOT / relative).read_text()
    match = re.search(r"\n" + name + r"\([^)]*\)\n\{", text)
    if match is None:
        raise AssertionError(f"Cannot find definition: {name}")
    body = match.end() - 1
    level = 1
    end = body + 1
    while level:
        if text[end] == "{":
            level += 1
        elif text[end] == "}":
            level -= 1
        end += 1
    return return_type + " " + text[match.start() + 1:end]


@unittest.skipUnless(platform.system() == "Darwin", "Requires native compiler")
class KernelContractTests(unittest.TestCase):
    def test_pi_cts_tail_failure_cleanup(self):
        function = function_text('bsd/nfs/gss/gss_krb5_mech.c', 'rpi5_crypt_cts_tail', 'int')
        self.compile(r'''
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
#define Z_WAITOK 1
#define Z_ZERO 2
#define MBUF_WAITOK 1
typedef unsigned char cccbc_ctx;
typedef unsigned char cccbc_iv;
struct ccmode_cbc { size_t block_size; };
typedef struct mbuf { unsigned char bytes[32]; struct mbuf *next; } *mbuf_t;
typedef size_t (*ccpad_func)(const struct ccmode_cbc *,cccbc_ctx *,cccbc_iv *,size_t,const void *,void *);
static unsigned fault,allocations,frees,copies,crypts,writes;
static unsigned char allocation[32];
static mbuf_t expected_tail;
static void *kalloc_data(size_t n,int flags) {
    assert(n==32 && flags==(Z_WAITOK|Z_ZERO)); allocations++;
    return fault==1 ? NULL : allocation;
}
static void kfree_data(void *p,size_t n) { assert(p==allocation && n==32); frees++; }
static int mbuf_copydata(mbuf_t tail,size_t offset,size_t n,void *out) {
    assert(tail==expected_tail && offset==0 && n<=32); copies++;
    if(fault==2) return EINVAL;
    memcpy(out,tail->bytes,n); return 0;
}
static size_t crypt(const struct ccmode_cbc *mode,cccbc_ctx *key,cccbc_iv *iv,
    size_t n,const void *in,void *out) {
    assert(mode->block_size==16 && key && iv && in==out); crypts++;
    memset(out,0xcc,n);
    if(fault==3) return 0;
    if(fault==5) return n-1;
    if(fault==6) return n+1;
    return n;
}
static int mbuf_copyback(mbuf_t tail,size_t offset,size_t n,const void *in,int flags) {
    assert(tail==expected_tail && offset==0 && flags==MBUF_WAITOK); writes++;
    if(fault==4) return ENOBUFS;
    memcpy(tail->bytes,in,n); return 0;
}
''' + function + r'''
int main(void) {
    const struct ccmode_cbc mode={16}; cccbc_ctx key=0; cccbc_iv iv=0;
    for(unsigned linked=0;linked<2;linked++) for(size_t n=17;n<=32;n++) for(fault=0;fault<=6;fault++) {
        struct mbuf root,tail;
        memset(&root,0,sizeof root); memset(&tail,0,sizeof tail);
        if(linked) root.next=&tail;
        expected_tail=linked?&tail:&root;
        allocations=frees=copies=crypts=writes=0;
        int result=rpi5_crypt_cts_tail(&mode,&key,&iv,expected_tail,n,crypt);
        int expected=fault==1?ENOMEM:fault==2?EINVAL:fault==4?ENOBUFS:fault?EIO:0;
        assert(result==expected && allocations==1 && frees==(fault!=1));
        assert(copies==(fault!=1)); assert(crypts==(fault!=1 && fault!=2));
        assert(writes==(fault==0 || fault==4));
        assert(root.next==(linked?&tail:NULL) && tail.next==NULL);
        for(size_t i=0;i<32;i++) assert(expected_tail->bytes[i]==(!fault && i<n ? 0xcc : 0));
    }
}
''', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', run=True)

    def test_pi_xts_failure_is_not_success(self):
        functions = '\n'.join(function_text('libkern/crypto/corecrypto_aesxts.c', name, 'int')
                              for name in ('xts_encrypt', 'xts_decrypt'))
        self.compile(r'''
#include <stddef.h>
#include <stdint.h>
#include <assert.h>
#define CCERR_INTERNAL -1
#define ccxts_tweak_decl(size,name) unsigned char name[size]
typedef struct { unsigned char enc[32],dec[32]; } symmetric_xts;
struct ccmode_xts {
    size_t tweak_size;
    int (*set_tweak)(const void *,void *,const void *);
    void *(*xts)(const void *,void *,size_t,const void *,void *);
};
static unsigned calls,fail_operation;
static int tweak_error;
static void panic(const char *message) { (void)message; __builtin_trap(); }
static int set_tweak(const void *ctx,void *tweak,const void *iv) {
    assert(ctx && tweak && iv); return tweak_error;
}
static void *operation(const void *ctx,void *tweak,size_t blocks,const void *in,void *out) {
    assert(ctx && tweak && blocks==2 && in && out); calls++;
    return fail_operation ? NULL : tweak;
}
static const struct ccmode_xts mode={16,set_tweak,operation};
static const struct {const struct ccmode_xts *ccaes_xts_encrypt,*ccaes_xts_decrypt;}
    table={&mode,&mode}, *g_crypto_funcs=&table;
''' + functions + r'''
int main(void) {
    symmetric_xts ctx={0}; unsigned char in[32]={0},out[32]={0},iv[16]={0};
    for(unsigned direction=0;direction<2;direction++) {
        int (*wrapper)(const uint8_t *,unsigned long,uint8_t *,const uint8_t *,symmetric_xts *)=
            direction ? xts_decrypt : xts_encrypt;
        calls=0; tweak_error=-7; fail_operation=0;
        assert(wrapper(in,32,out,iv,&ctx)==-7 && calls==0);
        tweak_error=0; fail_operation=1;
        assert(wrapper(in,32,out,iv,&ctx)==CCERR_INTERNAL && calls==1);
        fail_operation=0;
        assert(wrapper(in,32,out,iv,&ctx)==0 && calls==2);
    }
}
''', '-DARM64_BOARD_CONFIG_BCM2712=1', run=True)

    def test_pi_affinity_reset_index_capacity(self):
        source = (ROOT / "osfmk/arm64/machine_routines.c").read_text()
        macros = "\n".join(line for line in source.splitlines()
                           if line.startswith("#define MPIDR_CPU_ID(") or line.startswith("#define MPIDR_CLUSTER_ID("))
        self.assertEqual(len(macros.splitlines()), 2)
        start = source.index("unsigned int cur_cluster_offset = 0;")
        end = source.index("assert(cur_cluster_offset <= MAX_CPUS);", start) + len("assert(cur_cluster_offset <= MAX_CPUS);")
        offsets = source[start:end]
        self.compile(r'''
#include <stdint.h>
#include <assert.h>
#define DEVELOPMENT 1
''' + '#include "' + str(ROOT / "pexpert/pexpert/arm64/BCM2712.h") + '"\n' + r'''
#define MPIDR_AFF0_MASK 0xffu
#define MPIDR_AFF0_SHIFT 0
#define MPIDR_AFF1_MASK 0xff00u
#define MPIDR_AFF1_SHIFT 8
''' + macros + r'''
int main(void) {
    for (unsigned mask=1;mask<16;mask++) {
        int64_t cluster_offsets[MAX_CPU_CLUSTER_PHY_ID+1];
        int64_t cluster_phys_to_logical[MAX_CPU_CLUSTER_PHY_ID+1];
        int64_t cluster_max_cpu_phys_id[MAX_CPU_CLUSTER_PHY_ID+1]={0};
        for(unsigned i=0;i<=MAX_CPU_CLUSTER_PHY_ID;i++) {
            cluster_offsets[i]=-1; cluster_phys_to_logical[i]=-1;
        }
        unsigned logical=0;
        for(unsigned i=0;i<4;i++) if(mask&(1u<<i)) {
            unsigned affinity=i<<8;
            assert(MPIDR_CPU_ID(affinity)==0 && MPIDR_CLUSTER_ID(affinity)==i);
            cluster_phys_to_logical[i]=logical++;
        }
''' + offsets + r'''
        unsigned expected=0;
        for(unsigned i=0;i<4;i++) {
            if(mask&(1u<<i)) assert(cluster_offsets[i]+MPIDR_CPU_ID(i<<8)==expected++);
            else assert(cluster_offsets[i]==-1);
        }
        assert(cur_cluster_offset==logical);
    }
    return 0;
}
''', run=True)

    def test_bootstrap_capacity_compares_pages_to_pages(self):
        source = (ROOT / "osfmk/arm64/arm_vm_init.c").read_text()
        match = re.search(r"if \((pages_used > [^\n]+)\) \{\n\s*panic\(\"BOOTSTRAP_TABLE_SIZE", source)
        self.assertIsNotNone(match)
        expression = match.group(1)
        self.compile(r'''
#include <stddef.h>
#include <assert.h>
#define ARM_PGBYTES 16384u
#define BOOTSTRAP_TABLE_SIZE (ARM_PGBYTES * 8u)
static int exceeds(size_t pages_used) { return EXPR; }
int main(void) {
    assert(!exceeds(0));
    assert(!exceeds(4));
    assert(!exceeds(8));
    assert(exceeds(9));
    assert(exceeds(34));
    return 0;
}
'''.replace("EXPR", expression), run=True)

    def test_pi_sve_detection_does_not_read_optional_register(self):
        function = function_text("osfmk/arm/commpage/commpage.c", "commpage_init_arm_optional_features_zfr0", "void")
        harness = r'''
#include <stdint.h>
#include <assert.h>
static int gARM_FEAT_SVE_B16B16;
static int reads;
#if !defined(ARM64_BOARD_CONFIG_BCM2712)
static uint64_t read_feature(const char *name) { (void)name; reads++; return 1ull << 24; }
#define __builtin_arm_rsr64 read_feature
#define ID_AA64ZFR0_EL1_B16B16_MASK (15ull << 24)
#define ID_AA64ZFR0_EL1_B16B16_EN (1ull << 24)
#endif
''' + function + r'''
int main(void) {
    commpage_init_arm_optional_features_zfr0();
#if defined(ARM64_BOARD_CONFIG_BCM2712)
    assert(reads == 0 && gARM_FEAT_SVE_B16B16 == 0);
#else
    assert(reads == 1 && gARM_FEAT_SVE_B16B16 == 1);
#endif
    return 0;
}
'''
        self.compile(harness, "-DARM64_BOARD_CONFIG_BCM2712=1", run=True)
        self.compile(harness, run=True)

    def test_pi_does_not_enable_apple_watchdog_register(self):
        helper = function_text("osfmk/kern/debug.c", "awl_set_scratch_reg_hv_bit", "void")
        startup = function_text("osfmk/kern/debug.c", "set_awl_scratch_exists_flag_and_subscribe_for_pm", "void")
        # No DT or register builtins are declared: any retained use fails compilation.
        self.compile(helper + "\n" + startup + r'''
int main(void) {
    set_awl_scratch_exists_flag_and_subscribe_for_pm();
    awl_set_scratch_reg_hv_bit();
    return 0;
}
''', "-DARM64_BOARD_CONFIG_BCM2712=1", run=True)

    def test_pi_crypto_null_registration_preserves_state(self):
        function = function_text("libkern/crypto/register_crypto.c", "register_crypto_functions", "int")
        self.compile(r'''
#include <stddef.h>
#include <stdbool.h>
#include <assert.h>
typedef struct crypto_functions { int sentinel; } *crypto_functions_t;
/* Slot coverage is tested with real headers in test_crypto_table.py. */
static bool rpi5_crypto_slots_present(crypto_functions_t f) { return f && f->sentinel; }
static crypto_functions_t g_crypto_funcs;
static bool crypto_init;
''' + function + r'''
int main(void) {
    struct crypto_functions first = {1}, second = {2}, incomplete = {0};
    assert(register_crypto_functions(NULL) == -1);
    assert(register_crypto_functions(&incomplete) == -1);
    assert(!crypto_init && g_crypto_funcs == NULL);
    assert(register_crypto_functions(&first) == 0);
    assert(crypto_init && g_crypto_funcs == &first);
    assert(register_crypto_functions(&second) == -1);
    assert(register_crypto_functions(NULL) == -1);
    assert(crypto_init && g_crypto_funcs == &first);
    return 0;
}
''', "-DARM64_BOARD_CONFIG_BCM2712=1", run=True)

    def test_pi_prng_requires_every_used_callback(self):
        function = function_text("osfmk/prng/prng_random.c", "rpi5_prng_provider_complete", "bool")
        self.compile(r'''
#include <stdbool.h>
#include <stddef.h>
#include <assert.h>
struct cckprng_ctx { int unused; };
struct cckprng_funcs {
    void (*init)(void), (*init_with_getentropy)(void), (*initgen)(void);
    void (*reseed)(void), (*refresh)(void), (*generate)(void);
};
void callback(void) {}
''' + function + r'''
int main(void) {
    struct cckprng_ctx ctx = {0};
    for (unsigned mask = 0; mask < 32; mask++) {
        struct cckprng_funcs f = {0};
        f.init_with_getentropy = mask & 1 ? callback : NULL;
        f.initgen = mask & 2 ? callback : NULL;
        f.reseed = mask & 4 ? callback : NULL;
        f.refresh = mask & 8 ? callback : NULL;
        f.generate = mask & 16 ? callback : NULL;
        assert(rpi5_prng_provider_complete(&ctx, &f) == (mask == 31));
        assert(!rpi5_prng_provider_complete(NULL, &f));
    }
    assert(!rpi5_prng_provider_complete(&ctx, NULL));
    return 0;
}
''', run=True)

    def test_pi_random_before_registration_reports_without_dispatch(self):
        function = function_text("osfmk/prng/prng_random.c", "read_random", "void")
        self.compile(r'''
#include <assert.h>
#include <stdbool.h>
#include <setjmp.h>
typedef unsigned u_int;
static int prng_ready, refreshed, generated;
static void *prng_ctx;
static jmp_buf stop;
#define panic(...) longjmp(stop,1)
static void refresh(void *p) { assert(p==prng_ctx); refreshed++; }
static struct { void (*refresh)(void *); } prng_funcs={refresh};
static void read_random_generate(void *p,u_int n) {
    assert(n==1); *(unsigned char *)p=0x42; generated++;
}
''' + function + r'''
int main(void) {
    unsigned char output=0xa5;
    if(!setjmp(stop)) { read_random(&output,1); assert(0); }
    assert(!refreshed && !generated && output==0xa5);
    prng_ready=1;
    read_random(&output,1);
    assert(refreshed==1 && generated==1 && output==0x42);
}
''', "-DARM64_BOARD_CONFIG_BCM2712=1", run=True)

    def test_prng_generation_chunking_and_cpu_selection(self):
        function = function_text("osfmk/prng/prng_random.c", "read_random_generate", "void")
        self.compile(r'''
#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#include <string.h>
#define CCKPRNG_GENERATE_MAX_NBYTES 256
#define MIN(a,b) ((a)<(b)?(a):(b))
static unsigned calls,checked,queries;
static size_t total;
static void *prng_ctx;
static void ensure_gsbase(void) { checked++; }
static unsigned cpu_number(void) { return queries++%4; }
static void generate(void *ctx,unsigned cpu,size_t n,void *p) {
    assert(ctx==prng_ctx && cpu==calls%4 && n>0 && n<=256);
    memset(p,0x42,n); total+=n; calls++;
}
static struct {void (*generate)(void *,unsigned,size_t,void *);} prng_funcs={generate};
''' + function + r'''
int main(void) {
    const size_t sizes[]={0,1,255,256,257,511,512,513,1025};
    for(size_t t=0;t<sizeof sizes/sizeof sizes[0];t++) {
        unsigned char out[1027]; memset(out,0xa5,sizeof out);
        calls=checked=queries=0; total=0;
        read_random_generate(out+1,sizes[t]);
        assert(checked==1 && total==sizes[t] && calls==(sizes[t]+255)/256);
        assert(queries==calls && out[0]==0xa5);
        for(size_t i=1;i<sizeof out;i++) assert(out[i]==(i<=sizes[t]?0x42:0xa5));
    }
}
''', run=True)

    def test_pi_pmap_reports_shared_signing_configuration(self):
        function = function_text("osfmk/arm/pmap/pmap.c", "pmap_cs_configuration", "int")
        self.compile(r'''
#include <stdint.h>
#include <stddef.h>
#include <assert.h>
typedef uint32_t code_signing_config_t;
static code_signing_config_t value;
static unsigned calls;
void code_signing_configuration(void *monitor, code_signing_config_t *output) {
    assert(monitor == NULL); assert(output); *output = value; calls++;
}
''' + function + r'''
int main(void) {
    for (unsigned bit = 0; bit < 32; bit++) {
        value = (uint32_t)1 << bit;
        assert((uint32_t)pmap_cs_configuration() == value);
    }
    value = UINT32_MAX;
    assert((uint32_t)pmap_cs_configuration() == value);
    value = 0;
    assert(pmap_cs_configuration() == 0);
    assert(calls == 34);
    return 0;
}
''', run=True)

    def test_pi_guarded_io_capability_is_absent(self):
        function = function_text("osfmk/arm/pmap/pmap.c",
                                 "pmap_has_iofilter_protected_write", "bool")
        self.compile("#include <stdbool.h>\n" + function +
                     "\nint main(void) { return pmap_has_iofilter_protected_write() ? 1 : 0; }",
                     run=True)

    def test_pi_diagnostics_report_unsupported_without_side_effects(self):
        functions = function_text("osfmk/kern/zalloc.c", "zone_leaks", "kern_return_t")
        functions += "\n" + function_text("libkern/c++/OSKext.cpp", "OSKextGrabPgoDataLocked", "int")
        self.compile(r'''
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <assert.h>
#include <errno.h>
#define KERN_NOT_SUPPORTED 46
typedef int kern_return_t;
typedef void (*leak_site_proc)(void);
typedef struct OSKext OSKext;
typedef unsigned char uuid_t[16];
static int callbacks;
void leak_callback(void) { callbacks++; }
''' + functions + r'''
int main(void) {
    uint64_t size = 123;
    char buffer[8] = "KEEP";
    uuid_t uuid = {1};
    assert(zone_leaks("zone", 4, leak_callback) == KERN_NOT_SUPPORTED);
    assert(zone_leaks(NULL, 0, NULL) == KERN_NOT_SUPPORTED);
    assert(callbacks == 0);
    assert(OSKextGrabPgoDataLocked(NULL, 1, uuid, &size, buffer, sizeof(buffer)) == ENOTSUP);
    assert(size == 123 && buffer[0] == 'K' && buffer[3] == 'P' && uuid[0] == 1);
    assert(OSKextGrabPgoDataLocked(NULL, 0, NULL, NULL, NULL, 0) == ENOTSUP);
    return 0;
}
''',
                     "-DARM64_BOARD_CONFIG_BCM2712=1", run=True)

    def test_tcp_loss_without_symptoms_provider(self):
        functions = "\n".join(function_text("bsd/netinet/tcp_cache.c", name, "void")
                              for name in ("tcp_heuristic_tfo_loss", "tcp_heuristic_ecn_loss"))
        source = r'''
#include <stdint.h>
#include <assert.h>
#define TFO_S_SYN_DATA_SENT 1
#define TFO_S_COOKIE_REQ 2
#define TCPCACHE_F_TFO_DATA 1
#define TCPCACHE_F_TFO_REQ 2
#define TCPCACHE_F_ECN_SYN_LOSS 4
struct inpcb { int inp_last_outifp; };
struct tcpcb { struct inpcb *t_inpcb; int t_tfo_stats; };
struct tcp_cache_key_src { int initialized; };
static int calls, flags;
void tcp_cache_key_src_create(struct tcpcb *tp, struct tcp_cache_key_src *key) {
    assert(tp); key->initialized = 1;
}
void tcp_heuristic_inc_counters(struct tcp_cache_key_src *key, int flag) {
    assert(key->initialized); calls++; flags = flag;
}
#if MPTCP
static int lossy;
int symptoms_is_wifi_lossy(void) { return lossy; }
#define IFNET_IS_WIFI(ifp) ((ifp) == 1)
#endif
FUNCTIONS
int main(void) {
    struct inpcb inp = {0};
    struct tcpcb tp = {&inp, TFO_S_SYN_DATA_SENT};
    for (int wifi = 0; wifi < 2; wifi++) {
        inp.inp_last_outifp = wifi;
        for (int advice = 0; advice < 2; advice++) {
#if MPTCP
            lossy = advice;
            int expected = !(wifi && advice);
#else
            int expected = 1;
#endif
            calls = 0; flags = 0;
            tcp_heuristic_tfo_loss(&tp);
            assert(calls == expected);
            if (expected) assert(flags == 3);
            calls = 0; flags = 0;
            tcp_heuristic_ecn_loss(&tp);
            assert(calls == expected);
            if (expected) assert(flags == 4);
        }
    }
    return 0;
}
'''.replace("FUNCTIONS", functions)
        for feature in (0, 1):
            self.compile(source, f"-DMPTCP={feature}", run=True)

    def test_effective_mtu_without_ipsec(self):
        function = function_text("bsd/netinet/tcp_subr.c", "tcp_get_effective_mtu", "uint32_t")
        source = r'''
#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#ifndef __unused
#define __unused __attribute__((unused))
#endif
struct rtentry { int unused; };
FUNCTION
int main(void) {
    struct rtentry route = {0};
    uint32_t mtus[] = {0, 576, 1280, 1500, 9000, UINT32_MAX};
    for (unsigned i = 0; i < sizeof(mtus)/sizeof(mtus[0]); i++) {
        assert(tcp_get_effective_mtu(NULL, mtus[i]) == mtus[i]);
        assert(tcp_get_effective_mtu(&route, mtus[i]) == mtus[i]);
    }
    return 0;
}
'''.replace("FUNCTION", function)
        self.compile(source, "-DIPSEC=0", run=True)

    def test_read_probe_keepalive_reset_without_mptcp(self):
        function = function_text("bsd/netinet/tcp_timer.c", "tcp_disable_read_probe", "void")
        source = r'''
#include <assert.h>
#define TF_DETECT_READSTALL 4
struct tcpcb {
    int t_adaptive_rtimo, t_flagsext, t_rtimo_probes;
#if MPTCP
    int t_mpsub;
#endif
};
int resets;
void tcp_keepalive_reset(struct tcpcb *tp) { assert(tp); resets++; }
#if MPTCP
int mp_resets;
void mptcp_reset_keepalive(struct tcpcb *tp) { assert(tp->t_mpsub); mp_resets++; }
#endif
FUNCTION
int main(void) {
    struct tcpcb tp = {0};
    tcp_disable_read_probe(&tp); assert(resets == 0);
    tp.t_flagsext = TF_DETECT_READSTALL;
    tcp_disable_read_probe(&tp); assert(resets == 1);
    tp.t_adaptive_rtimo = 1;
    tcp_disable_read_probe(&tp); assert(resets == 1);
    tp.t_adaptive_rtimo = 0; tp.t_flagsext = 0; tp.t_rtimo_probes = 1;
#if MPTCP
    tp.t_mpsub = 1;
#endif
    tcp_disable_read_probe(&tp); assert(resets == 2);
#if MPTCP
    assert(mp_resets == 1);
#endif
    return 0;
}
'''.replace("FUNCTION", function)
        for feature in (0, 1):
            self.compile(source, f"-DMPTCP={feature}", run=True)

    def test_tcp_empty_segment_frees_mbuf_without_mptcp(self):
        text = (ROOT / "bsd/netinet/tcp_input.c").read_text()
        start = text.index("#if MPTCP\n\t\tif ((so->so_flags & SOF_MP_SUBFLOW) && tlen == 0 &&")
        end = text.index("\n\t}", text.index("\t\tthflags &= ~TH_FIN;", start))
        source = r'''
#include <assert.h>
#define TH_FIN 1
int frees;
void m_freem(void *m) { assert(m != 0); frees++; }
int main(void) {
    int storage;
    void *m = &storage;
    int thflags = TH_FIN | 4;
FRAGMENT
    assert(frees == 1);
    assert(thflags == 4);
    return 0;
}
'''.replace("FRAGMENT", text[start:end])
        self.compile(source, "-DMPTCP=0", run=True)

    def test_tcp_retransmit_reset_without_multipath(self):
        text = (ROOT / "bsd/netinet/tcp_var.h").read_text()
        start = text.index("#if MPTCP\n#define TCP_RESET_REXMT_STATE")
        end = text.index("#endif /* MPTCP */", start) + len("#endif /* MPTCP */")
        source = r'''
#include <assert.h>
struct tcpcb { int t_rxtshift; int t_rxtstart; int other; };
#if MPTCP
int calls;
void mptcp_reset_rexmit_state(struct tcpcb *tp) {
    assert(tp->t_rxtshift == 0 && tp->t_rxtstart == 0);
    calls++;
}
#endif
MACRO
int main(void) {
    struct tcpcb tp = {5, 7, 29};
    TCP_RESET_REXMT_STATE(&tp);
    assert(tp.t_rxtshift == 0 && tp.t_rxtstart == 0 && tp.other == 29);
#if MPTCP
    assert(calls == 1);
#endif
    return 0;
}
'''.replace("MACRO", text[start:end])
        for feature in (0, 1):
            self.compile(source, f"-DMPTCP={feature}", run=True)

    def test_codel_explicit_float_conversion_preserves_control_law(self):
        inverse = function_text("bsd/net/classq/classq_fq_codel.c", "fast_inv_sqrt", "float")
        law = function_text("bsd/net/classq/classq_fq_codel.c", "codel_control_law", "uint64_t")
        source = r'''
#include <stdint.h>
#include <assert.h>
#define VERIFY(x) assert(x)
INVERSE
LAW
int main(void) {
    uint32_t counts[] = {1, 2, 3, 16, 1000, 16777215, 16777216, 16777217, UINT32_MAX};
    uint64_t intervals[] = {10000000, 100000000, 16777217, UINT64_C(1) << 40};
    for (unsigned i = 0; i < sizeof(counts) / sizeof(counts[0]); i++) {
        /* Reference reproduces the upstream usual arithmetic conversions. */
        float inv = fast_inv_sqrt(counts[i]);
        assert(inv > 0 && inv <= 1);
        for (unsigned j = 0; j < sizeof(intervals) / sizeof(intervals[0]); j++) {
            uint64_t delta = (uint64_t)(inv * intervals[j]);
            assert(codel_control_law(fast_inv_sqrt((float)counts[i]), 500, intervals[j]) == 500 + delta);
        }
    }
    return 0;
}
'''.replace("INVERSE", inverse).replace("LAW", law)
        self.compile(source, run=True)

    def test_classq_default_dequeue_without_skywalk(self):
        function = function_text("bsd/net/classq/classq_subr.c", "ifclassq_dequeue", "errno_t")
        source = r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
typedef int errno_t;
typedef int boolean_t;
typedef int mbuf_svc_class_t;
typedef uint32_t u_int32_t;
typedef uint8_t u_int8_t;
typedef int classq_pkt_t;
#define MBUF_SC_UNSPEC 0
#define __improbable(x) (x)
struct ifclassq;
#define ARGS mbuf_svc_class_t sc, u_int32_t limit, u_int32_t bytes, classq_pkt_t *head, classq_pkt_t *tail, u_int32_t *cnt, u_int32_t *len, boolean_t drvmgt
#define IGNORE (void)limit; (void)bytes; (void)head; (void)tail; (void)cnt; (void)len; assert(drvmgt == (sc != 0))
#if SKYWALK
struct ops { int (*ni_dequeue)(void *, ARGS, int); };
struct ifnet { struct ops *if_na_ops; void *if_na; };
struct ifclassq { struct ifnet *ifcq_ifp; };
int adapter(void *ptr, ARGS, int error) { IGNORE; assert(ptr != NULL); assert(error == 17); return 29; }
#else
struct ifclassq { int unused; };
#endif
int ifclassq_dequeue_common_default(struct ifclassq *q, ARGS, u_int8_t grp) {
    IGNORE; assert(q != NULL); assert(grp == 3); return 17;
}
FUNCTION
int main(void) {
    struct ifclassq q = {0};
#if SKYWALK
    struct ifnet interface = {0}; q.ifcq_ifp = &interface;
#endif
    assert(ifclassq_dequeue(&q, 0, 1, 2, NULL, NULL, NULL, NULL, 3) == 17);
    assert(ifclassq_dequeue(&q, 1, 1, 2, NULL, NULL, NULL, NULL, 3) == 17);
#if SKYWALK
    struct ops ops = { adapter }; interface.if_na_ops = &ops; interface.if_na = &q;
    assert(ifclassq_dequeue(&q, 1, 1, 2, NULL, NULL, NULL, NULL, 3) == 29);
#endif
    return 0;
}
'''.replace("FUNCTION", function)
        for feature in (0, 1):
            self.compile(source, f"-DSKYWALK={feature}", run=True)

    def test_necp_browser_role_does_not_grant_pi_delegation(self):
        text = (ROOT / "bsd/net/necp_client.c").read_text()
        start = text.index("\t// Only allow entitled processes to set the client ID.")
        end = text.index("\n\tif (uap->client_id", start)
        check = text[start:end].replace("goto done;", "return error;")
        source = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#define __single
#define EAUTH 80
#define PRIV_NET_PRIVILEGED_SOCKET_DELEGATE 1
#define LOG_ERR 1
#define NECPLOG0(level, message) ((void)0)
typedef void *proc_t;
typedef void *task_t;
int browser, privileged;
proc_t current_proc(void) { return &browser; }
#ifndef ARM64_BOARD_CONFIG_BCM2712
const char *kCSWebBrowserNetworkEntitlement = "fixture";
task_t proc_task(proc_t proc) { return proc; }
bool IOTaskHasEntitlement(task_t task, const char *name) {
    (void)task; (void)name; return browser;
}
#endif
int kauth_cred_get(void) { return 0; }
int priv_check_cred(int cred, int privilege, int flags) {
    (void)cred; (void)flags;
    assert(privilege == PRIV_NET_PRIVILEGED_SOCKET_DELEGATE);
    return privileged ? 0 : EAUTH;
}
int check(void) {
    int error = 0;
CHECK
    (void)proc;
    return 0;
}
int main(void) {
    assert(check() == EAUTH);
    browser = 1;
#ifdef ARM64_BOARD_CONFIG_BCM2712
    assert(check() == EAUTH);
#else
    assert(check() == 0);
#endif
    browser = 0; privileged = 1;
    assert(check() == 0);
    return 0;
}
'''.replace("CHECK", check)
        self.compile(source, run=True)
        self.compile(source, "-DARM64_BOARD_CONFIG_BCM2712=1", run=True)

    def test_dlil_receive_strategy_without_skywalk(self):
        function = function_text("bsd/net/dlil_input.c", "dlil_input_handler", "errno_t")
        source = r'''
#include <assert.h>
#include <stddef.h>
#define __improbable(x) (x)
typedef int errno_t;
typedef int boolean_t;
struct ifnet;
struct mbuf { int unused; };
struct ifnet_stat_increment_param { int unused; };
struct thread { int unused; };
struct dlil_threading_info;
typedef struct dlil_threading_info *dlil_threading_info_ref_t;
#define PARAMS struct dlil_threading_info *inp, struct ifnet *ifp, struct mbuf *head, struct mbuf *tail, const struct ifnet_stat_increment_param *stats, boolean_t poll, struct thread *thread
#define IGNORE (void)inp; (void)ifp; (void)head; (void)tail; (void)stats; (void)poll; (void)thread
struct dlil_threading_info { errno_t (*dlth_strategy)(PARAMS); };
struct ifnet { dlil_threading_info_ref_t if_inp; };
int normal(PARAMS) { IGNORE; return 17; }
int fallback(PARAMS) { IGNORE; return 29; }
struct dlil_threading_info global_info = { fallback };
dlil_threading_info_ref_t dlil_main_input_thread = &global_info;
#if SKYWALK && (DEVELOPMENT || DEBUG)
#define NET_THREAD_SYNC_RX 4
int marked;
int net_thread_is_marked(int flag) { assert(flag == 4); return marked; }
int dlil_input_sync(PARAMS) { IGNORE; return 41; }
#endif
FUNCTION
int main(void) {
    struct dlil_threading_info local = { normal };
    struct ifnet interface = { &local };
    assert(dlil_input_handler(&interface, NULL, NULL, NULL, 0, NULL) == 17);
    interface.if_inp = NULL;
    assert(dlil_input_handler(&interface, NULL, NULL, NULL, 0, NULL) == 29);
#if SKYWALK && (DEVELOPMENT || DEBUG)
    marked = 1;
    assert(dlil_input_handler(&interface, NULL, NULL, NULL, 0, NULL) == 41);
#endif
    return 0;
}
'''.replace("FUNCTION", function)
        for skywalk in (0, 1):
            for development in (0, 1):
                self.compile(source, f"-DSKYWALK={skywalk}",
                             f"-DDEVELOPMENT={development}", "-DDEBUG=0", run=True)

    def test_native_nexus_requires_skywalk_and_adapter(self):
        function = function_text("bsd/net/dlil_subr.c", "dlil_is_native_netif_nexus", "boolean_t")
        source = r'''
#include <assert.h>
#include <stddef.h>
#ifndef __unused
#define __unused __attribute__((unused))
#endif
#define FALSE 0
#define IFEF_SKYWALK_NATIVE 4
typedef int boolean_t;
struct ifnet {
    unsigned if_eflags;
#if SKYWALK
    void *if_na;
#endif
};
typedef struct ifnet *ifnet_t;
FUNCTION
int main(void) {
    struct ifnet interface = {0};
    assert(!dlil_is_native_netif_nexus(&interface));
    interface.if_eflags = IFEF_SKYWALK_NATIVE;
    assert(!dlil_is_native_netif_nexus(&interface));
#if SKYWALK
    interface.if_na = &interface;
    assert(dlil_is_native_netif_nexus(&interface));
    interface.if_eflags = 0;
    assert(!dlil_is_native_netif_nexus(&interface));
#endif
    return 0;
}
'''.replace("FUNCTION", function)
        for feature in (0, 1):
            self.compile(source, f"-DSKYWALK={feature}", run=True)

    def test_driver_hwassist_without_skywalk(self):
        function = function_text("bsd/net/if.c", "if_get_driver_hwassist", "uint32_t")
        source = r'''
#include <stdint.h>
#include <stddef.h>
#include <assert.h>
struct netif { uint32_t nif_hwassist; };
struct adapter { struct netif *nifna_netif; };
struct ifnet {
    uint32_t if_hwassist;
#if SKYWALK
    struct adapter *adapter;
#endif
};
#if SKYWALK
#define NA(ifp) ((ifp)->adapter)
#endif
FUNCTION
int main(void) {
    struct ifnet interface = { .if_hwassist = 17 };
    assert(if_get_driver_hwassist(&interface) == 17);
#if SKYWALK
    struct netif net = { .nif_hwassist = 29 };
    struct adapter adapter = { .nifna_netif = &net };
    interface.adapter = &adapter;
    assert(if_get_driver_hwassist(&interface) == 29);
#endif
    return 0;
}
'''.replace("FUNCTION", function)
        for feature in (0, 1):
            self.compile(source, f"-DSKYWALK={feature}", run=True)

    def test_compiler_stack_probe_abi(self):
        result = subprocess.run(["xcrun", "clang", "-arch", "arm64", "-mcpu=cortex-a76",
                                 "-mkernel", "-O2", "-fstack-check", "-S", "-mllvm",
                                 "-stop-after=prologepilog",
                                 str(ROOT / "tools/rpi5/tests/stack_probe_fixture.c"), "-o", "-"],
                                check=True, capture_output=True, text=True)
        calls = [line for line in result.stdout.splitlines() if "StkChkIndirectCall" in line]
        self.assertTrue(calls, "Compiler did not produce the expected probe ABI")
        for call in calls:
            self.assertIn("csr_aarch64_stackprobe_darwin", call)
            self.assertIn("implicit $x9", call)
            self.assertIn("implicit $sp", call)
            self.assertIn("implicit-def dead $x16", call)
            self.assertIn("implicit-def dead $x17", call)

    @unittest.skipUnless(platform.machine() == "arm64", "Executes AArch64 assembly")
    def test_stack_probe_preservation_and_guard_faults(self):
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / "probe"
            subprocess.run(["xcrun", "clang", "-arch", "arm64", "-O2",
                            "-fno-stack-check", "-DARM64_BOARD_CONFIG_BCM2712=1",
                            "-DDEVELOPMENT=1", "-x", "assembler-with-cpp",
                            str(ROOT / "osfmk/arm64/rpi5_stack_probe.s"),
                            str(ROOT / "tools/rpi5/tests/stack_probe_harness.s"),
                            "-x", "c", str(ROOT / "tools/rpi5/tests/stack_probe_harness.c"),
                            "-o", str(executable)], check=True, capture_output=True, text=True)
            subprocess.run([str(executable)], check=True, timeout=15)

    def test_local_domain_registration_does_not_register_ip(self):
        source = (ROOT / "bsd/kern/uipc_domain.c").read_text()
        start = source.index("#if NETWORKING\n\tattach_domain(&inetdomain_s)")
        end = source.index("\n\n\t/*", start)
        harness = r'''
#include <assert.h>
static int seen[7], count;
static int systemdomain_s = 3, localdomain_s = 4, vsockdomain_s = 6;
#if NETWORKING
static int inetdomain_s = 1, inet6domain_s = 2, ndrvdomain_s = 5, routedomain_s = 7;
#endif
static void attach_domain(int *domain) { assert(count < 7); seen[count++] = *domain; }
int main(void) {
REGISTRATION
#if NETWORKING
    assert(count == 7);
    for (int i = 0; i < count; i++) assert(seen[i] == i + 1);
#else
    assert(count == 3 && seen[0] == 3 && seen[1] == 4 && seen[2] == 6);
#endif
    return 0;
}
'''.replace("REGISTRATION", source[start:end])
        for enabled in (0, 1):
            self.compile(harness, f"-DNETWORKING={enabled}", run=True)

    def test_syn_cookie_policy_without_multipath_fields(self):
        source = (ROOT / "bsd/netinet/tcp_var.h").read_text()
        start = source.index("#if MPTCP\n#define TCP_SYN_COOKIE_DISABLED")
        end = source.index("#endif", start) + len("#endif")
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#define TFO_ENABLED(tp) ((tp)->fast_open)
#define LOOPBACK_INTERFACE(tp) ((tp)->loopback)
#define TMPF_MPTCP_TRUE 1
struct connection {
    bool fast_open, loopback;
#if MPTCP
    unsigned t_mpflags;
#endif
};
POLICY
int main(void) {
    struct connection c = {0};
    struct connection *tp = &c;
    assert(!TCP_SYN_COOKIE_DISABLED(tp));
    c.fast_open = true;
    assert(TCP_SYN_COOKIE_DISABLED(tp));
    c.fast_open = false; c.loopback = true;
    assert(TCP_SYN_COOKIE_DISABLED(tp));
    c.loopback = false;
#if MPTCP
    c.t_mpflags = TMPF_MPTCP_TRUE;
    assert(TCP_SYN_COOKIE_DISABLED(tp));
#endif
    return 0;
}
'''.replace("POLICY", source[start:end])
        for enabled in (0, 1):
            self.compile(harness, f"-DMPTCP={enabled}", run=True)

    def test_commpage_flush_completes_before_ttbr_switch(self):
        source = (ROOT / "osfmk/arm/pmap/pmap.c").read_text()
        start = source.index("#if __ARM_MIXED_PAGE_SIZE__\n\tif (__improbable(do_commpage_flush))")
        end = source.index("\n}", start)
        tail = source[start:end]
        harness = r'''
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#define __improbable(x) (x)
#define __ARM_MIXED_PAGE_SIZE__ 1
#define _COMM_PAGE64_NESTING_SIZE 32768
#define _COMM_PAGE64_NESTING_START 0x10000
typedef uint64_t ppnum_t;
static int stage, local_count, range_count;
static void flush_core_tlb_async(void) __attribute__((unused));
static void flush_core_tlb_async(void) { assert(stage == 0); stage = 1; local_count++; }
static uint64_t generate_rtlbi_param(uint64_t n, int a, uint64_t va, uint64_t shift) __attribute__((unused));
static uint64_t generate_rtlbi_param(uint64_t n, int a, uint64_t va, uint64_t shift) {
    assert(n == 2 && a == 0 && va == 0x10000 && shift == 14); return 42;
}
static void flush_core_tlb_allrange_async(uint64_t value) __attribute__((unused));
static void flush_core_tlb_allrange_async(uint64_t value) { assert(value == 42 && stage == 0); stage = 1; range_count++; }
static void pmap_flush_core_tlb_asid_async(int p) { (void)p; assert(0); }
static void sync_tlb_flush_local(void) { assert(stage == 1); stage = 2; }
static void pmap_switch_user_ttb(int p, void *cpu) { (void)p; (void)cpu; assert(stage == 2); stage = 3; }
int main(void) {
    bool do_commpage_flush = true, do_asid_flush = false, do_shared_region_flush = false;
    struct { unsigned commpage_page_shift; } cpu = {14}, *cpu_data_ptr = &cpu;
    int pmap = 0;
TAIL
    assert(stage == 3);
#if __ARM_RANGE_TLBI__
    assert(range_count == 1 && local_count == 0);
#else
    assert(local_count == 1 && range_count == 0);
#endif
    return 0;
}
'''.replace("TAIL", tail)
        for feature in (0, 1):
            self.compile(harness, f"-D__ARM_RANGE_TLBI__={feature}", run=True)

    def compile(self, source, *defines, run=False):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.c"
            path.write_text(source)
            executable = Path(tmp) / "contract"
            result = subprocess.run(["xcrun", "clang", "-Wall", "-Wextra", "-Werror",
                                     *defines, str(path), "-o", str(executable)],
                                    capture_output=True, text=True)
            if run:
                self.assertEqual(result.returncode, 0, result.stderr)
                subprocess.run([str(executable)], check=True)
            return result

    def test_cache_callback_preserves_40bit_pa_and_full_pointer(self):
        text = (ROOT / "osfmk/arm/machine_routines.h").read_text()
        start = text.index("#if defined(ARM64_BOARD_CONFIG_BCM2712)\ntypedef uintptr_t cache_dispatch_arg_t;")
        end = text.index(";", text.index("typedef void (*cache_dispatch_t)", start)) + 1
        declarations = text[start:end]
        harness = r'''
#include <stdint.h>
#include <assert.h>
typedef void *cpu_id_t;
DECLARATIONS
static void receive(cpu_id_t cpu, unsigned int command,
                    cache_dispatch_arg_t address, cache_dispatch_arg_t output) {
    assert(cpu == 0 && command == 1);
    assert(address == UINT64_C(0x107d001000));
    *(uint32_t *)(uintptr_t)output = 0x12345678;
}
int main(void) {
    _Static_assert(sizeof(cache_dispatch_arg_t) == sizeof(uintptr_t), "pointer width");
    uint32_t value = 0;
    cache_dispatch_t callback = receive;
    callback(0, 1, UINT64_C(0x107d001000), (uintptr_t)&value);
    assert(value == 0x12345678);
    return 0;
}
'''.replace("DECLARATIONS", declarations)
        self.compile(harness, "-DARM64_BOARD_CONFIG_BCM2712=1", run=True)
        self.compile("#include <stdint.h>\ntypedef void *cpu_id_t;\n" + declarations +
                     '\n_Static_assert(sizeof(cache_dispatch_arg_t) == sizeof(unsigned int), "legacy ABI");'
                     '\nint main(void) { return 0; }', run=True)

    def test_panic_offset_high_address_and_bounds(self):
        body = function_text("pexpert/arm/pe_init.c", "PE_get_offset_into_panic_region", "uint32_t")
        self.compile(r'''
#include <stdint.h>
#include <setjmp.h>
static uintptr_t gPanicBase = UINT64_C(0xfffffff007000000);
static uintptr_t gPanicSize = 4096;
static jmp_buf rejected;
#define assert(condition) do { if (!(condition)) longjmp(rejected, 1); } while (0)
''' + body + r'''
int main(void) {
    if (setjmp(rejected)) return 1;
    if (PE_get_offset_into_panic_region((char *)(gPanicBase + 4095)) != 4095) return 2;
    if (!setjmp(rejected)) {
        PE_get_offset_into_panic_region((char *)(gPanicBase - 1)); return 3;
    }
    if (!setjmp(rejected)) {
        PE_get_offset_into_panic_region((char *)(gPanicBase + gPanicSize)); return 4;
    }
    gPanicSize = UINT64_C(0x200000000);
    if (!setjmp(rejected)) {
        PE_get_offset_into_panic_region((char *)(gPanicBase + UINT64_C(0x100000000))); return 5;
    }
    return 0;
}
''', run=True)

    def test_missing_trust_provider_never_marks_hash_trusted(self):
        code = "#include <stdint.h>\n#include <stdbool.h>\n#define CS_CDHASH_LEN 20\n"
        code += function_text("osfmk/arm/pmap/pmap.c",
                              "pmap_lookup_in_loaded_trust_caches_internal", "bool")
        code += "\n" + function_text("osfmk/arm/pmap/pmap.c",
                                     "pmap_lookup_in_static_trust_cache_internal", "uint32_t")
        code += r'''
int main(void) {
    uint8_t hash[CS_CDHASH_LEN] = {0};
    for (unsigned int i = 0; i < 256; ++i) {
        hash[i % CS_CDHASH_LEN] = (uint8_t)i;
        if (pmap_lookup_in_loaded_trust_caches_internal(hash)) return 1;
        if (pmap_lookup_in_static_trust_cache_internal(hash) != 0) return 2;
    }
    return 0;
}
'''
        self.compile(code, "-DARM64_BOARD_CONFIG_BCM2712=1", run=True)

    def test_entitlement_context_is_opaque_and_monitors_are_rejected(self):
        text = (ROOT / "libkern/libkern/amfi/amfi.h").read_text()
        start = text.index("#if defined(ARM64_BOARD_CONFIG_BCM2712)")
        end = text.index("#define KERN_AMFI_INTERFACE_VERSION", start)
        declarations = text[start:end]
        source = declarations + "\nint main(void) { const CEContext_t *p = 0; return p != 0; }"
        result = self.compile(source, "-DARM64_BOARD_CONFIG_BCM2712=1", "-DDEVELOPMENT=1")
        self.assertEqual(result.returncode, 0, result.stderr)
        for flag in ("-DCONFIG_PMAP_PPL=1", "-DCONFIG_SPTM=1", "-DDEVELOPMENT=0"):
            result = self.compile(source, "-DARM64_BOARD_CONFIG_BCM2712=1", flag)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("require monitor-free DEVELOPMENT", result.stderr)
        result = self.compile(declarations + "\nint main(void) { return sizeof(CEContext_t); }",
                              "-DARM64_BOARD_CONFIG_BCM2712=1", "-DDEVELOPMENT=1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("incomplete", result.stderr)


if __name__ == "__main__":
    unittest.main()
