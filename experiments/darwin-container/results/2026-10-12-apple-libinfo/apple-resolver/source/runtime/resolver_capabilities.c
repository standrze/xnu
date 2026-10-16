/* SPDX-License-Identifier: BSD-2-Clause
 * Explicit capability boundary for a single-thread static resolver process.
 * There is no notifyd/configd, pthread creation or multicast support here.
 * Missing services fail; original Apple res_ninit falls back to its file
 * parser. No host resolver or libSystem is linked.
 */
#include <sys/types.h>
#include <errno.h>
#include <ifaddrs.h>
#include <netdb.h>
#include <notify.h>
#include <pthread.h>
#include <stdlib.h>
#include <time.h>
#include <dnsinfo.h>
#include <resolv.h>
#include <os/lock.h>
#include <string.h>
#include <arpa/inet.h>

const struct in6_addr in6addr_any = IN6ADDR_ANY_INIT;
void bzero(void *bytes, size_t size) { memset(bytes, 0, size); }

/* Restricted ABI packaging for res_ninit's numeric nameserver entries, not
 * a replacement for Apple Libinfo hostname/service lookup. The address
 * parsing itself is original Apple inet_pton. All broader requests fail. */
#ifndef DARWIN_APPLE_LIBINFO
int getaddrinfo(const char *host, const char *service, const struct addrinfo *hints,
                struct addrinfo **result)
{
    if (!result) return EAI_FAIL;
    *result = NULL;
    if (!host || !service || !hints || hints->ai_flags != AI_NUMERICHOST ||
        hints->ai_family != AF_UNSPEC || hints->ai_socktype != SOCK_DGRAM ||
        hints->ai_protocol != 0) return EAI_BADFLAGS;
    unsigned int port = 0;
    for (const char *p = service; *p; p++) {
        if (*p < '0' || *p > '9' || port > 6553) return EAI_SERVICE;
        port = port * 10 + (unsigned int)(*p - '0');
    }
    if (!*service || port > 65535) return EAI_SERVICE;
    struct sockaddr_in address = {0};
    address.sin_len = sizeof(address);
    address.sin_family = AF_INET;
    address.sin_port = htons((unsigned short)port);
    if (inet_pton(AF_INET, host, &address.sin_addr) != 1) return EAI_NONAME;
    struct addrinfo *entry = calloc(1, sizeof(*entry));
    if (!entry) return EAI_MEMORY;
    entry->ai_addr = malloc(sizeof(address));
    if (!entry->ai_addr) { free(entry); return EAI_MEMORY; }
    memcpy(entry->ai_addr, &address, sizeof(address));
    entry->ai_flags = hints->ai_flags;
    entry->ai_family = AF_INET;
    entry->ai_socktype = SOCK_DGRAM;
    entry->ai_protocol = IPPROTO_UDP;
    entry->ai_addrlen = sizeof(address);
    *result = entry;
    return 0;
}
void freeaddrinfo(struct addrinfo *entry)
{
    while (entry) {
        struct addrinfo *next = entry->ai_next;
        free(entry->ai_addr);
        free(entry->ai_canonname);
        free(entry);
        entry = next;
    }
}
#endif

int h_errno;
static struct __res_state process_resolver;
struct __res_state *__res_state(void) { return &process_resolver; }

pthread_t pthread_self(void)
{
    /* The startup's TSD self pointer identifies this sole thread. It is not
     * a full pthread object and is used only as an opaque notification name. */
    return (pthread_t)__builtin_thread_pointer();
}
void *pthread_getspecific(pthread_key_t key)
{
    (void)key;
    errno = ENOTSUP;
    return NULL;
}

uint32_t notify_register_plain(const char *name, int *token)
{
    (void)name;
    if (token) *token = -1;
    return NOTIFY_STATUS_FAILED;
}
uint32_t notify_cancel(int token)
{
    (void)token;
    return NOTIFY_STATUS_INVALID_TOKEN;
}
uint32_t notify_get_state(int token, uint64_t *state)
{
    (void)token; (void)state;
    return NOTIFY_STATUS_INVALID_TOKEN;
}
dns_config_t *dns_configuration_copy(void)
{
    errno = ENOTSUP;
    return NULL;
}
void dns_configuration_free(dns_config_t *configuration)
{
    /* No object can be returned by the unavailable service. */
    if (configuration) abort();
}
void _dns_open_sys_config_notify(int *token) { *token = -1; }
int _dns_check_sys_config_notify(int token) { (void)token; return -1; }
void _dns_close_sys_config_notify(int *token)
{
    if (*token != -1) abort();
}
#ifndef DARWIN_APPLE_LIBINFO
int getifaddrs(struct ifaddrs **addresses)
{
    if (addresses) *addresses = NULL;
    errno = ENOTSUP;
    return -1;
}
void freeifaddrs(struct ifaddrs *addresses) { if (addresses) abort(); }
unsigned int if_nametoindex(const char *name)
{
    (void)name;
    errno = ENOTSUP;
    return 0;
}
int getnameinfo(const struct sockaddr *address, socklen_t size,
               char *host, socklen_t host_size, char *service, socklen_t service_size, int flags)
{
    (void)address; (void)size; (void)host; (void)host_size;
    (void)service; (void)service_size; (void)flags;
    errno = ENOTSUP;
    return EAI_SYSTEM;
}
#endif
int clock_gettime(clockid_t clock, struct timespec *time)
{
    /* Resolver file timestamp caching is optional; do not impersonate a
     * monotonic clock using wall time. Actual socket waits use pselect. */
    (void)clock; (void)time;
    errno = ENOTSUP;
    return -1;
}

/* Real exclusion for Apple's static arc4random implementation. This process
 * never creates threads; unexpected contention is a contract violation. */
void os_unfair_lock_lock(os_unfair_lock_t lock)
{
    if (__atomic_exchange_n(&lock->_os_unfair_lock_opaque, 1, __ATOMIC_ACQUIRE)) abort();
}
void os_unfair_lock_unlock(os_unfair_lock_t lock)
{
    if (__atomic_exchange_n(&lock->_os_unfair_lock_opaque, 0, __ATOMIC_RELEASE) != 1) abort();
}
