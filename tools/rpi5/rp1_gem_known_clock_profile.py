# SPDX-License-Identifier: BSD-2-Clause
"""Strict known-clock successor; preserve the original prototype as evidence."""
from tools.rpi5 import rp1_gem_identify_profile as prior
ROOT,util,FROZEN=prior.ROOT,prior.util,prior.FROZEN
FIELDS=prior.FIELDS
PROFILE='rp1-held-device-clocks-gem-mid-known-fields-v2'
header,transport,decode_header,decode_core,ADAPTER,diagnostic_calls=(getattr(prior,n) for n in
    ('header','transport','decode_header','decode_core','ADAPTER','diagnostic_calls'))


def gem_core(text):
    return util.once(text,'    if(!v || !(v[0]&(1u<<11))',
        '''    /* Only CS LOCK and REFDIV are defined by the pinned primary source.
     * Reject unknown modes (including a possible bypass bit) instead of
     * interpreting a locked-but-unknown configuration as measured200MHz.
     * PWR admits only its six explicitly defined power-control bits. */
    if(!v || (v[3]&~UINT32_C(0x8000003f)) || (v[4]&~UINT32_C(0x3f)) || !(v[0]&(1u<<11))''')


def emit(folder):
    sources=prior.emit(folder)
    path=folder/'rp1_gem_identify.c';path.write_text(gem_core(path.read_text()))
    return sources
