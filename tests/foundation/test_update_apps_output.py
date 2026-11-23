"""Only the newly observed pinned Frappe 16 list-apps output envelope."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "product"))
import update_engine as engine


class InstalledAppsEnvelopeTests(unittest.TestCase):
    site = "toeflhouse.localhost"
    apps = ["frappe", "erpnext", "education", "payments", "hrms", "foundation_security", "toefl_house"]

    def parse(self, value):
        runner = engine.BenchRunner("bench", Path("."))
        result = subprocess.CompletedProcess([], 0, stdout=json.dumps(value), stderr="")
        with patch.object(runner, "_run", return_value=result):
            return runner.list_apps(self.site)

    def test_pinned_frappe16_exact_requested_site_envelope(self):
        self.assertEqual(self.parse({self.site: self.apps}), sorted(self.apps))

    def test_unexpected_site_or_envelope_shape_remains_refused(self):
        for value in ({"other.localhost": self.apps},
                      {self.site: self.apps, "other.localhost": self.apps},
                      {self.site: {"frappe": "16.33.1"}},
                      {self.site: "frappe"}):
            with self.subTest(value=value):
                with self.assertRaises(engine.UpdateError) as caught:
                    self.parse(value)
                self.assertEqual(caught.exception.code, "apply.counts_unavailable")

    def test_mapped_apps_retain_strict_existing_name_validation(self):
        for apps in (["frappe", "../erpnext"], ["frappe", "erpnext\n"],
                     ["frappe", {"name": "erpnext"}], ["frappe", None]):
            with self.subTest(apps=apps):
                with self.assertRaises(engine.UpdateError) as caught:
                    self.parse({self.site: apps})
                self.assertEqual(caught.exception.code, "apply.counts_unavailable")


if __name__ == "__main__":
    unittest.main()
