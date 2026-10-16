/* SPDX-License-Identifier: BSD-2-Clause */
#include "runtime.h"
#if RPI5_SD_READ_TRIAL
#include "sdread.h"
#endif
#if RPI5_HFS_READ_TRIAL
#include "hfsro.h"
#endif
#if RPI5_HFS_WRITE_TRIAL
#include "hfsrw.h"
#include "hfswrite.h"
#endif

static int stream(int fd, int count, int hex)
{
    unsigned char data[1024];
    unsigned long bytes = 0, lines = 0, words = 0; int inside = 0;
    for (;;) {
        long n = rt_read(fd, data, sizeof(data));
        if (n == -4) continue;
        if (n < 0) { rt_error("read", n); return 1; }
        if (!n) break;
        if (!count && !hex) {
            if (rt_write_all(1, data, (size_t)n)) return 1;
            continue;
        }
        for (long i = 0; i < n; i++) {
            unsigned char c = data[i]; bytes++;
            if (hex) {
                static const char digits[] = "0123456789abcdef";
                char value[] = {digits[c >> 4], digits[c & 15], bytes % 16 ? ' ' : '\n'};
                if (rt_write_all(1, value, sizeof(value))) return 1;
            }
            if (c == '\n') lines++;
            int white = c == ' ' || (c >= '\t' && c <= '\r');
            if (!white && !inside) words++;
            inside = !white;
        }
    }
    if (hex && bytes % 16) rt_put(1, "\n");
    if (count) {
        rt_number(1, lines); rt_put(1, " "); rt_number(1, words);
        rt_put(1, " "); rt_number(1, bytes); rt_put(1, "\n");
    }
    return 0;
}
static int files(int argc, char **argv, int count, int hex)
{
    if (argc == 1) return stream(0, count, hex);
    int result = 0;
    for (int i = 1; i < argc; i++) {
        if (rt_equal(argv[i], "-")) { result |= stream(0, count, hex); continue; }
        long fd = rt_open(argv[i], RT_RDONLY);
        if (fd < 0) { rt_error(argv[i], fd); result = 1; continue; }
        result |= stream((int)fd, count, hex);
        rt_close((int)fd);
    }
    return result;
}
static unsigned short u16(const unsigned char *p)
{ return (unsigned short)(p[0] | ((unsigned)p[1] << 8)); }
static int list(const char *path)
{
    long fd = rt_open(path, RT_RDONLY), position = 0;
    if (fd < 0) { rt_error(path, fd); return 1; }
    int result = 0;
    for (;;) {
        unsigned char data[4096];
        long n = rt_entries((int)fd, data, sizeof(data), &position);
        if (n == -4) continue;
        if (n < 0) { rt_error(path, n); result = 1; break; }
        if (!n) break;
        size_t offset = 0;
        while (offset < (size_t)n) {
            const unsigned char *entry = data + offset;
            if ((size_t)n - offset < 22) { result = 1; break; }
            unsigned reclen = u16(entry + 16), namlen = u16(entry + 18);
            if (reclen < 22 || reclen > (size_t)n - offset ||
                namlen >= reclen - 21 || entry[21 + namlen] != 0) { result = 1; break; }
            const char *name = (const char *)entry + 21;
            if (!rt_equal(name, ".") && !rt_equal(name, "..")) {
                rt_write_all(1, name, namlen);
                rt_put(1, entry[20] == 4 ? "/\n" : "\n");
            }
            offset += reclen;
        }
        if (result) { rt_put(2, "ls: malformed directory result\n"); break; }
    }
    rt_close((int)fd); return result;
}
static int uname_value(int group, int item)
{
    int mib[2] = {group, item}; char value[256]; size_t size = sizeof(value);
    long result = rt_call(202, (long)mib, 2, (long)value, (long)&size, 0, 0);
    if (result < 0 || !size || size > sizeof(value) || value[size - 1]) {
        rt_error("uname/sysctl", result < 0 ? result : -22); return 1;
    }
    rt_put(1, value); return 0;
}
int utility_main(const char *name, int argc, char **argv, char **env)
{
#if RPI5_HFS_WRITE_TRIAL
    if (rt_equal(name, "hfsrw")) return hfsrw_main(argc, argv);
    if (rt_equal(name, "hfswrite")) return hfswrite_main(argc, argv);
#endif
#if RPI5_HFS_READ_TRIAL
    if (rt_equal(name, "hfsro")) return hfsro_main(argc, argv);
#endif
#if RPI5_SD_READ_TRIAL
    if (rt_equal(name, "sdread")) return sdread_main(argc,argv);
#endif
    if (rt_equal(name, "true")) return 0;
    if (rt_equal(name, "false")) return 1;
    if (rt_equal(name, "echo")) {
        int start = argc > 1 && rt_equal(argv[1], "-n") ? 2 : 1;
        for (int i = start; i < argc; i++) {
            if (i != start) rt_put(1, " ");
            rt_put(1, argv[i]);
        }
        if (start == 1) rt_put(1, "\n");
        return 0;
    }
    if (rt_equal(name, "cat") || rt_equal(name, "wc") || rt_equal(name, "hexdump"))
        return files(argc, argv, rt_equal(name, "wc"), rt_equal(name, "hexdump"));
    if (rt_equal(name, "ls")) {
        if (argc == 1) return list(".");
        int result = 0;
        for (int i = 1; i < argc; i++) result |= list(argv[i]);
        return result;
    }
    if (rt_equal(name, "sleep")) {
        unsigned seconds = 0;
        if (argc != 2 || !argv[1][0]) { rt_put(2, "usage: sleep seconds (0..3600)\n"); return 2; }
        for (const char *p = argv[1]; *p; p++) {
            if (*p < '0' || *p > '9' || seconds > 360 ||
                (seconds = seconds * 10 + (unsigned)(*p - '0')) > 3600) {
                rt_put(2, "sleep: invalid duration\n"); return 2;
            }
        }
        long result = rt_sleep(seconds);
        if (result < 0) { rt_error("sleep", result); return 1; }
        return 0;
    }
    if (rt_equal(name, "uname")) {
        int all = argc == 2 && rt_equal(argv[1], "-a");
        if (argc > 2 || (argc == 2 && !all)) { rt_put(2, "usage: uname [-a]\n"); return 2; }
        int result = uname_value(1, 1);
        if (all) {
            rt_put(1, " "); result |= uname_value(1, 10);
            rt_put(1, " "); result |= uname_value(1, 2);
            rt_put(1, " "); result |= uname_value(6, 1);
        }
        rt_put(1, "\n"); return result;
    }
    (void)env;
    rt_put(2, "unknown utility\n"); return 127;
}
