"""Native health acceptance checks values and fields, not a harmless help word."""
import copy
import json
import unittest

from tests.desk.test_rq_fallback import SITE, _FakeJob, _health_module
from tools.native.native_checks import validate_health_projection


PRIVATE_ERROR = "SYN_PRIVATE_ERROR_BODY_control_001"
PRIVATE_TRACE = "TRACEBACK MUST NOT LEAK"
PRIVATE_ARGUMENTS = "SYN_PRIVATE_JOB_ARGUMENTS_control_001"
PRIVATE_MULTILINE = 'Traceback (most recent call last):\n  File "private.py", line 1\nSYN_PRIVATE_MULTILINE_ERROR'


def health_item():
    return {"id": "SYN-JOB", "person": "SYN public job name", "detail": "queue default", "status": "failed",
            "stage": "Failed background job", "stage_definition": "The traceback stays on the native job form.",
            "next": "Open the native job form and read the traceback.", "next_role": "General Manager",
            "waiting_since": None}


class NativeHealthPrivacyTests(unittest.TestCase):
    def test_static_traceback_help_is_valid_without_private_values(self):
        items = [health_item()]
        self.assertIn("traceback", json.dumps(items).lower())  # The old broad match rejects this valid row.
        proof = validate_health_projection(items, (PRIVATE_ERROR, PRIVATE_TRACE, PRIVATE_ARGUMENTS), ("SYN-JOB",))
        self.assertTrue(proof["private_fields_absent"] and proof["private_values_absent"])
        self.assertEqual(proof["source_identities_observed"], 1)

    def test_actual_app_projection_keeps_private_sources_off_the_desk(self):
        module = _health_module(self, [_FakeJob(SITE + ":privacy", "failed", "default", "SYN public job",
                                              started_at="2026-11-05 00:00:00", ended_at="2026-11-05 00:01:00")])
        previous = module.project_rows

        def projected(desk, doctype, fields, **kwargs):
            if doctype == "Error Log":
                return [{"name": "SYN-ERROR", "method": "SYN public error method", "seen": 0,
                         "creation": "2026-11-05 00:00:00", "error": PRIVATE_ERROR}]
            return previous(desk, doctype, fields, **kwargs)

        module.project_rows = projected
        facts, items = module._system_health()
        self.assertEqual(next(row["value"] for row in facts if row["label"] == "Failed background jobs"), 1)
        self.assertIn("traceback", json.dumps(items).lower())
        validate_health_projection(items, (PRIVATE_ERROR, PRIVATE_TRACE), ("SYN-ERROR", SITE + ":privacy"))

    def test_private_native_values_are_rejected_in_every_projected_text_field(self):
        for value in (PRIVATE_ERROR, PRIVATE_TRACE, PRIVATE_ARGUMENTS, PRIVATE_MULTILINE):
            for field in health_item():
                item = health_item()
                item[field] = value
                with self.subTest(value=value, field=field), self.assertRaisesRegex(ValueError, "private native value"):
                    validate_health_projection([item], (value,))

    def test_extra_private_fields_and_nested_payloads_are_rejected(self):
        for field in ("error", "traceback", "exc_info", "arguments", "error_text", "kwargs", "_server_messages"):
            item = dict(health_item(), **{field: PRIVATE_TRACE})
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "private fields"):
                validate_health_projection([item], (PRIVATE_TRACE,))
        item = health_item()
        item["detail"] = {"error": PRIVATE_ERROR}
        with self.assertRaisesRegex(ValueError, "count-and-identity"):
            validate_health_projection([item], (PRIVATE_ERROR,))

    def test_private_source_cannot_disappear_and_make_the_control_vacuous(self):
        with self.assertRaisesRegex(ValueError, "source identities"):
            validate_health_projection([health_item()], (PRIVATE_TRACE,), ("MISSING-ERROR",))
        for bad in (None, {}, [None], [dict(health_item(), unexpected="field")]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_health_projection(copy.deepcopy(bad))

    def test_generated_alert_condition_has_no_receiver_or_delivery_action(self):
        condition = dict(health_item(), id="condition:failed_background_jobs", stage="Alert condition", status="observed",
                         stage_definition="Conditions are generated, never delivered: no alert receiver exists.")
        validate_health_projection([condition])
        for key, value in (("stage_definition", "Notification delivered to the configured receiver."),
                           ("stage_definition", "Generated, never delivered; receiver configured."),
                           ("status", "sent"), ("stage", "Notification"), ("next_role", "receiver@example.test")):
            changed = dict(condition, **{key: value})
            with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, "delivery boundary"):
                validate_health_projection([changed])
        for key in ("receiver", "recipient", "action", "endpoint"):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "private fields"):
                validate_health_projection([dict(condition, **{key: "not-authorized"})])
