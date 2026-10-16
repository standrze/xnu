/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../user/parser.h"
int main(void)
{
    struct sh_line r;
    assert(!sh_parse(&r, "echo 'a b' \"c d\" e\\ f '' $? $PWD | wc && pwd;", 7, "/etc"));
    assert(r.count == 3 && r.commands[0].argc == 7);
    const char *words[] = {"echo", "a b", "c d", "e f", "", "7", "/etc"};
    for (int i = 0; i < 7; i++) assert(!strcmp(r.commands[0].argv[i], words[i]));
    assert(r.commands[0].link == SH_PIPE && r.commands[1].link == SH_AND);
    assert(r.commands[2].link == SH_END);
    assert(!sh_parse(&r, "cat < /etc/motd >> /dev/null", 0, "/"));
    assert(!strcmp(r.commands[0].input, "/etc/motd"));
    assert(!strcmp(r.commands[0].output, "/dev/null") && r.commands[0].append);
    assert(!sh_parse(&r, "cat >> /dev/null < /etc/motd", 0, "/"));
    assert(r.commands[0].append);
    const char *bad[] = {"a |", "a &&", "a ||", "| a", "a & b", "a >", "'a", "a \\",
                         "a $HOME", "a > ''", "a < x < y", ";", "a || | b"};
    for (size_t i = 0; i < sizeof(bad) / sizeof(bad[0]); i++) assert(sh_parse(&r, bad[i], 0, "/"));
    assert(!sh_parse(&r, "# ignored", 0, "/") && !r.count);
    assert(!sh_parse(&r, "echo '#literal' # ignored", 0, "/") && r.commands[0].argc == 2);
    char path[64];
    assert(!sh_path(path, sizeof(path), "/etc", "../bin/./../etc//motd") && !strcmp(path, "/etc/motd"));
    assert(!sh_path(path, sizeof(path), "/", "../../") && !strcmp(path, "/"));
    assert(sh_path(path, 4, "/", "/long"));
    char large[8192]; memset(large, 'x', sizeof(large)); large[sizeof(large) - 1] = 0;
    assert(sh_parse(&r, large, 0, "/"));
    /* Deterministic malformed/random bounded inputs exercise parser limits. */
    unsigned seed = 0x5235;
    static const char alphabet[] = "abcPWD? $'\"\\|&;<>\t#";
    for (int iteration = 0; iteration < 20000; iteration++) {
        size_t n = (unsigned)iteration % 512;
        for (size_t i = 0; i < n; i++) {
            seed = seed * 1664525u + 1013904223u;
            large[i] = alphabet[seed % (sizeof(alphabet) - 1)];
        }
        large[n] = 0;
        if (!sh_parse(&r, large, 1, "/etc")) {
            assert(r.count <= SH_COMMANDS);
            for (int i = 0; i < r.count; i++) {
                assert(r.commands[i].argc > 0 && r.commands[i].argc <= SH_ARGUMENTS);
                assert(!r.commands[i].argv[r.commands[i].argc]);
            }
        }
    }
    puts("PARSER_PASS"); return 0;
}
