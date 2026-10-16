# SPDX-License-Identifier: BSD-2-Clause
import unittest
from tools.rpi5 import build_root42_confirmed_kernel as builder


class SourceTests(unittest.TestCase):
    def test_successful_mount_publication_precedes_old_diagnostic_and_no_pointer_export(self):
        text=builder.mount_source((builder.ROOT/'bsd/miscfs/mockfs/mockfs_vfsops.c').read_text())
        publish=text.index('(void)rpi5_root_confirmation_publish')
        self.assertLess(text.index('mp->mnt_data = (typeof(mp->mnt_data))data;'),publish)
        self.assertLess(text.index('mp->mnt_flag |= MNT_RDONLY;'),publish)
        self.assertLess(publish,text.index('printf("RPI5XNU:RAMROOT:MOUNT'))
        self.assertLess(text.index('rvalue = vflush('),text.index('rpi5_root_confirmation_clear'))
        self.assertLess(text.index('rpi5_root_confirmation_clear'),text.index('mockfs_ramroot_destroy(mockfs_mnt)'))
        snapshot=text[text.index('bool\nmockfs_rpi5_root_snapshot'):text.index('static void\nmockfs_ramroot_destroy')]
        self.assertNotIn('mnt_data',snapshot);self.assertNotIn('lck_',snapshot)

    def test_late_condition_bounds_repeats_not_deadline_and_preserves_ready(self):
        original=(builder.BASE/'pe_fiq.c').read_text();text=builder.pe_source(original)
        marker=text.index('kprintf("\\nRPI5XNU:TERMINAL:ROOT_READY')
        self.assertLess(text.index('rpi5_wdog_reloads++;'),marker)
        self.assertLess(text.index('mockfs_rpi5_root_snapshot(&nodes, &bytes)'),text.index('rpi5_wdog_root_reports++;'))
        self.assertIn('rpi5_wdog_root_reports < 3',text);self.assertIn('report_after != 0 && now >= report_after',text)
        self.assertEqual(text.count('rpi5_wdog_deadline ='),original.count('rpi5_wdog_deadline ='))
        self.assertIn(builder.prior.ANNOUNCE,text)
        self.assertIn('RPI5_TERMINAL_WDOG_SECONDS, nodes, bytes',text)

    def test_publication_single_atomic_value_and_bounded_shape(self):
        text=builder.HEADER.read_text()
        self.assertIn('__atomic_store_n(state, value, __ATOMIC_RELEASE)',text)
        self.assertIn('__atomic_load_n(state, __ATOMIC_ACQUIRE)',text)
        self.assertIn('nodes >= 4 && nodes <= 96',text)
        self.assertIn('bytes % 16384 == 0',text)
        self.assertNotIn('malloc',text);self.assertNotIn('while',text)
