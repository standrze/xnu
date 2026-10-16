# SPDX-License-Identifier: BSD-2-Clause
"""Unchanged bounded command protocol with explicit emitted FDT admission."""
import root96_trial_core as original
from root96_trial_core import (t,prior,identity,BEGIN,PASS,IDENTITY,SMOKE,BUFFER,CHECKS,
    exact_lines,pending_safe,drain_pending,bounded_exchange,commands,returned)

DEVICE=b'RPI5XNU:BL33:PCIE_DEVICE_HANDOFF RANGES=3 PAGES=5 DECLARATIONS_ONLY PCIE_MMIO=0 IRQ=0 DMA=0'
FDT=b'RPI5XNU:BL33:FIRMWARE_FDT RETAINED_DESCRIPTOR_ONLY NO_RAW_TREE_OR_SEED_PUBLISHED PCIE_MMIO=0'


def boot_ready(raw,report):
    if not original.boot_ready(raw,report):return False
    data=t.normalized(raw)
    markers=(t.TERMINAL_LOADER,DEVICE,FDT,report['root_copy_marker'].encode())
    if any(data.count(marker)!=1 for marker in markers):raise RuntimeError('Exact emitted Device/FDT handoff absent; zero TX')
    positions=[data.index(marker) for marker in markers]
    if positions!=sorted(positions):raise RuntimeError('Emitted handoff order differs; zero TX')
    if not all(report['handoff'].get(key) is True for key in
        ('required_by_kernel','linked_loader_handoff','descriptor_not_confused_with_kernel_string')):
        raise RuntimeError('Linked kernel/loader handoff contract absent; zero TX')
    return True
