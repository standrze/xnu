/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_profile.h"
#include "fdt.h"
static const char path[] = "/axi/pcie@1000120000";
static int prop(const void *fdt, size_t size, const char *name,
    const uint8_t **value, uint32_t *length)
{
    struct rpi5_fdt_property p;
    int rc = rpi5_fdt_property(fdt, size, path, name, &p);
    if (rc == -2) return 1;
    if (rc) return -1;
    *value = (const uint8_t *)fdt + p.offset; *length = p.length;
    return 0;
}
static int string_is(const uint8_t *value, uint32_t size, const char *wanted, uint32_t n)
{
    if (size != n) return 0;
    for (uint32_t i = 0; i < n; i++) if (value[i] != (uint8_t)wanted[i]) return 0;
    return 1;
}
int rpi5_pcie_profile_decode(const void *fdt, size_t size, struct rpi5_pcie_fdt *binding,
    struct rpi5_pcie_profile *out)
{
    if (!fdt || !binding || !out) return RPI5_PCIE_PROFILE_ARGUMENT;
    struct rpi5_pcie_fdt decoded;
    if (rpi5_fdt_pcie_rp1(fdt, size, &decoded)) return RPI5_PCIE_PROFILE_BINDING;
    struct rpi5_pcie_profile result = {2, 4, RPI5_PCIE_CLKREQ_ABSENT, 0, RPI5_PCIE_QOS_NONE, 0};
    const uint8_t *value; uint32_t length; int rc;
    /* These are unsupported declarations, not an inference of ownership from
     * their absence. The actual inherited controller domains remain required. */
    const char *unsupported[] = {"brcm,enable-ssc", "brcm,scb-sizes", "clocks", "clock-names",
        "power-domains", "power-domain-names", "iommus", "iommu-map", "iommu-map-mask"};
    for (unsigned i = 0; i < sizeof unsupported / sizeof unsupported[0]; i++) {
        rc = prop(fdt, size, unsupported[i], &value, &length);
        if (rc < 0) return RPI5_PCIE_PROFILE_OPTION;
        if (!rc) return RPI5_PCIE_PROFILE_UNSUPPORTED;
    }
    rc = prop(fdt, size, "brcm,tperst-clk-ms", &value, &length);
    if (rc < 0 || (!rc && length != 4)) return RPI5_PCIE_PROFILE_OPTION;
    if (!rc && (value[0] || value[1] || value[2] || value[3])) return RPI5_PCIE_PROFILE_UNSUPPORTED;
    rc = prop(fdt, size, "brcm,clkreq-mode", &value, &length);
    if (rc < 0) return RPI5_PCIE_PROFILE_OPTION;
    if (!rc) {
        if (string_is(value, length, "safe", sizeof "safe")) result.clkreq = RPI5_PCIE_CLKREQ_SAFE;
        else if (string_is(value, length, "default", sizeof "default")) result.clkreq = RPI5_PCIE_CLKREQ_DEFAULT;
        else if (string_is(value, length, "no-l1ss", sizeof "no-l1ss")) result.clkreq = RPI5_PCIE_CLKREQ_NO_L1SS;
        else return RPI5_PCIE_PROFILE_OPTION;
    }
    rc = prop(fdt, size, "aspm-no-l0s", &value, &length);
    if (rc < 0 || (!rc && length)) return RPI5_PCIE_PROFILE_OPTION;
    result.aspm_no_l0s = !rc;
    for (unsigned kind = RPI5_PCIE_QOS_FIFO; kind <= RPI5_PCIE_QOS_VDM; kind++) {
        rc = prop(fdt, size, kind == RPI5_PCIE_QOS_FIFO ? "brcm,fifo-qos-map" : "brcm,vdm-qos-map",
            &value, &length);
        if (rc < 0) return RPI5_PCIE_PROFILE_OPTION;
        if (rc) continue;
        if (result.qos_kind != RPI5_PCIE_QOS_NONE || length != (kind == RPI5_PCIE_QOS_FIFO ? 4u : 8u))
            return RPI5_PCIE_PROFILE_OPTION;
        result.qos_kind = kind;
        for (unsigned i = 0; i < length; i++) {
            if (value[i] > 15) return RPI5_PCIE_PROFILE_OPTION;
            result.qos_word |= (uint32_t)value[i] << (4*i);
        }
    }
    *binding = decoded; *out = result;
    return RPI5_PCIE_PROFILE_OK;
}
