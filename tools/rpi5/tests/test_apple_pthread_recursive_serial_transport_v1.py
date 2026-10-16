# SPDX-License-Identifier: BSD-2-Clause
"""Offline package, parser and mutation proof for recursive-mutex execution."""
import json
import unittest

from tools.rpi5 import apple_pthread_recursive_serial_transport_v1 as transport
from tools.rpi5 import qualify_apple_pthread_recursive_serial_transport_v1 as qualify


class RecursiveSerialTransportTests(unittest.TestCase):
    def test_exact_immutable_package_and_embedded_target(self):
        result = qualify.qualify()
        self.assertTrue(result["qualified"])
        self.assertFalse(result["hardware_execution"])
        self.assertEqual(result["hardware_actions"], 0)
        self.assertEqual(result["target_sha256"], transport.TARGET_SHA256)
        self.assertEqual(result["mutation_rejection_count"], 12)

    def test_exact_command_is_bounded_and_default_off(self):
        command = transport.command(qualify.NONCE)
        self.assertIn(transport.TARGET_PATH, command)
        self.assertLessEqual(len(command.encode("ascii")), 1023)
        contract = transport.execution_contract()
        self.assertTrue(contract["default_off"])
        self.assertFalse(contract["hardware_execution"])
        self.assertTrue(contract["one_shot_no_implicit_retry"])
        self.assertTrue(contract["automatic_nvme_linux_return_required"])
        self.assertTrue(contract["sealed_working_loader_restoration_required"])

    def test_exact_semantics_and_zero_unrelated_claims(self):
        result = transport.accept(qualify.receipt(), qualify.recovery(), qualify.NONCE, 2)
        self.assertEqual(result["foreign_owner_eperm_count"], 2)
        self.assertEqual(result["busy_observation_count"], 2)
        self.assertTrue(result["depth_three"])
        self.assertTrue(result["final_release"])
        self.assertTrue(result["batch_process_exit_verified"])
        for key in ("atfork_fork_qualified", "cancelable_variant_qualified",
                    "filex_stream_locking_qualified", "networking", "ssh_transport", "ssh_daemon"):
            self.assertFalse(result[key])

    def test_semantic_and_framing_mutations_are_rejected(self):
        raw = qualify.receipt()
        mutations = (
            raw.replace(b"DEPTH=3", b"DEPTH=4"),
            raw.replace(b"FOREIGN_EPERM=2", b"FOREIGN_EPERM=0"),
            raw.replace(b"BUSY=2", b"BUSY=0"),
            raw.replace(b"RELEASED=1", b"RELEASED=0"),
            raw.replace(b"STATUS:0", b"STATUS:1"),
            raw + b"\n" + transport.PASS_LINE,
            raw.replace(qualify.NONCE.encode(), b"f" * 32),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation[-80:]), self.assertRaises(ValueError):
                transport.accept(mutation, qualify.recovery(), qualify.NONCE, 1)
        for recovery in (b"xnu:/# ", qualify.recovery().replace(b"STATUS:0", b"STATUS:1"),
                         qualify.recovery() + b"\n" + qualify.recovery()):
            with self.assertRaises(ValueError):
                transport.accept(raw, recovery, qualify.NONCE, 1)

    def test_bounds_and_nonce_are_fail_closed(self):
        with self.assertRaises(ValueError):
            transport.command("short")
        with self.assertRaises(ValueError):
            transport.accept(qualify.receipt(), qualify.recovery(), qualify.NONCE, 31)
        with self.assertRaises(ValueError):
            transport.inspect_execution(b"x" * (transport.MAX_CAPTURE_BYTES + 1), qualify.NONCE)
        with self.assertRaises(ValueError):
            transport.accept(qualify.receipt() + b"x" * transport.MAX_CAPTURE_BYTES,
                             qualify.recovery(), qualify.NONCE, 1)

    def test_package_contains_no_execution_receipt(self):
        manifest = json.loads((qualify.PACKAGE / "manifest.json").read_text())
        self.assertFalse(manifest["installed"])
        self.assertFalse(manifest["pi_executed"])
        self.assertEqual(manifest["serial_actions"], 0)
        self.assertEqual(manifest["sd_actions"], 0)
        self.assertEqual(manifest["reboots"], 0)
        self.assertFalse(manifest["qualified_for_future_staging"])


if __name__ == "__main__":
    unittest.main()
