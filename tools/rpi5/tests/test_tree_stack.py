# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tree_stack import check, check_runtime_plan, check_gate4_binding


class TreeStackTests(unittest.TestCase):
    def test_gate4_binding_budget_requires_complete_frames(self):
        functions = {
            'probe_main': ['probe_el1_main', 'runtime_cpus', 'board_tree_diagnostic'],
            'fdt': ['rpi5_fdt_structure', 'rpi5_fdt_layout', 'rpi5_fdt_property', 'rpi5_fdt_phandles'],
            'fdt_reg': ['rpi5_fdt_sdhci', 'rpi5_fdt_sd_power', 'rpi5_fdt_reg', 'width', 'enabled',
                        'compatible', 'u32_property', 'exact_property', 'exact_cells'],
        }
        frames = [{'location': f'loader/rpi5/{u}.c:1:{f}', 'bytes': 16}
                  for u, names in functions.items() for f in names]
        result = check_gate4_binding(frames)
        self.assertEqual(result['paths_bytes']['sd_translation'], 144)
        self.assertEqual(result['paths_bytes']['sd_phandles'], 112)
        self.assertEqual(result['paths_bytes']['sd_power_binding'], 160)
        for missing in range(len(frames)):
            with self.assertRaises(ValueError):
                check_gate4_binding(frames[:missing] + frames[missing+1:])
        with self.assertRaises(ValueError):
            check_gate4_binding(frames + [frames[0]])
        with self.assertRaises(ValueError):
            check_gate4_binding(frames, 144 + 512)

    def test_runtime_planner_budget(self):
        functions={
            'probe_main':['probe_el1_main','runtime_cpus','board_tree_diagnostic','firmware_seed_diagnostic'],
            'firmware_seed_tree':['rpi5_firmware_seed_tree'],
            'boot_data':['rpi5_boot_data_publish','rpi5_boot_data_commit'],
            'tree_handoff':['rpi5_resolved_tree_handoff','rpi5_tree_handoff_plan'],
            'handoff':['rpi5_handoff_plan'],
            'macho':['rpi5_macho_placement','rpi5_macho_segments','rpi5_macho_commands','same_name',
                     'rpi5_macho_materialize','rpi5_macho_relocations','rpi5_macho_symbols',
                     'rpi5_macho_verify_materialized'],
            'apple_dt':['node','property','rpi5_adt_measure','rpi5_adt_encode'],
            'seed_tree':['rpi5_seed_tree_measure'],
            'boot_args':['rpi5_boot_args_encode'],
            'bootstrap':['rpi5_bootstrap_mapping'],
            'ranges':['rpi5_ranges_validate_live'],
            'memory_type':['rpi5_memory_type_for','rpi5_memory_types_validate','rpi5_memory_types_encode'],
            'board_tree':['rpi5_board_tree_memory_map'],
        }
        frames=[{'location':f'loader/rpi5/{u}.c:1:{f}','bytes':16}
                for u, fs in functions.items() for f in fs]
        result=check_runtime_plan(frames,64)
        self.assertEqual(result['paths_bytes']['kernel_placement'],160)
        self.assertEqual(result['paths_bytes']['seeded_length'],1168)
        for missing in range(len(frames)):
            with self.assertRaises(ValueError):
                check_runtime_plan(frames[:missing]+frames[missing+1:],64)
        with self.assertRaises(ValueError): check_runtime_plan(frames+[frames[0]],64)
        with self.assertRaises(ValueError): check_runtime_plan(frames,65)
        with self.assertRaises(ValueError): check_runtime_plan(frames,64,1680)
        frames[0]['bytes']=16384
        with self.assertRaises(ValueError): check_runtime_plan(frames,64)

    def test_chain_budget_and_missing_evidence(self):
        data=[('seed_tree','rpi5_seed_tree_encode',4512),
              ('seed_tree','rpi5_seed_tree_measure',48),
              ('apple_dt','rpi5_adt_measure',608),('apple_dt','node',64),
              ('apple_dt','property',0),('apple_dt','rpi5_adt_encode',624),
              ('boot_seed','rpi5_boot_seed_collect',384)]
        frames=[{'location':f'loader/rpi5/{u}.c:1:{f}','bytes':b} for u,f,b in data]
        result=check(frames,64)
        self.assertEqual(result['paths_bytes']['seed_encode_measure'],9328)
        self.assertEqual(result['minimum_remaining_bytes'],7056)
        for bad in (frames[:-1],frames+[frames[0]]):
            with self.assertRaises(ValueError): check(bad,64)
        with self.assertRaises(ValueError): check(frames,65)
        with self.assertRaises(ValueError): check(frames,64,9328)
        frames[3]['bytes']=200
        with self.assertRaises(ValueError): check(frames,64)
