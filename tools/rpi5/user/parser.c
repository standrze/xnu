/* SPDX-License-Identifier: BSD-2-Clause */
#include "parser.h"

static int space(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }
static int special(char c) { return c == ';' || c == '|' || c == '&' || c == '<' || c == '>'; }
static int append(char **out, char *end, char value)
{
    if (*out == end) return -1;
    *(*out)++ = value;
    return 0;
}
static int string(char **out, char *end, const char *value)
{
    while (*value) if (append(out, end, *value++)) return -1;
    return 0;
}

const char *sh_parse(struct sh_line *r, const char *p, int status, const char *cwd)
{
    char *out = r->storage, *end = out + sizeof(r->storage);
    r->count = 0;
    struct sh_command *c = &r->commands[0];
    *c = (struct sh_command){0};
    int redirect = 0;
    for (;;) {
        while (space(*p)) p++;
        if (!*p || *p == '#') {
            if (redirect) return "missing redirect path";
            if (!c->argc && (c->input || c->output || r->count)) return "missing command";
            if (c->argc) { c->link = SH_END; r->count++; }
            return 0;
        }
        if (special(*p)) {
            if (redirect) return "missing redirect path";
            if (*p == '<' || *p == '>') {
                redirect = *p++ == '<' ? 1 : 2;
                if (redirect == 2) {
                    c->append = *p == '>';
                    if (c->append) p++;
                }
                continue;
            }
            if (!c->argc) return "empty command";
            if (*p == ';') { c->link = SH_NEXT; p++; }
            else if (*p == '|' && p[1] == '|') { c->link = SH_OR; p += 2; }
            else if (*p == '&' && p[1] == '&') { c->link = SH_AND; p += 2; }
            else if (*p == '|') { c->link = SH_PIPE; p++; }
            else return "background jobs are not supported";
            while (space(*p)) p++;
            if (!*p || *p == '#') {
                if (c->link != SH_NEXT) return "missing command after operator";
                c->link = SH_END; r->count++; return 0;
            }
            if (++r->count == SH_COMMANDS) return "too many commands";
            c = &r->commands[r->count];
            *c = (struct sh_command){0};
            continue;
        }
        char *word = out;
        char quote = 0;
        while (*p && (quote || (!space(*p) && !special(*p)))) {
            char v = *p++;
            if ((v == '\'' || v == '"') && (!quote || quote == v)) {
                quote = quote ? 0 : v; continue;
            }
            if (v == '\\' && quote != '\'') {
                if (!*p) return "trailing escape";
                v = *p++;
            } else if (v == '$' && quote != '\'') {
                if (*p == '?') {
                    char digits[12]; unsigned n = (unsigned)status, i = 0;
                    p++;
                    do { digits[i++] = (char)('0' + n % 10); n /= 10; } while (n);
                    while (i) if (append(&out, end, digits[--i])) return "line storage full";
                    continue;
                }
                if (p[0] == 'P' && p[1] == 'W' && p[2] == 'D' &&
                    !(p[3] == '_' || (p[3] >= 'A' && p[3] <= 'Z') ||
                      (p[3] >= 'a' && p[3] <= 'z') || (p[3] >= '0' && p[3] <= '9'))) {
                    p += 3;
                    if (string(&out, end, cwd)) return "line storage full";
                    continue;
                }
                return "only $? and $PWD expansion are supported";
            }
            if (append(&out, end, v)) return "line storage full";
        }
        if (quote) return "unterminated quote";
        if (append(&out, end, 0)) return "line storage full";
        if (redirect) {
            if (!*word) return "empty redirect path";
            if (redirect == 1) {
                if (c->input) return "duplicate input redirect";
                c->input = word;
            } else {
                if (c->output) return "duplicate output redirect";
                c->output = word;
            }
            redirect = 0;
        } else {
            if (c->argc == SH_ARGUMENTS) return "too many arguments";
            c->argv[c->argc++] = word;
            c->argv[c->argc] = 0;
        }
    }
}

int sh_path(char *out, size_t capacity, const char *cwd, const char *path)
{
    if (capacity < 2 || cwd[0] != '/') return -1;
    char joined[1024]; size_t n = 0;
    if (path[0] != '/') {
        for (; *cwd; cwd++) {
            if (n + 2 >= sizeof(joined)) return -1;
            joined[n++] = *cwd;
        }
        joined[n++] = '/';
    }
    for (; *path; path++) {
        if (n + 1 >= sizeof(joined)) return -1;
        joined[n++] = *path;
    }
    joined[n] = 0;
    size_t length = 1, pos = 0;
    out[0] = '/';
    while (pos < n) {
        while (joined[pos] == '/') pos++;
        size_t start = pos;
        while (joined[pos] && joined[pos] != '/') pos++;
        size_t count = pos - start;
        if (!count || (count == 1 && joined[start] == '.')) continue;
        if (count == 2 && joined[start] == '.' && joined[start + 1] == '.') {
            while (length > 1 && out[length - 1] != '/') length--;
            if (length > 1) length--;
            continue;
        }
        if (length + (length > 1) + count >= capacity) return -1;
        if (length > 1) out[length++] = '/';
        for (size_t i = 0; i < count; i++) out[length++] = joined[start + i];
    }
    out[length] = 0;
    return 0;
}
