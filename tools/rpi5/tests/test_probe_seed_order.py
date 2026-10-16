"""Source sequencing regression checks, not hardware execution evidence."""
from pathlib import Path
import unittest
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


class ProbeSeedOrderTests(unittest.TestCase):
    def test_seed_deferred_until_cpu_and_irq_checks(self):
        source = (ROOT / 'loader/rpi5/probe_main.c').read_text()
        prepare = source.split('static int board_tree_diagnostic(', 1)[1].split(
            'void rpi5_hash_progress(', 1)[0]
        self.assertNotIn('firmware_seed_diagnostic(', prepare)
        self.assertLess(prepare.index('pending_boot_data.ready=0;'),
                        prepare.index('rpi5_macho_materialize('))
        self.assertLess(prepare.index('rpi5_macho_verify_materialized('),
                        prepare.index('pending_boot_data.ready=1;'))
        entry = source.split('void probe_el1_main(', 1)[1]
        statements = [
            'if (!runtime_cpus(fdt_pa, &cpus))',
            'if (!psci_secondary_probe(&cpus)) return;',
            'if (!timer_probe()) return;',
            'timer_irq_probe();',
            'if (!probe_irq_verified)',
            'if (!pending_boot_data.ready) return;',
            'pending_boot_data.ready=0;',
            'if (!firmware_seed_diagnostic(',
            'STOP BEFORE XNU LOADER',
        ]
        positions = [entry.index(statement) for statement in statements]
        self.assertEqual(positions, sorted(positions))

    def test_transfer_requires_embedded_kernel(self):
        result = subprocess.run([sys.executable, str(ROOT / 'tools/rpi5/build_probe.py'),
                                 '--load-address', '0x9000000', '--transfer'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--transfer requires --kernel', result.stderr)

    def test_transfer_console_flags_match_kernel_controls(self):
        source = (ROOT / 'loader/rpi5/probe_main.c').read_text()
        self.assertIn('"serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release"', source)
        self.assertIn('"serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress") : ""', source)
        self.assertIn('while (command_line[command_length]) command_length++;', source)
        self.assertIn('live,live_count,command_line,command_length,&handoff)', source)
        serial = (ROOT / 'osfmk/console/serial_protos.h').read_text()
        self.assertRegex(serial, r'#define\s+SERIALMODE_OUTPUT\s+0x01\b')
        debug = (ROOT / 'osfmk/kern/debug.h').read_text()
        self.assertRegex(debug, r'#define\s+DB_PRT\s+0x2\b')
        self.assertRegex(debug, r'#define\s+DB_KPRT\s+0x8\b')
        config = (ROOT / 'pexpert/arm/pe_kprintf.c').read_text()
        self.assertIn('debug_boot_arg & (DB_KPRT | DB_PRT)', config)
        self.assertIn('PE_parse_boot_argn("-enable_kprintf_spam"', config)
        allocator = (ROOT / 'osfmk/kern/zalloc_internal.h').read_text()
        self.assertRegex(allocator, r'KT_OPTIONS_DEBUG\s*=\s*0x00000002\b')
        startup = (ROOT / 'osfmk/kern/startup.c').read_text()
        before = startup.index('kprintf("BCM2712 crypto provider registration\\n");')
        call = startup.index('rpi5_crypto_platform_start();', before)
        after = startup.index('kprintf("BCM2712 crypto and PRNG registered\\n");')
        self.assertLess(before, call)
        self.assertLess(call, after)
        platform = (ROOT / 'pexpert/arm/pe_init.c').read_text()
        self.assertIn('PE_parse_boot_argn("-noprogress",', platform)

    def test_no_fallible_output_between_commit_and_transfer(self):
        source = (ROOT / 'loader/rpi5/probe_main.c').read_text()
        entry = source.split('void probe_el1_main(', 1)[1]
        start = entry.index('if (!firmware_seed_diagnostic(')
        end = entry.index('rpi5_transfer(', start)
        self.assertNotIn('text(', entry[start:end])
        self.assertNotIn('rpi5_uart_drain(', entry[start:end])
        self.assertLess(entry.index('WATCHDOG_15S'), start)
        self.assertLess(entry.index('write32(transfer_watchdog_base+0x24'), start)

    def test_commit_checkpoint_failure_uses_erasure_path(self):
        source = (ROOT / 'loader/rpi5/probe_main.c').read_text()
        seed = source.split('static int firmware_seed_diagnostic(', 1)[1].split(
            'static struct {', 1)[0]
        marker = seed.index('BOOT_DATA_COMMITTED TRANSFER_NEXT')
        failure = seed.index('if (status || written!=expected || !cleared || !published)', marker)
        self.assertIn('status=-1;', seed[marker:failure])
        cleanup = seed[failure:seed.index('if (RPI5_XNU_TRANSFER) return 1;', failure)]
        self.assertIn('if (RPI5_XNU_TRANSFER && published)', cleanup)
        self.assertIn('ad[i]=0;', cleanup)
        self.assertIn('td[i]=0;', cleanup)
        self.assertIn('return 0;', cleanup)
