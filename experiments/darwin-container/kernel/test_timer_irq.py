#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Compile the actual VZ dispatcher with fake registers; not hardware proof."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class TimerTests(unittest.TestCase):
    def test_timer_context_sync_precedes_eoi(self):
        source = (HERE / "overlay/pexpert/arm/pe_vzgeneric.c").read_text()
        completion = source.split("pe_vz_irq_complete(uint32_t iar)", 1)[1].split("pe_vz_send_self_sgi", 1)[0]
        self.assertLess(completion.index("__builtin_arm_isb(ISB_SY)"), completion.index('"ICC_EOIR1_EL1"'))

    def test_pending_stale_sgi_reserved_and_invalid_interrupts(self):
        with tempfile.TemporaryDirectory(prefix="vz-timer-test-") as temporary:
            executable = Path(temporary) / "test"
            subprocess.run(["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", str(HERE / "timer_irq_test.c"),
                            "-o", str(executable)], check=True, capture_output=True, timeout=30)
            subprocess.run([str(executable)], check=True, capture_output=True, timeout=10)

    def test_sync_hook_is_idempotent_and_drift_checked(self):
        spec = importlib.util.spec_from_file_location("vzbuild", HERE / "build.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        old = '''\tuint32_t iar = pe_vz_irq_acknowledge();
\tif (iar == 27U) {
\t\tif (!ml_get_timer_pending()) panic("VZGENERIC: timer IRQ without pending timer");
\t\tcdp->cpu_decrementer = -1;
\t\tml_interrupt_masked_debug_start(rtclock_intr, DBG_INTR_TYPE_TIMER);
\t\trtclock_intr(TRUE);
\t\tml_interrupt_masked_debug_end();
\t\tpe_vz_irq_complete(iar);
\t} else if (iar == 1U) {
\t\tpe_vz_irq_complete(iar);
\t\tcpu_signal_handler();
\t} else if (iar < 1020U || iar > 1023U) {
\t\tpanic("VZGENERIC: unexpected IRQ %u", iar);
\t}
'''
        before = '#if defined(ARM64_BOARD_CONFIG_BCM2712)\npi_dispatch();\n#elif defined(ARM64_BOARD_CONFIG_VZGENERIC)\n'
        after = '#elif USE_APPLEARMSMP\napple_dispatch();\n#endif\n'
        with tempfile.TemporaryDirectory(prefix="vz-timer-hook-") as temporary:
            root = Path(temporary)
            target = root / "osfmk/arm64/sleh.c"
            target.parent.mkdir(parents=True)
            target.write_text(before + old + after)
            module.apply_timer_irq_fix(root)
            once = target.read_bytes()
            module.apply_timer_irq_fix(root)
            self.assertEqual(once, target.read_bytes())
            self.assertIn(b'#include "vz_irq.inc"', once)
            self.assertEqual(once.decode(), before + '#include "vz_irq.inc"\n' + after)
            target.write_text("unexpected source drift")
            with self.assertRaises(ValueError):
                module.apply_timer_irq_fix(root)


if __name__ == "__main__":
    unittest.main()
