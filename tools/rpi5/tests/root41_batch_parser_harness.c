/* SPDX-License-Identifier: BSD-2-Clause */
/* Native actual recovery-parser harness. Never executes a parsed command. */
#include "parser.h"
#include <stdio.h>
#include <string.h>
int main(int argc,char **argv)
{
    if(argc!=2 || strlen(argv[1])>1023) return 2;
    struct sh_line parsed;
    const char *error=sh_parse(&parsed,argv[1],17,"/");
    if(error || parsed.count!=1 || parsed.commands[0].link!=SH_END) return 3;
    for(int i=0;i<parsed.commands[0].argc;i++) puts(parsed.commands[0].argv[i]);
    return 0;
}
