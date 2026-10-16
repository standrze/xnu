# SPDX-License-Identifier: BSD-2-Clause
"""Six bounded GPIO32 records from retained memory only."""
import json
from tools.rpi5 import rp1_phy_gpio_observe_profile as core
ROOT,FROZEN=core.ROOT,core.FROZEN
FIELDS=json.loads((FROZEN.parent/'manifest.json').read_text())['link_trace_fields']
def records():
    return r'''    const auto *gpio=transport?transport->tracePHYGPIO():nullptr;
    kprintf("RPI5XNU:PCIEID:GPIO STATE=%u RC=%d READS=%u MAPPED=%x UNMAPPED=%x INDEX=%u\n",
        gpio?gpio->state:0,gpio?gpio->error:0,gpio?gpio->reads:0,gpio?gpio->mapped:0,gpio?gpio->unmapped:0,gpio?gpio->index:0);
    kprintf("RPI5XNU:PCIEID:GPIO_PROGRESS PASS=%u WORD=%u PENDING=%u\n",
        gpio?gpio->pass:0,gpio?gpio->word:0,gpio?gpio->pending:0);
    kprintf("RPI5XNU:PCIEID:GPIO0_CTRL STATUS=%08x CTRL=%08x PAD=%08x\n",
        gpio?gpio->raw[0][0]:0,gpio?gpio->raw[0][1]:0,gpio?gpio->raw[0][5]:0);
    kprintf("RPI5XNU:PCIEID:GPIO0_RIO OUT=%08x OE=%08x IN=%08x\n",
        gpio?gpio->raw[0][2]:0,gpio?gpio->raw[0][3]:0,gpio?gpio->raw[0][4]:0);
    kprintf("RPI5XNU:PCIEID:GPIO1_CTRL STATUS=%08x CTRL=%08x PAD=%08x\n",
        gpio?gpio->raw[1][0]:0,gpio?gpio->raw[1][1]:0,gpio?gpio->raw[1][5]:0);
    kprintf("RPI5XNU:PCIEID:GPIO1_RIO OUT=%08x OE=%08x IN=%08x\n",
        gpio?gpio->raw[1][2]:0,gpio?gpio->raw[1][3]:0,gpio?gpio->raw[1][4]:0);
'''
def emit(folder):
    sources=core.emit(folder);header=folder/'BCM2712PCIePHYTransport.h'
    header.write_text(core.util.once(header.read_text(),
        '    const struct rpi5_gem_cap_session *traceCapabilities() const { return &capabilitySession; }',
        '    const struct rpi5_gem_cap_session *traceCapabilities() const { return &capabilitySession; }\n'
        '    const struct rpi5_phy_gpio_session *tracePHYGPIO() const { return &phyGPIO; }'))
    progress=folder/'BCM2712PCIeIDTrialProgress.inc';needle='    kprintf("RPI5XNU:PCIEID:END '
    progress.write_text(core.util.once(progress.read_text(),needle,records()+needle));return sources
