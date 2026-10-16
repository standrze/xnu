# SPDX-License-Identifier: BSD-2-Clause
"""Explicit Pi export policy. No linked-symbol intersection is permitted.

Initial policy covers disabled filesystem compression and Skywalk. Other feature
families remain unresolved; this is not yet wired into kernel packaging.
"""
import re
import shlex
import argparse
from pathlib import Path
import sys


def generated_features(config_text, ecc_header):
    """Read the generated doconf flag assignment and its ECC option header.

    No make evaluation or shell execution. Undefined option macros in this
    complete CONFIG_DEFINES assignment are false, as in C preprocessing.
    ECC is generated separately as an OPTIONS header, so it is required too.
    """
    assignments = [line.split("=", 1)[1] for line in config_text.splitlines()
                   if line.startswith("export CONFIG_DEFINES =")]
    if len(assignments) != 1:
        raise ValueError("Expected exactly one generated CONFIG_DEFINES assignment")
    defines = {}
    for token in shlex.split(assignments[0]):
        if not token.startswith("-D"):
            raise ValueError("Unexpected generated configuration token")
        name, sep, value = token[2:].partition("=")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name) or name in defines:
            raise ValueError("Invalid or duplicate generated definition")
        defines[name] = value if sep else "1"
    def boolean(name):
        value = defines.get(name, "0")
        if value not in ("0", "1"):
            raise ValueError(f"Non-boolean feature {name}")
        return value == "1"
    if not boolean("CONFIG_RPI5_BRINGUP") or not boolean("DEVELOPMENT"):
        raise ValueError("Expected Pi DEVELOPMENT configuration")
    matches = re.findall(r"^#define CONFIG_ECC_LOGGING ([01])\s*$", ecc_header, re.M)
    if len(matches) != 1:
        raise ValueError("Expected one explicit ECC option value")
    if "CONFIG_ECC_LOGGING" in defines and boolean("CONFIG_ECC_LOGGING") != (matches[0] == "1"):
        raise ValueError("Conflicting ECC configuration")
    features = {name: boolean(name) for name in (
        "FS_COMPRESSION", "SKYWALK", "CONFIG_MACH_BRIDGE_RECV_TIME", "CONFIG_SYSDIAGNOSE")}
    features["CONFIG_ECC_LOGGING"] = matches[0] == "1"
    return features

COMPRESSION_EXPORTS = frozenset("""
_register_decmpfs_decompressor
_unregister_decmpfs_decompressor
_decmpfs_cnode_destroy
_decmpfs_cnode_get_vnode_cached_size
_decmpfs_cnode_get_vnode_cached_nchildren
_decmpfs_cnode_get_vnode_cached_total_size
_decmpfs_cnode_get_vnode_state
_decmpfs_cnode_init
_decmpfs_cnode_alloc
_decmpfs_cnode_free
_decmpfs_cnode_set_vnode_cached_size
_decmpfs_cnode_set_vnode_cached_nchildren
_decmpfs_cnode_set_vnode_cached_total_size
_decmpfs_cnode_set_vnode_state
_decmpfs_cnode_cmp_type
_decmpfs_ctx
_decmpfs_decompress_file
_decmpfs_file_is_compressed
_decmpfs_hides_rsrc
_decmpfs_hides_xattr
_decmpfs_init
_decmpfs_lock_compressed_data
_decmpfs_pagein_compressed
_decmpfs_read_compressed
_decmpfs_unlock_compressed_data
_decmpfs_update_attributes
_decmpfs_validate_compressed_file
""".split())

SKYWALK_EXPORTS = frozenset({
    "_kern_packet_set_ulpn_flag", "_nxioctl_kernel",
    "_pktap_input_packet", "_pktap_output_packet",
})

# Matches the BCM2712 exclusion of kern_trustcache.c and its private API header.
# PMAP trust lookups continue to fail closed; no service success is fabricated.
PI_UNAVAILABLE_TRUST_EXPORTS = frozenset({
    "_check_trust_cache_runtime_for_uuid", "_unload_trust_cache",
    "_load_trust_cache", "_load_trust_cache_with_type", "_load_legacy_trust_cache",
    "_query_trust_cache", "_query_trust_cache_for_rem", "_static_trust_cache_capabilities",
})

# The selected osfmk/arm/pmap/pmap_iommu.c contains only a placeholder.
# These private extension interfaces have no downstream Pi implementation.
PI_UNAVAILABLE_IOMMU_EXPORTS = frozenset("""
_pmap_iommu_init
_pmap_iommu_iovmalloc
_pmap_iommu_map
_pmap_iommu_unmap
_pmap_iommu_iovmfree
_pmap_iommu_ioctl
_pmap_iommu_alloc_contiguous_pages
_pmap_acquire_iommu_scratch_area
_pmap_alloc_iommu_page
_pmap_free_iommu_page
_pmap_create_aligned_buffer
_pmap_destroy_aligned_buffer
_pmap_ref_iommu_table
_pmap_register_iommu_mapping
_pmap_release_iommu_scratch_area
_pmap_unregister_iommu_mapping
""".split())

# Apple device/monitor extensions are not part of the BCM2712 hardware ABI.
# Keep exact names so upstream additions cannot be silently excluded.
PI_APPLE_DEVICE_EXPORTS = frozenset("""
_nvme_ppl_get_desc
_sart_get_desc
_t8020dart_get_desc
_t8020dart_vo_tte
_t6000dart_get_desc
_t6000dart_vo_tte
_t8110dart_get_desc
_t8110dart_max_translation_levels
_t8110dart_vo_tte
_t8110dart_vo_tt_index
_sptm_gen3dart_init
_sptm_gen3dart_map_table
_sptm_gen3dart_unmap_table
_sptm_gen3dart_map
_sptm_gen3dart_unmap
_sptm_gen3dart_powerdown
_sptm_gen3dart_powerup
_sptm_gen3dart_disable_translation
_sptm_gen3dart_enable_translation
_sptm_gen3dart_clear_err
_sptm_gen3dart_clear_perf_interrupts
_sptm_gen3dart_clear_all_interrupts
_sptm_gen3dart_disable_all_interrupts
_sptm_gen3dart_clear_exception
_sptm_gen3dart_query_tlb
_sptm_gen3dart_set_smmu_window
_sptm_gen3dart_read_smmu_stt_index
_sptm_gen3dart_clamp_tlimits
_sptm_gen3dart_test_translation
_uat_get_desc
""".split())

# No IOUnifiedAddressTranslator definition is published in this checkout.
# Do not promise its C++ class ABI to downstream Pi extensions.
PI_UNAVAILABLE_UAT_EXPORTS = frozenset("""
__ZN26IOUnifiedAddressTranslator10gMetaClassE
__ZN26IOUnifiedAddressTranslator10superClassE
__ZN26IOUnifiedAddressTranslator17getPageTableEntryEy
__ZN26IOUnifiedAddressTranslator18setClientContextIDEjb
__ZN26IOUnifiedAddressTranslator21removeClientContextIDEv
__ZN26IOUnifiedAddressTranslator19isPageFaultExpectedEyj
__ZN26IOUnifiedAddressTranslator7getModeEv
__ZN26IOUnifiedAddressTranslator29getFirmwareAddressSpaceHandleEv
__ZN26IOUnifiedAddressTranslator22registerTaskForServiceEP4taskP9IOService
__ZN26IOUnifiedAddressTranslator23createMappingInApertureEjP18IOMemoryDescriptorjym
__ZN26IOUnifiedAddressTranslator23getTotalPageTableMemoryEv
__ZN26IOUnifiedAddressTranslator3mapEP11IOMemoryMapj
__ZN26IOUnifiedAddressTranslator5doMapEP18IOMemoryDescriptoryyj
__ZN26IOUnifiedAddressTranslator5unmapEP11IOMemoryMap
__ZN26IOUnifiedAddressTranslator7doUnmapEP18IOMemoryDescriptoryy
__ZN26IOUnifiedAddressTranslator8taskDiedEv
__ZN26IOUnifiedAddressTranslator12commitUnmapsEv
__ZN26IOUnifiedAddressTranslator14prepareFWUnmapEyy
__ZTV26IOUnifiedAddressTranslator
""".split())

# Each tuple identifies the export file and exact provider-dependent APIs.
DIAGNOSTIC_EXPORTS = {
    "CONFIG_ECC_LOGGING": ("Private.arm64.exports", frozenset({
        "_ecc_log_memory_error", "_ecc_log_memory_error_ce",
        "_ecc_log_memory_error_delayed", "_ecc_log_record_event",
        "_kern_ecc_poll_register",
    })),
    "CONFIG_MACH_BRIDGE_RECV_TIME": ("Private.arm64.exports", frozenset({
        "_mach_bridge_recv_timestamps", "_mach_bridge_init_timestamp",
        "_mach_bridge_set_params",
    })),
    "CONFIG_SYSDIAGNOSE": ("Private.exports", frozenset({
        "_sysdiagnose_notify_user",
    })),
}


def diagnostic_policy(text, *, filename, board, development, features):
    """Missing feature values are errors, never implicitly disabled providers."""
    if board != "BCM2712":
        return text
    if not development:
        raise ValueError("Pi export policy requires DEVELOPMENT")
    for feature, (source, exports) in DIAGNOSTIC_EXPORTS.items():
        if filename != source:
            continue
        if feature not in features or type(features[feature]) is not bool:
            raise ValueError(f"Explicit boolean required for {feature}")
        if not features[feature]:
            text = exclude_exact(text, exports)
    return text


def compression_policy(text, *, board, development, fs_compression):
    """Transform Private.exports only, preserving all unrelated lines verbatim.

    Caller must obtain feature values from generated config, not SDK identity.
    Reject stale/duplicate exclusions so upstream changes require review.
    """
    if board != "BCM2712":
        return text
    if not development:
        raise ValueError("Pi export policy requires DEVELOPMENT")
    if fs_compression:
        return text
    return exclude_exact(text, COMPRESSION_EXPORTS)


def skywalk_policy(text, *, board, development, skywalk):
    """Packet APIs require Skywalk; mbuf-based networking APIs are preserved."""
    if board != "BCM2712":
        return text
    if not development:
        raise ValueError("Pi export policy requires DEVELOPMENT")
    if skywalk:
        return text
    return exclude_exact(text, SKYWALK_EXPORTS)


def exclude_exact(text, exclusions):
    """Apply a reviewed set, rejecting upstream removals or duplicate entries."""
    seen = set()
    kept = []
    for line in text.splitlines(keepends=True):
        entry = line.split("#", 1)[0].strip()
        if entry in exclusions:
            if entry in seen:
                raise ValueError(f"Duplicate policy export: {entry}")
            seen.add(entry)
        else:
            kept.append(line)
    missing = exclusions - seen
    if missing:
        raise ValueError(f"Stale export policy entries: {sorted(missing)}")
    return "".join(kept)


def apply_reviewed_policy(text, *, filename, config_text, ecc_header):
    """Single entry point for currently reviewed Pi Private export policies.

    This does not claim completeness: unreviewed exports remain and must still
    pass kextsymboltool. Input comes from doconf, not the linked symbol set.
    """
    if filename not in ("Private.exports", "Private.arm64.exports"):
        raise ValueError(f"No reviewed policy for {filename}")
    features = generated_features(config_text, ecc_header)
    if filename == "Private.exports":
        text = compression_policy(text, board="BCM2712", development=True,
                                  fs_compression=features["FS_COMPRESSION"])
        text = skywalk_policy(text, board="BCM2712", development=True,
                              skywalk=features["SKYWALK"])
        text = exclude_exact(text, PI_UNAVAILABLE_TRUST_EXPORTS)
    else:
        text = exclude_exact(text, PI_UNAVAILABLE_IOMMU_EXPORTS)
        text = exclude_exact(text, PI_APPLE_DEVICE_EXPORTS)
        text = exclude_exact(text, PI_UNAVAILABLE_UAT_EXPORTS)
    return diagnostic_policy(text, filename=filename, board="BCM2712",
                             development=True, features=features)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--ecc-header", type=Path, required=True)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    sys.stdout.write(apply_reviewed_policy(
        args.source.read_text(), filename=args.source.name,
        config_text=args.config.read_text(), ecc_header=args.ecc_header.read_text()))
