"""Pure local unit checks only; these do NOT qualify native Frappe behavior."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/toefl_house"))
from toefl_house.policy import (can_read, canonical, digest, is_config_transition,
                                validate_blueprint, validate_config_code, validate_policy)


def blueprint(total=None):
    sections = [
        {"id": "listening", "skill": "Listening", "minutes": 30, "item_count": 10},
        {"id": "reading", "skill": "Reading", "minutes": 40, "item_count": 12},
    ]
    return {"mode": "Digital", "sections": sections,
            "total_minutes": 70 if total is None else total}


def policy():
    return {"result_validity_days": 90, "retest_wait_days": 14,
            "release_working_days": 2, "appeal_working_days": 5, "retention_years": 3}


class BlueprintValidationTests(unittest.TestCase):
    def test_valid_blueprint(self):
        self.assertEqual(validate_blueprint(blueprint()), blueprint())

    def test_definition_digest_is_canonical_and_sensitive(self):
        value = blueprint()
        self.assertEqual(digest(value), digest(json.loads(canonical(value))))
        changed = copy.deepcopy(value)
        changed["sections"][0]["item_count"] = 11
        self.assertNotEqual(digest(value), digest(changed))

    def test_exact_top_level_fields(self):
        for field in blueprint():
            value = blueprint(); value.pop(field)
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_blueprint(value)
        value = blueprint(); value["flags"] = 1
        with self.assertRaises(ValueError):
            validate_blueprint(value)

    def test_mode(self):
        for mode in ("Remote", "digital", ""):
            value = blueprint(); value["mode"] = mode
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                validate_blueprint(value)

    def test_definition_cannot_carry_identity_or_privileged_fields(self):
        # The record-level code is identity and never travels inside the definition.
        for field in ("code", "flags", "owner", "status"):
            value = blueprint(); value[field] = "x"
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_blueprint(value)

    def test_section_count_bounds(self):
        value = blueprint(); value["sections"] = []
        with self.assertRaises(ValueError):
            validate_blueprint(value)
        value = blueprint()
        value["sections"] = [dict(value["sections"][0], id=f"s{i}") for i in range(13)]
        value["total_minutes"] = 30 * 13
        with self.assertRaises(ValueError):
            validate_blueprint(value)

    def test_duplicate_section_id(self):
        value = blueprint(); value["sections"][1]["id"] = "listening"
        with self.assertRaises(ValueError):
            validate_blueprint(value)

    def test_bad_section_id(self):
        for section_id in ("Listening", "1listening", "a" * 17, "has space"):
            value = blueprint(); value["sections"][0]["id"] = section_id
            with self.subTest(id=section_id), self.assertRaises(ValueError):
                validate_blueprint(value)

    def test_section_shape_and_values(self):
        # All six skills are legitimate section skills; unknown ones are not.
        value = blueprint(); value["sections"][0]["skill"] = "TOEFL"
        with self.assertRaises(ValueError):
            validate_blueprint(value)
        for skill in ("Speaking", "Writing"):
            ok = blueprint(); ok["sections"][0]["skill"] = skill
            validate_blueprint(ok)
        for field, bad in (("minutes", 0), ("minutes", 241), ("minutes", True),
                           ("item_count", 0), ("item_count", 101), ("item_count", "10")):
            value = blueprint(); value["sections"][0][field] = bad
            with self.subTest(field=field, value=bad), self.assertRaises(ValueError):
                validate_blueprint(value)
        value = blueprint(); value["sections"][0]["extra"] = 1
        with self.assertRaises(ValueError):
            validate_blueprint(value)

    def test_total_must_match_section_sum(self):
        for total in (0, 71, 241):
            with self.subTest(total=total), self.assertRaises(ValueError):
                validate_blueprint(blueprint(total=total))


class PolicyValidationTests(unittest.TestCase):
    def test_valid_policy(self):
        self.assertEqual(validate_policy(policy()), policy())

    def test_exact_fields(self):
        for field in policy():
            value = policy(); value.pop(field)
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_policy(value)
        value = policy(); value["cutoff_percent"] = 70
        with self.assertRaises(ValueError):
            validate_policy(value)

    def test_definition_cannot_carry_identity_or_privileged_fields(self):
        for field in ("code", "flags", "owner", "status"):
            value = policy(); value[field] = "x"
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_policy(value)

    def test_parameter_bounds_are_structural_not_business_values(self):
        cases = [("result_validity_days", 0), ("result_validity_days", 731),
                 ("retest_wait_days", -1), ("retest_wait_days", 91),
                 ("release_working_days", 0), ("release_working_days", 31),
                 ("appeal_working_days", 0), ("appeal_working_days", 31),
                 ("retention_years", 0), ("retention_years", 11),
                 ("result_validity_days", True), ("retest_wait_days", "14")]
        for field, bad in cases:
            value = policy(); value[field] = bad
            with self.subTest(field=field, value=bad), self.assertRaises(ValueError):
                validate_policy(value)

    def test_zero_retest_wait_is_structurally_allowed(self):
        value = policy(); value["retest_wait_days"] = 0
        self.assertEqual(validate_policy(value), value)


class ConfigCodeAndStateTests(unittest.TestCase):
    def test_validate_config_code(self):
        validate_config_code("SYN-BP-MAIN-1", 1)
        for code, revision in [("REAL", 1), (12, 1), ("SYN-BP-MAIN-1", 0),
                               ("SYN-BP-MAIN-1", 100001), ("SYN-BP-MAIN-1", True)]:
            with self.subTest(code=code, revision=revision), self.assertRaises(ValueError):
                validate_config_code(code, revision)

    def test_state_machine_forward_only(self):
        for before, after in [("Draft", "Draft"), ("Draft", "Reviewed"),
                              ("Reviewed", "Published"), ("Published", "Retired"),
                              ("Retired", "Retired")]:
            with self.subTest(before=before, after=after):
                self.assertTrue(is_config_transition(before, after))
        for before, after in [("Draft", "Published"), ("Draft", "Retired"), ("Reviewed", "Draft"),
                              ("Reviewed", "Retired"), ("Published", "Draft"), ("Published", "Reviewed"),
                              ("Retired", "Draft"), ("Retired", "Published"), ("Retired", "Reviewed"),
                              ("Unknown", "Draft")]:
            with self.subTest(before=before, after=after):
                self.assertFalse(is_config_transition(before, after))


class ConfigReadBoundaryTests(unittest.TestCase):
    def test_author_reads_own_any_status_and_others_published_only(self):
        self.assertTrue(can_read("blueprint", ["Placement Author"], "a", "a", "Draft"))
        self.assertFalse(can_read("blueprint", ["Placement Author"], "a", "b", "Draft"))
        self.assertFalse(can_read("blueprint", ["Placement Author"], "a", "b", "Reviewed"))
        self.assertTrue(can_read("blueprint", ["Placement Author"], "a", "b", "Published"))
        self.assertTrue(can_read("policy", ["Placement Author"], "a", "a", "Retired"))
        self.assertFalse(can_read("policy", ["Placement Author"], "a", "b", "Retired"))

    def test_publisher_reads_all_statuses(self):
        for status in ("Draft", "Reviewed", "Published", "Retired"):
            for kind in ("blueprint", "policy"):
                with self.subTest(kind=kind, status=status):
                    self.assertTrue(can_read(kind, ["Placement Publisher"], "p", "a", status))

    def test_auditor_reads_published_only(self):
        for kind in ("blueprint", "policy"):
            self.assertFalse(can_read(kind, ["Placement Auditor"], "x", "a", "Draft"))
            self.assertFalse(can_read(kind, ["Placement Auditor"], "x", "a", "Reviewed"))
            self.assertTrue(can_read(kind, ["Placement Auditor"], "x", "a", "Published"))
            self.assertFalse(can_read(kind, ["Placement Auditor"], "x", "a", "Retired"))

    def test_unrelated_roles_read_nothing(self):
        for roles in (["Student", "Guest"], ["Assessor"], []):
            for kind in ("blueprint", "policy", "audit", "operation", "key", "item"):
                with self.subTest(roles=roles, kind=kind):
                    self.assertFalse(can_read(kind, roles, "x", "x", "Published"))

    def test_increment1_boundaries_unchanged(self):
        self.assertTrue(can_read("item", ["Placement Author"], "a", "a", "Draft"))
        self.assertFalse(can_read("item", ["Placement Author"], "a", "b", "Draft"))
        self.assertTrue(can_read("item", ["Placement Author"], "a", "b", "Published"))
        self.assertFalse(can_read("key", ["Placement Author"], "a", "b", "Published"))
        self.assertTrue(can_read("key", ["Placement Author"], "a", "a"))
        self.assertFalse(can_read("key", ["Placement Auditor"], "a", "b"))
        self.assertTrue(can_read("key", ["Placement Publisher"], "p", "a"))
        self.assertTrue(can_read("audit", ["Placement Auditor"], "a", "b"))
        self.assertFalse(can_read("operation", ["Placement Publisher"], "p", "a"))
        self.assertFalse(can_read("item", ["Placement Auditor"], "a", "b", "Draft"))
        self.assertTrue(can_read("item", ["Placement Auditor"], "a", "b", "Published"))


if __name__ == "__main__":
    unittest.main()
