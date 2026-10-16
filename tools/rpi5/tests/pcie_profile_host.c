/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_profile.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv)
{
    assert(argc == 7);
    FILE *f = fopen(argv[1], "rb"); assert(f);
    assert(!fseek(f, 0, SEEK_END)); long length = ftell(f); assert(length > 0); rewind(f);
    unsigned char *bytes = malloc((size_t)length), *before = malloc((size_t)length); assert(bytes && before);
    assert(fread(bytes, 1, (size_t)length, f) == (size_t)length); assert(!fclose(f));
    memcpy(before, bytes, (size_t)length);
    struct rpi5_pcie_profile profile, saved;
    struct rpi5_pcie_fdt binding, prior;
    memset(&profile, 0xa5, sizeof profile); saved = profile;
    memset(&binding, 0xa5, sizeof binding); prior = binding;
    int rc = rpi5_pcie_profile_decode(bytes, (size_t)length, &binding, &profile);
    assert(rc == atoi(argv[2]) && !memcmp(bytes, before, (size_t)length));
    if (!rc) {
        assert(profile.generation == 2 && profile.lanes == 4);
        assert(profile.qos_kind == strtoul(argv[3], 0, 0));
        assert(profile.qos_word == strtoul(argv[4], 0, 0));
        assert(profile.clkreq == strtoul(argv[5], 0, 0));
        assert(profile.aspm_no_l0s == strtoul(argv[6], 0, 0));
        assert(binding.bridge_regs.start == UINT64_C(0x1000120000));
    } else {
        assert(!memcmp(&profile, &saved, sizeof saved));
        assert(!memcmp(&binding, &prior, sizeof prior));
    }
    assert(rpi5_pcie_profile_decode(0, (size_t)length, &binding, &profile) == RPI5_PCIE_PROFILE_ARGUMENT);
    assert(rpi5_pcie_profile_decode(bytes, (size_t)length, 0, &profile) == RPI5_PCIE_PROFILE_ARGUMENT);
    assert(rpi5_pcie_profile_decode(bytes, (size_t)length, &binding, 0) == RPI5_PCIE_PROFILE_ARGUMENT);
    free(before); free(bytes); puts("PCIE_PROFILE_HOST_PASS NO_MMIO=1");
    return 0;
}
