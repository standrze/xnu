/* SPDX-License-Identifier: BSD-2-Clause */
#include "psci_restart_candidate.h"
#include "fdt.h"

static int exact(const uint8_t *p, size_t size, const char *wanted)
{
    size_t n = 0;
    while (wanted[n]) n++;
    if (size != n + 1) return 0;
    for (size_t i = 0; i <= n; i++) if (p[i] != (uint8_t)wanted[i]) return 0;
    return 1;
}

static int binding(const void *tree, size_t bytes)
{
    struct rpi5_fdt_property p;
    const uint8_t *raw = tree;
    if (rpi5_fdt_psci_smc(tree, bytes) ||
        rpi5_fdt_property(tree, bytes, "/", "compatible", &p)) return -1;
    uint32_t found = 0, at = 0;
    while (at < p.length) {
        uint32_t begin = at;
        while (at < p.length && raw[p.offset + at]) at++;
        if (at == p.length || at == begin) return -1;
        at++;
        uint32_t bit = exact(raw + p.offset + begin, at - begin, "raspberrypi,5-model-b") ? 1 :
            exact(raw + p.offset + begin, at - begin, "brcm,bcm2712") ? 2 : 0;
        if (!bit || (found & bit)) return -1;
        found |= bit;
    }
    if (found != 3) return -1;
    int status = rpi5_fdt_property(tree, bytes, "/", "status", &p);
    if (status != -2 && (status ||
        (!exact(raw + p.offset, p.length, "ok") && !exact(raw + p.offset, p.length, "okay")))) return -1;
    return 0;
}

int rpi5_restart_attempt(struct rpi5_restart_once *once, const void *tree, size_t bytes)
{
    uintptr_t a = (uintptr_t)once, b = (uintptr_t)tree;
    if (!once || !tree || a % _Alignof(struct rpi5_restart_once) ||
        bytes < 40 || bytes > 2u * 1024u * 1024u ||
        a > UINTPTR_MAX - sizeof(*once) || b > UINTPTR_MAX - bytes ||
        (a < b + bytes && b < a + sizeof(*once)) || binding(tree, bytes)) return RPI5_RESTART_REFUSED;
    if (rpi5_restart_current_el() != 4) return RPI5_RESTART_REFUSED;
    uint32_t expected = 0;
    if (!__atomic_compare_exchange_n(&once->entered, &expected, 1, 0,
        __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return RPI5_RESTART_BUSY;
    /* Deliberately narrow to the currently audited normal TF-A 1.1 image.
     * A later version requires a new qualification, not an optimistic reset.
     */
    if ((uint32_t)rpi5_restart_psci_version() != UINT32_C(0x00010001)) return RPI5_RESTART_VERSION;
    if ((uint32_t)rpi5_restart_psci_feature() != 0) return RPI5_RESTART_UNSUPPORTED;
    (void)rpi5_restart_psci_reset();
    return RPI5_RESTART_RETURNED;
}
