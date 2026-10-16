/* SPDX-License-Identifier: BSD-2-Clause */
/* Compiled twice: actual original client flags versus provider flags. */
#include <dirent.h>
#include <stddef.h>
#include <pthread.h>
#define OFF(type,member) __builtin_offsetof(type,member)
const unsigned long long directory_abi[] = {
    sizeof(DIR),_Alignof(DIR),OFF(DIR,__dd_fd),OFF(DIR,__dd_loc),
    OFF(DIR,__dd_size),OFF(DIR,__dd_buf),OFF(DIR,__dd_len),OFF(DIR,__dd_seek),
    OFF(DIR,__dd_flags),OFF(DIR,__dd_lock),OFF(DIR,__dd_td),sizeof(((DIR *)0)->__dd_lock),
    sizeof(pthread_mutex_t),sizeof(struct dirent),_Alignof(struct dirent),
    OFF(struct dirent,d_ino),OFF(struct dirent,d_seekoff),OFF(struct dirent,d_reclen),
    OFF(struct dirent,d_namlen),OFF(struct dirent,d_type),OFF(struct dirent,d_name),
    sizeof(((struct dirent *)0)->d_name)
};
