"""D16 production activation: fixture separation between synthetic and production.

Owner decision D16 (2026-09-19) authorizes one explicitly activated
production site. These tests lock the mirror rule: the same bounds hold
everywhere, SYN- test markers are REQUIRED on synthetic qualification sites
and FORBIDDEN on the production site, and any mixed or unactivated site is
REFUSED. Hosted probes remain the real permission proof; these unit checks
guard the mode logic itself.
"""
import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as Obj
from unittest.mock import patch

APP = Path(__file__).resolve().parents[2] / "apps" / "toefl_house" / "toefl_house"


def load_security(conf, site):
    """Load security.py with a stubbed frappe pinned to one site/config."""
    frappe = Obj(
        conf=dict(conf),
        local=Obj(site=site),
        session=Obj(user="tester@example.test"),
        get_roles=lambda user: [],
        PermissionError=type("PermissionError", (Exception,), {}),
    )
    spec = importlib.util.spec_from_file_location("security_under_test", APP / "security.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"frappe": frappe}):
        spec.loader.exec_module(module)
    return module


def load_policy():
    spec = importlib.util.spec_from_file_location("policy_under_test", APP / "policy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SYNTHETIC_CONF = {"toefl_house_synthetic_only": 1, "allow_tests": 1}
PROD_SITE = "erp.toeflhouse.example"


def production_conf(site=PROD_SITE):
    return {"toefl_house_production_active": 1, "toefl_house_production_site": site}


class SiteModeTests(unittest.TestCase):
    def test_synthetic_triple_resolves_synthetic_on_both_hostnames(self):
        for site in ("placement-test.localhost", "placement-second.localhost"):
            security = load_security(SYNTHETIC_CONF, site)
            self.assertEqual(security.site_mode(), security.SYNTHETIC, site)

    def test_synthetic_missing_any_leg_is_refused(self):
        legs = [
            ({"allow_tests": 1}, "placement-test.localhost"),
            ({"toefl_house_synthetic_only": 1}, "placement-test.localhost"),
            (dict(SYNTHETIC_CONF), "other.localhost"),
        ]
        for conf, site in legs:
            security = load_security(conf, site)
            self.assertEqual(security.site_mode(), security.REFUSED, (conf, site))

    def test_production_triple_resolves_production(self):
        security = load_security(production_conf(), PROD_SITE)
        self.assertEqual(security.site_mode(), security.PRODUCTION)

    def test_production_missing_any_leg_is_refused(self):
        cases = [
            ({"toefl_house_production_active": 0,
              "toefl_house_production_site": PROD_SITE}, PROD_SITE),
            ({"toefl_house_production_site": PROD_SITE}, PROD_SITE),
            ({"toefl_house_production_active": 1}, PROD_SITE),
            ({"toefl_house_production_active": 1,
              "toefl_house_production_site": "other.example"}, PROD_SITE),
            ({"toefl_house_production_active": 1,
              "toefl_house_production_site": 12345}, PROD_SITE),
        ]
        for conf, site in cases:
            security = load_security(conf, site)
            self.assertEqual(security.site_mode(), security.REFUSED, conf)

    def test_qualification_hostname_can_never_be_the_production_site(self):
        security = load_security(production_conf("placement-test.localhost"),
                                 "placement-test.localhost")
        self.assertEqual(security.site_mode(), security.REFUSED)

    def test_mixed_synthetic_and_production_is_refused(self):
        conf = dict(SYNTHETIC_CONF)
        conf.update(production_conf("placement-test.localhost"))
        security = load_security(conf, "placement-test.localhost")
        self.assertEqual(security.site_mode(), security.REFUSED)
        # And in the copied-config direction: qualification flags left on
        # the production hostname alongside its activation claim refuse too.
        conf = dict(SYNTHETIC_CONF)
        conf.update(production_conf(PROD_SITE))
        security = load_security(conf, PROD_SITE)
        self.assertEqual(security.site_mode(), security.REFUSED)

    def test_bare_site_is_refused(self):
        security = load_security({}, "plain.example")
        self.assertEqual(security.site_mode(), security.REFUSED)

    def test_is_production_true_only_on_activated_site(self):
        self.assertTrue(load_security(production_conf(), PROD_SITE).is_production())
        self.assertFalse(load_security(SYNTHETIC_CONF, "placement-test.localhost").is_production())
        self.assertFalse(load_security({}, "plain.example").is_production())


class GateTests(unittest.TestCase):
    def test_require_operational_accepts_synthetic_and_production(self):
        load_security(SYNTHETIC_CONF, "placement-test.localhost").require_operational()
        load_security(production_conf(), PROD_SITE).require_operational()

    def test_require_operational_refuses_mixed_bare_and_wrong_site(self):
        mixed = dict(SYNTHETIC_CONF)
        mixed.update(production_conf("placement-test.localhost"))
        for conf, site in ((mixed, "placement-test.localhost"),
                            ({}, "plain.example"),
                            (production_conf("other.example"), PROD_SITE)):
            security = load_security(conf, site)
            with self.assertRaises(security.frappe.PermissionError, msg=(conf, site)):
                security.require_operational()

    def test_record_synthetic_flag_mirrors_the_mode(self):
        synthetic = load_security(SYNTHETIC_CONF, "placement-test.localhost")
        production = load_security(production_conf(), PROD_SITE)
        self.assertEqual(synthetic.record_synthetic_flag(), 1)
        self.assertEqual(production.record_synthetic_flag(), 0)

    def test_record_synthetic_flag_refuses_instead_of_stamping_blindly(self):
        security = load_security({}, "plain.example")
        with self.assertRaises(security.frappe.PermissionError):
            security.record_synthetic_flag()

    def test_require_synthetic_stays_qualification_only(self):
        load_security(SYNTHETIC_CONF, "placement-test.localhost").require_synthetic()
        production = load_security(production_conf(), PROD_SITE)
        with self.assertRaises(production.frappe.PermissionError):
            production.require_synthetic()


class PolicyMirrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_policy()

    def test_family_production_accepts_real_code_rejects_markers(self):
        self.policy.validate_family("FALL-2026-A", 1, production=True)
        for bad in ("SYN-ABC-1", "SYNTHETIC-X", "", "x" * 65, None, 7):
            with self.assertRaises(ValueError, msg=bad):
                self.policy.validate_family(bad, 1, production=True)

    def test_family_synthetic_still_requires_marker(self):
        with self.assertRaises(ValueError):
            self.policy.validate_family("FALL-2026-A", 1)
        self.policy.validate_family("SYN-ABC-1", 1)

    def test_config_code_production_mirror(self):
        self.policy.validate_config_code("MATH-L2", 3, production=True)
        for bad in ("SYN-MATH-1", "SYNTHETIC-M", "y" * 65):
            with self.assertRaises(ValueError, msg=bad):
                self.policy.validate_config_code(bad, 3, production=True)
        with self.assertRaises(ValueError):
            self.policy.validate_config_code("MATH-L2", 3)

    def test_content_production_forbids_fixture_marker(self):
        base = {"skill": "Reading", "difficulty": "Core",
                "question_type": "Single Choice",
                "options": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
                "answer": "a"}
        real = dict(base, prompt="Read the passage and answer.")
        self.policy.validate_content(real, production=True)
        fixture = dict(base, prompt="SYNTHETIC: read the passage.")
        with self.assertRaises(ValueError):
            self.policy.validate_content(fixture, production=True)
        with self.assertRaises(ValueError):
            self.policy.validate_content(real)

    def test_course_map_production_mirror(self):
        real = {"algorithm": "course-map-v1", "entries": [
            {"internal_level": "L2", "course_code": "ENG-201",
             "match": "any_correct"}]}
        self.policy.validate_course_map(real, production=True)
        marked = {"algorithm": "course-map-v1", "entries": [
            {"internal_level": "SYN-L2", "course_code": "ENG-201",
             "match": "any_correct"}]}
        with self.assertRaises(ValueError):
            self.policy.validate_course_map(marked, production=True)
        with self.assertRaises(ValueError):
            self.policy.validate_course_map(real)

    def test_group_name_production_mirror(self):
        self.assertEqual(
            self.policy.validate_group_name("Grade-9-A", production=True),
            "Grade-9-A")
        for bad in ("SYN-GROUP-1", "SYNTHETIC-G", "z" * 65):
            with self.assertRaises(ValueError, msg=bad):
                self.policy.validate_group_name(bad, production=True)
        with self.assertRaises(ValueError):
            self.policy.validate_group_name("Grade-9-A")

    def test_recommend_course_production_uses_real_codes(self):
        course_map = {"algorithm": "course-map-v1", "entries": [
            {"internal_level": "L2", "course_code": "ENG-201",
             "match": "any_correct"}]}
        score = {"presented": 4, "correct": 2, "incorrect": 1, "missing": 1}
        result = self.policy.recommend_course(score, course_map, production=True)
        self.assertEqual(result["course_code"], "ENG-201")
        self.assertNotIn("Synthetic", result["rationale"])


class StampAndGuardWiringTests(unittest.TestCase):
    STAMPED = ("api.py", "admission/__init__.py",
               "finance/corrections.py", "teaching/compensation.py")
    GUARDED = ("admission/__init__.py", "enrollment/__init__.py",
               "finance/__init__.py", "teaching/__init__.py")

    def test_command_records_stamp_through_the_mode_helper(self):
        for relative in self.STAMPED:
            source = (APP / relative).read_text(encoding="utf-8")
            self.assertIn("record_synthetic_flag()", source, relative)
            for line in source.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                self.assertNotIn("synthetic=1", stripped,
                                 f"{relative}: unconditional fixture stamp")

    def test_domain_guards_use_the_operational_gate(self):
        for relative in self.GUARDED:
            source = (APP / relative).read_text(encoding="utf-8")
            self.assertIn("require_operational()", source, relative)
            self.assertNotIn("require_synthetic()", source,
                             f"{relative}: stale synthetic-only gate")

    def test_controller_enforces_the_stamp_per_mode(self):
        source = (APP / "controllers.py").read_text(encoding="utf-8")
        self.assertIn("mode = site_mode()", source)
        self.assertIn("Only synthetic records are supported", source)
        self.assertIn("Synthetic fixture records are not accepted on the production site",
                      source)


if __name__ == "__main__":
    unittest.main()
