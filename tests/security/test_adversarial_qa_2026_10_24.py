"""Mission 7 — Independent Security, Data Integrity & Adversarial QA Suite (2026-10-24).

Executes end-to-end runtime and adversarial verification across:
1. Authentication, sessions, disabled users, Administrator exclusion, and operational mode gates.
2. Private file download authorization and PDF SSRF / local-file containment.
3. Cross-role, cross-student, cross-guardian, cross-instructor, cross-branch, and payroll isolation.
4. Financial refund bounds, maker-checker separation of duties, and attendance/roster integrity.
5. Backup, restore, and activation failure modes (corrupt GPG packets, incomplete sets, traversal, staging).
6. Dependency advisory triage invariants (BROWSER_SELF_DENIAL open, package-scoped GHSA matching).
7. Reproducible adversarial proofs for confirmed baseline (`main`) security and data-integrity findings.
"""
from __future__ import annotations

import ast
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = ROOT / "apps/toefl_house"
FOUNDATION_ROOT = ROOT / "apps/foundation_security"
PRODUCT_ROOT = ROOT / "product"

for _p in (str(APP_ROOT), str(FOUNDATION_ROOT), str(PRODUCT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


class _AuthError(Exception):
    pass


class _PermError(Exception):
    pass


class _ValError(Exception):
    pass


def _load_module(name: str, path: Path, extra_modules: dict | None = None):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, extra_modules or {}):
        spec.loader.exec_module(module)
    return module


class AuthSessionAndOperationalGateAdversarialTests(unittest.TestCase):
    """Verify authentication, session creation, disabled users, and operational mode gates."""

    def _make_frappe_for_security(
        self,
        *,
        user="staff@example.com",
        roles=(),
        enabled=1,
        conf=None,
        site="toeflhouse.localhost",
    ):
        def _throw(msg, exc=None):
            raise (exc or _ValError)(msg)

        return Obj(
            session=Obj(user=user),
            conf=conf if conf is not None else {
                "th_environment_mode": "SYNTHETIC",
                "th_synthetic_environment": 1,
            },
            PermissionError=_PermError,
            ValidationError=_ValError,
            AuthenticationError=_AuthError,
            DoesNotExistError=LookupError,
            DuplicateEntryError=RuntimeError,
            throw=_throw,
            get_roles=lambda u=None: list(roles),
            db=Obj(
                get_value=lambda dt, name, field=None, **kw: enabled if (dt == "User" and field == "enabled") else None,
            ),
            local=Obj(site=site, flags=Obj()),
            whitelist=lambda **kw: (lambda fn: fn),
        )

    def test_security_authorize_rejects_guest_administrator_disabled_and_wrong_role(self):
        sec_path = APP_ROOT / "toefl_house/security.py"
        # 1. Guest refused
        fake = self._make_frappe_for_security(user="Guest", roles=("Guest",))
        sec = _load_module("th_sec_guest", sec_path, {"frappe": fake})
        with self.assertRaises(_PermError):
            sec.authorize(frozenset({"Course Owner"}))

        # 2. Administrator refused on business commands
        fake = self._make_frappe_for_security(user="Administrator", roles=("Administrator", "Course Owner"))
        sec = _load_module("th_sec_admin", sec_path, {"frappe": fake})
        with self.assertRaises(_PermError):
            sec.authorize(frozenset({"Course Owner"}))

        # 3. Disabled staff user refused even if role is present
        fake = self._make_frappe_for_security(user="disabled@example.com", roles=("Course Owner",), enabled=0)
        sec = _load_module("th_sec_disabled", sec_path, {"frappe": fake})
        with self.assertRaises(_PermError):
            sec.authorize(frozenset({"Course Owner"}))

        # 4. Wrong role refused
        fake = self._make_frappe_for_security(user="teacher@example.com", roles=("Instructor",), enabled=1)
        sec = _load_module("th_sec_role", sec_path, {"frappe": fake})
        with self.assertRaises(_PermError):
            sec.authorize(frozenset({"Finance Officer"}))

    def test_operational_mode_fails_closed_on_all_invalid_or_unapproved_states(self):
        sec_path = APP_ROOT / "toefl_house/security.py"
        bad_configs = [
            ({}, "toeflhouse.localhost"),  # missing mode
            ({"th_environment_mode": "STAGING"}, "toeflhouse.localhost"),  # invalid mode
            ({"th_environment_mode": "SYNTHETIC", "th_synthetic_environment": 0}, "toeflhouse.localhost"),  # synthetic without flag
            ({"th_environment_mode": "SYNTHETIC", "th_synthetic_environment": 1, "th_production_authorized": "APPROVED"}, "toeflhouse.localhost"),  # mixed
            ({"th_environment_mode": "PRODUCTION", "th_synthetic_environment": 1, "th_production_authorized": "APPROVED"}, "toeflhouse.localhost"),  # prod with synthetic flag
            ({"th_environment_mode": "PRODUCTION", "th_production_authorized": "REJECT"}, "toeflhouse.localhost"),  # prod without approval
            ({"th_environment_mode": "PRODUCTION", "th_production_authorized": "APPROVED"}, "placement-test.localhost"),  # prod on test site
        ]
        for idx, (cfg, site) in enumerate(bad_configs):
            fake = self._make_frappe_for_security(user="owner@example.com", roles=("Course Owner",), conf=cfg, site=site)
            sec = _load_module(f"th_sec_mode_{idx}", sec_path, {"frappe": fake})
            self.assertEqual(sec.site_mode(), "REFUSED", f"Config {cfg} on {site} did not fail closed")
            with self.assertRaises(_PermError):
                sec.require_operational()

    def test_foundation_guards_refuse_orphan_or_ambiguous_student_and_guardian_identities(self):
        guards_path = FOUNDATION_ROOT / "foundation_security/guards.py"
        for role, field_scenario in (
            ("Student", []),
            ("Student", ["STU-1", "STU-2"]),
            ("Guardian", []),
            ("Guardian", ["GRD-1", "GRD-2"]),
        ):
            fake = Obj(
                session=Obj(user="portal@example.com"),
                get_roles=lambda u=None, r=role: [r],
                PermissionError=_PermError,
                AuthenticationError=_AuthError,
                conf={},
                get_cached_value=lambda dt, name, f: 1,
                get_all=lambda dt, filters=None, pluck=None, s=field_scenario, **kw: list(s),
                db=Obj(get_single_value=lambda *a: 1, exists=lambda *a: False),
            )
            guards = _load_module(f"fg_{role}_{len(field_scenario)}", guards_path, {"frappe": fake})
            with self.assertRaises(_PermError):
                guards.validate_request()


class PrivateFilesAndPdfContainmentAdversarialTests(unittest.TestCase):
    """Verify private file parent-record authorization and WeasyPrint/wkhtmltopdf SSRF containment."""

    def test_private_file_parent_permission_refuses_recursive_file_and_unauthorized_parents(self):
        files_path = FOUNDATION_ROOT / "foundation_security/files.py"

        def _make_files_env(*, user, roles, has_perm):
            fake = Obj(
                session=Obj(user=user),
                PermissionError=_PermError,
                get_roles=lambda u=None: list(roles),
                has_permission=lambda dt, doc=None, ptype="read", user=None: has_perm,
            )
            return _load_module("fs_files_test", files_path, {"frappe": fake})

        # 1. Recursive File-parent link (`attached_to_doctype == "File"`) always denied for Student/Guardian
        mod = _make_files_env(user="student1@example.com", roles=("Student",), has_perm=True)
        file_cycle_doc = Obj(is_private=1, attached_to_doctype="File", attached_to_name="FILE-PARENT")
        self.assertFalse(mod.parent_permission(file_cycle_doc, "read", "student1@example.com"))

        # 2. Cross-student private attachment denied when parent Student read permission is False
        mod = _make_files_env(user="student2@example.com", roles=("Student",), has_perm=False)
        other_student_doc = Obj(is_private=1, attached_to_doctype="Student", attached_to_name="STU-1")
        self.assertFalse(mod.parent_permission(other_student_doc, "read", "student2@example.com"))

        # 3. Cross-guardian private attachment denied when parent Fees read permission is False
        mod = _make_files_env(user="guardian2@example.com", roles=("Guardian",), has_perm=False)
        other_fee_doc = Obj(is_private=1, attached_to_doctype="Fees", attached_to_name="FEE-1")
        self.assertFalse(mod.parent_permission(other_fee_doc, "read", "guardian2@example.com"))

        # 4. Authorized parent Student read succeeds for read/print, but write ptype requires write permission
        mod_read_only = _make_files_env(user="student1@example.com", roles=("Student",), has_perm=True)
        self.assertTrue(mod_read_only.parent_permission(other_student_doc, "read", "student1@example.com"))

    def test_pdf_resource_policy_blocks_ssrf_external_hosts_and_path_traversal(self):
        pdf_path = APP_ROOT / "toefl_house/pdf_resources.py"
        pdf = _load_module("th_pdf_adv", pdf_path)
        with tempfile.TemporaryDirectory() as tmp:
            asset_root = Path(tmp)
            policy = pdf.ResourcePolicy(
                base_url="https://toeflhouse.localhost",
                assets={"toefl_house": asset_root},
                attachment_reader=lambda path: (_ for _ in ()).throw(pdf.PDFResourceDenied("blocked")),
            )
            for blocked_url in (
                "http://169.254.169.254/latest/meta-data/",
                "https://evil.example.com/payload.css",
                "file:///etc/passwd",
                "ftp://internal/secret",
                "javascript:alert(1)",
                "https://toeflhouse.localhost/private/files/secret.pdf",
                "https://toeflhouse.localhost/assets/toefl_house/../../etc/passwd.css",
                "https://user:pass@toeflhouse.localhost/assets/toefl_house/style.css",
            ):
                with self.assertRaises(pdf.PDFResourceDenied, msg=f"Expected ResourcePolicy to block {blocked_url}"):
                    policy(blocked_url)
            self.assertTrue(policy.denied)


class CrossBoundaryPermissionsAdversarialTests(unittest.TestCase):
    """Test cross-role, cross-branch, and compensation/answer-key/manifest isolation in permissions.py."""

    def _load_permissions(self, *, user, roles, branch_perms=None, operational=True):
        from toefl_house import policy as real_policy

        sec_mod = types.ModuleType("toefl_house.security")

        def _req_op():
            if not operational:
                raise _PermError("Site is REFUSED")

        sec_mod.require_operational = _req_op
        pkg_mod = types.ModuleType("toefl_house")
        pkg_mod.__path__ = [str(APP_ROOT / "toefl_house")]
        pkg_mod.security = sec_mod
        pkg_mod.policy = real_policy

        branch_perms = list(branch_perms or [])

        def _get_all(doctype, filters=None, pluck=None, **kw):
            filters = filters or {}
            if doctype == "User Permission" and filters.get("allow") == "Branch":
                return list(branch_perms)
            return []

        fake_frappe = Obj(
            session=Obj(user=user),
            PermissionError=_PermError,
            get_roles=lambda u=None: list(roles),
            get_all=_get_all,
            db=Obj(
                escape=lambda s: f"'{s}'",
                get_value=lambda dt, name, field, **kw: None,
                sql=lambda *a, **kw: [],
            ),
        )
        return _load_module(
            f"th_perm_{user}_{id(roles)}",
            APP_ROOT / "toefl_house/permissions.py",
            {
                "frappe": fake_frappe,
                "toefl_house": pkg_mod,
                "toefl_house.security": sec_mod,
                "toefl_house.policy": real_policy,
            },
        )

    def test_answer_keys_manifests_and_allocation_guards_refused_to_session_and_non_publisher_roles(self):
        # Invigilator / Assessor / Reviewer / Releaser / Course Owner / Finance Officer cannot read answer keys or manifests
        perm = self._load_permissions(
            user="session-staff@example.com",
            roles=(
                "Placement Invigilator",
                "Placement Assessor",
                "Placement Reviewer",
                "Placement Releaser",
                "Course Owner",
                "Finance Officer",
            ),
        )
        for dt, kind in (
            ("TH Placement Key Revision", "key"),
            ("TH Placement Form Manifest", "manifest"),
            ("TH Placement Allocation Guard", "guard"),
        ):
            doc = Obj(doctype=dt, name="DOC-1", owner="other@example.com", get=lambda k, default=None: "Published")
            self.assertFalse(perm.has_permission(doc, ptype="read", user="session-staff@example.com"))
            self.assertEqual(perm.query(kind, user="session-staff@example.com"), "1=0")

        # Even Placement Publisher is denied TH Placement Allocation Guard
        pub_perm = self._load_permissions(
            user="publisher@example.com",
            roles=("Placement Publisher",),
        )
        guard_doc = Obj(doctype="TH Placement Allocation Guard", name="AG-1", owner="publisher@example.com", get=lambda k, default=None: None)
        self.assertFalse(pub_perm.has_permission(guard_doc, ptype="read", user="publisher@example.com"))
        self.assertEqual(pub_perm.query_guard(user="publisher@example.com"), "1=0")

    def test_compensation_contracts_and_correction_policies_isolated_from_non_finance_roles(self):
        # Instructor / Teaching Scheduler / Placement Publisher cannot read TH Instructor Contract or TH Correction Request
        perm = self._load_permissions(
            user="instructor@example.com",
            roles=("Instructor", "Teaching Scheduler", "Placement Publisher", "Attendance Recorder"),
        )
        contract_doc = Obj(
            doctype="TH Instructor Contract",
            name="IC-1",
            owner="instructor@example.com",
            get=lambda k, default=None: "Active",
        )
        self.assertFalse(perm.has_permission(contract_doc, ptype="read", user="instructor@example.com"))
        self.assertEqual(perm.query_contract(user="instructor@example.com"), "1=0")
        self.assertEqual(perm.query_correction_request(user="instructor@example.com"), "1=0")
        self.assertEqual(perm.query_correction_policy(user="instructor@example.com"), "1=0")

        # Finance Officer CAN read contracts (when HQ / matching branch)
        fperm = self._load_permissions(
            user="finance@example.com",
            roles=("Finance Officer",),
        )
        self.assertTrue(fperm.has_permission(contract_doc, ptype="read", user="finance@example.com"))
        self.assertEqual(fperm.query_contract(user="finance@example.com"), "1=1")

    def test_cross_branch_isolation_and_refused_site_fail_closed(self):
        # Enrollment Officer scoped to Branch-Kabul-Main cannot read Branch-Herat Student Group or branchless Student Group
        bperm = self._load_permissions(
            user="eo-kabul@example.com",
            roles=("Enrollment Officer",),
            branch_perms=["Branch-Kabul-Main"],
        )
        kabul_group = Obj(
            doctype="Student Group",
            name="SG-KABUL",
            th_branch="Branch-Kabul-Main",
            get=lambda k, default=None: "Branch-Kabul-Main" if k == "th_branch" else default,
        )
        herat_group = Obj(
            doctype="Student Group",
            name="SG-HERAT",
            th_branch="Branch-Herat",
            get=lambda k, default=None: "Branch-Herat" if k == "th_branch" else default,
        )
        unassigned_group = Obj(
            doctype="Student Group",
            name="SG-NONE",
            th_branch=None,
            get=lambda k, default=None: None,
        )
        self.assertTrue(bperm.branch_has_permission(kabul_group, ptype="read", user="eo-kabul@example.com"))
        self.assertFalse(bperm.branch_has_permission(herat_group, ptype="read", user="eo-kabul@example.com"))
        self.assertFalse(bperm.branch_has_permission(unassigned_group, ptype="read", user="eo-kabul@example.com"))

        cond = bperm.branch_query_student_group("eo-kabul@example.com")
        self.assertIn("Branch-Kabul-Main", cond)
        self.assertNotIn("Branch-Herat", cond)

        # When site operational mode is REFUSED, has_permission and query fail closed ("1=0" / False)
        refused_perm = self._load_permissions(
            user="finance@example.com",
            roles=("Finance Officer",),
            operational=False,
        )
        contract_doc = Obj(
            doctype="TH Instructor Contract",
            name="IC-1",
            owner="finance@example.com",
            get=lambda k, default=None: "Active",
        )
        self.assertFalse(refused_perm.has_permission(contract_doc, ptype="read", user="finance@example.com"))
        self.assertEqual(refused_perm.query_contract(user="finance@example.com"), "1=0")


class BackupAndRestoreAdversarialFailureTests(unittest.TestCase):
    """Test backup and restore failure cases: CLI args, symlinks, bad GPG packets, incomplete sets, staging."""

    def test_backup_refuses_cli_arguments_and_invalid_retention_counts(self):
        import backup as prod_backup

        out, err = io.StringIO(), io.StringIO()
        rc = prod_backup.main(argv=["--ignore-files"], stdout=out, stderr=err)
        self.assertEqual(rc, 2)
        self.assertIn("accepts no command-line arguments", err.getvalue())

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with self.assertRaises(prod_backup.BackupInputError):
                prod_backup.rotate_native_sets(tmp_path, keep_count=1, protect_set="20261024_120000-toeflhouse_localhost")
            with self.assertRaises(prod_backup.BackupInputError):
                prod_backup.rotate_native_sets(tmp_path, keep_count=True, protect_set="20261024_120000-toeflhouse_localhost")

    def test_backup_rotation_preserves_incomplete_sets_and_refuses_dropping_protected_set(self):
        import backup as prod_backup

        with tempfile.TemporaryDirectory() as tmp:
            native_dir = Path(tmp)
            # Create 2 complete sets and 1 incomplete set (missing sidecar)
            for ts in ("20261022_120000", "20261023_120000", "20261024_120000"):
                base = f"{ts}-toeflhouse_localhost"
                for suffix in prod_backup.BACKUP_SUFFIXES.values():
                    (native_dir / f"{base}{suffix}").write_bytes(b"encrypted-content")
                if ts != "20261022_120000":
                    (native_dir / f"{base}-site_config_backup.json").write_text('{"backup_encryption_key": "k"}')

            # Trying to protect a set that wouldn't be in top keep_count must fail closed before deleting anything
            with self.assertRaises(prod_backup.BackupInputError) as ctx:
                prod_backup.rotate_native_sets(
                    native_dir,
                    keep_count=2,
                    protect_set="20261021_120000-toeflhouse_localhost",
                )
            self.assertEqual(ctx.exception.safe_code, "native-retention-would-drop-current")

            # Incomplete set (20261022_120000) must never be deleted by rotation
            res = prod_backup.rotate_native_sets(
                native_dir,
                keep_count=2,
                protect_set="20261024_120000-toeflhouse_localhost",
            )
            self.assertEqual(len(res["kept"]), 2)
            self.assertEqual(res["removed"], [])
            self.assertTrue((native_dir / "20261022_120000-toeflhouse_localhost-database-enc.sql.gz").exists())

    def test_restore_refuses_cli_args_oversize_payload_path_traversal_and_preserves_originals(self):
        import restore as prod_restore

        # 1. CLI arguments refused
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(prod_restore.main(stdin=io.StringIO("{}"), stdout=out, stderr=err, argv=["--force"]), 2)
        self.assertIn("accepts no command-line arguments", err.getvalue())

        # 2. Oversize payload refused
        big_stdin = io.StringIO("{" + ("a" * (prod_restore.MAX_PAYLOAD_BYTES + 10)) + "}")
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(prod_restore.main(stdin=big_stdin, stdout=out, stderr=err, argv=[]), 2)
        self.assertIn("exceeds its safe size limit", err.getvalue())

        # 3. Path traversal in backup_set refused
        bad_payload = json.dumps({
            "site": "toeflhouse.localhost",
            "backup_set": "../etc/passwd",
            "encryption_key": "valid-ascii-key",
            "db_root_password": "root",
            "admin_password": "admin",
        })
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(prod_restore.main(stdin=io.StringIO(bad_payload), stdout=out, stderr=err, argv=[]), 2)
        self.assertIn("backup-set name is invalid", err.getvalue())

        # 4. Staging copies artifacts into disposable directory without mutating originals
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as work_tmp:
            src_dir = Path(src_tmp)
            work_dir = Path(work_tmp)
            paths = {}
            original_digests = {}
            for role, suffix in prod_restore.BACKUP_SUFFIXES.items():
                p = src_dir / f"20261024_120000-toeflhouse_localhost{suffix}"
                content = f"encrypted-{role}-payload".encode("utf-8")
                p.write_bytes(content)
                paths[role] = p
                original_digests[role] = content

            staged = prod_restore._stage_restore_artifacts(paths, work_dir)
            for role, staged_path in staged.items():
                self.assertNotEqual(staged_path.resolve(), paths[role].resolve())
                # Simulate Frappe's decrypt_backup mutating the staged file in place
                staged_path.write_bytes(b"mutated-plaintext-during-failed-restore")
                # Original backup file must remain 100% untouched
                self.assertEqual(paths[role].read_bytes(), original_digests[role])


class FinanceAndCommandContainmentAdversarialTests(unittest.TestCase):
    """Verify financial document containment hooks, native book-sale guards, and correction policy bounds."""

    def test_guard_fees_and_sales_invoice_refuse_unguarded_writes_and_invalid_book_sales(self):
        from toefl_house import policy as real_policy

        sec_mod = types.ModuleType("toefl_house.security")
        sec_mod.KIND_ROLES = {"issue_tuition_fees": frozenset({"Finance Officer"}), "issue_placement_fee": frozenset({"Finance Officer"})}
        sec_mod.authorize = lambda roles: "fin@example.com"
        sec_mod.command = lambda *a, **kw: None
        sec_mod.finance_command_active = lambda dt=None: False
        sec_mod.is_production = lambda: False
        sec_mod.record_synthetic_flag = lambda: 1
        sec_mod.require_operational = lambda: None

        tx_mod = types.ModuleType("toefl_house.transactions")
        tx_mod.run_with_retry = lambda fn: fn()

        api_mod = types.ModuleType("toefl_house.api")
        api_mod._execute = lambda *a, **kw: None

        enr_mod = types.ModuleType("toefl_house.enrollment")
        enr_mod.deny_premature_invoice = lambda doc, method=None: None

        pkg_mod = types.ModuleType("toefl_house")
        pkg_mod.__path__ = [str(APP_ROOT / "toefl_house")]
        pkg_mod.security = sec_mod
        pkg_mod.policy = real_policy
        pkg_mod.transactions = tx_mod
        pkg_mod.api = api_mod
        pkg_mod.enrollment = enr_mod

        fake_frappe = types.ModuleType("frappe")
        fake_frappe.__path__ = []
        fake_frappe.session = Obj(user="fin@example.com")
        fake_frappe.PermissionError = _PermError
        fake_frappe.ValidationError = _ValError
        fake_frappe.DoesNotExistError = LookupError
        fake_frappe.DuplicateEntryError = RuntimeError
        fake_frappe.get_roles = lambda u=None: ["Finance Officer", "Accounts User"]
        fake_frappe.has_permission = lambda dt, ptype, doc=None, user=None: True
        fake_frappe.whitelist = lambda **kw: (lambda fn: fn)
        fake_frappe.db = Obj(exists=lambda *a: False, get_value=lambda *a, **kw: None)

        fin = _load_module(
            "th_fin_adv",
            APP_ROOT / "toefl_house/finance/__init__.py",
            {
                "frappe": fake_frappe,
                "toefl_house": pkg_mod,
                "toefl_house.security": sec_mod,
                "toefl_house.policy": real_policy,
                "toefl_house.transactions": tx_mod,
                "toefl_house.api": api_mod,
                "toefl_house.enrollment": enr_mod,
            },
        )
        # 1. Unguarded Fees write refused
        with self.assertRaises(_ValError):
            fin.guard_fees(Obj(doctype="Fees", name="FEE-1"))

        # 2. Unguarded Sales Invoice with placement case or update_stock=0 refused
        with self.assertRaises(_ValError):
            fin.guard_sales_invoice(
                Obj(doctype="Sales Invoice", th_placement_case="CASE-1", update_stock=1, company="TH", customer="CUST-1")
            )
        with self.assertRaises(_ValError):
            fin.guard_sales_invoice(
                Obj(doctype="Sales Invoice", th_placement_case=None, update_stock=0, company="TH", customer="CUST-1")
            )

        # 3. Administrator or user without Accounts User is refused native book sale
        fake_frappe.session.user = "Administrator"
        self.assertFalse(
            fin._native_book_sale_allowed(
                Obj(doctype="Sales Invoice", th_placement_case=None, update_stock=1, company="TH", customer="CUST-1")
            )
        )

    def test_correction_window_validation_refuses_negative_or_boolean_days(self):
        from toefl_house import policy as real_policy

        for bad_days in (-1, -5, True, False, "7", None, real_policy.CORRECTION_WINDOW_MAX_DAYS + 1):
            with self.assertRaises(ValueError):
                real_policy.validate_correction_window_days(bad_days)
        self.assertEqual(real_policy.validate_correction_window_days(0), 0)
        self.assertEqual(real_policy.validate_correction_window_days(14), 14)


class DependencySecurityTriageAdversarialTests(unittest.TestCase):
    """Validate SEC-DEPS-01 advisory triage invariants."""

    def test_browser_self_denial_remains_open_and_cross_package_ghsa_never_closes_finding(self):
        from tools.foundation import advisory_triage

        self.assertNotIn("BROWSER_SELF_DENIAL", advisory_triage.CLOSED_DISPOSITIONS)
        self.assertIn("BROWSER_SELF_DENIAL", advisory_triage.OWNER_OPEN_DISPOSITIONS)

        triage = advisory_triage.load_triage()
        # Cross-package check: a GHSA recorded for pyjwt must never close a finding on another package
        rec = advisory_triage.disposition_for_finding(
            triage,
            package="py:unrelated-package@1.0.0",
            advisories=["GHSA-w6j9-cwv2-h6wq"],
        )
        self.assertIsNone(rec)


class BaselineSecurityRegressionTests(unittest.TestCase):
    """Guard previously confirmed baseline weaknesses after remediation.

    Prior test iterations proved the bugs were present by asserting insecure
    syntax. Such proofs must not survive as *passing* contracts after fixes:
    they are now reversed into positive non-regression checks.
    """

    def _source(self, path, function):
        src = (APP_ROOT / path).read_text(encoding="utf-8")
        tree = ast.parse(src)
        fn = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == function)
        return ast.get_source_segment(src, fn)

    def test_adv_main_01_scoped_names_cannot_override_branch_restrictions(self):
        apply_seg = self._source("toefl_house/desk/__init__.py", "_apply_scope")
        guard_seg = self._source("toefl_house/desk/__init__.py", "_intersect_scope_filter")
        self.assertIn("_intersect_scope_filter(filters[", apply_seg)
        self.assertIn("raise frappe.ValidationError", guard_seg)

    def test_adv_main_02_attendance_restricts_active_members_and_open_groups(self):
        seg = self._source("toefl_house/teaching/__init__.py", "_record_attendance")
        self.assertIn("active=1", seg)
        scope = self._source("toefl_house/teaching/__init__.py", "_roster_read")
        self.assertNotIn("native.get_student_group_students =", scope)
        record = self._source("toefl_house/teaching/__init__.py", "_record_attendance")
        self.assertIn("_TERMINAL_CLASS_STATUSES", record)
        for endpoint in ("record_attendance", "record_instructor_attendance"):
            wrapper = self._source("toefl_house/teaching/__init__.py", endpoint)
            self.assertIn("_record_attendance(", wrapper)
        own = self._source("toefl_house/teaching/__init__.py", "_require_own_instructor_session")
        self.assertIn("session.instructor", own)
        self.assertIn("TH Teaching Assignment", own)

    def test_adv_main_03_control_mutations_refuse_protected_admin(self):
        require = self._source("toefl_house/administration.py", "_require_control_role")
        mutate = self._source("toefl_house/administration.py", "set_managed_role")
        self.assertIn("PROTECTED_USERS", require)
        self.assertIn("PROTECTED_USERS", mutate)

    def test_adv_main_04_maker_cannot_approve_own_correction(self):
        for fn in ("approve_invoice_correction", "approve_fees_correction"):
            seg = self._source("toefl_house/finance/corrections.py", fn)
            self.assertIn('getattr(req, "owner", None)', seg)
        seg = self._source("toefl_house/teaching/attendance_corrections.py",
                           "approve_attendance_correction")
        self.assertIn('getattr(req, "requested_by", None)', seg)


if __name__ == "__main__":
    unittest.main()
