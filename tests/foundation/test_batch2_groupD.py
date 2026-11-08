"""Batch-2 Group D regressions (ERP defect hunt 2026-11-05, U-08/U-14/U-15/U-19/U-20).

Each test fails on the 5032608d base and passes with the Group D fix:

* U-08: a tampered image layer with identical config/labels must not pass
  preflight or verify-release as ``allow``/``verified``; layer contents
  are verified by default, so a caller that forgets the flag is safe.
* U-14: a disposable restore must recheck staged artifact hashes against the
  gate-time digests, exactly like the production path; the recheck is
  mandatory (no digests -> refuse), and day-old staging left by a killed
  restore is reaped by the next restore.
* U-15: a kill between the synthetic-flags probe writes must not leave a
  mixed PRODUCTION + synthetic-flags site that can never be re-activated;
  set_fee_item must prove the fee-item key landed. Higher bar (Area C
  execution): EVERY crash window is enumerated -- the unverified
  triple-only state, the non-atomic copy2 rollback, and Ctrl-C during
  the gates -- and each is closed or reported in the handover.
* U-19: seed_sites must refuse symlink targets and write atomically.
* U-20: the migration census must parse only a single marked JSON line
  (TH_CENSUS), refusing on absence or ambiguity; fees totals must be
  finite and orphan reports must hold exactly one row per checked child.

Synthetic fixtures only; no real bench, GPG key, or live site.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))
sys.path.insert(0, str(ROOT / "tests" / "foundation"))

import native_gpg  # noqa: E402
import update_engine as engine  # noqa: E402
from test_product_activation import BACKUP_SET, POLICY, SITE, load_activate  # noqa: E402
from test_production_activation import load_policy, load_security  # noqa: E402
from test_update_engine import NOW, UpdateFixture, codes  # noqa: E402


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# U-08 — image layer contents verified at preflight / verify-release
# --------------------------------------------------------------------------

def tamper_image_layer(archive_path: Path) -> None:
    """Replace the layer bytes, keeping config, labels and manifest.json.

    The tampered archive is then re-bound by a freshly signed manifest in
    the test, so the only evidence of the tamper is the layer content hash
    (rootfs diff_ids) — exactly the check verify_layers performs.
    """
    with tarfile.open(archive_path, "r") as source:
        members = [(member, source.extractfile(member).read())
                   for member in source.getmembers()]
    with tarfile.open(archive_path, "w") as target:
        for member, data in members:
            if member.name == "layer/layer.tar":
                data = b"tampered application layer\n" + data[26:]
            member.size = len(data)
            target.addfile(member, io.BytesIO(data))


class TamperedLayerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fixture = UpdateFixture(Path(self.tmp.name) / "fixture")
        observer = patch.object(engine, "_observe_host",
                                side_effect=self.fixture.live_observation)
        observer.start()
        self.addCleanup(observer.stop)

    def _rebind_tampered_archive(self):
        staging_archive = self.fixture.staging / "toefl-house-erp-app.tar"
        tamper_image_layer(staging_archive)
        raw = staging_archive.read_bytes()
        self.fixture.identity = {
            "config_digest": self.fixture.identity["config_digest"],
            "labels": self.fixture.identity["labels"],
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        }
        manifest = self.fixture.build_manifest()
        self.fixture.write_signed_manifest(manifest, "update")

    def test_untampered_bundle_still_allows(self):
        decision = self.fixture.preflight()
        self.assertEqual(decision["decision"], "allow")

    def test_tampered_layer_does_not_pass_preflight_as_allow(self):
        self._rebind_tampered_archive()
        decision = self.fixture.preflight()
        self.assertNotEqual(decision["decision"], "allow")
        self.assertIn("release.archive.identity_mismatch", codes(decision))

    def test_verify_release_refuses_tampered_layer_even_with_verify_layers_false(self):
        self._rebind_tampered_archive()
        request = {
            "action": "verify-release",
            "product_root": str(self.fixture.product_root),
            "trust_store": self.fixture.trust_store_rel,
            "manifest": self.fixture.manifest_rel,
            "signature": self.fixture.signature_rel,
            "archive": str((self.fixture.staging / "toefl-house-erp-app.tar")
                           .relative_to(self.fixture.product_root)),
            "verify_layers": False,
        }
        with self.assertRaises(engine.UpdateError) as caught:
            engine.verify_release(request, now=NOW)
        self.assertEqual(caught.exception.code, "release.archive.identity_mismatch")

    def test_layer_contents_are_verified_by_default(self):
        # U-08 hardening: inspect_image_archive verifies layers unless a
        # caller explicitly opts out -- a future caller that forgets the
        # flag must not silently skip the diff_ids check.
        self._rebind_tampered_archive()
        archive = self.fixture.staging / "toefl-house-erp-app.tar"
        with self.assertRaises(engine.UpdateError) as caught:
            engine.inspect_image_archive(archive, expected=self.fixture.identity)
        self.assertEqual(caught.exception.code, "release.archive.identity_mismatch")


# --------------------------------------------------------------------------
# U-14 — disposable restores recheck staged hashes
# --------------------------------------------------------------------------

def tar_header_bytes() -> bytes:
    header = bytearray(512)
    header[257:262] = b"ustar"
    header[263:265] = b"00"
    return bytes(header)


class FakeDecryptStdin:
    def __init__(self):
        self.written = []

    def write(self, data: bytes) -> int:
        self.written.append(data)
        return len(data)

    def close(self) -> None:
        pass


def make_popen(*, returncode=0, stdout_bytes=b"", stderr_bytes=b""):
    calls = []

    class FakePopen:
        def __init__(self, arguments, **kwargs):
            self.arguments = list(arguments)
            self.stdin = FakeDecryptStdin()
            self.stdout = io.BytesIO(stdout_bytes)
            self.stderr = io.BytesIO(stderr_bytes)
            calls.append(self)

        def wait(self) -> int:
            return returncode

    FakePopen.calls = calls
    return FakePopen


@contextlib.contextmanager
def _null_transport(*args, **kwargs):
    yield


def _restore_site(tmp: Path, restore, site: str, backup_set: str):
    backup_dir = restore.SITES_DIR / site / "private" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for role, suffix in restore.BACKUP_SUFFIXES.items():
        path = backup_dir / f"{backup_set}{suffix}"
        path.write_bytes(f"synthetic {backup_set} {role}".encode())
        paths[role] = path
    return paths


class DisposableStagedHashTests(unittest.TestCase):
    """U-14: the disposable path must apply the staged-hash recheck."""

    def setUp(self):
        self.restore = load_module("batch2_gd_restore_under_test", PRODUCT / "restore.py")
        self.tmp = Path(tempfile.mkdtemp(prefix="batch2-gd-disposable-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.restore.SITES_DIR = self.tmp / "sites"
        self.site = "toeflhouse-restore.localhost"
        self.backup_set = "20261105-test"
        _restore_site(self.tmp, self.restore, self.site, self.backup_set)
        self.state = self.tmp / "state"
        self.env = patch.dict(os.environ, {"RESTORE_STATE_DIR": str(self.state)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.calls = []

    def _run_disposable(self, *, tamper_staged=False, direct=False):
        frappe = types.ModuleType("frappe")
        frappe.__path__ = []
        frappe.conf = types.SimpleNamespace(db_type="mariadb")
        frappe.init = lambda name, sites_path=".": None
        frappe.destroy = lambda: None
        frappe.utils = types.ModuleType("frappe.utils")
        frappe.utils.__path__ = []
        frappe.utils.execute_in_shell = lambda *a, **k: (b"", b"")
        commands = types.ModuleType("frappe.commands")
        commands.__path__ = []
        site_commands = types.ModuleType("frappe.commands.site")

        def native_restore(**kwargs):
            self.calls.append(kwargs)

        site_commands._restore = native_restore
        synchronization = types.ModuleType("frappe.utils.synchronization")

        @contextlib.contextmanager
        def filelock(name, timeout):
            yield

        synchronization.filelock = filelock
        modules = {
            "frappe": frappe,
            "frappe.commands": commands,
            "frappe.commands.site": site_commands,
            "frappe.utils": frappe.utils,
            "frappe.utils.synchronization": synchronization,
        }
        popen = make_popen(stdout_bytes=tar_header_bytes())
        original_stage = self.restore._stage_restore_artifacts

        def staging(*args, **kwargs):
            staged = original_stage(*args, **kwargs)
            if tamper_staged:
                # A swap of the source artifact between the gate check and
                # staging: the staged bytes no longer match the gate hashes.
                with staged["database"].open("ab") as handle:
                    handle.write(b"swapped after the gate check")
            return staged

        with patch.dict(sys.modules, modules):
            with patch.object(native_gpg.subprocess, "Popen", popen):
                with patch.object(self.restore, "safe_mariadb_credential_transport",
                                  _null_transport):
                    with patch.object(self.restore, "safe_gpg_transport", _null_transport):
                        with patch.object(self.restore, "_stage_restore_artifacts",
                                          side_effect=staging):
                            if direct:
                                # A direct call of _run_native_restore with
                                # no gate-time digests: the mandatory
                                # recheck must refuse before native restore.
                                self.restore._run_native_restore(
                                    self.site, self.backup_set, "synthetic-key",
                                    "synthetic-db-password", "synthetic-admin-password")
                            else:
                                self.restore._native_restore(
                                    self.site, self.backup_set, "synthetic-key",
                                    "synthetic-db-password", "synthetic-admin-password",
                                    target="disposable")

    def test_swapped_staged_artifact_is_refused_before_native_restore(self):
        with self.assertRaises(self.restore.RestoreInputError) as caught:
            self._run_disposable(tamper_staged=True)
        self.assertIn("changed after", str(caught.exception))
        self.assertEqual(self.calls, [])

    def test_untampered_disposable_restore_still_reaches_native_restore(self):
        self._run_disposable(tamper_staged=False)
        self.assertEqual(len(self.calls), 1)
        self.assertIs(self.calls[0]["force"], True)

    def test_verify_refuses_when_no_gate_hashes_are_supplied(self):
        # U-14 hardening: the recheck is mandatory, not "skip when None".
        # Any path that forgets the gate-time digests is refused before
        # native restore, instead of silently restoring unverified bytes.
        with self.assertRaises(self.restore.RestoreInputError):
            self.restore._verify_staged_restore_hashes(
                {"database": Path("/nonexistent")}, None)

    def test_direct_run_without_gate_hashes_refuses_before_native_restore(self):
        with self.assertRaises(self.restore.RestoreInputError):
            self._run_disposable(direct=True)
        self.assertEqual(self.calls, [])

    def test_stale_staging_from_a_killed_restore_is_reaped(self):
        # A kill mid-restore leaves staging (possibly plaintext after
        # native decryption) behind: day-old leftovers are removed by
        # the next restore, a fresh concurrent staging is never touched.
        import time as _time
        stale = Path(tempfile.mkdtemp(prefix="toefl-house-native-restore-",
                                      dir="/tmp"))
        (stale / "plaintext-marker.txt").write_text("stale", encoding="utf-8")
        old = _time.time() - 25 * 3600
        os.utime(stale, (old, old))
        fresh = Path(tempfile.mkdtemp(prefix="toefl-house-native-restore-",
                                      dir="/tmp"))
        (fresh / "in-use.txt").write_text("fresh", encoding="utf-8")
        self.addCleanup(lambda: shutil.rmtree(stale, ignore_errors=True))
        self.addCleanup(lambda: shutil.rmtree(fresh, ignore_errors=True))
        self._run_disposable(tamper_staged=False)
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(stale.exists())
        self.assertTrue((fresh / "in-use.txt").is_file())

    def test_reaper_skips_symlinks_and_fresh_staging(self):
        import time as _time
        outside = Path(tempfile.mkdtemp(prefix="batch2-gd-outside-"))
        target = outside / "target.txt"
        target.write_text("do not delete", encoding="utf-8")
        self.addCleanup(lambda: shutil.rmtree(outside, ignore_errors=True))
        link = Path("/tmp") / ("toefl-house-native-restore-link-" + os.urandom(4).hex())
        link.symlink_to(target)
        self.addCleanup(lambda: link.unlink(missing_ok=True))
        old = _time.time() - 25 * 3600
        os.utime(target, (old, old))
        fresh = Path(tempfile.mkdtemp(prefix="toefl-house-native-restore-",
                                      dir="/tmp"))
        self.addCleanup(lambda: shutil.rmtree(fresh, ignore_errors=True))
        self.restore._reap_stale_restore_staging()
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_text(encoding="utf-8"), "do not delete")
        self.assertTrue(fresh.is_dir())


# --------------------------------------------------------------------------
# U-15 — activate() crash window / set_fee_item post-write probe
# --------------------------------------------------------------------------

class ActivationCrashRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.act = load_activate()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.act.SITES_DIR = Path(self.tmp.name)
        self.site_dir = self.act.SITES_DIR / SITE
        self.backup_dir = self.site_dir / "private" / "backups"
        self.backup_dir.mkdir(parents=True)
        self.receipt_path = self.act.SITES_DIR / "activation" / "backup-receipt.json"
        self.act.BACKUP_RECEIPT_PATH = self.receipt_path
        self.write({"db_name": "x", "db_type": "mariadb"})
        self.mirror_ok = True
        self.policy = dict(POLICY)
        patcher = patch.object(self.act, "probe", side_effect=self.fake_probe)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, config):
        (self.site_dir / "site_config.json").write_text(json.dumps(config))

    def config(self):
        return json.loads((self.site_dir / "site_config.json").read_text())

    def fresh_backup(self, age=0, *, encrypted=True, same_drive=False):
        created = datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() - age, timezone.utc)
        created_text = created.isoformat().replace("+00:00", "Z")
        artifacts = []
        for role, suffix in self.act.EXPECTED_BACKUP_ROLES.items():
            name = BACKUP_SET + suffix
            payload = f"verified encrypted fixture for {role}".encode()
            (self.backup_dir / name).write_bytes(payload)
            artifacts.append({"role": role, "name": name,
                              "sha256": hashlib.sha256(payload).hexdigest(),
                              "bytes": len(payload)})
        manifest = {"schema_version": 2, "backup_set": BACKUP_SET, "encrypted": encrypted,
                    "verified": True, "artifacts": artifacts}
        manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
        receipt = {
            "schema_version": 1, "source_site": SITE, "source_drive": "C:",
            "backup_drive": "C:" if same_drive else "D:", "backup_set": BACKUP_SET,
            "created_utc": created_text, "encrypted": encrypted, "verified": True,
            "automation_ready": True, "task_name": "TOEFL House ERP Backup",
            "schedule_time": POLICY["schedule_time"],
            "retention_versions": POLICY["retention_versions"],
            "retention_behavior": POLICY["retention_behavior"],
            "policy_hash": POLICY["policy_hash"],
            "recovery_key_sha256": POLICY["recovery_key_sha256"],
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "artifacts": artifacts,
        }
        self.receipt_path.parent.mkdir(parents=True, exist_ok=True)
        self.receipt_path.write_text(json.dumps(receipt))
        return receipt

    def fake_probe(self, site, *extra):
        security = load_security(self.config(), site)
        result = {"mode": security.site_mode(), "backup_policy": dict(self.policy)}
        try:
            result["flag"] = security.record_synthetic_flag()
        except Exception:
            result["flag"] = None
        if result["mode"] == "PRODUCTION":
            policy = load_policy()
            try:
                policy.validate_family("SYN-PLACE-1", 1, production=True)
                result["mirror"] = False
            except ValueError:
                result["mirror"] = self.mirror_ok
        if extra:
            result["item"] = extra[0] == "PLACEMENT-FEE"
            result["rate"] = 500.0
        return result

    def write_crash_leftover(self):
        """The exact state a kill between the synthetic-flags writes leaves:
        activation triple set, both synthetic flags still present."""
        self.write({"db_name": "x", "db_type": "mariadb",
                    self.act.ACTIVE_KEY: 1, self.act.SITE_KEY: SITE,
                    "toefl_house_synthetic_only": 1, "allow_tests": 1})
        self.assertEqual(self.fake_probe(SITE)["mode"], "REFUSED")

    def test_crash_leftover_site_can_be_reactivated(self):
        self.fresh_backup()
        self.write_crash_leftover()
        self.act.activate(SITE, log=lambda *_: None)
        config = self.config()
        self.assertEqual(config[self.act.ACTIVE_KEY], 1)
        self.assertEqual(config[self.act.SITE_KEY], SITE)
        for key in self.act.SYNTHETIC_KEYS:
            self.assertNotIn(key, config)
        self.assertEqual(self.fake_probe(SITE)["mode"], "PRODUCTION")

    def test_crash_leftover_is_not_recovered_without_a_fresh_backup(self):
        self.write_crash_leftover()
        before = self.config()
        with self.assertRaises(self.act.Refused):
            self.act.activate(SITE, log=lambda *_: None)
        self.assertEqual(self.config(), before)

    def test_deactivate_from_crash_leftover_leaves_a_clean_reactivatable_site(self):
        self.fresh_backup()
        self.write_crash_leftover()
        self.act.deactivate(SITE, log=lambda *_: None)
        config = self.config()
        for key in (self.act.ACTIVE_KEY, self.act.SITE_KEY, *self.act.SYNTHETIC_KEYS):
            self.assertNotIn(key, config)
        self.assertEqual(self.fake_probe(SITE)["mode"], "REFUSED")
        # And the cleaned site activates normally afterwards.
        self.act.activate(SITE, log=lambda *_: None)
        self.assertEqual(self.fake_probe(SITE)["mode"], "PRODUCTION")

    def test_fee_item_write_is_proved_after_the_write(self):
        self.fresh_backup()
        self.act.activate(SITE, log=lambda *_: None)
        calls = {"n": 0}

        def failing_probe(site, *extra):
            # The first two probes are the pre-write gates; only the
            # post-write verification probe reports the site as REFUSED.
            calls["n"] += 1
            result = self.fake_probe(site, *extra)
            if calls["n"] >= 3:
                result["mode"] = "REFUSED"
            return result

        with patch.object(self.act, "probe", side_effect=failing_probe):
            with self.assertRaises(self.act.Refused):
                self.act.set_fee_item(SITE, "PLACEMENT-FEE", log=lambda *_: None)
        self.assertNotIn(self.act.FEE_ITEM_KEY, self.config())

    # -- U-15 higher bar: EVERY interrupted-activation crash window ----
    # activate() makes three sequential write_config calls (triple,
    # synthetic flags, flags removed), each atomic, so a kill can land
    # in exactly these states; the rollback (copy2) and the
    # already-activated early return were two further windows.

    def write_triple_only(self):
        """The state a kill between the activation write and the
        synthetic-flags write leaves: triple set, gates never proven."""
        self.write({"db_name": "x", "db_type": "mariadb",
                    self.act.ACTIVE_KEY: 1, self.act.SITE_KEY: SITE})
        self.assertEqual(self.fake_probe(SITE)["mode"], "PRODUCTION")

    def test_triple_only_state_is_not_trusted_without_proven_gates(self):
        # W1: the mirror gate never ran for this state. Re-running
        # activate() must refuse fail-closed, not report "Already
        # activated", and must leave the config exactly as found.
        self.fresh_backup()
        self.write_triple_only()
        self.mirror_ok = False
        before = self.config()
        with self.assertRaises(self.act.Refused):
            self.act.activate(SITE, log=lambda *_: None)
        self.assertEqual(self.config(), before)
        self.assertEqual(self.fake_probe(SITE)["mode"], "PRODUCTION")

    def test_triple_only_state_with_proven_gates_is_already_activated(self):
        self.fresh_backup()
        self.write_triple_only()
        self.mirror_ok = True
        self.act.activate(SITE, log=lambda *_: None)
        self.assertEqual(self.config()[self.act.ACTIVE_KEY], 1)

    def test_production_with_a_nonzero_flag_is_refused_not_trusted(self):
        self.fresh_backup()
        self.write_triple_only()

        def lying_probe(site, *extra):
            result = self.fake_probe(site, *extra)
            result["flag"] = 1
            return result

        with patch.object(self.act, "probe", side_effect=lying_probe):
            with self.assertRaises(self.act.Refused):
                self.act.activate(SITE, log=lambda *_: None)

    def test_keyboard_interrupt_during_activation_rolls_back(self):
        # W3: except Exception misses KeyboardInterrupt, so a Ctrl-C
        # during the gate sequence used to leave the unverified triple
        # behind with no rollback at all.
        self.fresh_backup()
        before = self.config()
        calls = {"n": 0}

        def interrupting_probe(site, *extra):
            calls["n"] += 1
            if calls["n"] == 2:
                raise KeyboardInterrupt
            return self.fake_probe(site, *extra)

        with patch.object(self.act, "probe", side_effect=interrupting_probe):
            with self.assertRaises(KeyboardInterrupt):
                self.act.activate(SITE, log=lambda *_: None)
        self.assertEqual(self.config(), before)
        self.assertEqual(self.fake_probe(SITE)["mode"], "REFUSED")

    def test_keyboard_interrupt_during_deactivation_rolls_back(self):
        self.fresh_backup()
        self.act.activate(SITE, log=lambda *_: None)
        active = self.config()

        def interrupting_probe(site, *extra):
            raise KeyboardInterrupt

        with patch.object(self.act, "probe", side_effect=interrupting_probe):
            with self.assertRaises(KeyboardInterrupt):
                self.act.deactivate(SITE, log=lambda *_: None)
        self.assertEqual(self.config(), active)
        self.assertEqual(self.fake_probe(SITE)["mode"], "PRODUCTION")

    def test_rollback_does_not_depend_on_copy2(self):
        # W2: the old rollback wrote the destination in place with
        # shutil.copy2, so a kill mid-copy left a truncated
        # site_config.json. The rollback is atomic now: even with copy2
        # made to explode, a failed gate still restores the exact
        # pre-activation settings.
        self.fresh_backup()
        self.mirror_ok = False
        before = self.config()
        with patch.object(self.act.shutil, "copy2",
                          side_effect=AssertionError("copy2 must not be used")):
            with self.assertRaises(self.act.Refused):
                self.act.activate(SITE, log=lambda *_: None)
        self.assertEqual(self.config(), before)

    def test_restore_saved_config_is_byte_identical(self):
        # The saved backup is restored verbatim, not re-serialized, and
        # no temp file is left behind in the site directory.
        raw = (b'{\n  "db_name": "x",\n  "db_type": "mariadb",\n'
               b'  "toefl_house_production_active": 1\n}\n')
        (self.site_dir / "site_config.json").write_bytes(raw)
        saved = self.act.backup_config(SITE)
        (self.site_dir / "site_config.json").write_bytes(b'{"db_type": "garbage"')
        self.act._restore_saved_config(saved, SITE)
        self.assertEqual((self.site_dir / "site_config.json").read_bytes(), raw)
        self.assertEqual(oct((self.site_dir / "site_config.json").stat().st_mode & 0o777),
                         "0o600")
        leftovers = [p for p in self.site_dir.iterdir() if p.suffix == ".tmp"]
        self.assertEqual(leftovers, [])


# --------------------------------------------------------------------------
# U-19 — bootstrap.seed_sites symlink / atomic write
# --------------------------------------------------------------------------

class SeedSitesTests(unittest.TestCase):
    def setUp(self):
        self.bootstrap = load_module("batch2_gd_bootstrap_under_test",
                                     PRODUCT / "bootstrap.py")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.seed = Path(self.tmp.name) / "seed"
        self.sites = Path(self.tmp.name) / "sites"
        self.seed.mkdir()
        self.outside = Path(self.tmp.name) / "outside.txt"
        self.outside.write_text("do not overwrite", encoding="utf-8")
        for name in ("apps.txt", "apps.json", "common_site_config.json"):
            (self.seed / name).write_text(f"image {name}", encoding="utf-8")

    def test_symlink_target_is_refused_and_the_link_target_is_untouched(self):
        self.sites.mkdir()
        (self.sites / "apps.txt").symlink_to(self.outside)
        with self.assertRaises(RuntimeError):
            self.bootstrap.seed_sites(self.sites, self.seed)
        self.assertEqual(self.outside.read_text(encoding="utf-8"), "do not overwrite")

    def test_symlink_common_site_config_is_refused(self):
        self.sites.mkdir()
        (self.sites / "common_site_config.json").symlink_to(self.outside)
        with self.assertRaises(RuntimeError):
            self.bootstrap.seed_sites(self.sites, self.seed)
        self.assertEqual(self.outside.read_text(encoding="utf-8"), "do not overwrite")

    def test_dangling_symlink_is_refused_not_followed(self):
        self.sites.mkdir()
        (self.sites / "common_site_config.json").symlink_to(self.tmp.name + "/no-such-target")
        with self.assertRaises(RuntimeError):
            self.bootstrap.seed_sites(self.sites, self.seed)

    def test_seeded_files_land_with_the_expected_modes(self):
        written = sorted(self.bootstrap.seed_sites(self.sites, self.seed))
        self.assertEqual(written, ["apps.json", "apps.txt", "common_site_config.json"])
        self.assertEqual((self.sites / "apps.txt").read_text(encoding="utf-8"), "image apps.txt")
        self.assertEqual((self.sites / "common_site_config.json").read_text(encoding="utf-8"),
                         "image common_site_config.json")
        if os.name == "posix":
            self.assertEqual(oct((self.sites / "common_site_config.json").stat().st_mode & 0o777),
                             "0o600")
            self.assertEqual(oct((self.sites / "apps.txt").stat().st_mode & 0o777), "0o644")

    def test_reseed_still_refreshes_registry_but_not_owner_config(self):
        self.bootstrap.seed_sites(self.sites, self.seed)
        (self.sites / "common_site_config.json").write_text("owner runtime settings",
                                                           encoding="utf-8")
        (self.seed / "apps.txt").write_text("updated image apps", encoding="utf-8")
        written = sorted(self.bootstrap.seed_sites(self.sites, self.seed))
        self.assertEqual(written, ["apps.json", "apps.txt"])
        self.assertEqual((self.sites / "common_site_config.json").read_text(encoding="utf-8"),
                         "owner runtime settings")
        self.assertEqual((self.sites / "apps.txt").read_text(encoding="utf-8"),
                         "updated image apps")


# --------------------------------------------------------------------------
# U-20 — marked census parsing
# --------------------------------------------------------------------------

class MarkedCensusTests(unittest.TestCase):
    def setUp(self):
        self.runner = engine.BenchRunner("bench", Path("/tmp"), timeout=60)

    def _stub(self, stdout, returncode=0):
        namespace = types.SimpleNamespace(returncode=returncode, stdout=stdout)
        return patch.object(self.runner, "_run",
                            side_effect=lambda *args, **kwargs: namespace)

    # INTEGRATION NOTE (Batch 2 execution, 2026-11-06): the candidate used
    # doctype "Fees" here, but "Fees" is in CENSUS_DOCTYPES only on the
    # dangerous-fixes branch (5032608d, PR #137 census expansion), not on
    # main (b2e608e9). "Student" pins the same marked-line behaviour
    # against main's allowlist; "Fees" coverage returns with #137.
    def test_count_accepts_only_the_single_marked_line(self):
        with self._stub('[["TH_CENSUS", "12"]]\n'):
            self.assertEqual(self.runner.count("toeflhouse.localhost", "Student"), 12)

    def test_count_refuses_unmarked_trailing_log_and_bare_integer(self):
        for stdout in ('[["12"]]\n',
                       '[["TH_CENSUS", "12"]]\nbench: warning\n',
                       '12\n',
                       '[["TH_CENSUS", "12"], ["TH_CENSUS", "3"]]\n',
                       '[["TH_CENSUS", "-1"]]\n',
                       '[["TH_CENSUS", "12"]]\n[["TH_CENSUS", "12"]]\n'):
            with self.subTest(stdout=stdout), self._stub(stdout):
                self.assertIsNone(self.runner.count("toeflhouse.localhost", "Student"))

    def test_orphans_accepts_only_marked_rows(self):
        stdout = '[["TH_CENSUS", "Sales Invoice Item", "0"], ["TH_CENSUS", "Payment Entry Reference", "2"]]\n'
        with self._stub(stdout):
            self.assertEqual(self.runner.orphans("toeflhouse.localhost"),
                             {"Sales Invoice Item": 0, "Payment Entry Reference": 2})

    def test_orphans_refuses_unmarked_or_ambiguous_output(self):
        for stdout in ('[["Sales Invoice Item", "0"], ["Payment Entry Reference", "2"]]\n',
                       'log line\n[["TH_CENSUS", "Sales Invoice Item", "0"], ["TH_CENSUS", "Payment Entry Reference", "2"]]\n',
                       '[["TH_CENSUS", "Sales Invoice Item", "0"]]\n[["TH_CENSUS", "Payment Entry Reference", "2"]]\n',
                       'not a report\n'):
            with self.subTest(stdout=stdout), self._stub(stdout):
                with self.assertRaises(engine.UpdateError):
                    self.runner.orphans("toeflhouse.localhost")

    def test_orphans_refuses_duplicate_or_extra_rows(self):
        # Two rows for one child (second silently winning) or a row for
        # an unknown child are ambiguous answers, not a census: the
        # report must hold exactly one row per checked child.
        for stdout in ('[["TH_CENSUS", "Sales Invoice Item", "0"], '
                       '["TH_CENSUS", "Sales Invoice Item", "1"]]\n',
                       '[["TH_CENSUS", "Sales Invoice Item", "0"], '
                       '["TH_CENSUS", "Payment Entry Reference", "2"], '
                       '["TH_CENSUS", "Fees", "0"]]\n'):
            with self.subTest(stdout=stdout), self._stub(stdout):
                with self.assertRaises(engine.UpdateError):
                    self.runner.orphans("toeflhouse.localhost")

    def test_fees_total_accepts_exact_marked_report(self):
        with self._stub('[["TH_CENSUS", "12345.6700"]]\n'):
            self.assertEqual(
                self.runner.fees_total("toeflhouse.localhost"), "12345.67")

    def test_fees_total_refuses_ambiguous_or_unmarked_report(self):
        invalid = (
            '[["12345.67"]]\n',
            'warning\n[["TH_CENSUS", "12345.67"]]\n',
            '[["TH_CENSUS", "12345.67"]]\nwarning\n',
            '[["TH_CENSUS", "12345.67"]]\n[["TH_CENSUS", "12345.67"]]\n',
            '[["TH_CENSUS", "12"], ["TH_CENSUS", "13"]]\n',
            '[["TH_CENSUS", "12", "13"]]\n',
            '[["TH_CENSUS", 12]]\n',
            '[["TH_CENSUS", "-1"]]\n',
        )
        for stdout in invalid:
            with self.subTest(stdout=stdout), self._stub(stdout):
                with self.assertRaises(engine.UpdateError):
                    self.runner.fees_total("toeflhouse.localhost")

    def test_record_hash_accepts_exact_marked_rows(self):
        fields = engine.CENSUS_HASH_FIELDS["Fees"]
        columns = ["name", *fields]
        row = ["FEE-001", *("1" if field in engine._CENSUS_NUMERIC_FIELDS
                            else "sample" for field in fields)]
        numeric = frozenset(index for index, column in enumerate(columns)
                            if column in engine._CENSUS_NUMERIC_FIELDS)
        expected = engine._census_digest([row], numeric_columns=numeric)
        with self._stub(json.dumps([["TH_CENSUS", *row]]) + "\n"):
            self.assertEqual(
                self.runner._census_hash("toeflhouse.localhost", "Fees"),
                expected)

    def test_record_hash_refuses_unmarked_ambiguous_or_wrong_width(self):
        fields = engine.CENSUS_HASH_FIELDS["Fees"]
        row = ["FEE-001", *("1" if field in engine._CENSUS_NUMERIC_FIELDS
                            else "sample" for field in fields)]
        marked = json.dumps([["TH_CENSUS", *row]])
        invalid = (
            json.dumps([row]) + "\n",
            marked + "\nwarning\n",
            "warning\n" + marked + "\n",
            marked + "\n" + marked + "\n",
            json.dumps([["TH_CENSUS", "FEE-001"]]) + "\n",
            json.dumps([["TH_CENSUS", *row, "extra"]]) + "\n",
        )
        for stdout in invalid:
            with self.subTest(stdout=stdout), self._stub(stdout):
                with self.assertRaises(engine.UpdateError):
                    self.runner._census_hash("toeflhouse.localhost", "Fees")



if __name__ == "__main__":
    unittest.main()
