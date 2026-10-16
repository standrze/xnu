/* SPDX-License-Identifier: BSD-2-Clause
 * Native parser/packed-record fixture only. No public lookup, OS file, or
 * DirectoryService provider is replaced. The complete original file TU is
 * included to reach its private parsers; unused services are dead-stripped.
 */
#include TEST_FILE_MODULE
#include <assert.h>
#include <grp.h>
#include <pwd.h>

static si_item_t *user(const char *line, int format, const char *name,
                      uid_t uid, int selection)
{
    char *copy = line ? strdup(line) : NULL;
    si_item_t *item = _fsi_parse_user(NULL, name, uid, selection, copy,
                                     format, 123, 456);
    free(copy);
    return item;
}

static si_item_t *group(const char *line, const char *name, gid_t gid,
                       int selection)
{
    char *copy = line ? strdup(line) : NULL;
    si_item_t *item = _fsi_parse_group(NULL, name, gid, selection, copy, 123, 456);
    free(copy);
    return item;
}

int main(void)
{
    const char *passwd = "fixture:*:501:20:Fixture Account:/Users/fixture:/bin/zsh";
    const char *master = "fixture:*:501:20:staff:23:42:Fixture Account:/Users/fixture:/bin/zsh";
    unsigned users = 0, groups = 0, rejected = 0;
    for (int format = 0; format != 2; ++format) {
        for (int which = 0; which != 3; ++which) {
            const int select[] = {SEL_ALL, SEL_NAME, SEL_NUMBER};
            si_item_t *item = user(format ? passwd : master, format, "fixture", 501, select[which]);
            assert(item && item->type == CATEGORY_USER && item->refcount == 1);
            assert(item->validation_a == 123 && item->validation_b == 456);
            const struct passwd *p = (const struct passwd *)(item + 1);
            assert(!strcmp(p->pw_name, "fixture") && !strcmp(p->pw_passwd, "*"));
            assert(p->pw_uid == 501 && p->pw_gid == 20);
            assert(!strcmp(p->pw_gecos, "Fixture Account"));
            assert(!strcmp(p->pw_dir, "/Users/fixture") && !strcmp(p->pw_shell, "/bin/zsh"));
            assert(p->pw_change == (format ? 0 : 23) && p->pw_expire == (format ? 0 : 42));
            assert(!strcmp(p->pw_class, format ? "" : "staff"));
            si_item_retain(item); assert(item->refcount == 2);
            si_item_release(item); si_item_release(item); ++users;
        }
    }
    const char *baduser[] = {NULL, "", "a:b", "a:b:1:2:c:d:e:f", "a:b:1:2:c:d"};
    for (unsigned i = 0; i != sizeof(baduser)/sizeof(*baduser); ++i) {
        assert(!user(baduser[i], 1, "fixture", 501, SEL_ALL)); ++rejected;
    }
    assert(!user(passwd, 1, "missing", 501, SEL_NAME)); ++rejected;
    assert(!user(passwd, 1, "fixture", 502, SEL_NUMBER)); ++rejected;
    assert(!user(master, 1, "fixture", 501, SEL_ALL)); ++rejected;
    assert(!user(passwd, 0, "fixture", 501, SEL_ALL)); ++rejected;
    const int select[] = {SEL_ALL, SEL_NAME, SEL_NUMBER};
    for (unsigned i = 0; i != 3; ++i) {
        si_item_t *item = group("staff:*:20:fixture,second", "staff", 20, select[i]);
        assert(item && item->type == CATEGORY_GROUP);
        const struct group *g = (const struct group *)(item + 1);
        assert(!strcmp(g->gr_name, "staff") && !strcmp(g->gr_passwd, "*") && g->gr_gid == 20);
        assert(!strcmp(g->gr_mem[0], "fixture") && !strcmp(g->gr_mem[1], "second") && !g->gr_mem[2]);
        si_item_release(item); ++groups;
    }
    const char *badgroup[] = {NULL, "", "staff:*:20", "staff:*:20:fixture:extra"};
    for (unsigned i = 0; i != sizeof(badgroup)/sizeof(*badgroup); ++i) {
        assert(!group(badgroup[i], "staff", 20, SEL_ALL)); ++rejected;
    }
    assert(!group("staff:*:20:fixture", "missing", 20, SEL_NAME)); ++rejected;
    assert(!group("staff:*:20:fixture", "staff", 21, SEL_NUMBER)); ++rejected;
    printf("LIBINFO_FILE_PARSERS PASS USERS=%u GROUPS=%u REJECTED=%u PACKED_RECORDS_ONLY\n", users, groups, rejected);
    return 0;
}
