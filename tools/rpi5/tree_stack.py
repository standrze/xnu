# SPDX-License-Identifier: BSD-2-Clause
"""Reviewed C call-chain sums; not a whole-program stack proof."""
def check_gate4_binding(frames, stack_bytes=0x4000):
    def size(unit, function):
        matches = [r['bytes'] for r in frames if
                   r['location'].split(':')[0] == 'loader/rpi5/' + unit + '.c'
                   and r['location'].split(':')[-1] == function]
        if len(matches) != 1:
            raise ValueError('missing or ambiguous Gate 4 frame: ' + function)
        return matches[0]
    outer = sum(size('probe_main', f) for f in
                ('probe_el1_main', 'runtime_cpus', 'board_tree_diagnostic'))
    outer += size('fdt_reg', 'rpi5_fdt_sdhci')
    framing = size('fdt', 'rpi5_fdt_structure') + size('fdt', 'rpi5_fdt_layout')
    prop = size('fdt', 'rpi5_fdt_property') + framing
    # These alternatives are sequential, not recursive. width/enabled helpers
    # call property; translation retains its own local bus/range scratch.
    paths = {
        'sd_phandles': outer + size('fdt', 'rpi5_fdt_phandles') + framing,
        'sd_translation': outer + size('fdt_reg', 'rpi5_fdt_reg') + prop + max(
            size('fdt_reg', 'width'), size('fdt_reg', 'enabled')),
        'sd_properties': outer + prop + max(size('fdt_reg', 'compatible'),
            size('fdt_reg', 'enabled'), size('fdt_reg', 'u32_property')),
    }
    # Power binding calls the SD binding first; afterwards its own GPIO/pad
    # translations and exact-property helpers are sequential alternatives.
    power_outer = outer - size('fdt_reg', 'rpi5_fdt_sdhci') + size('fdt_reg', 'rpi5_fdt_sd_power')
    paths.update({
        'sd_power_binding': max(paths.values()) + size('fdt_reg', 'rpi5_fdt_sd_power'),
        'sd_power_translation': power_outer + size('fdt_reg', 'rpi5_fdt_reg') + prop + max(
            size('fdt_reg', 'width'), size('fdt_reg', 'enabled')),
        'sd_power_properties': power_outer + prop + max(size('fdt_reg', 'compatible'),
            size('fdt_reg', 'enabled'), size('fdt_reg', 'u32_property'),
            size('fdt_reg', 'exact_property'), size('fdt_reg', 'exact_cells')),
    })
    if max(paths.values()) + 512 >= stack_bytes:
        raise ValueError('Gate 4 binding exhausts early stack headroom')
    return {'paths_bytes': paths, 'reserved_headroom_bytes': 512,
            'minimum_remaining_bytes': stack_bytes - max(paths.values()),
            'scope': 'Listed nonrecursive FDT binding paths; no SD protocol or hardware proof'}

def check_runtime_plan(frames, max_depth, stack_bytes=0x4000):
    def size(unit, function):
        matches=[r['bytes'] for r in frames if
                 r['location'].split(':')[0]=='loader/rpi5/'+unit+'.c' and
                 r['location'].split(':')[-1]==function]
        if len(matches)!=1:
            raise ValueError(f'missing or ambiguous planner frame: {unit}:{function}')
        return matches[0]
    if not 0 <= max_depth <= 64:
        raise ValueError('unreviewed Apple tree depth')
    outer=sum(size('probe_main',f) for f in
              ('probe_el1_main','runtime_cpus','board_tree_diagnostic'))
    resolved=outer+size('tree_handoff','rpi5_resolved_tree_handoff')
    tree=resolved+size('tree_handoff','rpi5_tree_handoff_plan')
    handoff=tree+size('handoff','rpi5_handoff_plan')
    placement=size('macho','rpi5_macho_placement')+size('macho','rpi5_macho_segments')+size('macho','rpi5_macho_commands')+size('macho','same_name')
    recursive=(max_depth+1)*size('apple_dt','node')+size('apple_dt','property')
    # Seed publication now occurs after runtime_cpus has returned and the
    # secondary/primary interrupt tests have completed.
    seed_outer=size('probe_main','probe_el1_main')
    paths={
        'kernel_placement':handoff+placement,
        'physical_copy_placement':outer+size('macho','rpi5_macho_materialize')+placement,
        'physical_copy_relocations':outer+size('macho','rpi5_macho_materialize')+
            size('macho','rpi5_macho_relocations')+max(size('macho','rpi5_macho_symbols'),
                size('macho','rpi5_macho_segments')+size('macho','same_name'))+
            size('macho','rpi5_macho_commands'),
        'physical_readback':outer+size('macho','rpi5_macho_verify_materialized')+placement,
        'seeded_length':tree+size('seed_tree','rpi5_seed_tree_measure')+size('apple_dt','rpi5_adt_measure')+recursive,
        'boot_arguments':handoff+size('boot_args','rpi5_boot_args_encode'),
        'bootstrap':handoff+size('bootstrap','rpi5_bootstrap_mapping'),
        'live_ranges':handoff+size('ranges','rpi5_ranges_validate_live'),
        'memory_types':resolved+size('memory_type','rpi5_memory_type_for')+size('memory_type','rpi5_memory_types_validate'),
        'memory_map_encoding':outer+size('board_tree','rpi5_board_tree_memory_map')+
            size('memory_type','rpi5_memory_types_encode')+size('memory_type','rpi5_memory_types_validate'),
        'unseeded_encode':outer+size('apple_dt','rpi5_adt_encode')+recursive,
        'firmware_seed_encode':seed_outer+size('probe_main','firmware_seed_diagnostic')+
            size('firmware_seed_tree','rpi5_firmware_seed_tree')+size('apple_dt','rpi5_adt_encode')+recursive,
        'boot_data_publication':seed_outer+size('probe_main','firmware_seed_diagnostic')+
            size('boot_data','rpi5_boot_data_commit')+size('boot_data','rpi5_boot_data_publish'),
        'firmware_seed_measure':seed_outer+size('probe_main','firmware_seed_diagnostic')+
            size('firmware_seed_tree','rpi5_firmware_seed_tree')+size('seed_tree','rpi5_seed_tree_measure')+
            size('apple_dt','rpi5_adt_measure')+recursive,
    }
    # Leave explicit headroom beyond listed C frames. Fault reporting uses
    # separate stacks; this is not a proof of the entire probe's call graph.
    if max(paths.values())+512>=stack_bytes:
        raise ValueError('runtime planner exhausts early stack headroom')
    return {'paths_bytes':paths,'reserved_headroom_bytes':512,
            'minimum_remaining_bytes':stack_bytes-max(paths.values()),
            'scope':'Reviewed runtime planner C paths; no physical transfer or seed collection'}

def check(frames, max_depth, stack_bytes=0x4000):
    def size(unit, function):
        matching=[x['bytes'] for x in frames
                  if x['location'].split(':')[0] == 'loader/rpi5/'+unit+'.c'
                  and x['location'].split(':')[-1] == function]
        if len(matching)!=1:
            raise ValueError(f'missing or ambiguous stack frame: {unit}:{function}')
        return matching[0]
    if not 0 <= max_depth <= 64:
        raise ValueError('unreviewed Apple tree depth')
    recursive=(max_depth+1)*size('apple_dt','node')+size('apple_dt','property')
    outer=size('seed_tree','rpi5_seed_tree_encode')
    paths={
        'seed_encode_measure':outer+size('seed_tree','rpi5_seed_tree_measure')+
            size('apple_dt','rpi5_adt_measure')+recursive,
        'seed_encode_write':outer+size('apple_dt','rpi5_adt_encode')+recursive,
        'seed_collect_excluding_provider':outer+size('boot_seed','rpi5_boot_seed_collect'),
    }
    if max(paths.values())>=stack_bytes:
        raise ValueError('reviewed seed/tree C chain exhausts early stack')
    return {'paths_bytes':paths,'stack_bytes':stack_bytes,
            'minimum_remaining_bytes':stack_bytes-max(paths.values()),
            'scope':'Listed C chains only; caller, provider callbacks, exception frames and hardware execution not covered'}
