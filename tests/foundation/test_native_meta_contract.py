"""Pin the Frappe v16 Meta API used in the native acceptance verifier."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NativeMetaContractTests(unittest.TestCase):
    def test_refund_request_native_meta_uses_supported_field(self):
        source = (ROOT / "tools/native/native_checks.py").read_text(encoding="utf-8")
        self.assertIn("meta.get('is_submittable')", source)
        self.assertNotIn("meta.issubmittable", source)
        self.assertIn("'Refund request became postable'", source)


if __name__ == "__main__":
    unittest.main()
