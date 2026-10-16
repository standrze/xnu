# SPDX-License-Identifier: BSD-2-Clause
"""Narrow selected-source admission; no measured frequency or gate-state claim.

Pinned clk-rp1.c get_parent uses nonzero SEL, not CTRL.ENABLE, as the live
parent selector. SYS declares standard parent2=PLL_SYS and SRC mask3. Its
generic is_on still tests ENABLE11; public RP1 docs do not publish per-bit SYS
semantics. Consequently this correction accepts only CTRL exactly2 or0x802
with the existing SEL4/lockedPLL/rational-rate checks, and does not assert that
bit11 is RES0 or the clock is universally always-on. ETH/TSU are unchanged.
"""
from tools.rpi5 import pcie_root_forward_profile as prior
ROOT,util=prior.ROOT,prior.util
FROZEN=ROOT/'build/rpi5/pcie-root-forward-kernel-20261013-v1/overlay'
PROFILE='rp1-observed-sys-selected-source-profile-v1'
FIELDS=prior.FIELDS


def gem_core(text):
    text=util.once(text,' || !(v[0]&(1u<<11)) || (v[0]&3)!=2 || v[2]!=4 ||',
        ' || (v[0]!=2 && v[0]!=0x802) || v[2]!=4 ||')
    return util.once(text,'    /* Only CS LOCK and REFDIV',
        '''    /* Selected-source register-profile admission, not measured clock
     * frequency or independent gate-state proof. Pinned RP1 get_parent uses
     * live one-hot SEL; SYS parent2 is PLL_SYS. Accept only the exact normal
     * CTRL2 seen on this board or the prior ENABLE11 form0x802, with SEL4.
     * Unknown SYS controls (including all other modes) are rejected. The
     * generic Linux is_on tests bit11, so no RES0/always-on claim is made.
     * ETH/TSU, PLL, rate arithmetic, repeated reads and guards are unchanged.
     */
    /* Only CS LOCK and REFDIV''')


def emit(folder):
    folder.mkdir(exist_ok=False)
    for path in FROZEN.iterdir():
        if path.is_file():(folder/path.name).write_bytes(path.read_bytes())
    core=folder/'rp1_gem_identify.c';core.write_text(gem_core(core.read_text()))
    return (core,)
