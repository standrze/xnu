# SPDX-License-Identifier: BSD-2-Clause
"""Distinct diagnostic guard composition, not a larger lease or cached proof.

The actual firmware owner's CHECK does IRQ-check -> SMC -> IRQ-check; each
IRQ-check does PM-check -> actual IRQ core -> PM-check. Those immutable owners
therefore freshly cover PM and IRQ both before and after each SMC. The two
CHECKs surrounding the independently bounded lifecycle callback already cover
the transport's outer PM and IRQ checks, without moving any MMIO guard site.
"""
from tools.rpi5 import rp1_bars_root_profile as previous
ROOT=previous.ROOT
FROZEN=ROOT/'build/rpi5/pcie-owner-trace-kernel-20261013-v1/overlay'
PROFILE='pcie-fresh-nested-guard-composition-v1'
FIELDS='AVAILABLE=%u STAGE=%u RC=%d STATE=%u SEQ=%u FREQ=%llu LAST=%llu DEADLINE=%llu'


def guard_source(text):
    # Exact substitutions ensure this proof never silently applies to a
    # different transport or to owners with weaker semantics.
    text=previous.once(text,
        '!ownerProvider || !ownerProvider->isOpen(this) || !pe_rpi5_watchdog_check_pcie(this))TRACE_FAIL(1);',
        '!ownerProvider || !ownerProvider->isOpen(this) ||\n'
        '        (!controllerMode && !pe_rpi5_watchdog_check_pcie(this)))TRACE_FAIL(1);')
    text=previous.once(text,'        struct rpi5_pcie_irq_observation irq;\n','')
    text=previous.once(text,'        if(!pe_rpi5_pcie_irq_check(this,&irq))TRACE_FAIL(3);\n','')
    text=previous.once(text,'        if(!pe_rpi5_pcie_irq_check(this,&irq))TRACE_FAIL(8);\n','')
    text=previous.once(text,'        if(!pe_rpi5_watchdog_check_pcie(this))TRACE_FAIL(9);\n','')
    text=previous.once(text,'        if(!pe_rpi5_pcie_fw_check(this,&fw))TRACE_FAIL(4);',
        '''        /* Current, uncached firmware CHECK includes fresh PM/IRQ
         * guards on both sides of its SMC. Retain two whole CHECKs around
         * this callback, and every transport MMIO pre/post guard call. */
        if(!pe_rpi5_pcie_fw_check(this,&fw))TRACE_FAIL(4);''')
    return text


def unchanged_contract():
    return dict(mmio_guard_sites_unchanged=True,firmware_checks_per_full_guard=2,
        guard_site_scope='Transport callbacks only; provider register reads retain individual owner checks and whole lifecycle callback firmware bracketing',
        irq_checks_per_full_guard=4,pm_checks_per_full_guard=8,
        prior_irq_checks_per_full_guard=6,prior_pm_checks_per_full_guard=14,
        claim_setup_pm_checks=12,cumulative_pm_limit=65536,cumulative_fw_limit=65536,
        deadline_seconds=[9,10,12,15],cached_authority=False,
        firmware_owner_and_client_unchanged=True,irq_owner_and_core_unchanged=True,
        watchdog_owner_and_core_unchanged=True,secure_firmware_unchanged=True,
        mmio_permissions_unchanged=True,physical_success_proven=False)


def emit(folder):
    folder.mkdir(exist_ok=False)
    for path in FROZEN.iterdir():
        if path.is_file():(folder/path.name).write_bytes(path.read_bytes())
    source=folder/'BCM2712PCIeFWTransport.inc'
    source.write_text(guard_source(source.read_text()))
    return (folder/'BCM2712PCIePHYTransport.cpp',)
