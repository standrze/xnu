# SPDX-License-Identifier: BSD-2-Clause
"""Six bounded passive MDIO records; no diagnostic accesses."""
import json
from tools.rpi5 import rp1_gem_mdio_profile as core
ROOT,FROZEN=core.ROOT,core.FROZEN
FIELDS=json.loads((FROZEN.parent/'manifest.json').read_text())['link_trace_fields']
NAMES=('MDIO','MDIO_IO','MDIO_NCR','MDIO_CFG','MDIO_PHY','MDIO_TIME')


def records():
    return r'''    const auto *mdio=transport?transport->traceMDIO():nullptr;
    kprintf("RPI5XNU:PCIEID:MDIO STATE=%u STAGE=%u RC=%d PHY=%u TRANSFERS=%u\n",
        mdio?mdio->state:0,mdio?mdio->stage:0,mdio?mdio->error:0,mdio?mdio->phy_address:0,mdio?mdio->transfer:0);
    kprintf("RPI5XNU:PCIEID:MDIO_IO READS=%u WRITES=%u POLLS=%u CLOCKS=%u CLK_CHANGED=%u\n",
        mdio?mdio->reads:0,mdio?mdio->writes:0,mdio?mdio->polls:0,mdio?mdio->clocks:0,mdio?mdio->changed_divider:0);
    kprintf("RPI5XNU:PCIEID:MDIO_NCR BEFORE=%08x LIVE=%08x AFTER=%08x\n",
        mdio?mdio->ncr_before:0,mdio?mdio->ncr_live:0,mdio?mdio->ncr_after:0);
    kprintf("RPI5XNU:PCIEID:MDIO_CFG BEFORE=%08x LIVE=%08x AFTER=%08x\n",
        mdio?mdio->ncfgr_before:0,mdio?mdio->ncfgr_live:0,mdio?mdio->ncfgr_after:0);
    kprintf("RPI5XNU:PCIEID:MDIO_PHY ID1=%04x ID2=%04x BMCR=%04x BMSR_FIRST=%04x BMSR_NOW=%04x\n",
        mdio?mdio->raw[0]:0,mdio?mdio->raw[1]:0,mdio?mdio->raw[2]:0,mdio?mdio->raw[3]:0,mdio?mdio->raw[4]:0);
    kprintf("RPI5XNU:PCIEID:MDIO_TIME START_US=%llu LAST_US=%llu DEADLINE_US=%llu\n",
        (unsigned long long)(mdio?mdio->start_us:0),(unsigned long long)(mdio?mdio->last_us:0),
        (unsigned long long)(mdio?mdio->deadline_us:0));
'''


def emit(folder):
    sources=core.emit(folder)
    header=folder/'BCM2712PCIePHYTransport.h'
    header.write_text(core.util.once(header.read_text(),
        '    const struct rpi5_gem_cap_session *traceCapabilities() const { return &capabilitySession; }',
        '    const struct rpi5_gem_cap_session *traceCapabilities() const { return &capabilitySession; }\n'
        '    const struct rpi5_gem_mdio_session *traceMDIO() const { return &mdioSession; }'))
    progress=folder/'BCM2712PCIeIDTrialProgress.inc';needle='    kprintf("RPI5XNU:PCIEID:END '
    progress.write_text(core.util.once(progress.read_text(),needle,records()+needle))
    return sources
