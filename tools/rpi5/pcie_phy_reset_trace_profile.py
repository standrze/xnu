# SPDX-License-Identifier: BSD-2-Clause
"""Bounded passive reset/MDIO rows; no logging-time device access."""
import json
from tools.rpi5 import rp1_phy_reset_transport_profile as core
from tools.rpi5 import pcie_phy_gpio_trace_profile as gpio
from tools.rpi5 import pcie_gem_mdio_trace_profile as mdio
ROOT,FROZEN=core.ROOT,core.FROZEN
FIELDS=json.loads((FROZEN.parent/'manifest.json').read_text())['link_trace_fields']


def records():
    return mdio.records()+r'''    const auto *reset=transport?transport->tracePHYReset():nullptr;
    const auto *hold=transport?transport->tracePHYGPIO():nullptr;
    kprintf("RPI5XNU:PCIEID:PHYRESET STATE=%u RC=%d STEP=%u READS=%u WRITES=%u PENDING=%u\n",
        reset?reset->state:0,reset?reset->error:0,reset?reset->step:0,reset?reset->reads:0,reset?reset->writes:0,reset?reset->pending:0);
    kprintf("RPI5XNU:PCIEID:PHYRESET_MAP STATE=%u RC=%d MAPPED=%x UNMAPPED=%x LINK_CONTROL=%04x\n",
        hold?hold->state:0,hold?hold->error:0,hold?hold->mapped:0,hold?hold->unmapped:0,
        transport?transport->traceResetLinkControl():0);
    kprintf("RPI5XNU:PCIEID:PHYRESET_CTRL BEFORE=%08x AFTER=%08x PAD_BEFORE=%08x PAD_AFTER=%08x\n",
        reset?reset->observed.ctrl_before:0,reset?reset->observed.ctrl_after:0,
        reset?reset->observed.pad_before:0,reset?reset->observed.pad_after:0);
    kprintf("RPI5XNU:PCIEID:PHYRESET_RIO OUT_BEFORE=%08x OUT_AFTER=%08x OE_BEFORE=%08x OE_AFTER=%08x\n",
        reset?reset->observed.out_before:0,reset?reset->observed.out_after:0,
        reset?reset->observed.oe_before:0,reset?reset->observed.oe_after:0);
    kprintf("RPI5XNU:PCIEID:PHYRESET_INPUT LOW=%08x HIGH=%08x PCIE_INTE=%08x\n",
        reset?reset->observed.low_input:0,reset?reset->observed.high_input:0,reset?reset->observed.initial_pcie_inte:0);
    kprintf("RPI5XNU:PCIEID:PHYRESET_TIME START_US=%llu LAST_US=%llu DEADLINE_US=%llu ASSERTED_US=%llu DEASSERTED_US=%llu COMPLETED_US=%llu\n",
        (unsigned long long)(reset?reset->started_us:0),(unsigned long long)(reset?reset->last_us:0),
        (unsigned long long)(reset?reset->deadline_us:0),(unsigned long long)(reset?reset->observed.asserted_us:0),
        (unsigned long long)(reset?reset->observed.deasserted_us:0),(unsigned long long)(reset?reset->observed.completed_us:0));
'''


def emit(folder):
    core.emit(folder)
    header=folder/'BCM2712PCIePHYTransport.h'
    header.write_text(core.util.once(header.read_text(),
        '    const struct rpi5_phy_gpio_session *tracePHYGPIO() const { return &phyGPIO; }',
        '''    const struct rpi5_phy_gpio_session *tracePHYGPIO() const { return &phyGPIO; }
    const struct rpi5_gem_mdio_session *traceMDIO() const { return &mdioSession; }
    const struct rpi5_phy_reset_session *tracePHYReset() const { return &phyReset; }
    uint16_t traceResetLinkControl() const { return phyResetLinkControl; }'''))
    progress=folder/'BCM2712PCIeIDTrialProgress.inc'
    progress.write_text(core.util.once(progress.read_text(),gpio.records(),records()))
    return tuple(folder/name for name in ('BCM2712PCIePHYTransport.cpp','rp1_phy_gpio_observe.c',
        'rp1_gem_mdio.c','rp1_phy_reset_cycle.c'))
