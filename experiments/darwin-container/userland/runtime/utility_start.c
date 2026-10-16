/* SPDX-License-Identifier: BSD-2-Clause
 * Static entry and explicitly C/POSIX-only locale integration. Command
 * algorithms and conversion routines come from the pinned Apple sources.
 */
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <runetype.h>
#include <stdio.h>
static char **command_argv;
extern int darwin_utility_main(int, char **);
extern int _none_init(_RuneLocale *);
extern size_t _none_mbrtowc(wchar_t *, const char *, size_t, mbstate_t *);
size_t (*__mbrtowc)(wchar_t *, const char *, size_t, mbstate_t *) = _none_mbrtowc;
int (*__mbsinit)(const mbstate_t *);
size_t (*__mbsnrtowcs)(wchar_t *, const char **, size_t, size_t, mbstate_t *);
size_t (*__wcrtomb)(char *, wchar_t, mbstate_t *);
size_t (*__wcsnrtombs)(char *, const wchar_t **, size_t, size_t, mbstate_t *);
char ***_NSGetArgv(void) { return &command_argv; }
/* No account database service exists yet. Report the actual numeric IDs,
 * never invented user/group names. Keep separate buffers for one prompt. */
char *user_from_uid(uid_t uid, int nouser)
{
    static char value[32];
    if (nouser) return NULL;
    snprintf(value, sizeof(value), "%u", (unsigned)uid);
    return value;
}
char *group_from_gid(gid_t gid, int nogroup)
{
    static char value[32];
    if (nogroup) return NULL;
    snprintf(value, sizeof(value), "%u", (unsigned)gid);
    return value;
}
int setrunelocale(const char *name)
{
    if (!strcmp(name, "C") || !strcmp(name, "POSIX"))
        return _none_init(&_DefaultRuneLocale);
    errno = ENOENT;
    return ENOENT;
}
int zsh_main(int argc, char **argv)
{
    command_argv = argv;
    return darwin_utility_main(argc, argv);
}
