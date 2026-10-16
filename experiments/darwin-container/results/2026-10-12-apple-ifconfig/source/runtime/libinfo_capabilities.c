/* SPDX-License-Identifier: BSD-2-Clause
 * Static single-process network module binding for original Apple Libinfo.
 * System-wide plug-ins, directory services and asynchronous lookup are absent.
 */
#include <si_module.h>
#include <errno.h>
#include <string.h>
#include <arpa/inet.h>
#include <arpa/nameser.h>
#include <resolv.h>
#include <notify.h>
#include <pthread.h>
#include <dlfcn.h>
#include <os/log.h>
#include <mach/mach_time.h>
#include <sys/time.h>

/* Project transport binding, not Apple's unavailable mDNSResponder service.
 * Public getaddrinfo, validation, address packaging/order and wire query/send
 * remain the original Apple implementations. This process has no DNS cache.
 */
static unsigned short nameserver_port = 53;
void darwin_network_nameserver_port(unsigned short port) { nameserver_port = port; }

static si_item_t *network_host_byname(si_mod_t *module, const char *name, int family,
                                    const char *interface, uint32_t *error)
{
    if (error) *error = SI_STATUS_H_ERRNO_NO_RECOVERY;
    if (!name || strlen(name) > 253 || (interface && *interface) ||
        (family != AF_INET && family != AF_INET6)) { errno = ENOTSUP; return NULL; }
    struct __res_state state = {0};
    if (res_ninit(&state) != 0 || state.nscount != 1) {
        res_ndestroy(&state);
        return NULL;
    }
    state.nsaddr_list[0].sin_port = htons(nameserver_port);
    state.retry = 1;
    state.retrans = 2;
    unsigned char answer[4096], addresses[16][16];
    char *pointers[17] = {0}, *aliases[1] = {0};
    int type = family == AF_INET ? ns_t_a : ns_t_aaaa;
    int width = family == AF_INET ? 4 : 16;
    int size = res_nquery(&state, name, ns_c_in, type, answer, sizeof(answer));
    res_ndestroy(&state);
    if (size < 0) return NULL;
    ns_msg message;
    if (ns_initparse(answer, size, &message) != 0) return NULL;
    unsigned int count = 0;
    for (int i = 0; i < ns_msg_count(message, ns_s_an); i++) {
        ns_rr record;
        if (ns_parserr(&message, ns_s_an, i, &record) != 0) return NULL;
        if (ns_rr_class(record) != ns_c_in || ns_rr_type(record) != type) continue;
        if (ns_rr_rdlen(record) != width || count == 16) { errno = EOVERFLOW; return NULL; }
        memcpy(addresses[count], ns_rr_rdata(record), width);
        pointers[count] = (char *)addresses[count];
        count++;
    }
    if (!count) {
        if (error) *error = SI_STATUS_H_ERRNO_HOST_NOT_FOUND;
        return NULL;
    }
    const uint64_t unused = 0;
    si_item_t *item = (si_item_t *)LI_ils_create(
        family == AF_INET ? "L4488s*44a" : "L4488s*44c", (unsigned long)module,
        family == AF_INET ? CATEGORY_HOST_IPV4 : CATEGORY_HOST_IPV6, 1,
        unused, unused, name, aliases, family, width, pointers);
    if (item && error) *error = SI_STATUS_NO_ERROR;
    return item;
}

static const struct si_mod_vtable_s network_vtable = {.sim_host_byname = network_host_byname};
static si_mod_t network_module = {
    .name = "darwin-network", .vers = 1, .refcount = 1,
    .flags = SI_MOD_FLAG_STATIC, .vtable = &network_vtable
};

si_mod_t *darwin_network_module_factory(const char *name)
{
    if (!name || strcmp(name, "search")) { errno = ENOTSUP; return NULL; }
    return &network_module;
}

/* Honest unavailable services. Apple code takes its own fallback paths. */
uint32_t notify_register_check(const char *name, int *token)
{
    (void)name;
    if (token) *token = -1;
    return NOTIFY_STATUS_FAILED;
}
uint32_t notify_check(int token, int *changed)
{
    (void)token; (void)changed;
    return NOTIFY_STATUS_INVALID_TOKEN;
}
void *dlopen(const char *path, int mode)
{
    (void)path; (void)mode;
    errno = ENOTSUP;
    return NULL;
}
char *dlerror(void) { return "static guest: dynamic loading unavailable"; }
int pthread_atfork(void (*prepare)(void), void (*parent)(void), void (*child)(void))
{
    (void)prepare; (void)parent; (void)child;
    return ENOTSUP;
}

/* Single-thread process adapters. Track actual ownership/initialization and
 * reject recursion; these do not impersonate a general pthread runtime. */
static struct { const void *key; unsigned int state; } once_entries[32], mutex_entries[32];
int pthread_once(pthread_once_t *once, void (*initialize)(void))
{
    if (!once || !initialize) return EINVAL;
    for (unsigned int i = 0; i < 32; i++) {
        if (!once_entries[i].key) once_entries[i].key = once;
        if (once_entries[i].key != once) continue;
        if (once_entries[i].state == 2) return 0;
        if (once_entries[i].state == 1) abort();
        once_entries[i].state = 1;
        initialize();
        once_entries[i].state = 2;
        return 0;
    }
    abort();
}
int pthread_mutex_lock(pthread_mutex_t *mutex)
{
    if (!mutex) return EINVAL;
    for (unsigned int i = 0; i < 32; i++) {
        if (!mutex_entries[i].key) mutex_entries[i].key = mutex;
        if (mutex_entries[i].key != mutex) continue;
        if (mutex_entries[i].state) abort();
        mutex_entries[i].state = 1;
        return 0;
    }
    abort();
}
int pthread_mutex_unlock(pthread_mutex_t *mutex)
{
    for (unsigned int i = 0; i < 32; i++) {
        if (mutex_entries[i].key != mutex) continue;
        if (!mutex_entries[i].state) abort();
        mutex_entries[i].state = 0;
        return 0;
    }
    abort();
}

extern int __gettimeofday_with_mach(struct timeval *, struct timezone *, uint64_t *);
uint64_t mach_absolute_time(void)
{
    struct timeval wall;
    uint64_t ticks;
    if (__gettimeofday_with_mach(&wall, NULL, &ticks) < 0) abort();
    return ticks;
}

/* Unified logging is explicitly disabled: no log service/capture exists. */
struct os_log_s { unsigned char unavailable; };
struct os_log_s _os_log_default, _os_log_disabled;
os_log_t os_log_create(const char *subsystem, const char *category)
{
    (void)subsystem; (void)category;
    return OS_LOG_DISABLED;
}
bool os_log_type_enabled(os_log_t log, os_log_type_t type)
{
    (void)log; (void)type;
    return false;
}
#define DISABLED_LOG_IMPLEMENTATION(name) \
    void name(void *dso, os_log_t log, os_log_type_t type, const char *format, uint8_t *buf, uint32_t size) \
    { (void)dso; (void)log; (void)type; (void)format; (void)buf; (void)size; abort(); }
DISABLED_LOG_IMPLEMENTATION(_os_log_debug_impl)
DISABLED_LOG_IMPLEMENTATION(_os_log_error_impl)
DISABLED_LOG_IMPLEMENTATION(_os_log_fault_impl)
