# SPDX-License-Identifier: BSD-2-Clause
"""Actual complete kernel linkage and hostile evidence checks; no Pi I/O."""
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import build_pcie_kernel as builder


class PCIeKernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temporary.name) / 'complete-kernel'
        cls.report = builder.build(cls.output)
        cls.raw = (cls.output / 'kernel.pcie-fdt').read_bytes()
        cls.listing = (cls.output / 'kernel.symbols').read_text()
        cls.linkmap = (cls.output / 'kernel.pcie-fdt.map').read_text(errors='surrogateescape')

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_actual_full_link_replaces_boot_objects_preserves_original_and_binds_initializers(self):
        r = self.report
        self.assertTrue(r['complete_kernel_link_proven'])
        self.assertTrue(r['original_kernel_replay']['all_non_uuid_bytes_identical'])
        self.assertEqual(r['original_kernel_replay']['excluded_metadata_bytes'], 16)
        self.assertEqual(len(r['link']['added_initializers']), 7)
        self.assertEqual(r['link']['initializer_table_segment'], '__DATA_CONST')
        self.assertEqual(r['new_linker_warnings'], [])
        self.assertEqual(r['kernel_sha256'], builder.audit.sha(self.output / 'kernel.pcie-fdt'))
        self.assertEqual(r['replaced_objects'], list(map(str, builder.REPLACED)))
        self.assertIn(str(builder.BASE / 'arm_init.c.o'), r['component_objects'])
        # The partial linker localizes arm_init; never pass that combined object
        # to the final link and mask the resulting undefined reset entry.
        self.assertNotIn(str(builder.COMPONENT), (self.output / 'kernel.pcie-fdt.filelist').read_text())
        for name, digest in {**r['inputs_sha256'], **r['generated_sha256']}.items():
            self.assertEqual(builder.audit.sha(Path(name)), digest, name)
        for key in ('initializer_runtime_executed', 'provider_personality_added', 'boot_caller_added',
                    'power_clock_ownership_proven', 'hardware_recovery_proven', 'installed',
                    'pi_executed', 'pcie_mmio_enabled', 'ethernet_proven', 'loader_package_created',
                    'sd_actions', 'serial_actions', 'reboots'):
            self.assertFalse(r[key], key)
        before = (self.output / 'manifest.json').read_bytes()
        with self.assertRaises(FileExistsError):
            builder.build(self.output)
        self.assertEqual(before, (self.output / 'manifest.json').read_bytes())

    def test_replay_excludes_only_exact_uuid_payload_and_rejects_real_byte_changes(self):
        original = builder.audit.KERNEL.read_bytes()
        self.assertTrue(builder.verify_replay(original, original)['entire_file_identical'])
        changed = bytearray(original)
        cursor = 32
        for _ in range(struct.unpack_from('<I', original, 16)[0]):
            command, size = struct.unpack_from('<II', original, cursor)
            if command == 0x1b:
                changed[cursor + 8] ^= 1
                break
            cursor += size
        result = builder.verify_replay(changed, original)
        self.assertTrue(result['all_non_uuid_bytes_identical'])
        self.assertFalse(result['entire_file_identical'])
        audited = builder.inspect_macho(original)
        executable = next(s for s in audited['segments'] if s['initprot'] & 4 and s['filesize'])
        changed[executable['fileoff']] ^= 1
        with self.assertRaisesRegex(ValueError, 'differs outside'):
            builder.verify_replay(changed, original)

    def test_dummy_dso_missing_duplicate_constructor_and_pointer_corruption_rejected(self):
        r = self.report['link']
        header = int(r['logging_dso_address'], 16)
        dso_line = next(line for line in self.linkmap.splitlines() if line.endswith(' ___dso_handle')
                        or line.endswith('\t___dso_handle'))
        changed = self.linkmap.replace(dso_line, dso_line.replace(f'0x{header:X}', f'0x{header + 8:X}'))
        self.assertNotEqual(changed, self.linkmap)
        with self.assertRaisesRegex(ValueError, 'DSO must alias'):
            builder.linked_audit(self.raw, self.listing, changed)
        with self.assertRaisesRegex(ValueError, 'DSO must alias'):
            builder.linked_audit(self.raw, self.listing, self.linkmap + '\n' + dso_line + '\n')
        name = builder.INITIALIZERS[0]
        removed = '\n'.join(line for line in self.listing.splitlines() if not line.endswith(' ' + name))
        with self.assertRaisesRegex(ValueError, 'Missing/ambiguous'):
            builder.linked_audit(self.raw, removed, self.linkmap)
        line = next(line for line in self.listing.splitlines() if line.endswith(' ' + name))
        with self.assertRaisesRegex(ValueError, 'Missing/ambiguous'):
            builder.linked_audit(self.raw, self.listing + '\n' + line, self.linkmap)
        site = int(r['added_initializers'][0]['pointer_site'], 16)
        segment = next(s for s in r['macho']['segments'] if s['vmaddr'] <= site < s['vmaddr'] + s['filesize'])
        offset = segment['fileoff'] + site - segment['vmaddr']
        changed = bytearray(self.raw)
        struct.pack_into('<Q', changed, offset, header)
        with self.assertRaisesRegex(ValueError, 'not present exactly once'):
            builder.linked_audit(changed, self.listing, self.linkmap)
        changed = bytearray(self.raw)
        # Duplicate a new initializer in another slot of the very same real table.
        struct.pack_into('<Q', changed, offset + 8, int(r['added_initializers'][0]['address'], 16))
        with self.assertRaisesRegex(ValueError, 'not present exactly once'):
            builder.linked_audit(changed, self.listing, self.linkmap)

    def test_actual_constructor_relocation_is_required(self):
        changed, cursor = bytearray(self.raw), 32
        target = int(self.report['link']['added_initializers'][0]['pointer_site'], 16)
        base = self.report['link']['macho']['relocation_base']
        found = False
        for _ in range(struct.unpack_from('<I', changed, 16)[0]):
            command, size = struct.unpack_from('<II', changed, cursor)
            if command == 0xb:
                offset, count = struct.unpack_from('<II', changed, cursor + 72)
                for i in range(count):
                    site, _ = struct.unpack_from('<II', changed, offset + 8 * i)
                    if base + site == target:
                        # Remove precisely this relocation from the active prefix.
                        end = offset + 8 * count
                        changed[offset + 8 * i:end - 8] = changed[offset + 8 * (i + 1):end]
                        struct.pack_into('<I', changed, cursor + 76, count - 1)
                        found = True
                        break
            cursor += size
        self.assertTrue(found)
        with self.assertRaisesRegex(ValueError, 'lacks real local relocation'):
            builder.linked_audit(changed, self.listing, self.linkmap)

    def test_dependency_drift_and_source_output_rejected(self):
        with patch.object(builder, 'BASE_SHA', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'receipt changed'):
                builder.inputs()
        for parent in (builder.ROOT / 'iokit', builder.ROOT / 'loader', builder.BASE,
                       builder.audit.OBJ, builder.audit.SDK):
            output = parent / 'must-not-create-complete-kernel'
            with self.assertRaisesRegex(ValueError, 'separate fresh'):
                builder.build(output)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
