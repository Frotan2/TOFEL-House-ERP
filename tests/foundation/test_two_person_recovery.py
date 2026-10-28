"""Two-person recovery authorization for migrating updates.

The schema-1 recovery document proved only that one recovery-key holder
signed two literal role strings.  These tests prove, against the real engine
and real RSA keys, that a migrating update now requires two distinct trusted
keys, bound to distinct approver identities and roles (one Course Owner, one
General Manager or designated recovery authority), signing the identical
document bytes bound to one site, operation, backup and single-use request
id, before any migration.  They run without Docker, Windows or a live site.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))
sys.path.insert(0, str(ROOT / "tests" / "foundation"))

import update_engine as engine  # noqa: E402
from test_update_engine import UpdateEngineBase  # noqa: E402


def codes(response: dict) -> set[str]:
    return {item["code"] for item in response["blockers"]}


class TwoPersonRecoveryTests(UpdateEngineBase):
    def test_two_distinct_approvals_allow_the_update(self):
        fixture = self.fixture()
        response = fixture.preflight()
        self.assertEqual(response["decision"], "allow", response["blockers"])

    def test_a_single_signature_is_refused(self):
        fixture = self.fixture()
        response = fixture.preflight(recovery_signature_2="")
        self.assertEqual(response["decision"], "refuse")
        self.assertIn("preflight.recovery.approval_missing", codes(response))

    def test_the_old_single_signature_schema_is_refused(self):
        fixture = self.fixture()
        fixture.write_recovery_authorization(mutate={
            "schema_version": 1,
            "authorized_by": "owner",
            "attested_by": "toefl-house-support",
        })
        # Remove the schema-2 approvals so the document is a genuine v1 shape.
        document = json.loads((fixture.product_root / fixture.authorization_rel).read_text())
        document.pop("approvals", None)
        document.pop("operation", None)
        document.pop("request_id", None)
        (fixture.product_root / fixture.authorization_rel).write_text(
            json.dumps(document, indent=2, sort_keys=True))
        response = fixture.preflight()
        self.assertEqual(response["decision"], "refuse")
        self.assertIn("preflight.recovery.authorization_invalid", codes(response))

    def test_self_approval_by_the_same_person_twice_is_refused(self):
        fixture = self.fixture()
        fixture.write_recovery_authorization(mutate={
            "approvals": [
                {"approver_identity": "course-owner", "approver_role": "course-owner",
                 "key_id": "support-2026a"},
                {"approver_identity": "course-owner", "approver_role": "general-manager",
                 "key_id": "manager-2026a"},
            ],
        })
        response = fixture.preflight()
        self.assertIn("preflight.recovery.approval_invalid", codes(response))

    def test_two_owners_without_an_independent_second_approver_are_refused(self):
        fixture = self.fixture()
        fixture.write_recovery_authorization(mutate={
            "approvals": [
                {"approver_identity": "course-owner", "approver_role": "course-owner",
                 "key_id": "support-2026a"},
                {"approver_identity": "other-owner", "approver_role": "course-owner",
                 "key_id": "manager-2026a"},
            ],
        })
        response = fixture.preflight()
        self.assertIn("preflight.recovery.approval_invalid", codes(response))

    def test_the_same_key_signing_both_approvals_is_refused(self):
        fixture = self.fixture()
        fixture.write_recovery_authorization(second_key=fixture.support,
                                             second_key_id="support-2026a")
        response = fixture.preflight()
        self.assertIn("preflight.recovery.approval_invalid", codes(response))

    def test_a_signature_envelope_claiming_the_wrong_approver_is_refused(self):
        fixture = self.fixture()
        # The first envelope now claims the manager's key id while carrying
        # the owner's signature: verification against the manager's key fails.
        # (Swapping the two signature files themselves is not an attack: both
        # signatures cover the identical document bytes, so file order is
        # irrelevant and the update correctly still allows.)
        first = fixture.product_root / fixture.authorization_signature_rel
        envelope = json.loads(first.read_text())
        envelope["key_id"] = "manager-2026a"
        first.write_text(json.dumps(envelope))
        response = fixture.preflight()
        # Both envelopes now claim the same key, so distinct-approver
        # validation refuses before any signature is trusted.
        self.assertIn("preflight.recovery.approval_invalid", codes(response))

    def test_an_unbound_recovery_key_does_not_count_as_an_approver(self):
        fixture = self.fixture()
        # Rewrite the trust store without approver bindings: the keys are
        # still trusted for recovery, but they no longer prove who signed.
        fixture.write_trust_store(keys=[
            fixture.signing.trust_entry("release-2026a", ("update-manifest",)),
            fixture.support.trust_entry("support-2026a", ("recovery-authorization",)),
            fixture.manager.trust_entry("manager-2026a", ("recovery-authorization",)),
        ])
        response = fixture.preflight()
        self.assertIn("preflight.recovery.approval_invalid", codes(response))

    def test_a_wrong_purpose_key_for_the_second_approval_is_refused(self):
        fixture = self.fixture()
        fixture.write_recovery_authorization(second_key=fixture.signing,
                                             second_key_id="release-2026a")
        response = fixture.preflight()
        self.assertIn("trust.key_unknown", codes(response))

    def test_an_altered_document_invalidates_both_signatures(self):
        fixture = self.fixture()
        document_path = fixture.product_root / fixture.authorization_rel
        document = json.loads(document_path.read_text())
        document["request_id"] = "c" * 32
        document_path.write_text(json.dumps(document, indent=2, sort_keys=True))
        response = fixture.preflight()
        self.assertIn("preflight.recovery.authorization_invalid", codes(response))

    def test_a_recovery_bound_to_another_operation_is_refused(self):
        fixture = self.fixture()
        fixture.write_recovery_authorization(mutate={"operation": "site-restore"})
        response = fixture.preflight()
        self.assertIn("preflight.recovery.binding_mismatch", codes(response))

    def test_a_replayed_request_id_is_refused_after_apply_consumes_it(self):
        # Use the full apply harness: a successful apply consumes both the
        # transaction and the recovery request id in the durable state dir.
        from test_update_engine import ApplyTests  # noqa: PLC0415

        apply_case = ApplyTests("test_supported_migration_runs_twice_and_preserves_all_records")
        apply_case.setUp()
        try:
            transaction = apply_case.transaction()
            report = apply_case.apply(transaction=transaction)
            self.assertEqual(report["status"], "succeeded", report["blockers"])
            # A fresh preflight in the same state dir, with the same recovery
            # document and request id, must now be refused as a replay.
            fixture = apply_case.fixture
            response = fixture.preflight()
            self.assertIn("preflight.recovery.request_replayed", codes(response))
        finally:
            # doCleanups, not tearDown: the harness is constructed manually,
            # so only doCleanups stops its host-observer patch and pops its
            # bench environment. A leaked observer patch would otherwise be
            # captured as the "real" observer by later live-host tests.
            apply_case.doCleanups()

    def test_failed_transaction_marker_cannot_leave_recovery_approval_reusable(self):
        # Simulate failure to create the second single-use marker.
        # The recovery request must already be spent, even when apply aborts
        # before migrations or the transaction marker can be written.
        fixture = self.fixture()
        transaction = {
            "transaction_id": "f" * 32,
            "target": {"version": "synthetic"},
            "evidence": {"recovery_request_id": "a" * 32},
        }
        blocked = fixture.state_dir / engine.TRANSACTION_CONSUMED_DIR
        blocked.write_text("unsafe marker directory", encoding="utf-8")
        with self.assertRaises(engine.UpdateError):
            engine._consume_transaction(fixture.state_dir, transaction)
        marker = (fixture.state_dir / engine.RECOVERY_CONSUMED_DIR
                  / ("a" * 32 + ".json"))
        self.assertTrue(marker.is_file())
        self.assertIn("preflight.recovery.request_replayed", codes(fixture.preflight()))

    def test_a_fresh_request_id_allows_a_later_update(self):
        fixture = self.fixture()
        marker = fixture.state_dir / engine.RECOVERY_CONSUMED_DIR / ("a" * 32 + ".json")
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text('{"request_id": "' + "a" * 32 + '"}\n')
        response = fixture.preflight()
        self.assertIn("preflight.recovery.request_replayed", codes(response))
        # A new request id, signed by both approvers, is a new authorization.
        fixture.write_recovery_authorization(mutate={"request_id": "d" * 32})
        response = fixture.preflight()
        self.assertEqual(response["decision"], "allow", response["blockers"])


if __name__ == "__main__":
    unittest.main()
