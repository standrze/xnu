/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef DARWIN_VM_SHELL_PARSER_H
#define DARWIN_VM_SHELL_PARSER_H
#include <stddef.h>
#define SH_COMMANDS 16
#define SH_ARGUMENTS 32
#define SH_STORAGE 4096
enum sh_link { SH_END, SH_PIPE, SH_NEXT, SH_AND, SH_OR };
struct sh_command {
    int argc;
    char *argv[SH_ARGUMENTS + 1];
    char *input, *output;
    int append;
    enum sh_link link;
};
struct sh_line {
    struct sh_command commands[SH_COMMANDS];
    int count;
    char storage[SH_STORAGE];
};
/* No allocation, evaluation, globbing, substitution or filesystem access. */
const char *sh_parse(struct sh_line *result, const char *line, int status,
                     const char *cwd);
int sh_path(char *out, size_t capacity, const char *cwd, const char *path);
#endif
