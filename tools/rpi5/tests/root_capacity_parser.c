/* SPDX-License-Identifier: BSD-2-Clause */
#include <stdio.h>
#include <stdlib.h>
#include <miscfs/mockfs/rpi5_ramroot_format.h>
int main(int argc, char **argv)
{
    uint8_t page[RPI5_RFS_PAGE];
    uint32_t count = 123;
    if (argc != 2 || fread(page, 1, sizeof(page), stdin) != sizeof(page)) return 2;
    int result = rpi5_rfs_validate(page, strtoull(argv[1], NULL, 10), &count);
    if (result && count != 123) return 3;
    return result ? 1 : 0;
}
