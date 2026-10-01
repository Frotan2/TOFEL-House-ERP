"""Owner activation UX (product/activate.py) keeps every LAUNCH-RUNBOOK gate.

The site mode is resolved by the app's own security.site_mode (loaded with a
stubbed frappe reading the on-disk site_config), so these tests prove the
wrapper cannot activate, stay activated, or leave mixed flags unless the real
resolver agrees.
"""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from tests.foundation.test_production_activation import load_policy, load_security

ROOT = Path(__file__).resolve().parents[2]
SITE = "toeflhouse.localhost"


def load_activate():
    spec = importlib.util.spec_from_file_location("activate_under_test", ROOT / "product" / "activate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ActivationFlow(unittest.TestCase):
    def setUp(self):
        self.act = load_activate()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.act.SITES_DIR = Path(self.tmp.name)
        self.site_dir = self.act.SITES_DIR / SITE
        (self.site_dir / "private" / "backups").mkdir(parents=True)
        self.write({"db_name": "x", "db_type": "mariadb"})
        self.mirror_ok = True
        patcher = patch.object(self.act, "probe", side_effect=self.fake_probe)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, config):
        (self.site_dir / "site_config.json").write_text(json.dumps(config))

    def config(self):
        return json.loads((self.site_dir / "site_config.json").read_text())

    def fresh_backup(self, age=0):
        path = self.site_dir / "private" / "backups" / "20260930-database.sql.gz"
        path.write_bytes(b"x")
        os.utime(path, (time.time() - age, time.time() - age))

    def fake_probe(self, site, *extra):
        security = load_security(self.config(), site)
        result = {"mode": security.site_mode()}
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
            result.update(item=extra[0] == "PLACEMENT-FEE", rate=500.0)
        return result

    def test_refuses_without_a_fresh_backup(self):
        with self.assertRaises(self.act.Refused):
            self.act.activate(SITE, log=lambda *_: None)
        self.fresh_backup(age=2 * 24 * 3600)
        with self.assertRaises(self.act.Refused):
            self.act.activate(SITE, log=lambda *_: None)
        self.assertNotIn(self.act.ACTIVE_KEY, self.config())

    def test_activation_passes_real_gates_and_leaves_no_mixed_flags(self):
        self.fresh_backup()
        self.act.activate(SITE, log=lambda *_: None)
        config = self.config()
        self.assertEqual(config[self.act.ACTIVE_KEY], 1)
        self.assertEqual(config[self.act.SITE_KEY], SITE)
        for key in self.act.SYNTHETIC_KEYS:
            self.assertNotIn(key, config)
        self.assertEqual(self.fake_probe(SITE)["mode"], "PRODUCTION")
        self.assertTrue(list((self.site_dir / "private").glob("site_config.json.*.bak")))

    def test_failed_gate_restores_previous_settings(self):
        self.fresh_backup()
        self.mirror_ok = False
        before = self.config()
        with self.assertRaises(self.act.Refused):
            self.act.activate(SITE, log=lambda *_: None)
        self.assertEqual(self.config(), before)
        self.assertEqual(self.fake_probe(SITE)["mode"], "REFUSED")

    def test_stale_test_flags_block_activation(self):
        self.fresh_backup()
        self.write({"db_type": "mariadb", "allow_tests": 1})
        with self.assertRaises(self.act.Refused):
            self.act.activate(SITE, log=lambda *_: None)

    def test_qualification_hostname_and_other_backends_refused(self):
        backups = [("a-database.sql.gz", time.time())]
        for site in ("placement-test.localhost", "placement-second.localhost"):
            with self.assertRaises(self.act.Refused):
                self.act.check_preconditions(site, {}, backups, time.time())
        with self.assertRaises(self.act.Refused):
            self.act.check_preconditions(SITE, {"db_type": "postgres"}, backups, time.time())

    def test_deactivate_returns_to_refused(self):
        self.fresh_backup()
        self.act.activate(SITE, log=lambda *_: None)
        self.act.deactivate(SITE, log=lambda *_: None)
        self.assertEqual(self.fake_probe(SITE)["mode"], "REFUSED")

    def test_failed_deactivation_verification_restores_previous_settings(self):
        # Deactivation must be as safe as activation: if the post-verification
        # read fails or resolves anything but REFUSED, the previous settings
        # are restored and the site deterministically stays ACTIVE — never an
        # ambiguous half-deactivated state.
        self.fresh_backup()
        self.act.activate(SITE, log=lambda *_: None)
        before = self.config()
        self.assertIn(self.act.ACTIVE_KEY, before)

        def stale_probe(site, *extra):
            # After the deactivation write the config no longer carries the
            # active key, but the site still resolves PRODUCTION (stale read).
            if self.act.ACTIVE_KEY not in self.config():
                return {"mode": "PRODUCTION"}
            return self.fake_probe(site, *extra)

        with patch.object(self.act, "probe", side_effect=stale_probe):
            with self.assertRaises(self.act.Refused):
                self.act.deactivate(SITE, log=lambda *_: None)
        self.assertEqual(self.config(), before,
                         "failed deactivation verification must restore the "
                         "previous settings (site stays ACTIVE)")
        self.assertEqual(self.fake_probe(SITE)["mode"], "PRODUCTION")

    def test_fee_item_requires_activation_existing_item_and_no_fixture(self):
        with self.assertRaises(self.act.Refused):
            self.act.set_fee_item(SITE, "PLACEMENT-FEE", log=lambda *_: None)
        self.fresh_backup()
        self.act.activate(SITE, log=lambda *_: None)
        for bad in ("SYN-PLACEMENT-FEE", "SYNTHETIC-1", "", "MISSING"):
            with self.assertRaises(self.act.Refused):
                self.act.set_fee_item(SITE, bad, log=lambda *_: None)
        self.act.set_fee_item(SITE, "PLACEMENT-FEE", log=lambda *_: None)
        self.assertEqual(self.config()[self.act.FEE_ITEM_KEY], "PLACEMENT-FEE")

    def test_confirmation_must_name_the_site(self):
        with self.assertRaises(self.act.Refused):
            self.act.require_confirm(SITE, None)
        self.act.require_confirm(SITE, SITE)


class ActivationConstantsMatchApp(unittest.TestCase):
    def test_keys_and_hostnames_are_the_apps_own(self):
        act = load_activate()
        security = load_security({}, SITE)
        self.assertEqual(act.ACTIVE_KEY, security.PRODUCTION_ACTIVE_CONF_KEY)
        self.assertEqual(act.SITE_KEY, security.PRODUCTION_SITE_CONF_KEY)
        self.assertEqual(act.SYNTHETIC_SITES, security.SYNTHETIC_SITES)
        finance = (ROOT / "apps/toefl_house/toefl_house/finance/__init__.py").read_text()
        self.assertIn(f'PLACEMENT_FEE_ITEM_CONF_KEY = "{act.FEE_ITEM_KEY}"', finance)
        self.assertIn(f'PRICE_LIST = "{act.PRICE_LIST}"', finance)

    def test_script_is_baked_into_the_image(self):
        self.assertIn("!product/activate.py", (ROOT / ".dockerignore").read_text())
        self.assertIn("COPY product/activate.py /product/activate.py",
                      (ROOT / "product/app.Dockerfile").read_text())


if __name__ == "__main__":
    unittest.main()
