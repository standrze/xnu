/* SPDX-License-Identifier: BSD-2-Clause */
/* Distinct v2 entry point; preserve the already-receipted v1 source. */
#define RPI5_SOCKETPROBE_HOST_TEST
#include "socketprobe.c"
int rootidentity_main(void);
int socketprobe_identity_main(int argc, char **argv)
{
    if (argc==2 && argv && argv[1] && rt_equal(argv[1],"identity")) return rootidentity_main();
    return socketprobe_main(argc,argv);
}
#ifndef RPI5_IDENTITY_HOST_TEST
_Noreturn void user_start(uintptr_t *stack)
{
    if (stack[0]!=2 || !((char **)(stack+1))[0]) rt_exit(2);
    rt_exit(socketprobe_identity_main((int)stack[0],(char **)(stack+1)));
}
#endif
