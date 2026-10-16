# SPDX-License-Identifier: BSD-2-Clause
"""Private C1 reserved-zero AXI overlay; never edit frozen controller sources.

Raspberry Pi linux rpi-6.18.y pcie-brcmstb.c:1013-1030 selects a 15-request
fallback when the timing-fix bit reads zero. Our physical passive trace reads
0x60 at0x416c after the fix-bit write. Do not require unavailable fix bits.
Keep unknown mixed capability shapes, propagation, and bad fallback readbacks
fail-closed. Source profile evidence does not itself authorize device accesses.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEADER = '''/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_AXI_RESERVED_PROFILE_H
#define RPI5_AXI_RESERVED_PROFILE_H
#include <stdint.h>
/* Supported capabilities: all fixes, reserved timing only, or C1 all reserved.
 * Partial/unknown combinations are not inferred from a successful bus read. */
static inline int rpi5_axi_capabilities_valid(uint32_t value)
{
    uint32_t fixes = value & UINT32_C(0x3800);
    return value != UINT32_MAX && !(value & UINT32_C(0x80)) &&
        (fixes == UINT32_C(0x3800) || fixes == UINT32_C(0x2800) || fixes == 0);
}
static inline int rpi5_axi_configured(uint32_t value)
{
    return rpi5_axi_capabilities_valid(value) &&
        ((value & UINT32_C(0x1000)) || (value & UINT32_C(0x3f)) == 15);
}
#endif
'''


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unexpected frozen AXI source shape: ' + old)
    return text.replace(old, new)


def transform(name, text):
    text = once(text, '#include "' + name.removesuffix('.c') + '.h"',
        '#include "' + name.removesuffix('.c') + '.h"\n#include "rpi5_axi_reserved_profile.h"')
    if name == 'pcie_ubus.c':
        text = once(text, '#define AXI_REQUIRED UINT32_C(0x2800)\n', '')
        text = once(text,
            '    if ((result.axi_after & (AXI_REQUIRED | AXI_PROPAGATION)) != AXI_REQUIRED)',
            '    if (!rpi5_axi_capabilities_valid(result.axi_after) ||\n'
            '        (result.axi_after & ~(AXI_SET | AXI_PROPAGATION)) !=\n'
            '        (result.axi_before & ~(AXI_SET | AXI_PROPAGATION)))')
        text = once(text,
            '        if ((result.axi_final & (AXI_REQUIRED | AXI_PROPAGATION | AXI_TIMING | 0x3f)) != (AXI_REQUIRED | 15))',
            '        if (result.axi_final != ((result.axi_after & ~UINT32_C(0x3f)) | 15) ||\n'
            '            !rpi5_axi_configured(result.axi_final))')
    elif name in ('pcie_qos.c', 'pcie_clock.c'):
        text = once(text, '(axi & 0x2880) != 0x2800', '!rpi5_axi_configured(axi)')
    else:
        raise ValueError('Only the three exact AXI consumer cores may change')
    return text


def emit(directory):
    directory.mkdir(exist_ok=False)
    paths = []
    for name in ('pcie_ubus.c', 'pcie_qos.c', 'pcie_clock.c'):
        path = directory / name
        path.write_text(transform(name, (ROOT / 'loader/rpi5' / name).read_text()))
        paths.append(path)
    (directory / 'rpi5_axi_reserved_profile.h').write_text(HEADER)
    return paths
