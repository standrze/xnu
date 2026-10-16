/* SPDX-License-Identifier: BSD-2-Clause */
bool BCM2712GEMDMARings::route(const struct rpi5_pcie_window_plan *plan,
    struct rpi5_gem_dma_route *out) const
{
    if (!resolved_ || resolved_!=rpi5_boot_reservation_record() ||
        rpi5_reservation_kernel_buffer(resolved_,physical_,AllocationBytes)) return false;
    /* Every original dynamic request was bound one-to-one at kernel boot and
     * again against this private FDT's semantic reservation plan. Their actual
     * resolved extents remain excluded above. This is not a blanket removal
     * of an unresolved alloc-ranges window: missing kernel record is fatal.
     * Reuse all original full-span preferred PCIe/RP1 route/encoding checks. */
    struct rpi5_reservation_plan fixed=reservations_;
    fixed.count=0;
    return !rpi5_gem_dma_route(&binding_,plan,&ram_,&fixed,
        hasInitrd_ ? &initrd_ : nullptr,physical_,AllocationBytes,out);
}
