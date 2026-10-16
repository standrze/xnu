#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Arithmetic regression for VZ's non-monitor physical-aperture VA budget.

This is not a kernel runtime test. It reproduces arm_vm_physmap_slide's
block-congruence adjustment for the two real non-monitor PTOV entries.
"""
import unittest

PAGE = 1 << 14
TWIG = 1 << 25
MANAGED_BYTES = 320 << 20
HEADER_OFFSET = 0x1004000
TABLE_CAPACITY = 8


def slide(cursor, physical, size):
    delta = (physical - cursor) & (TWIG - 1)
    return cursor + delta + ((size + PAGE - 1) & -PAGE)


def aperture_end(random_slide, retained_top):
    cursor = slide(random_slide, 0, HEADER_OFFSET)
    return slide(cursor, retained_top, MANAGED_BYTES - retained_top)


class PhysicalApertureTests(unittest.TestCase):
    def test_old_exact_size_budget_can_fail(self):
        random_slide = PAGE
        retained_top = 0x02018000
        self.assertGreater(aperture_end(random_slide, retained_top),
                           random_slide + MANAGED_BYTES)

    def test_reserved_alignment_slack_covers_every_slide(self):
        # Every 16-KiB offset in a 32-MiB block (the complete repeating set
        # across the 1-GiB randomized range), including differing top offsets.
        for retained_top in (0x01F00000, 0x02018000, 0x03000000, 0x04210000):
            for random_slide in range(0, TWIG, PAGE):
                with self.subTest(top=retained_top, slide=random_slide):
                    actual = aperture_end(random_slide, retained_top)
                    reserved = random_slide + MANAGED_BYTES + TABLE_CAPACITY * TWIG
                    self.assertLessEqual(actual, reserved)

    def test_l1_reservation_includes_slide_and_alignment_slack(self):
        l1_span = 1 << 36
        slide_range = 1 << 30
        slack = TABLE_CAPACITY * TWIG
        for physical_size in (MANAGED_BYTES, l1_span - slide_range - slack // 2, 2 * l1_span):
            entries = ((physical_size + slide_range + slack) // l1_span) + 1
            highest_end = slide_range - PAGE + physical_size + slack
            self.assertLessEqual(highest_end, entries * l1_span)


if __name__ == "__main__":
    unittest.main()
