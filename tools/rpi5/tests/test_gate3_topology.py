# SPDX-License-Identifier: BSD-2-Clause
"""Guard the distinct physical-affinity and logical-cluster roles on Pi 5."""

from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]


class Gate3TopologyTests(unittest.TestCase):
    def test_aff1_is_not_published_as_four_cache_domains(self):
        source = (ROOT / "osfmk/arm64/machine_routines.c").read_text()
        pi = source.split("#if defined(ARM64_BOARD_CONFIG_BCM2712)", 2)[1]
        self.assertIn("cpu->cluster_id = 0;", pi)
        self.assertIn("cluster_phys_to_logical[phys_cluster_id] = 0;", pi)
        self.assertIn("cluster_offsets[i] = cur_cluster_offset;", source)
        self.assertIn("cpu->cluster_core_id = (int)ml_readprop(child, \"cluster-core-id\",", source)
        self.assertIn("    cpu->cpu_id);", source)

    def test_reset_lookup_keeps_aff1(self):
        startup = (ROOT / "osfmk/arm64/start.s").read_text()
        self.assertIn("and\t\tx0, x15, #0xFFFF", startup)
        board = (ROOT / "pexpert/pexpert/arm64/BCM2712.h").read_text()
        self.assertIn("#define HAS_CLUSTER", board)
        self.assertIn("#define MAX_CPU_CLUSTER_PHY_ID", board)

    def test_secondary_registration_does_not_implicitly_boot(self):
        source = (ROOT / "osfmk/arm64/machine_routines.c").read_text()
        registration = source.split("ml_processor_register(ml_processor_info_t", 1)[1]
        lifecycle = registration.split("#if !USE_APPLEARMSMP", 1)[1].split(
            "#endif /* !USE_APPLEARMSMP */", 1
        )[0]
        pi = lifecycle.split("#if defined(ARM64_BOARD_CONFIG_BCM2712)", 1)[1].split(
            "#else", 1
        )[0]
        self.assertIn("if (is_boot_cpu) {\n\t\tprocessor_boot(processor);", pi)
        self.assertNotIn("PE_cpu_start_internal", pi)

    def test_secondary_start_publishes_handoff_before_psci(self):
        source = (ROOT / "iokit/Kernel/BCM2712PlatformExpert.cpp").read_text()
        start = source.split("BCM2712CPU::startCPU(vm_offset_t, vm_offset_t)", 1)[1]
        start = start.split("void BCM2712CPU::haltCPU", 1)[0]
        self.assertLess(
            start.index("rpi5_publish_secondary_handoff("),
            start.index("rpi5_psci_cpu_on("),
        )
        self.assertIn("topologyCPU.phys_id, entryPA, resetPA", start)
        self.assertIn("return result == 0 ? KERN_SUCCESS : KERN_FAILURE;", start)

    def test_four_core_trial_requires_explicit_boot_arg_and_exact_topology(self):
        platform = (ROOT / "iokit/Kernel/BCM2712PlatformExpert.cpp").read_text()
        loader = (ROOT / "loader/rpi5/probe_main.c").read_text()
        builder = (ROOT / "tools/rpi5/build_probe.py").read_text()
        self.assertIn('"bcm2712_cpu_on_all"', platform)
        self.assertIn("bootAll && ml_get_topology_info()->num_cpus != 4", platform)
        self.assertIn("bootAll ? 3U : bootCPU1 ? 1U : 0U", platform)
        self.assertIn("#elif RPI5_GATE3_CPU_ON_ALL", loader)
        self.assertIn("bcm2712_cpu_on_all=1", loader)
        self.assertIn('parser.add_argument("--gate3-cpu-on-all"', builder)
        self.assertIn("args.gate3_cpu_on_1, args.gate3_cpu_on_all", builder)

    def test_tlb_trial_is_separate_from_four_core_start(self):
        platform = (ROOT / "iokit/Kernel/BCM2712PlatformExpert.cpp").read_text()
        loader = (ROOT / "loader/rpi5/probe_main.c").read_text()
        builder = (ROOT / "tools/rpi5/build_probe.py").read_text()
        test = (ROOT / "osfmk/arm64/rpi5_tlb_test.c").read_text()
        self.assertIn('"bcm2712_tlb_trial"', platform)
        self.assertIn("if (bootSecondaries == 3)", platform)
        self.assertIn("#elif RPI5_GATE3_TLB_TRIAL", loader)
        self.assertIn("args.gate3_tlb_trial and not args.gate3_cpu_on_all", builder)
        self.assertIn("pmap_remove(kernel_pmap, first, first + PAGE_SIZE)", test)
        self.assertIn("rpi5_tlb_observe(test, round + 1, expected, false)", test)
        self.assertIn("rpi5_tlb_stress_run(first, page_a, page_b, &mapped_page)", test)
        self.assertIn("rpi5_tlb_write_preflight_on_target", test)
        stress = test.split("rpi5_tlb_stress_reader(", 1)[1].split(
            "rpi5_tlb_read_on_target(", 1)[0]
        self.assertIn("mmu_kvtop_wpreflight(stress->address)", stress)
        self.assertIn("pmap_protect(kernel_pmap, address, address + PAGE_SIZE,", stress)
        self.assertIn("STRESS_PERMISSION_ROUNDS=32", test)
        self.assertIn('kprintf("RPI5XNU:TLB:PASS\\n");', test)
        self.assertIn('kprintf("RPI5XNU:TLB:FAIL\\n");', test)
        self.assertIn('RPI5XNU:TLB:TIMING TICKS=%llu FREQ=%llu', test)
        translation = (ROOT / "osfmk/arm64/machine_routines_asm.s").read_text()
        write_probe = translation.split("LEXT(mmu_kvtop_wpreflight)", 1)[1]
        self.assertLess(write_probe.index("at\t\ts1e1w, x0"),
                        write_probe.index("isb\t\tsy"))
        self.assertLess(write_probe.index("isb\t\tsy"),
                        write_probe.index("mrs\t\tx1, PAR_EL1"))

    def test_xnupost_selection_is_opt_in_and_single_test(self):
        loader = (ROOT / "loader/rpi5/probe_main.c").read_text()
        builder = (ROOT / "tools/rpi5/build_probe.py").read_text()
        self.assertIn("#elif RPI5_GATE3_XNUPOST_INDEX > 0", loader)
        self.assertIn("kernPOST=1 kernPOST_config=", loader)
        self.assertIn('"_" RPI5_STRINGIFY(RPI5_GATE3_XNUPOST_INDEX)', loader)
        self.assertIn("kernPOST=4", loader)
        self.assertIn("Gate 3 TLB/user-TLB/concurrency/XNUPOST/soak/qualification modes are mutually exclusive", builder)
        bsd = (ROOT / "bsd/kern/bsd_init.c").read_text()
        self.assertIn('RPI5XNU:XNUPOST:TIMING TICKS=%llu FREQ=%llu', bsd)
        self.assertIn("rpi5_gate3_xnupost_status(void)", bsd)
        self.assertIn("os_atomic_store(&rpi5_xnupost_status, 1, release)", bsd)
        self.assertIn("selected > 0 && selected == passed ? 2 : 3, release", bsd)

    def test_concurrency_trial_requires_four_pinned_workers(self):
        source = (ROOT / "osfmk/arm64/rpi5_concurrency_test.c").read_text()
        loader = (ROOT / "loader/rpi5/probe_main.c").read_text()
        builder = (ROOT / "tools/rpi5/build_probe.py").read_text()
        self.assertIn("thread_bind(cpu_to_processor", source)
        self.assertIn("RPI5_CONCURRENCY_ROUNDS 1000000U", source)
        self.assertIn("latest_start < earliest_end", source)
        self.assertIn("peer_midpoint[cpu]", source)
        self.assertIn("rpi5_shared_count", source)
        self.assertIn('"RPI5XNU:SMP_CONCURRENCY:%s', source)
        self.assertIn('RPI5XNU:SMP_CONCURRENCY:TIMING TICKS=%llu FREQ=%llu', source)
        self.assertIn("bcm2712_concurrency_trial=1", loader)
        self.assertIn("--gate3-concurrency-trial requires --gate3-cpu-on-all", builder)

    def test_terminal_watchdog_uses_periodic_callout_not_idle_cpu_timer(self):
        platform = (ROOT / "iokit/Kernel/BCM2712PlatformExpert.cpp").read_text()
        kernel = (ROOT / "osfmk/arm64/sleh.c").read_text()
        watchdog = (ROOT / "pexpert/arm/pe_fiq.c").read_text()
        self.assertIn('"bcm2712_terminal_watchdog"', platform)
        self.assertIn("rpi5_terminal_watchdog_start()", platform)
        self.assertIn("thread_call_allocate_with_priority(\n\t    rpi5_terminal_watchdog_callout", kernel)
        self.assertIn("thread_call_enter_delayed(rpi5_terminal_watchdog_call, deadline)", kernel)
        self.assertIn("!os_atomic_load(&rpi5_terminal_watchdog_enabled, acquire)", kernel)
        self.assertIn("RPI5_TERMINAL_WDOG_SECONDS 3600U", watchdog)
        self.assertIn("RPI5XNU:TERMINAL:WATCHDOG_KICK RELOADS=%u", watchdog)

    def test_soak_requires_four_cores_and_has_bounded_duration(self):
        platform = (ROOT / "iokit/Kernel/BCM2712PlatformExpert.cpp").read_text()
        loader = (ROOT / "loader/rpi5/probe_main.c").read_text()
        builder = (ROOT / "tools/rpi5/build_probe.py").read_text()
        kernel = (ROOT / "osfmk/arm64/sleh.c").read_text()
        self.assertIn('"bcm2712_soak_seconds"', platform)
        self.assertIn("rpi5_gate3_enable_soak", platform)
        self.assertIn("pe_rpi5_watchdog_enable_soak", kernel)
        self.assertIn("thread_call_enter_delayed(rpi5_gate3_soak_call", kernel)
        self.assertIn("#elif RPI5_GATE3_SOAK_SECONDS > 0", loader)
        self.assertIn("--gate3-soak-seconds requires --gate3-cpu-on-all", builder)
        self.assertIn("args.gate3_soak_seconds <= 28800", builder)

    def test_qualification_serializes_trials_before_arming_soak(self):
        source = (ROOT / "osfmk/arm64/rpi5_gate3_qualification.c").read_text()
        bsd = (ROOT / "bsd/kern/bsd_init.c").read_text()
        loader = (ROOT / "loader/rpi5/probe_main.c").read_text()
        builder = (ROOT / "tools/rpi5/build_probe.py").read_text()
        self.assertLess(source.index("rpi5_gate3_xnupost_status()"),
                        source.index("rpi5_gate3_start_concurrency_test()"))
        self.assertLess(source.index("rpi5_gate3_start_concurrency_test()"),
                        source.index("rpi5_gate3_start_tlb_test()"))
        self.assertLess(source.index("rpi5_gate3_start_tlb_test()"),
                        source.index("rpi5_gate3_start_user_tlb_test()"))
        self.assertLess(source.index("rpi5_gate3_start_user_tlb_test()"),
                        source.index("rpi5_gate3_enable_soak("))
        self.assertIn('RPI5XNU:CROSS_CORE_INVALIDATION:PASS', source)
        self.assertIn('"bcm2712_gate3_qualify"', bsd)
        self.assertIn("bcm2712_gate3_qualify=1", loader)
        self.assertIn('parser.add_argument("--gate3-qualification-config"', builder)

    def test_trial_terminal_status_follows_serial_result(self):
        for filename, marker, status in (
            ("rpi5_concurrency_test.c", "RPI5XNU:SMP_CONCURRENCY:%s",
             "os_atomic_store(&rpi5_concurrency_status, passed ? 2 : 3, release)"),
            ("rpi5_tlb_test.c", "RPI5XNU:TLB:PASS",
             "os_atomic_store(&rpi5_tlb_status, passed ? 2 : 3, release)"),
            ("rpi5_user_tlb_test.c", "RPI5XNU:USER_TLB:%s",
             "os_atomic_store(&rpi5_user_tlb_status, passed ? 2 : 3, release)"),
        ):
            source = (ROOT / "osfmk/arm64" / filename).read_text()
            self.assertLess(source.index(marker), source.index(status))

    def test_cache_pass_waits_for_verified_not_just_arrived_ipis(self):
        source = (ROOT / "osfmk/arm64/sleh.c").read_text()
        self.assertIn("rpi5_gate3_ipi_verified[cpu] < 64U", source)
        self.assertIn("rpi5_gate3_ipi_verified[3] >= 64", source)

    def test_user_asid_trial_is_opt_in_and_uses_remote_hardware_translation(self):
        source = (ROOT / "osfmk/arm64/rpi5_user_tlb_test.c").read_text()
        pmap = (ROOT / "osfmk/arm/pmap/pmap.c").read_text()
        platform = (ROOT / "iokit/Kernel/BCM2712PlatformExpert.cpp").read_text()
        loader = (ROOT / "loader/rpi5/probe_main.c").read_text()
        self.assertIn('"bcm2712_user_tlb_trial"', platform)
        self.assertIn("bcm2712_user_tlb_trial=1", loader)
        self.assertIn("thread_bind(cpu_to_processor", source)
        self.assertIn("pmap_switch(test->pmap, thread)", source)
        self.assertIn("mmu_uvtop(RPI5_USER_TLB_VA)", source)
        self.assertIn("pmap_remove(user_pmap, RPI5_USER_TLB_VA", source)
        self.assertIn("RPI5_USER_TLB_ROUNDS 64U", source)
        self.assertIn("rpi5_pmap_switch_local_flush_count()", source)
        self.assertIn("RPI5XNU:USER_TLB:FAIL STAGE=SWITCH_FLUSH", source)
        self.assertIn("do_asid_flush || do_shared_region_flush || do_commpage_flush", pmap)
        self.assertIn("rpi5_pmap_switch_local_flushes[cpu_number()]", pmap)

    def test_bcm_vfp_test_uses_architected_rounding_modes(self):
        source = (ROOT / "osfmk/tests/vfp_state_test.c").read_text()
        board = source.split("#if defined(ARM64_BOARD_CONFIG_BCM2712)", 1)[1]
        board = board.split("#else", 1)[0]
        self.assertIn("VFP_STATE_TEST_CONTROL_SHIFT            22", board)
        self.assertIn("VFP_STATE_TEST_CONTROL_VALUES           4", board)
        self.assertIn("fp_control_expected &= ~(UINT64_C(3)", source)

    def test_xnupost_ranges_reject_overlap_and_reordering(self):
        script = ROOT / "tools/rpi5/build_probe.py"
        common = [sys.executable, str(script), "--load-address", "0x9000000",
                  "--kernel", "unused", "--init", "unused", "--transfer",
                  "--gate3-cpu-on-all"]
        for option in ("--gate3-xnupost-config", "--gate3-qualification-config"):
            for ranges in ("1_3,3_4", "5_5,2_2"):
                result = subprocess.run(common + [option, ranges], cwd=ROOT,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn("ascending and non-overlapping", result.stderr)

    def test_every_cpu_queues_first_self_sgi(self):
        platform = (ROOT / "iokit/Kernel/BCM2712PlatformExpert.cpp").read_text()
        initialization = platform.split("BCM2712CPU::initCPU(bool)", 1)[1]
        initialization = initialization.split("void BCM2712CPU::quiesceCPU", 1)[0]
        self.assertIn("if (!pe_rpi5_sgi_send(target))", initialization)
        self.assertNotIn("topologyCPU.cpu_id != ml_get_boot_cpu_number()", initialization)


if __name__ == "__main__":
    unittest.main()
