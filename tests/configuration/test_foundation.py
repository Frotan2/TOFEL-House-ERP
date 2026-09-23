"""Contract for the configuration foundation + the D1 reference domain.

Phase 1 pins, offline:

1. The FOUNDATION RULES — generic version primitives (monotone appends,
   governing-date resolution, strict ambiguity refusal), the mandatory
   change reason, the computed readiness model, stable version snapshots,
   hash-chain verification, and the declared authorities.
2. The D1 DOCTYPE JSONs — set-once identity, no delete for any role,
   Course-Owner-only writes, native Version audit, carrier links only
   (zero business values in structure).
3. The AUDIT LEDGER — read-only receipts and append-only events, bound to
   exactly the D1 command kinds under exactly the business_policy
   authority, with no site-mode machinery (governance boundary).
4. The D1 COMMANDS — whitelisted, request-key-first, audit-wrapped,
   Course-Owner-gated through the bound authority, consuming the pure
   rules instead of re-implementing them.
5. The TIES — Configuration desk registry/Page/hooks/projection entries
   and the dialog-signature mirroring for the D1 guided actions.
6. The HARD-CODED-POLICY EXTENSION — no assessment numeric literals in
   owned code and no policy defaults/options in the D1 structure.
7. The COMMAND-ONLY BOUNDARY — the ContextVar mechanism itself (no
   command active by default, marked inside, always reset, nesting
   restores the outer kind). The wiring — commands establish it, the
   controllers require it, native writes meet the business-language
   refusal — is pinned by the lifecycle boundary tests.
8. The D1 FACET STRUCTURES — the seven owner-defined policy facets
   (components, weights, pass rules, rubrics, progression, retakes,
   level mapping): shapes, bounds, structural vocabularies,
   cross-references and canonical storage, all without a single business
   value. Reusable policy stays separated from per-group scheduled
   plans (A-D1-1) and native weight columns are never read (A-D1-2).
"""
import ast
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "apps/toefl_house/toefl_house"
ACADEMIC = APP / "academic"
sys.path.insert(0, str(REPO / "apps/toefl_house"))
sys.path.insert(0, str(ACADEMIC))

import rules as academic_rules  # noqa: E402  (pure module, no frappe)
from toefl_house.configuration import rules as foundation  # noqa: E402


def _version(effective_from, **extra):
    row = {"effective_from": effective_from}
    row.update(extra)
    return row


def _doctype(name):
    slug = name.lower().replace(" ", "_")
    paths = list(APP.glob(f"*/doctype/{slug}/{slug}.json"))
    assert paths, f"missing DocType JSON for {name}"
    return json.loads(paths[0].read_text(encoding="utf-8"))


class FoundationVersionTests(unittest.TestCase):
    def test_academic_delegates_to_one_implementation(self):
        rows = [_version("2026-07-01"), _version("2026-01-01")]
        self.assertEqual(academic_rules.normalize_versions(rows),
                         foundation.normalize_versions(rows))
        self.assertEqual(academic_rules.resolve_duration(rows, "2026-06-01"),
                         foundation.resolve_governing(rows, "2026-06-01"))
        self.assertEqual(academic_rules.latest_version(rows),
                         foundation.latest_version(rows))

    def test_monotone_appends_name_the_domain(self):
        rows = [_version("2026-01-01")]
        with self.assertRaises(ValueError) as ctx:
            foundation.check_appends(rows, "2026-01-01",
                                     what="assessment policy version")
        self.assertIn("assessment policy version", str(ctx.exception))
        self.assertIn("2026-01-01", str(ctx.exception))
        # Strictly-later versions append cleanly.
        foundation.check_appends(rows, "2026-01-02",
                                 what="assessment policy version")
        foundation.check_appends([], "2026-01-01",
                                 what="assessment policy version")

    def test_strict_resolution_refuses_ambiguity(self):
        ambiguous = [_version("2026-01-01", reason="one"),
                     _version("2026-01-01", reason="two")]
        with self.assertRaises(ValueError) as ctx:
            foundation.resolve_governing_strict(
                ambiguous, "2026-06-01", what="assessment policy version")
        self.assertIn("ambiguous", str(ctx.exception))
        with self.assertRaises(ValueError):
            foundation.assert_no_ambiguous_versions(
                ambiguous, what="assessment policy version")

    def test_strict_resolution_matches_plain_resolution_when_sound(self):
        rows = [_version("2026-01-01"), _version("2026-07-01")]
        for on_date in ("2025-12-31", "2026-01-01", "2026-06-30",
                        "2026-07-01", "2027-01-01"):
            self.assertEqual(
                foundation.resolve_governing_strict(rows, on_date),
                foundation.resolve_governing(rows, on_date), on_date)
        self.assertIsNone(foundation.resolve_governing_strict(rows, "2025-01-01"))
        self.assertIsNone(foundation.resolve_governing_strict([], "2026-01-01"))

    def test_version_states(self):
        self.assertEqual(
            foundation.version_state(_version("2026-01-01"), "2026-06-01"),
            "effective")
        self.assertEqual(
            foundation.version_state(_version("2027-01-01"), "2026-06-01"),
            "scheduled")
        self.assertEqual(
            foundation.version_state(_version("2026-01-01", superseded_on="2026-07-01"),
                                     "2026-06-01"),
            "superseded")


class ChangeReasonTests(unittest.TestCase):
    def test_reason_is_mandatory(self):
        for bad in ("", "   ", None, 7):
            with self.assertRaises(ValueError, msg=repr(bad)):
                foundation.validate_change_reason(bad)
        self.assertEqual(foundation.validate_change_reason("  term rollover  "),
                         "term rollover")
        with self.assertRaises(ValueError):
            foundation.validate_change_reason("x" * 501)


class ReadinessTests(unittest.TestCase):
    def test_retired_is_terminal(self):
        rows = [_version("2026-01-01")]
        digest = foundation.snapshot_digest(rows)
        self.assertEqual(
            foundation.compute_readiness(
                status="Retired", versions=rows,
                validations=[{"after_hash": digest}], today="2026-06-01"),
            "retired")

    def test_unknown_status_fails_closed(self):
        with self.assertRaises(ValueError):
            foundation.compute_readiness(
                status="Draft", versions=[_version("2026-01-01")],
                validations=[], today="2026-06-01")

    def test_incomplete_without_versions(self):
        self.assertEqual(
            foundation.compute_readiness(
                status="Active", versions=[], validations=[],
                today="2026-06-01"),
            "incomplete")

    def test_configured_without_current_validation(self):
        rows = [_version("2026-01-01")]
        self.assertEqual(
            foundation.compute_readiness(
                status="Active", versions=rows, validations=[],
                today="2026-06-01"),
            "configured")
        # A stale validation (older snapshot) does not count.
        stale = foundation.snapshot_digest([_version("2025-01-01")])
        self.assertEqual(
            foundation.compute_readiness(
                status="Active", versions=rows,
                validations=[{"after_hash": stale}], today="2026-06-01"),
            "configured")

    def test_validated_when_nothing_governs_yet(self):
        rows = [_version("2027-01-01")]
        digest = foundation.snapshot_digest(rows)
        self.assertEqual(
            foundation.compute_readiness(
                status="Active", versions=rows,
                validations=[{"after_hash": digest}], today="2026-06-01"),
            "validated")

    def test_effective_when_validated_and_governing(self):
        rows = [_version("2026-01-01")]
        digest = foundation.snapshot_digest(rows)
        self.assertEqual(
            foundation.compute_readiness(
                status="Active", versions=rows,
                validations=[{"after_hash": digest}], today="2026-06-01"),
            "effective")

    def test_new_version_returns_a_validated_policy_to_configured(self):
        old = [_version("2026-01-01")]
        digest = foundation.snapshot_digest(old)
        new = old + [_version("2027-01-01")]
        self.assertEqual(
            foundation.compute_readiness(
                status="Active", versions=old,
                validations=[{"after_hash": digest}], today="2026-06-01"),
            "effective")
        self.assertEqual(
            foundation.compute_readiness(
                status="Active", versions=new,
                validations=[{"after_hash": digest}], today="2026-06-01"),
            "configured")

    def test_ambiguity_fails_closed_before_any_state(self):
        ambiguous = [_version("2026-01-01"), _version("2026-01-01")]
        with self.assertRaises(ValueError):
            foundation.compute_readiness(
                status="Active", versions=ambiguous, validations=[],
                today="2026-06-01")


class SnapshotTests(unittest.TestCase):
    def test_snapshot_is_stable_and_meaning_sensitive(self):
        rows = [_version("2026-01-01", grading_scale="GS",
                         set_by="owner@example.com", name="ROW-1", idx=1,
                         parent="P", parenttype="T", docstatus=0,
                         creation="2026-01-01", modified="2026-01-02",
                         owner="x", modified_by="y")]
        reordered = [dict(reversed(list(row.items()))) for row in rows]
        self.assertEqual(foundation.snapshot_digest(rows),
                         foundation.snapshot_digest(reordered))
        changed = [dict(row, grading_scale="OTHER") for row in rows]
        self.assertNotEqual(foundation.snapshot_digest(rows),
                            foundation.snapshot_digest(changed))
        # Identity/bookkeeping columns never affect the fingerprint.
        renamed = [dict(row, name="ROW-9", idx=9) for row in rows]
        self.assertEqual(foundation.snapshot_digest(rows),
                         foundation.snapshot_digest(renamed))
        # Unset reads as unset regardless of representation.
        none_row = [_version("2026-01-01", grading_scale=None)]
        empty_row = [_version("2026-01-01", grading_scale="")]
        missing_row = [_version("2026-01-01")]
        self.assertEqual(foundation.snapshot_digest(none_row),
                         foundation.snapshot_digest(empty_row))
        self.assertEqual(foundation.snapshot_digest(none_row),
                         foundation.snapshot_digest(missing_row))

    def test_empty_snapshot_is_stable(self):
        self.assertEqual(foundation.snapshot_digest([]),
                         foundation.snapshot_digest([]))


class ChainTests(unittest.TestCase):
    def _event(self, target, before, after):
        return {"target": target, "before_hash": before, "after_hash": after}

    def test_valid_chains_verify(self):
        events = [self._event("P1", "", "a1"),
                  self._event("P1", "a1", "a2"),
                  self._event("P2", "", "b1"),
                  self._event("P1", "a2", "a3")]
        self.assertEqual(foundation.verify_chain(events), 4)
        self.assertEqual(foundation.verify_chain([]), 0)

    def test_broken_chain_names_the_target(self):
        events = [self._event("P1", "", "a1"),
                  self._event("P1", "tampered", "a2")]
        with self.assertRaises(ValueError) as ctx:
            foundation.verify_chain(events)
        self.assertIn("P1", str(ctx.exception))

    def test_missing_after_hash_refuses(self):
        with self.assertRaises(ValueError):
            foundation.verify_chain([self._event("P1", "", "")])
        with self.assertRaises(ValueError):
            foundation.verify_chain([self._event("", "", "a1")])


class AuthorityTests(unittest.TestCase):
    def test_business_policy_is_bound_to_course_owner(self):
        self.assertEqual(foundation.authority_roles("business_policy"),
                         ("Course Owner",))
        self.assertEqual(foundation.require_bound_authority("business_policy"),
                         ("Course Owner",))

    def test_operations_is_unbound_and_refuses(self):
        self.assertEqual(foundation.authority_roles("operations"), ())
        with self.assertRaises(ValueError) as ctx:
            foundation.require_bound_authority("operations")
        self.assertIn("not bound", str(ctx.exception))

    def test_custody_never_binds_to_frappe(self):
        with self.assertRaises(ValueError) as ctx:
            foundation.require_bound_authority("custody")
        self.assertIn("never acts through Frappe", str(ctx.exception))

    def test_unknown_authority_refuses(self):
        with self.assertRaises(ValueError):
            foundation.require_bound_authority("treasury")


class AssessmentPolicyContractTests(unittest.TestCase):
    POLICY = "TH Assessment Policy"
    VERSION = "TH Assessment Policy Version"

    def test_doctype_directories_are_complete(self):
        for slug in ("th_assessment_policy", "th_assessment_policy_version"):
            directory = ACADEMIC / "doctype" / slug
            for expected in (directory / f"{slug}.json",
                             directory / f"{slug}.py",
                             directory / "__init__.py"):
                self.assertTrue(expected.exists(), f"missing {expected}")

    def test_identity_permissions_and_audit(self):
        policy = _doctype(self.POLICY)
        self.assertEqual(policy["module"], "Academic")
        self.assertEqual(policy["autoname"], "field:code")
        self.assertEqual(policy["track_changes"], 1,
                         "native Version audit must be on")
        fields = {row["fieldname"]: row for row in policy["fields"]}
        self.assertEqual(fields["code"].get("set_only_once"), 1)
        self.assertEqual(fields["code"].get("unique"), 1)
        self.assertEqual(fields["family"].get("set_only_once"), 1)
        self.assertEqual(fields["versions"]["fieldtype"], "Table")
        self.assertEqual(fields["versions"]["options"], self.VERSION)
        owners = [row for row in policy["permissions"]
                  if row["role"] == "Course Owner"]
        self.assertEqual(len(owners), 1)
        self.assertEqual(owners[0].get("write"), 1)
        self.assertEqual(owners[0].get("create"), 1)
        for row in policy["permissions"]:
            for denied in ("delete", "cancel", "submit"):
                self.assertIsNone(row.get(denied),
                                  f"{row['role']} must not hold {denied}")
            if row["role"] != "Course Owner":
                self.assertIsNone(row.get("write"),
                                  f"{row['role']} must be read-only")
                self.assertIsNone(row.get("create"),
                                  f"{row['role']} must be read-only")

    def test_version_rows_carry_scale_link_and_facet_structures(self):
        version = _doctype(self.VERSION)
        self.assertEqual(version.get("istable"), 1)
        fields = {row["fieldname"]: row for row in version["fields"]}
        self.assertEqual(fields["effective_from"]["fieldtype"], "Date")
        self.assertEqual(fields["effective_from"].get("reqd"), 1)
        self.assertEqual(fields["reason"].get("reqd"), 1,
                         "the change reason is mandatory on every version")
        self.assertEqual(fields["grading_scale"]["fieldtype"], "Link")
        self.assertEqual(fields["grading_scale"]["options"], "Grading Scale")
        self.assertNotIn("assessment_plan", fields,
                         "A-D1-1: per-group scheduled plans are instances, "
                         "never reusable policy references")
        facets = ("components", "weights", "pass_rules", "rubrics",
                  "progression", "retakes", "level_mapping")
        for facet in facets:
            self.assertEqual(fields[facet]["fieldtype"], "Long Text", facet)
        for optional in ("grading_scale", "set_by", "set_on",
                         "superseded_on") + facets:
            self.assertIsNone(fields[optional].get("reqd"),
                              f"{optional} must stay optional (structure only)")
        # Zero business values in structure: no defaults on any value
        # field, no Select options encoding policy.
        for name, field in fields.items():
            self.assertIsNone(field.get("default"),
                              f"{name} must carry no default value")
        for name, field in fields.items():
            if field.get("fieldtype") == "Select":
                self.fail(f"{name} encodes policy as Select options")

    def test_controller_classes_exist(self):
        for slug, classname in (
                ("th_assessment_policy", "THAssessmentPolicy"),
                ("th_assessment_policy_version", "THAssessmentPolicyVersion")):
            source = (ACADEMIC / "doctype" / slug / f"{slug}.py").read_text(
                encoding="utf-8")
            tree = ast.parse(source)
            classes = [node.name for node in ast.walk(tree)
                       if isinstance(node, ast.ClassDef)]
            self.assertIn(classname, classes,
                          "migrate drops DocTypes without a controller class")
        parent = (ACADEMIC / "doctype/th_assessment_policy/"
                  "th_assessment_policy.py").read_text(encoding="utf-8")
        for literal in ("validate_change_reason",
                        "cannot share one effective date",
                        "must fall after its effective date"):
            self.assertIn(literal, parent)


class ConfigurationAuditContractTests(unittest.TestCase):
    OPERATION = "TH Configuration Operation"
    AUDIT = "TH Configuration Audit Event"

    def test_ledger_doctypes_are_read_only_and_untracked(self):
        for name in (self.OPERATION, self.AUDIT):
            definition = _doctype(name)
            self.assertEqual(definition["module"], "Operations")
            self.assertEqual(definition.get("track_changes"), 0,
                             "immutable receipts/events need no Version noise")
            self.assertTrue(definition["permissions"],
                            "readership must be explicit")
            for row in definition["permissions"]:
                for denied in ("write", "create", "delete", "cancel",
                               "submit"):
                    self.assertIsNone(row.get(denied),
                                      f"{name}: {row['role']} holds {denied}")

    def test_operation_shape(self):
        operation = _doctype(self.OPERATION)
        self.assertEqual(operation["autoname"], "prompt",
                         "receipt names are idempotency digests")
        fields = {row["fieldname"]: row for row in operation["fields"]}
        for required in ("kind", "actor", "input_hash", "status"):
            self.assertEqual(fields[required].get("reqd"), 1, required)
        self.assertEqual(fields["status"]["options"], "Applying\nComplete")

    def test_audit_event_shape(self):
        event = _doctype(self.AUDIT)
        fields = {row["fieldname"]: row for row in event["fields"]}
        for required in ("actor", "operation", "action", "target",
                         "after_hash"):
            self.assertEqual(fields[required].get("reqd"), 1, required)
        self.assertEqual(fields["operation"]["options"], self.OPERATION)
        self.assertNotIn("synthetic", fields,
                         "governance audit is not site-mode stamped")

    def test_controllers_keep_the_ledger_append_only(self):
        base = APP / "operations/doctype"
        operation = (base / "th_configuration_operation/"
                     "th_configuration_operation.py").read_text(encoding="utf-8")
        self.assertIn("Completed configuration operation receipts are immutable",
                      operation)
        event = (base / "th_configuration_audit_event/"
                 "th_configuration_audit_event.py").read_text(encoding="utf-8")
        self.assertIn("Configuration audit events are append-only", event)

    def test_kinds_bind_exactly_the_d1_commands_to_business_policy(self):
        # S5: the twelve academic catalog commands join the eleven D1
        # commands on the same business_policy (Course Owner) authority.
        source = (APP / "configuration/audit.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        kinds = None
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign)
                    and getattr(node.targets[0], "id", "") == "KIND_AUTHORITY"):
                kinds = ast.literal_eval(node.value)
        self.assertEqual(kinds, {
            "create_assessment_policy": "business_policy",
            "set_assessment_policy_version": "business_policy",
            "set_assessment_policy_status": "business_policy",
            "validate_assessment_policy": "business_policy",
            "set_assessment_components": "business_policy",
            "set_assessment_weights": "business_policy",
            "set_assessment_pass_rules": "business_policy",
            "set_assessment_rubrics": "business_policy",
            "set_assessment_progression": "business_policy",
            "set_assessment_retakes": "business_policy",
            "set_assessment_mapping": "business_policy",
            "create_program": "business_policy",
            "create_level": "business_policy",
            "set_level_duration": "business_policy",
            "set_next_level": "business_policy",
            "set_program_status": "business_policy",
            "set_level_status": "business_policy",
            "create_academic_year": "business_policy",
            "create_fee_type": "business_policy",
            "set_level_fee_component": "business_policy",
            "remove_level_fee_component": "business_policy",
            "create_discount_rule": "business_policy",
            "set_discount_rule_status": "business_policy",
            "create_returning_student_policy": "business_policy",
            "set_returning_student_policy_version": "business_policy",
            "set_returning_student_policy_status": "business_policy",
            "create_roster_change_policy": "business_policy",
            "set_roster_change_policy_version": "business_policy",
            "set_roster_change_policy_status": "business_policy",
            "create_attendance_correction_policy": "business_policy",
            "set_attendance_correction_policy_version": "business_policy",
            "set_attendance_correction_policy_status": "business_policy",
            "create_enrollment_exit_policy": "business_policy",
            "set_enrollment_exit_policy_version": "business_policy",
            "set_enrollment_exit_policy_status": "business_policy",
        })

    def test_audit_reuses_the_command_pattern_without_site_gates(self):
        source = (APP / "configuration/audit.py").read_text(encoding="utf-8")
        for literal in ("run_with_retry", "request_digest", "digest([kind, request_key])",
                        "Idempotency key conflicts with an existing request",
                        "DuplicateEntryError",
                        "Configuration audit requires a target and an after-hash"):
            self.assertIn(literal, source)
        for banned in ("require_synthetic", "require_operational",
                       "record_synthetic_flag", "site_mode"):
            self.assertNotIn(banned, source,
                             "configuration audit is governance, not site-gated")


class D1CommandContractTests(unittest.TestCase):
    COMMANDS = {
        "create_assessment_policy": ["request_key", "family", "code",
                                     "title", "description"],
        "set_assessment_policy_version": ["request_key", "policy",
                                          "effective_from", "reason",
                                          "grading_scale"],
        "set_assessment_policy_status": ["request_key", "policy", "active"],
        "validate_assessment_policy": ["request_key", "policy"],
        "set_assessment_components": ["request_key", "policy",
                                      "effective_from", "reason",
                                      "components"],
        "set_assessment_weights": ["request_key", "policy", "effective_from",
                                   "reason", "weights"],
        "set_assessment_pass_rules": ["request_key", "policy",
                                      "effective_from", "reason",
                                      "pass_rules"],
        "set_assessment_rubrics": ["request_key", "policy", "effective_from",
                                   "reason", "rubrics"],
        "set_assessment_progression": ["request_key", "policy",
                                       "effective_from", "reason",
                                       "progression"],
        "set_assessment_retakes": ["request_key", "policy", "effective_from",
                                   "reason", "retakes"],
        "set_assessment_mapping": ["request_key", "policy", "effective_from",
                                   "reason", "mapping"],
    }

    @classmethod
    def setUpClass(cls):
        cls.source = (ACADEMIC / "__init__.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.functions = {node.name: node for node in ast.walk(cls.tree)
                         if isinstance(node, ast.FunctionDef)}

    def test_commands_are_whitelisted_post_and_request_key_first(self):
        for name, signature in self.COMMANDS.items():
            node = self.functions[name]
            decorated = any("whitelist" in ast.unparse(dec)
                            for dec in node.decorator_list)
            self.assertTrue(decorated, f"{name} must be whitelisted")
            position = self.source.index(f"def {name}")
            window = self.source[max(0, position - 200):position]
            self.assertIn("@frappe.whitelist", window)
            self.assertIn('methods=["POST"]', window,
                          f"{name} mutates and must stay POST-only")
            args = [arg.arg for arg in node.args.args]
            self.assertEqual(args, signature,
                             f"{name} signature drift (dialogs mirror it)")

    def test_commands_run_inside_the_audited_execute(self):
        for name in self.COMMANDS:
            self.assertIn(
                f'configuration_audit.execute(\n        "{name}", request_key',
                self.source, f"{name} must run inside the audited execute")

    def test_commands_consume_the_pure_rules(self):
        for literal in ("rules.validate_code",
                        "rules.parse_date",
                        "rules.canonical_facet",
                        "rules.validate_policy_facets",
                        "configuration_rules.validate_change_reason",
                        "configuration_rules.check_appends",
                        "configuration_rules.snapshot_digest",
                        "configuration_rules.compute_readiness",
                        "configuration_audit.latest_after_hash"):
            self.assertIn(literal, self.source,
                          f"commands must reuse {literal}")

    def test_commands_row_lock_and_stay_governance(self):
        for name in ("create_assessment_policy",
                     "set_assessment_policy_version",
                     "set_assessment_policy_status",
                     "set_assessment_components",
                     "set_assessment_weights",
                     "set_assessment_pass_rules",
                     "set_assessment_rubrics",
                     "set_assessment_progression",
                     "set_assessment_retakes",
                     "set_assessment_mapping"):
            body = ast.unparse(self.functions[name])
            self.assertIn("for_update=True", body,
                          f"{name} mutations must row-lock the target")
        for banned in ("require_synthetic", "require_operational",
                       "ignore_links=True"):
            self.assertNotIn(banned, self.source,
                             "D1 commands are governance; native link checks stay on")


class ConfigurationNavigationTests(unittest.TestCase):
    def test_desk_registry_page_hooks_and_client_agree(self):
        init_source = (APP / "desk/__init__.py").read_text(encoding="utf-8")
        self.assertIn('"th-configuration"', init_source)
        self.assertIn('"configuration"', init_source)
        page = json.loads((APP / "operations/page/th-configuration/"
                           "th-configuration.json").read_text(encoding="utf-8"))
        self.assertEqual(page["doctype"], "Page")
        self.assertEqual(page["module"], "Operations")
        self.assertEqual(page["title"], "TOEFL House Configuration")
        self.assertEqual([row["role"] for row in page["roles"]],
                         ["Course Owner"])
        self.assertEqual(page.get("standard"), "Yes")
        hooks = (APP / "hooks.py").read_text(encoding="utf-8")
        self.assertIn('"th-configuration"', hooks)
        client = (APP / "public/js/th_role_desks.js").read_text(encoding="utf-8")
        self.assertIn('"th-configuration"', client)
        self.assertIn('"toefl_house.desk.configuration.work"', client)
        for pair in (('("configuration", "TH Assessment Policy")',),
                     ('("configuration", "TH Assessment Policy Version")',),
                     ('("configuration", "TH Configuration Audit Event")',),
                     ('("setup", "TH Assessment Policy")',),
                     ('("setup", "TH Assessment Policy Version")',),
                     ('("setup", "TH Configuration Audit Event")',)):
            self.assertIn(pair[0], init_source,
                          f"missing projection allow-list {pair[0]}")

    def test_configuration_desk_is_a_read_only_map(self):
        source = (APP / "desk/configuration.py").read_text(encoding="utf-8")
        self.assertIn("@frappe.whitelist", source)
        self.assertIn('methods=["GET", "POST"]', source)
        self.assertNotIn("allow_guest", source)
        self.assertIn("require_desk_audience(SLUG)", source)
        self.assertIn("compute_readiness", source,
                      "readiness must be computed, never stored")
        for banned in ("guided_action", "get_doc", "insert(", "save(",
                       ".write(", "frappe.db.set_value"):
            self.assertNotIn(banned, source,
                             "the map desk configures nothing")
        self.assertIn("never decided here", source)

    def test_dialog_fields_mirror_the_d1_signatures(self):
        client = (APP / "public/js/th_role_desks.js").read_text(encoding="utf-8")
        expected = {
            "toefl_house.academic.create_assessment_policy":
                ["family", "code", "title", "description"],
            "toefl_house.academic.set_assessment_policy_version":
                ["policy", "effective_from", "reason", "grading_scale"],
            "toefl_house.academic.set_assessment_policy_status":
                ["policy", "active"],
            "toefl_house.academic.validate_assessment_policy": ["policy"],
            "toefl_house.academic.set_assessment_components":
                ["policy", "effective_from", "reason", "components"],
            "toefl_house.academic.set_assessment_weights":
                ["policy", "effective_from", "reason", "weights"],
            "toefl_house.academic.set_assessment_pass_rules":
                ["policy", "effective_from", "reason", "pass_rules"],
            "toefl_house.academic.set_assessment_rubrics":
                ["policy", "effective_from", "reason", "rubrics"],
            "toefl_house.academic.set_assessment_progression":
                ["policy", "effective_from", "reason", "progression"],
            "toefl_house.academic.set_assessment_retakes":
                ["policy", "effective_from", "reason", "retakes"],
            "toefl_house.academic.set_assessment_mapping":
                ["policy", "effective_from", "reason", "mapping"],
        }
        import re
        for endpoint, fields in expected.items():
            match = re.search(
                r'"' + endpoint + r'": \[(.*?)\],\n', client, re.S)
            self.assertTrue(match, f"{endpoint} missing from the desk client")
            found = re.findall(r"fieldname: \"(\w+)\"", match.group(1))
            self.assertEqual(found, fields,
                             f"{endpoint} dialog drift from the signature")

    def test_setup_grading_consumes_the_foundation(self):
        source = (APP / "desk/setup.py").read_text(encoding="utf-8")
        self.assertIn("configuration_rules.compute_readiness", source)
        self.assertIn("configuration_rules.resolve_governing", source)
        self.assertIn('"toefl_house.academic.create_assessment_policy"',
                      source)
        self.assertIn("Integrity fault", source)


class FoundationHardCodedPolicyTests(unittest.TestCase):
    """No assessment policy literals in owned code or structure."""

    def test_no_owned_python_module_contains_assessment_numeric_policy(self):
        import re
        offenders = []
        pattern = re.compile(
            r"(pass_mark|cutoff|threshold|grade|weight|retake)[a-z_]*\s*=\s*[0-9]",
            re.IGNORECASE)
        for path in APP.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            for match in pattern.finditer(
                    path.read_text(encoding="utf-8", errors="ignore")):
                offenders.append((str(path), match.group(0)))
        self.assertEqual(offenders, [],
                         "hard-coded assessment policy found (D1 values may "
                         "only ever be entered through guarded commands)")

    def test_d1_structure_carries_zero_business_values(self):
        policy = _doctype("TH Assessment Policy")
        version = _doctype("TH Assessment Policy Version")
        for field in policy["fields"] + version["fields"]:
            if field.get("fieldname") == "status":
                continue  # Active default: a state-machine default, not policy
            self.assertIsNone(field.get("default"),
                              f"{field['fieldname']} must carry no default")
        for field in version["fields"]:
            self.assertNotEqual(field.get("fieldtype"), "Select",
                                "no Select-encoded policy on version rows")


class CommandOnlyBoundaryTests(unittest.TestCase):
    """The command-only mechanism: marked inside commands, absent outside."""

    def test_no_command_is_active_by_default(self):
        self.assertIsNone(foundation.active_command())
        with self.assertRaises(ValueError) as ctx:
            foundation.assert_command_context("business-language refusal")
        self.assertEqual(str(ctx.exception), "business-language refusal")

    def test_context_marks_the_command_and_always_resets(self):
        with foundation.command_context("set_assessment_policy_version"):
            self.assertEqual(foundation.active_command(),
                             "set_assessment_policy_version")
        self.assertIsNone(foundation.active_command())
        # A failing command must not leak its context into later writes.
        with self.assertRaises(RuntimeError):
            with foundation.command_context("create_assessment_policy"):
                raise RuntimeError("boom")
        self.assertIsNone(foundation.active_command())

    def test_nested_contexts_restore_the_outer_command(self):
        with foundation.command_context("outer"):
            with foundation.command_context("inner"):
                self.assertEqual(foundation.active_command(), "inner")
            self.assertEqual(foundation.active_command(), "outer")
        self.assertIsNone(foundation.active_command())


class D1FacetValidationTests(unittest.TestCase):
    """Facet shapes, bounds, vocabularies and canonical storage.

    Structures only: every literal below is test scaffolding for shape
    validation, never a business value, and the hard-coded-policy test
    keeps it that way.
    """

    COMPONENTS = [
        {"code": "SPK", "title": "Speaking", "maximum_score": 25,
         "criteria": "Speaking"},
        {"code": "WRT", "title": "Writing", "maximum_score": 25},
    ]

    def test_components_shape_and_canonical_form(self):
        import json
        stored = academic_rules.canonical_facet("components", self.COMPONENTS)
        self.assertEqual(json.loads(stored), [
            {"code": "SPK", "criteria": "Speaking",
             "maximum_score": 25.0, "title": "Speaking"},
            {"code": "WRT", "maximum_score": 25.0, "title": "Writing"},
        ])
        # Key order in input does not affect the stored form (list order
        # is meaning and is preserved).
        shuffled = [{"maximum_score": 25, "code": "SPK", "title": "Speaking",
                     "criteria": "Speaking"},
                    {"title": "Writing", "maximum_score": 25,
                     "code": "WRT"}]
        self.assertEqual(
            academic_rules.canonical_facet("components", shuffled), stored)

    def test_components_refuse_bad_shapes(self):
        for bad in ("not json", 7, {"code": "SPK"}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                academic_rules.canonical_facet("components", bad)
        with self.assertRaises(ValueError):
            academic_rules.canonical_facet(
                "components", [{"code": "SPK", "title": "S",
                               "maximum_score": 25, "typo": 1}])
        with self.assertRaises(ValueError):
            academic_rules.canonical_facet(
                "components", [{"code": "SPK", "title": "One",
                                "maximum_score": 25},
                               {"code": "SPK", "title": "Two",
                                "maximum_score": 25}])
        for score in (0, -5, "25", None):
            with self.assertRaises(ValueError, msg=repr(score)):
                academic_rules.canonical_facet(
                    "components", [{"code": "SPK", "title": "Speaking",
                                    "maximum_score": score}])

    def test_absent_and_withdrawn_facets_normalize_to_empty(self):
        for facet, empty in (("components", []), ("weights", []),
                             ("pass_rules", {}), ("rubrics", []),
                             ("progression", {}), ("retakes", {}),
                             ("level_mapping", {})):
            for raw in (None, "", empty):
                self.assertEqual(
                    academic_rules.canonical_facet(facet, raw), "",
                    f"{facet} {raw!r} must normalize to absent")

    def test_weights_reference_defined_components(self):
        stored = academic_rules.canonical_facet(
            "weights", [{"component": "SPK", "weight": 3},
                        {"component": "WRT", "weight": 1}],
            self.COMPONENTS)
        import json
        self.assertEqual(json.loads(stored), [
            {"component": "SPK", "weight": 3.0},
            {"component": "WRT", "weight": 1.0}])
        with self.assertRaises(ValueError):
            academic_rules.canonical_facet(
                "weights", [{"component": "SPK", "weight": 1}], None)
        with self.assertRaises(ValueError):
            academic_rules.canonical_facet(
                "weights", [{"component": "NOPE", "weight": 1}],
                self.COMPONENTS)
        with self.assertRaises(ValueError):
            academic_rules.canonical_facet(
                "weights", [{"component": "SPK", "weight": -1}],
                self.COMPONENTS)
        with self.assertRaises(ValueError):
            academic_rules.canonical_facet(
                "weights", [{"component": "SPK", "weight": 1},
                            {"component": "SPK", "weight": 2}],
                self.COMPONENTS)

    def test_pass_rules_accept_percent_or_grade_minima(self):
        payload = {
            "components": [
                {"component": "SPK",
                 "minimum": {"kind": "percent", "value": 60}},
                {"component": "WRT",
                 "minimum": {"kind": "grade", "value": "B"}}],
            "overall": {"kind": "percent", "value": 50},
        }
        import json
        stored = academic_rules.canonical_facet(
            "pass_rules", payload, self.COMPONENTS)
        self.assertEqual(json.loads(stored)["overall"],
                         {"kind": "percent", "value": 50.0})
        overall_only = academic_rules.canonical_facet(
            "pass_rules", {"overall": {"kind": "grade", "value": "C"}},
            self.COMPONENTS)
        self.assertEqual(json.loads(overall_only)["components"], [])
        for bad in ({"components": [], "overall": None},
                    {"components": []},
                    {"components": [
                        {"component": "SPK",
                         "minimum": {"kind": "stars", "value": 3}}]},
                    {"components": [
                        {"component": "SPK",
                         "minimum": {"kind": "percent", "value": 101}}]},
                    {"components": [
                        {"component": "NOPE",
                         "minimum": {"kind": "percent", "value": 10}}]},
                    {"components": [], "overall": {"kind": "grade"}}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                academic_rules.canonical_facet(
                    "pass_rules", bad, self.COMPONENTS)

    def test_rubrics_require_evidence_and_unique_codes(self):
        payload = [{"code": "SPK-R1", "title": "Speaking fluency",
                    "component": "SPK",
                    "evidence": ["recorded sample", "assessor notes"],
                    "levels": [{"code": "L1", "title": "Basic",
                                "description": "hesitant"}]}]
        import json
        stored = academic_rules.canonical_facet(
            "rubrics", payload, self.COMPONENTS)
        self.assertEqual(len(json.loads(stored)), 1)
        for bad in ([{"code": "R1", "title": "T",
                      "evidence": []}],
                    [{"code": "R1", "title": "T"}],
                    [{"code": "R1", "title": "T",
                      "component": "NOPE", "evidence": ["x"]}],
                    [{"code": "R1", "title": "T", "evidence": ["x"]},
                     {"code": "R1", "title": "U", "evidence": ["y"]}],
                    [{"code": "R1", "title": "T", "evidence": ["x"],
                      "levels": [{"code": "L1", "title": "A"},
                                 {"code": "L1", "title": "B"}]}]):
            with self.assertRaises(ValueError, msg=repr(bad)):
                academic_rules.canonical_facet(
                    "rubrics", bad, self.COMPONENTS)

    def test_progression_evidence_kinds_and_target(self):
        payload = {"target": "next",
                   "requires": [
                       {"kind": "assessment_pass", "policy": "ASM-GEN"},
                       {"kind": "attendance", "minimum_percent": 80},
                       {"kind": "approval", "role": "Academic Manager"}]}
        import json
        stored = academic_rules.canonical_facet("progression", payload)
        self.assertEqual(json.loads(stored)["target"], "next")
        explicit = academic_rules.canonical_facet(
            "progression", {"target": "PREP-1",
                            "requires": [{"kind": "approval",
                                          "role": "General Manager"}]})
        self.assertEqual(json.loads(explicit)["target"], "PREP-1")
        for bad in ({"target": "next", "requires": []},
                    {"target": "next"},
                    {"requires": [{"kind": "approval",
                                   "role": "Academic Manager"}]},
                    {"target": "next",
                     "requires": [{"kind": "lottery"}]},
                    {"target": "next",
                     "requires": [{"kind": "attendance",
                                   "minimum_percent": 120}]},
                    {"target": "next",
                     "requires": [{"kind": "assessment_pass"}]}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                academic_rules.canonical_facet("progression", bad)

    def test_retakes_are_all_explicit(self):
        import json
        stored = academic_rules.canonical_facet(
            "retakes", {"max_attempts": 2, "wait_days": 7,
                        "scope": "full", "governing": "latest"})
        self.assertEqual(json.loads(stored)["wait_days"], 7)
        unlimited = academic_rules.canonical_facet(
            "retakes", {"max_attempts": None, "wait_days": 0,
                        "scope": "partial", "governing": "best"})
        self.assertIsNone(json.loads(unlimited)["max_attempts"])
        base = {"max_attempts": 2, "wait_days": 7, "scope": "full",
                "governing": "latest"}
        for key in base:
            partial = {other: base[other] for other in base if other != key}
            with self.assertRaises(ValueError, msg=key):
                academic_rules.canonical_facet("retakes", partial)
        for bad in (dict(base, max_attempts=0),
                    dict(base, wait_days=-1),
                    dict(base, wait_days=1.5),
                    dict(base, scope="sometimes"),
                    dict(base, governing="loudest"),
                    dict(base, max_attempts=True)):
            with self.assertRaises(ValueError, msg=repr(bad)):
                academic_rules.canonical_facet("retakes", bad)

    def test_level_mapping_is_an_explicit_code_list(self):
        import json
        stored = academic_rules.canonical_facet(
            "level_mapping", {"levels": ["PREP-1", "GEN-A1"]})
        self.assertEqual(json.loads(stored),
                         {"levels": ["PREP-1", "GEN-A1"]})
        empty = academic_rules.canonical_facet(
            "level_mapping", {"levels": []})
        self.assertEqual(json.loads(empty), {"levels": []})
        for bad in ({"levels": ["PREP-1", "PREP-1"]},
                    {"levels": "PREP-1"},
                    {"levels": ["x"]},
                    {"stages": []}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                academic_rules.canonical_facet("level_mapping", bad)

    def test_policy_facets_validate_coherently_per_row(self):
        row = {"components": academic_rules.canonical_facet(
                   "components", self.COMPONENTS),
               "weights": academic_rules.canonical_facet(
                   "weights", [{"component": "SPK", "weight": 1}],
                   self.COMPONENTS)}
        parsed = academic_rules.validate_policy_facets(row)
        self.assertEqual(set(parsed), {"components", "weights"})
        self.assertEqual(academic_rules.validate_policy_facets({}), {})
        with self.assertRaises(ValueError):
            academic_rules.validate_policy_facets({"weights": "[oops"})
        with self.assertRaises(ValueError):
            academic_rules.validate_policy_facets(
                {"weights": academic_rules.canonical_facet(
                    "weights", [{"component": "SPK", "weight": 1}],
                    self.COMPONENTS)})

    def test_owned_code_never_reads_native_weight_columns(self):
        offenders = []
        for path in APP.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in ("Course Assessment Criteria",
                           "get_assessment_criteria"):
                if marker in text:
                    offenders.append((str(path), marker))
        self.assertEqual(offenders, [],
                         "A-D1-2: owned code must never read native weight "
                         "columns; weighting is the owned weights facet")


if __name__ == "__main__":
    unittest.main()
