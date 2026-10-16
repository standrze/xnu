/* SPDX-License-Identifier: BSD-2-Clause */
#define main accepted_locale_contract_main
#include "ssh_locale_host.c"
#undef main
#include <signal.h>
#include <stdint.h>
#include <sched.h>

int fixture_strsignal_r(int, char *, size_t);
int fixture_original_strsignal_r(int, char *, size_t);
static atomic_uint signal_ready;
static uintptr_t signal_pointers[4];

static unsigned word(char *out, unsigned index, unsigned maximum)
{
    for (unsigned length = 0, count = 1; length <= maximum; length++, count *= 3) {
        if (index < count) {
            for (unsigned i = 0; i < length; i++, index /= 3) out[i] = "aBc"[index % 3];
            out[length] = 0; return length;
        }
        index -= count;
    }
    abort();
}

static unsigned char fold(unsigned char c)
{
    return c >= 'A' && c <= 'Z' ? (unsigned char)(c + 'a' - 'A') : c;
}

static char *oracle(const char *haystack, const char *needle)
{
    if (!needle[0]) return (char *)haystack;
    for (size_t at = 0; haystack[at]; at++) {
        size_t j = 0;
        while (needle[j] && haystack[at + j] && fold((unsigned char)needle[j]) == fold((unsigned char)haystack[at + j])) j++;
        if (!needle[j]) return (char *)haystack + at;
    }
    return NULL;
}

static void *case_worker(void *raw)
{
    uintptr_t index = (uintptr_t)raw;
    locale_t local = duplocale(LC_GLOBAL_LOCALE);
    struct custom_ctype *custom = malloc(sizeof(*custom));
    if (!local || !custom) abort();
    custom->ctype = _DefaultRuneXLocale;
    custom->runes = *custom->ctype._CurrentRuneLocale;
    custom->ctype._CurrentRuneLocale = &custom->runes;
    custom->ctype.header.header.retain_count = 1;
    custom->ctype.header.header.destructor = dispose_ctype;
    custom->runes.__maplower[128] = (index & 1) ? 'a' : 128;
    xlocale_release(local->components[XLC_CTYPE]);
    local->components[XLC_CTYPE] = (struct xlocale_component *)custom;
    if (uselocale(local) != LC_GLOBAL_LOCALE || freelocale(local)) return (void *)1;
    const char haystack[] = {'x', (char)128, 'B', 'c', 0};
    for (unsigned i = 0; i < 1024; i++) {
        const char *expected = (index & 1) ? haystack + 1 : NULL;
        if (strcasestr(haystack, "AbC") != expected ||
            strcasestr_l(haystack, "AbC", __current_locale()) != expected ||
            strcasestr_l(haystack, "AbC", LC_C_LOCALE) ||
            strcasestr_l(haystack, "AbC", LC_GLOBAL_LOCALE)) return (void *)2;
    }
    return NULL;
}

static void *signal_worker(void *raw)
{
    uintptr_t index = (uintptr_t)raw;
    char *buffer = strsignal(SIGTERM);
    if (!buffer || strcmp(buffer, "Terminated: 15")) return (void *)1;
    signal_pointers[index] = (uintptr_t)buffer;
    atomic_fetch_add(&signal_ready, 1);
    while (atomic_load(&signal_ready) != 4) sched_yield();
    for (unsigned i = 0; i < 4; i++)
        if (i != index && signal_pointers[i] == (uintptr_t)buffer) return (void *)2;
    for (unsigned i = 0; i < 512; i++) {
        if (strsignal(SIGTERM) != buffer || strcmp(buffer, "Terminated: 15")) return (void *)3;
    }
    return NULL;
}

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "original-small-buffer")) {
        char *buffer = malloc(1); if (!buffer) abort();
        fixture_original_strsignal_r(SIGTERM, buffer, 0); free(buffer); return 90;
    }
    if (argc == 2 && !strcmp(argv[1], "original-int-min")) {
        char buffer[128]; fixture_original_strsignal_r(INT_MIN, buffer, sizeof(buffer)); return 91;
    }
    if (accepted_locale_contract_main(1, argv)) return 1;
    unsigned cases = 0;
    for (unsigned alignment = 0; alignment < 4; alignment++)
        for (unsigned h = 0; h < 1093; h++)
            for (unsigned n = 0; n < 40; n++) {
                char text[7], needle[4]; unsigned length = word(text, h, 6); word(needle, n, 3);
                char *storage = malloc(alignment + length + 1); if (!storage) abort();
                char *haystack = storage + alignment; memcpy(haystack, text, length + 1);
                char *expected = oracle(haystack, needle);
                if (strcasestr(haystack, needle) != expected ||
                    strcasestr_l(haystack, needle, LC_C_LOCALE) != expected ||
                    strcasestr_l(haystack, needle, LC_GLOBAL_LOCALE) != expected) return 2;
                free(storage); cases++;
            }
    for (unsigned c = 1; c < 256; c++) {
        const char haystack[] = {'x', (char)c, 0}, needle[] = {(char)c, 0};
        if (strcasestr(haystack, needle) != (c == 'x' || c == 'X' ? haystack : haystack + 1)) return 3;
    }
    pthread_t threads[4];
    for (uintptr_t i = 0; i < 4; i++) if (pthread_create(&threads[i], NULL, case_worker, (void *)i)) return 4;
    for (unsigned i = 0; i < 4; i++) { void *result; if (pthread_join(threads[i], &result) || result) return 5; }
    if (atomic_load(&destroyed) != 8) return 6;
    const int numbers[] = {-1, 0, SIGHUP, SIGTERM, SIGUSR2, NSIG, INT_MIN, INT_MAX};
    unsigned buffers = 0;
    for (unsigned i = 0; i < sizeof(numbers) / sizeof(numbers[0]); i++) {
        int number = numbers[i], known = number > 0 && number < NSIG;
        const char *description = known ? sys_siglist[number] : "Unknown signal";
        char full[128], suffix[32]; snprintf(full, sizeof(full), "%s: %d", description, number);
        snprintf(suffix, sizeof(suffix), ": %d", number);
        for (size_t capacity = 0; capacity <= 80; capacity++) {
            char *buffer = malloc(capacity ? capacity : 1); if (!buffer) abort();
            memset(buffer, 0xa5, capacity ? capacity : 1);
            int result = fixture_strsignal_r(number, buffer, capacity);
            int fits = strlen(full) < capacity;
            if (result != (known ? (fits ? 0 : ERANGE) : EINVAL)) return 7;
            if (capacity) {
                char expected[128];
                strlcpy(expected, fits ? full : description, capacity);
                if (strcmp(buffer, expected)) return 8;
            } else if ((unsigned char)buffer[0] != 0xa5) return 9;
            free(buffer); buffers++;
        }
        errno = EDOM; char *public = strsignal(number);
        if (!public || strcmp(public, full) || errno != (known ? EDOM : EINVAL)) return 10;
    }
    for (int number = 1; number < NSIG; number++) {
        char expected[128]; snprintf(expected, sizeof(expected), "%s: %d", sys_siglist[number], number);
        if (!sys_signame[number] || !sys_siglist[number] || strcmp(strsignal(number), expected)) return 11;
    }
    for (uintptr_t i = 0; i < 4; i++) if (pthread_create(&threads[i], NULL, signal_worker, (void *)i)) return 12;
    for (unsigned i = 0; i < 4; i++) { void *result; if (pthread_join(threads[i], &result) || result) return 13; }
    if (cases != 174880 || buffers != 648) return 14;
    puts("APPLE_CASE_SIGNAL PASS SEARCH_CASES=174880 MODES=3 HIGH_BYTES=255 CASE_THREADS=4 SIGNAL_BUFFERS=648 SIGNALS=31 SIGNAL_THREADS=4 INT_MIN=1 ORIGINAL_NEGATIVES_SEPARATE");
    return 0;
}
