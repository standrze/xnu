# SPDX-License-Identifier: BSD-2-Clause
"""Synthetic transport guards only, not Pi or real zsh evidence."""
import copy
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import serial_zsh_trial as trial
import check_zsh_trial_package as package


def boot():
    return b'\n'.join((b'Boot mode: SD (01)', b'Read probe.bin bytes 18008768 hnd 0x123',
                       trial.ENTRY + b'0008', trial.TERMINAL_LOADER, package.TOPOLOGY_PASS,
                       trial.TRANSFER, package.RAMROOT, trial.READY, b'xnu:/# '))


class ZshSerialTests(unittest.TestCase):
    def test_fresh_ordered_boot_required(self):
        self.assertTrue(trial.boot_ready(boot(), 18008768))
        self.assertFalse(trial.boot_ready(trial.READY + b'\nxnu:/# ', 18008768))
        self.assertFalse(trial.boot_ready(boot().split(trial.TRANSFER)[0], 18008768))
        for bad in (boot() + trial.ENTRY,
                    boot().replace(b'NODES=24 BYTES=1392640', b'NODES=19 BYTES=589824'),
                    boot().replace(b'18008768', b'17205952'),
                    boot().replace(trial.TRANSFER, b''),
                    boot() + b'\nRPI5XNU:HFSWRITE:READY\n'):
            with self.subTest(raw=bad):
                try:
                    self.assertFalse(trial.boot_ready(bad, 18008768))
                except RuntimeError:
                    pass

    def test_wrong_or_unsafe_boot_never_transmits(self):
        for raw in (boot().replace(b'NODES=24 BYTES=1392640', b'NODES=19 BYTES=589824'),
                    boot() + b'panic(cpu 0)', boot() + b'RPI5XNU:HFSRW:'):
            progress = {'checks': [], 'transmitted_bytes': 0}
            with patch.object(trial.shell, 'receive', return_value=raw), \
                    patch.object(trial.os, 'write') as write, self.assertRaises(RuntimeError):
                trial.trial(1, io.BytesIO(), 1, {'image_bytes': 18008768}, progress)
            write.assert_not_called()
            self.assertEqual(progress['transmitted_bytes'], 0)

    def test_exact_complete_output_then_correct_prompt(self):
        prompt = trial.re.compile(trial.re.escape(trial.ZPROMPT))
        self.assertTrue(trial.response_complete(b'PI_ZSH:5.9\r\r\npi-zsh# ', [b'PI_ZSH:5.9'], prompt))
        for raw in (b'print -r -- "PI_ZSH:5.9"\npi-zsh# ',
                    b'PI_ZSH:5.9', b'pi-zsh# \nPI_ZSH:5.9\n',
                    b'PI_ZSH:5.9\nxnu:/# ', b'PI_ZSH:5.9x\npi-zsh# '):
            with self.subTest(raw=raw):
                self.assertFalse(trial.response_complete(raw, [b'PI_ZSH:5.9'], prompt))

    def test_failure_after_input_stops_without_cleanup_commands(self):
        progress = {'checks': [], 'transmitted_bytes': 0}
        with patch.object(trial, 'send') as send, \
                patch.object(trial.shell, 'receive', return_value=b'DARWIN:ZSH:FAULT:SIGNAL=4'), \
                self.assertRaises(RuntimeError):
            trial.exchange(1, io.BytesIO(), 'print ok', [b'ok'], trial.shell.PROMPT, progress)
        send.assert_called_once()

    def test_success_path_requires_both_zsh_instances_and_recovery(self):
        progress = {'checks': [], 'transmitted_bytes': 0}
        calls = []
        def exchange(fd, output, text, expected, prompt, state, seconds=30):
            calls.append(text)
            if text == trial.LAUNCH:
                return b'DARWIN:ZSH:MAIN\nDARWIN:ZSH:MAIN\npi-zsh# '
            return b'\n'.join(expected) + b'\nxnu:/# '
        with patch.object(trial, 'wait_boot'), patch.object(trial, 'exchange', side_effect=exchange):
            trial.trial(1, io.BytesIO(), 1, {'image_bytes': 18008768}, progress)
        self.assertEqual(len(progress['checks']), 6)
        self.assertEqual(calls[-2], 'exit')
        self.assertTrue(calls[-1].startswith('echo RECOVERED_Z'))
        self.assertIn('zsh -f /etc/zsh-smoke.zsh', calls)

    def test_package_profiles_exclude_storage_and_hardware_operations(self):
        manifest = {'commands': [['clang', 'probe_main.c', '-DRPI5_GATE5_PCIE_TOPOLOGY=1'],
                                 ['clang', 'pcie_fdt.c'], ['clang', 'pcie_topology.c']],
                    'gate5_pcie_topology': True, 'gate5_pcie_mmio_enabled': False,
                    **{name: False for name in ('gate4_storage_binding_snapshot', 'gate4_sd_readonly',
                                               'gate4_hfs_readonly', 'gate4_hfs_write_trial')}}
        self.assertTrue(all(package.profile_checks(manifest).values()))
        for change in ('storage', 'reset', 'ubus', 'windows', 'link', 'access', 'rc', 'mmio', 'switch'):
            bad = copy.deepcopy(manifest)
            if change == 'storage': bad['gate4_hfs_write_trial'] = True
            if change == 'reset': bad['commands'].append(['clang', 'pcie_reset.c'])
            if change == 'ubus': bad['commands'].append(['clang', 'pcie_ubus.c'])
            if change == 'windows': bad['commands'].append(['clang', 'pcie_windows.c'])
            if change == 'link': bad['commands'].append(['clang', 'pcie_link.c'])
            if change == 'access': bad['commands'].append(['clang', 'pcie_access.c'])
            if change == 'rc': bad['commands'].append(['clang', 'pcie_rc.c'])
            if change == 'mmio': bad['gate5_pcie_mmio_enabled'] = True
            if change == 'switch': bad['commands'][0].pop()
            with self.subTest(change=change):
                self.assertFalse(all(package.profile_checks(bad).values()))


if __name__ == '__main__':
    unittest.main()
