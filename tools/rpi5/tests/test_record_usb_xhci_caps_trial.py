import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "tools/rpi5/record_usb_xhci_caps_trial.py"


class USBXHCICapabilityRecorderTests(unittest.TestCase):
    def test_recorder_is_receive_only_and_parser_gated(self):
        text = SOURCE.read_text()
        tree = ast.parse(text)
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        self.assertFalse(any(isinstance(call.func, ast.Attribute) and
                             call.func.attr in ("write", "send", "sendall") and
                             isinstance(call.func.value, ast.Name) and
                             call.func.value.id == "fd" for call in calls))
        self.assertNotIn("os.write", text)
        self.assertIn("ZERO_SERIAL_TX", text)
        self.assertIn("evidence.parse", text)
        self.assertIn("Boot mode: NVME", text)
        self.assertIn('"transmitted_bytes": 0', text)


if __name__ == "__main__":
    unittest.main()
