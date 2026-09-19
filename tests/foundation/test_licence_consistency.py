"""The three licence surfaces must agree.

Owner decision D11 (2026-09-19) selected MIT. Before that decision the
repository contradicted itself three ways: both hooks.py files declared
``app_license = "MIT"``, the README stated that no licence was selected, and no
LICENSE file existed. A licence is a legal grant, so a silent drift between what
the metadata declares and what the repository actually grants is a real defect,
not a documentation nit. These checks make the agreement mechanical.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = (ROOT / "apps/toefl_house/toefl_house/hooks.py",
         ROOT / "apps/foundation_security/foundation_security/hooks.py")


class LicenceConsistencyTests(unittest.TestCase):
    def test_a_licence_file_exists_and_is_mit(self):
        licence = ROOT / "LICENSE"
        self.assertTrue(licence.is_file(), "no LICENSE file in the repository")
        text = licence.read_text(encoding="utf-8")
        self.assertIn("MIT License", text)
        self.assertIn("Permission is hereby granted, free of charge", text)
        self.assertIn("TOEFL House", text, "the copyright holder must be named")

    def test_every_app_declares_the_same_licence_as_the_licence_file(self):
        for hooks in HOOKS:
            with self.subTest(app=hooks.parent.name):
                source = hooks.read_text(encoding="utf-8")
                self.assertIn('app_license = "MIT"', source,
                              f"{hooks} does not declare MIT")

    def test_the_readme_states_the_selected_licence(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Product license: MIT", readme)
        self.assertNotIn("No product license has been selected", readme,
                         "the README still claims no licence is selected")

    def test_d11_is_recorded_as_decided(self):
        record = (ROOT / "docs/engineering/canonical-owner-decision-record.json")
        self.assertIn('"D11"', record.read_text(encoding="utf-8"))


class NoStaleLicenceClaimTests(unittest.TestCase):
    """A decided decision must not still read as undecided anywhere active.

    D11 was decided on 2026-09-19, yet three active surfaces still said the
    licence was unselected - including a summary table row inside the very file
    whose D11 section recorded the decision. Section 10 of the owner directive
    requires exactly one authoritative state per decision, so these checks scan
    the active surfaces for the stale wording rather than trusting a single
    field. Historical provenance lines are allowed, but only when they say so.
    """

    ACTIVE_SURFACES = ("README.md",
                       "docs/engineering/OWNER-DECISIONS.md",
                       "docs/engineering/RELEASE-GAP-MAP.md")
    STALE = ("No product license has been selected",
             "NOT SELECTED — owner decision required",
             "OPEN — owner decision required")
    HISTORICAL = ("historical", "superseded", "was recorded", "recorded 2026-09-17")

    def test_no_active_surface_still_calls_the_licence_unselected(self):
        offenders = []
        for rel in self.ACTIVE_SURFACES:
            for lineno, line in enumerate(
                    (ROOT / rel).read_text(encoding="utf-8").splitlines(), start=1):
                if any(s in line for s in self.STALE) and not any(
                        h in line.lower() for h in self.HISTORICAL):
                    offenders.append(f"{rel}:{lineno}")
        self.assertEqual(offenders, [],
                         "a decided decision still reads as undecided: " + ", ".join(offenders))

    def test_the_canonical_record_agrees_with_the_licence_file(self):
        import json
        record = json.loads(
            (ROOT / "docs/engineering/canonical-owner-decision-record.json")
            .read_text(encoding="utf-8"))
        licensing = record["licensing"]
        self.assertIn("MIT", licensing["state"])
        self.assertNotIn("No product license has been selected",
                         licensing.get("readme_statement", ""))
        self.assertIn("present", licensing.get("repository_license_file", ""))
        # The decided block and the historical note must not disagree.
        self.assertEqual(record["resolved_business_decisions"]["D11"]["status"],
                         "DECIDED")
        self.assertIn("MIT", json.dumps(
            record["resolved_business_decisions"]["D11"]["owner_answers"]))
