"""New Owner authorization/host binding only; no live ERP and no key creation.

The already tested RSA primitive is replaced by a deterministic byte-digest
stub here. This suite tests the NEW policy, document, evidence and transaction
dispatch, including signature-byte changes, without generating any RSA key.
Real CNG-signed release packet verification remains an integration check.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import itertools
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from datetime import timedelta
from unittest.mock import patch
import zipfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("owner_update_shared_fixture", HERE / "test_update_engine.py")
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
engine = shared.engine
NOW = shared.NOW
iso = shared.iso
SID = "S-1-5-21-100-200-300-1001"
OWNER = "owner@example.invalid"
THUMB = "C" * 40
KEY = "owner-existing-publisher"


class DigestStubKey:
    """A public-number fixture, not an RSA key pair or production signature."""
    def __init__(self, directory, name):
        self.modulus = (1 << 2047) + int.from_bytes(hashlib.sha256(name.encode()).digest(), "big")
        self.exponent = 65537

    def sign(self, raw):
        return hashlib.sha256(raw).digest()

    def trust_entry(self, key_id, purposes, **unused):
        return {"key_id": key_id, "algorithm": "rsa-pkcs1v15-sha256", "purposes": list(purposes),
                "modulus_b64": base64.b64encode(self.modulus.to_bytes(256, "big")).decode(),
                "exponent_b64": "AQAB", "not_before_utc": iso(NOW - timedelta(days=1)),
                "not_after_utc": iso(NOW + timedelta(days=365))}


class OwnerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="th-owner-policy-unit-")
        self.addCleanup(self.temp.cleanup)
        key_patch = patch.object(shared, "RsaKey", DigestStubKey)
        key_patch.start(); self.addCleanup(key_patch.stop)
        crypto = patch.object(engine, "rsa_pkcs1v15_sha256_verify",
                              side_effect=lambda n, e, raw, sig: sig == hashlib.sha256(raw).digest())
        crypto.start(); self.addCleanup(crypto.stop)
        self.f = shared.UpdateFixture(Path(self.temp.name) / "fixture", version="institute-owner-e9",
                                      previous_version="ci-legacy57", migration="none", reversible=True)
        observer = patch.object(engine, "_observe_host", side_effect=self.f.live_observation)
        observer.start(); self.addCleanup(observer.stop)
        self.f.write_channel(offline=True)
        self.f.manifest["requirements"]["minimum_installed_version"] = self.f.previous_version
        self.f.manifest["signature"]["key_id"] = KEY
        self.f.manifest["legacy_bridge"] = {"source_version": self.f.previous_version,
                                            "source_revision": "9" * 40,
                                            "source_image_id": "sha256:" + "9" * 64,
                                            "source_sequence": 42, "target_sequence": 43}
        self.f.write_trust_store(keys=[{**self.f.signing.trust_entry(KEY, (
            "update-manifest", "update-policy", "owner-update-authorization")),
            "approver_identity": OWNER, "approver_role": "course-owner",
            "approver_windows_sid": SID, "publisher_thumbprint": THUMB}])
        self.refresh_manifest()
        self.build_owner_documents()

    def refresh_manifest(self):
        self.f.manifest_rel, self.f.signature_rel = self.f.write_signed_manifest(self.f.manifest, "update", key_id=KEY)
        self.f.manifest_rel = self.f.manifest_rel.replace('\\', '/')
        self.f.signature_rel = self.f.signature_rel.replace('\\', '/')

    def write_signed(self, relative, document, doc_type):
        p = self.f.product_root / relative; p.parent.mkdir(parents=True, exist_ok=True)
        raw = engine.canonical_manifest_bytes(document); p.write_bytes(raw)
        envelope = shared.signature_envelope(doc_type + "-signature", KEY, hashlib.sha256(raw).digest())
        p.with_name(p.name + ".sig").write_text(json.dumps(envelope), encoding="utf-8")
        return hashlib.sha256(raw).hexdigest()

    def build_owner_documents(self):
        transition = {**self.f.manifest["legacy_bridge"], "target_version": self.f.version,
                      "target_revision": "a" * 40, "target_image_config_digest": self.f.identity["config_digest"],
                      "target_image_id": self.f.manifest["image"].get("runtime_id", self.f.identity["config_digest"]),
                      "target_archive_sha256": self.f.manifest["image"]["sha256"]}
        decision = {"status": "EXPLICIT_OWNER_POLICY_CHANGE_APPROVED", "owner_email": OWNER,
                    "windows_sid": SID, "existing_recovery_key_must_be_preserved": True}
        decision_raw = engine.canonical_manifest_bytes(decision)
        dp = self.f.product_root / engine.OWNER_POLICY_DECISION_PATH; dp.parent.mkdir(parents=True, exist_ok=True)
        dp.write_bytes(decision_raw)
        self.policy = {"schema_version": 1, "document_type": engine.DOCUMENT_OWNER_POLICY,
                       "product": engine.PRODUCT, "site": engine.SITE_NAME, "mode": engine.OWNER_POLICY_MODE,
                       "policy_id": "1" * 32, "key_id": KEY, "owner_identity": OWNER,
                       "owner_role": "course-owner", "owner_windows_sid": SID, "publisher_thumbprint": THUMB,
                       "issued_utc": iso(NOW - timedelta(minutes=5)), "expires_utc": iso(NOW + timedelta(days=1)),
                       "approval_record_sha256": hashlib.sha256(decision_raw).hexdigest(),
                       "installation": self.f.live_observation()["identity"], "transition": transition}
        self.policy_sha = self.write_signed(engine.OWNER_POLICY_PATH, self.policy, engine.DOCUMENT_OWNER_POLICY)
        self.restore_rel = "data/updates/prior-restore-evidence.json"
        self.restore = {"status": "PASS", "verified": True, "backup_set": "older-restored-set",
                        "verified_utc": iso(NOW - timedelta(days=2)), "source_revision": "9" * 40,
                        "source_image_id": "sha256:" + "9" * 64}
        restore_raw = engine.canonical_manifest_bytes(self.restore)
        (self.f.product_root / self.restore_rel).write_bytes(restore_raw)
        self.approval = {"schema_version": 1, "document_type": engine.DOCUMENT_OWNER_APPROVAL,
                         "product": engine.PRODUCT, "site": engine.SITE_NAME, "operation": "site-update",
                         "scope": "exact-legacy-nonmigrating-update", "policy_id": self.policy["policy_id"],
                         "policy_sha256": self.policy_sha, "request_id": "2" * 32, "key_id": KEY,
                         "owner_identity": OWNER, "owner_role": "course-owner", "owner_windows_sid": SID,
                         "issued_utc": iso(NOW - timedelta(minutes=1)), "expires_utc": iso(NOW + timedelta(minutes=20)),
                         "manifest_sha256": engine.sha256_file(self.f.product_root / self.f.manifest_rel),
                         "backup_receipt_sha256": self.f.receipt_sha256,
                         "existing_recovery_key_access_verified": True, "separate_key_custody_verified": False,
                         "restore_rehearsal": {"report": self.restore_rel, "report_sha256": hashlib.sha256(restore_raw).hexdigest(),
                                               **{n: self.restore[n] for n in ("backup_set", "verified_utc", "source_revision", "source_image_id")},
                                               "verified": True}}
        self.approval_rel = "data/updates/owner-approval.json"
        self.resign_approval()

    def resign_policy(self):
        self.policy_sha = self.write_signed(engine.OWNER_POLICY_PATH, self.policy, engine.DOCUMENT_OWNER_POLICY)
        self.approval["policy_sha256"] = self.policy_sha; self.resign_approval()

    def resign_approval(self):
        self.write_signed(self.approval_rel, self.approval, engine.DOCUMENT_OWNER_APPROVAL)

    def request(self):
        req = self.f.preflight_request(recovery_authorization=self.approval_rel,
                                       recovery_signature=self.approval_rel + ".sig")
        req.pop("recovery_signature_2", None)
        for field in ("manifest", "signature", "archive"):
            req[field] = req[field].replace('\\', '/')
        return req

    def preflight(self):
        return engine.preflight(self.request(), now=NOW, state_dir=self.f.state_dir)

    def authorized(self):
        first = self.preflight(); self.assertEqual(first["decision"], "allow", first["blockers"])
        result = engine.authorize({**self.request(), "action": "authorize", "transaction": first["transaction"]},
                                   now=NOW, state_dir=self.f.state_dir)
        self.assertEqual(result["decision"], "allow", result["blockers"])
        return result["transaction"]

    def assert_refused(self, code=None):
        result = self.preflight(); self.assertEqual(result["decision"], "refuse", result)
        if code: self.assertIn(code, shared.codes(result))

    def test_exact_owner_transition_preserves_pending_custody_and_older_restore_scope(self):
        result = self.preflight(); self.assertEqual(result["decision"], "allow", result["blockers"])
        self.assertIn("warning.separate_key_custody_pending", {i["code"] for i in result["warnings"]})
        evidence = result["transaction"]["evidence"]
        self.assertFalse(evidence["separate_key_custody_verified"])
        self.assertEqual(len(evidence["recovery_approvals"]), 1)
        self.assertNotEqual(self.restore["backup_set"], result["plan"]["backup_set"])

    def test_nonwaivable_legacy_owner_bridge_protection_flags(self):
        """Every weakened flag combination refuses before approval dispatch.

        The policy, target and signatures remain valid and matched. When the
        manifest attempts to disable approval, remove the attempt document too,
        reproducing the reviewed policy-only authorization gap exactly.
        """
        baseline = copy.deepcopy(self.f.manifest)
        flags = (
            ("requirements", "backup", "required"),
            ("requirements", "backup", "require_restore_verification"),
            ("database", "requires_verified_backup"),
            ("requirements", "recovery_authorization", "required"),
        )
        for count in range(1, len(flags) + 1):
            for weakened in itertools.combinations(flags, count):
                with self.subTest(weakened=weakened):
                    self.f.manifest = copy.deepcopy(baseline)
                    for path in weakened:
                        target = self.f.manifest
                        for key in path[:-1]:
                            target = target[key]
                        target[path[-1]] = False
                    self.refresh_manifest(); self.build_owner_documents()
                    if ("requirements", "recovery_authorization", "required") in weakened:
                        (self.f.product_root / self.approval_rel).unlink()
                        (self.f.product_root / (self.approval_rel + '.sig')).unlink()
                    self.assert_refused("release.manifest.invalid")

    def test_nonwaivable_legacy_owner_bridge_valid_protection_minima(self):
        transaction = self.authorized()
        self.assertEqual(transaction['evidence']['authorization_mode'], engine.OWNER_POLICY_MODE)
        self.assertEqual(transaction['evidence']['backup_receipt_sha256'], self.f.receipt_sha256)
        self.assertIsNotNone(transaction['evidence']['recovery_authorization_sha256'])
        self.assertIsNotNone(transaction['evidence']['restore_evidence_sha256'])

    def test_missing_policy_cannot_enable_legacy_ordering(self):
        (self.f.product_root / engine.OWNER_POLICY_PATH).unlink()
        self.assert_refused("compat.installed_version_unknown")

    def test_unsigned_policy_tampering_is_refused(self):
        p = self.f.product_root / engine.OWNER_POLICY_PATH
        p.write_bytes(p.read_bytes().replace(OWNER.encode(), b"other@example.invalid"))
        self.assert_refused("preflight.recovery.authorization_invalid")

    def test_wrong_owner_is_refused_even_after_signature_verification(self):
        self.approval["owner_identity"] = "other@example.invalid"; self.resign_approval()
        self.assert_refused("preflight.recovery.binding_mismatch")

    def test_wrong_windows_identity_is_refused(self):
        self.policy["owner_windows_sid"] = "S-1-5-21-99-88-77-1001"; self.resign_policy()
        self.assert_refused("preflight.recovery.approval_invalid")

    def test_wrong_publisher_is_refused(self):
        self.policy["publisher_thumbprint"] = "D" * 40; self.resign_policy()
        self.assert_refused("preflight.recovery.approval_invalid")

    def test_wrong_installation_is_refused(self):
        self.policy["installation"]["storage_sha256"] = "d" * 64; self.resign_policy()
        self.assert_refused("preflight.recovery.binding_mismatch")

    def test_changed_explicit_owner_decision_is_refused(self):
        (self.f.product_root / engine.OWNER_POLICY_DECISION_PATH).write_text('{}')
        self.assert_refused("preflight.recovery.binding_mismatch")

    def test_target_scope_cannot_be_broadened_by_owner_document(self):
        self.policy["transition"]["target_image_id"] = "sha256:" + "b" * 64; self.resign_policy()
        self.assert_refused("preflight.recovery.binding_mismatch")

    def test_manifest_or_backup_swap_is_refused(self):
        for field in ("manifest_sha256", "backup_receipt_sha256"):
            with self.subTest(field=field):
                old = self.approval[field]; self.approval[field] = "d" * 64; self.resign_approval()
                self.assert_refused("preflight.recovery.binding_mismatch")
                self.approval[field] = old

    def test_expired_approval_is_refused(self):
        self.approval["issued_utc"] = iso(NOW - timedelta(minutes=4))
        self.approval["expires_utc"] = iso(NOW - timedelta(minutes=1)); self.resign_approval()
        self.assert_refused("preflight.recovery.authorization_expired")

    def test_overlong_approval_is_refused(self):
        self.approval["expires_utc"] = iso(NOW + timedelta(minutes=31)); self.resign_approval()
        self.assert_refused("preflight.recovery.authorization_invalid")

    def test_recovery_key_access_cannot_be_assumed(self):
        self.approval["existing_recovery_key_access_verified"] = False; self.resign_approval()
        self.assert_refused("preflight.recovery.key_custody_unverified")

    def test_prior_restore_report_change_is_refused(self):
        p = self.f.product_root / self.restore_rel; p.write_bytes(p.read_bytes() + b' ')
        self.assert_refused("preflight.recovery.rehearsal_unverified")

    def test_migrating_bridge_is_not_accepted(self):
        self.f.manifest["database"].update(migration="supported", reversible=False)
        self.refresh_manifest(); self.assert_refused("release.manifest.invalid")

    def test_owner_key_with_only_manifest_purpose_cannot_authorize_policy(self):
        store = json.loads((self.f.product_root / self.f.trust_store_rel).read_text())
        store["keys"][0]["purposes"] = ["update-manifest"]
        (self.f.product_root / self.f.trust_store_rel).write_text(json.dumps(store))
        self.assert_refused("trust.key_unknown")

    def test_successfully_consumed_request_cannot_authorize_another_transaction(self):
        tx = self.authorized(); engine._consume_transaction(self.f.state_dir, tx)
        self.assert_refused("preflight.recovery.request_replayed")

    def test_apply_revalidates_owner_signature_envelope_and_prior_evidence(self):
        tx = self.authorized(); self.f.live_applying = True; self.f.live_transaction_id = tx["transaction_id"]
        store = engine.load_trust_store(self.f.product_root / self.f.trust_store_rel, now=NOW)
        manifest = engine.verify_manifest_signature(self.f.product_root / self.f.manifest_rel,
                                                    self.f.product_root / self.f.signature_rel, store, now=NOW)
        engine._rebind_apply(self.request(), self.f.product_root, tx, manifest, store, NOW, state_dir=self.f.state_dir)
        p = self.f.product_root / (self.approval_rel + '.sig'); p.write_bytes(p.read_bytes() + b' ')
        with self.assertRaises(engine.UpdateError) as caught:
            engine._rebind_apply(self.request(), self.f.product_root, tx, manifest, store, NOW, state_dir=self.f.state_dir)
        self.assertEqual(caught.exception.code, "apply.evidence_mismatch")

    def test_default_numeric_path_still_requires_two_recovery_signatures(self):
        f = shared.UpdateFixture(Path(self.temp.name) / "normal")
        with patch.object(engine, "_observe_host", side_effect=f.live_observation):
            req = f.preflight_request(recovery_signature_2=None)
            for field in ("manifest", "signature", "archive"):
                req[field] = req[field].replace('\\', '/')
            response = engine.preflight(req, now=NOW, state_dir=f.state_dir)
        self.assertEqual(response["decision"], "refuse")
        self.assertIn("preflight.recovery.approval_missing", shared.codes(response))

    def prepare_host_bundle(self):
        payload = b'# synthetic new updater\n'
        entry = {"path": "windows/Backup TOEFL House ERP.ps1", "old_sha256": None,
                 "new_sha256": hashlib.sha256(payload).hexdigest(), "size_bytes": len(payload)}
        path = self.f.staging / engine.HOST_SERVICE_ARCHIVE
        with zipfile.ZipFile(path, 'w') as z: z.writestr(entry["path"], payload)
        self.f.manifest["host_service"] = {"archive": path.name, "sha256": engine.sha256_file(path),
                                          "size_bytes": path.stat().st_size, "files": [entry]}
        self.f.live_changes = {"host_files": {entry["path"]: None}}
        self.refresh_manifest(); self.build_owner_documents()
        return path, entry

    def test_host_code_changed_after_authorization_is_refused(self):
        path, entry = self.prepare_host_bundle(); self.authorized()
        actual = self.f.product_root / entry["path"]; actual.parent.mkdir(parents=True); actual.write_bytes(b'changed')
        self.assert_refused("apply.evidence_mismatch")

    def test_new_host_zip_tamper_is_refused(self):
        path, entry = self.prepare_host_bundle()
        with path.open('ab') as handle: handle.write(b'changed')
        self.assert_refused("release.archive.hash_mismatch")

    def test_new_manifest_host_plan_precedes_download_but_authorize_requires_the_zip(self):
        path, entry = self.prepare_host_bundle(); raw = path.read_bytes(); path.unlink()
        first = self.preflight(); self.assertEqual(first['decision'], 'allow', first['blockers'])
        self.assertEqual(first['target']['host_service'], self.f.manifest['host_service'])
        req = {**self.request(), 'action': 'authorize', 'transaction': first['transaction']}
        missing = engine.authorize(req, now=NOW, state_dir=self.f.state_dir)
        self.assertEqual(missing['decision'], 'refuse')
        self.assertIn('release.archive.hash_mismatch', shared.codes(missing))
        path.write_bytes(raw)
        ready = engine.authorize(req, now=NOW, state_dir=self.f.state_dir)
        self.assertEqual(ready['decision'], 'allow', ready['blockers'])

    def test_new_host_zip_extra_file_is_refused_even_if_archive_is_resigned(self):
        path, entry = self.prepare_host_bundle()
        with zipfile.ZipFile(path, 'a') as z: z.writestr('data/secrets/not-allowed', b'changed')
        self.f.manifest['host_service']['sha256'] = engine.sha256_file(path)
        self.f.manifest['host_service']['size_bytes'] = path.stat().st_size
        self.refresh_manifest(); self.build_owner_documents()
        self.assert_refused("release.archive.identity_mismatch")

    def test_new_policy_changed_between_manifest_and_image_authorization_is_refused(self):
        first = self.preflight(); self.assertEqual(first['decision'], 'allow', first['blockers'])
        self.policy['expires_utc'] = iso(NOW + timedelta(days=2)); self.resign_policy()
        result, exit_code = engine.run({**self.request(), 'action': 'authorize', 'transaction': first['transaction']},
                                       now=NOW, state_dir=self.f.state_dir)
        self.assertEqual(result['decision'], 'refuse')
        self.assertEqual(exit_code, 3)
        self.assertIn('transaction.mismatch', shared.codes(result))

    def test_new_oci_runtime_binding_requires_independent_matching_rootfs_at_apply(self):
        archive = self.f.staging / 'toefl-house-erp-app.tar'
        expected = add_oci_identity(archive, self.f.identity)
        self.f.identity.update(expected)
        self.f.manifest['image'].update({k: expected[k] for k in ('runtime_id', 'sha256', 'size_bytes')})
        self.refresh_manifest(); self.build_owner_documents()
        tx = self.authorized(); self.f.live_applying = True; self.f.live_transaction_id = tx['transaction_id']
        self.f.live_changes = {'tag_image_id': expected['runtime_id'], 'tag_rootfs_layers': expected['rootfs_layers']}
        store = engine.load_trust_store(self.f.product_root / self.f.trust_store_rel, now=NOW)
        manifest = engine.verify_manifest_signature(self.f.product_root / self.f.manifest_rel,
                                                    self.f.product_root / self.f.signature_rel, store, now=NOW)
        engine._rebind_apply(self.request(), self.f.product_root, tx, manifest, store, NOW, state_dir=self.f.state_dir)
        self.f.live_changes['tag_rootfs_layers'] = ['sha256:' + 'f' * 64]
        with self.assertRaises(engine.UpdateError) as caught:
            engine._rebind_apply(self.request(), self.f.product_root, tx, manifest, store, NOW, state_dir=self.f.state_dir)
        self.assertEqual(caught.exception.code, 'apply.installed_mismatch')


def add_oci_identity(p, identity):
    with tarfile.open(p) as archive:
        config = archive.extractfile(archive.getmember(identity['config_digest'][7:] + '.json')).read()
        config_doc = json.loads(config); layer = archive.getmember('layer/layer.tar')
    oci = json.dumps({'schemaVersion': 2, 'config': {'digest': identity['config_digest'], 'size': len(config)},
                      'layers': [{'digest': config_doc['rootfs']['diff_ids'][0], 'size': layer.size}]}).encode()
    runtime = 'sha256:' + hashlib.sha256(oci).hexdigest()
    with tarfile.open(p, 'a') as archive:
        member = tarfile.TarInfo('blobs/sha256/' + runtime[7:]); member.size = len(oci)
        archive.addfile(member, io.BytesIO(oci))
    return {**identity, 'sha256': engine.sha256_file(p), 'size_bytes': p.stat().st_size,
            'runtime_id': runtime, 'rootfs_layers': config_doc['rootfs']['diff_ids']}


class OciImageIdentityTests(unittest.TestCase):
    def test_actual_oci_manifest_id_is_bound_to_exact_config_and_layer_graph(self):
        with tempfile.TemporaryDirectory(prefix='th-owner-oci-unit-') as directory:
            p, identity = shared.image_archive(Path(directory), 'qualified-e9', 'a' * 40)
            expected = add_oci_identity(p, identity); runtime = expected['runtime_id']
            result = engine.inspect_image_archive(p, expected=expected)
            self.assertEqual(result['runtime_id'], runtime)
            self.assertEqual(result['config_digest'], identity['config_digest'])
            with self.assertRaises(engine.UpdateError):
                engine.inspect_image_archive(p, expected={**expected, 'runtime_id': 'sha256:' + '0' * 64})


if __name__ == '__main__':
    unittest.main()
