"""Final hosted acceptance report must not confuse CI success with release."""
import ast
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

from tools.native.final_acceptance_report import (
    MIN_NATIVE_CHECKS, REQUIRED_JOURNEYS, REQUIRED_ROLE_PAGES,
    ROLE_PAGE_API, ROLE_PAGE_CSS, ROLE_PAGE_EXTRA_CONTROLS, verify_report,
)
from tools.native.native_checks import (
    ROLE_PAGE_API as NATIVE_ROLE_PAGE_API,
    ROLE_PAGE_CASES,
    ROLE_PAGE_CSS as NATIVE_ROLE_PAGE_CSS,
    role_page_api_observation, role_page_css_observation, role_page_identity,
)

COMMIT = "a" * 40


def page_observation(page, user, projection):
    script = ("frappe.provide('toefl_house.role_desks'); "
              f"frappe.pages['{page}'] = {{on_page_load() {{}}}}; "
              f"const surface = {{endpoint: '{projection}', stylesheet: '{ROLE_PAGE_CSS}'}};")
    return dict(method="GET", endpoint=ROLE_PAGE_API, page=page, user=user, http_status=200,
                docs=[dict(doctype="Page", name=page, page_name=page, script=script)])


def authorization_observation():
    audiences = {user for user, _ in REQUIRED_ROLE_PAGES.values()} | {"synthetic-outsider@example.test", "Guest"}
    controls = {(page, user) for page, (user, _) in REQUIRED_ROLE_PAGES.items()} | ROLE_PAGE_EXTRA_CONTROLS
    return dict(
        method="GET", endpoint=ROLE_PAGE_API,
        controls=[dict(page=page, user=user, http_status=200, returned_page=page) for page, user in sorted(controls)],
        denials=[dict(page=page, user=user, http_status=403, exc_type="PermissionError", docs=[])
                 for page, (audience, _) in REQUIRED_ROLE_PAGES.items() for user in sorted(audiences) if user != audience],
    )


def css_observation():
    body = ".th-page { display: grid; }\n.th-section { padding: 1rem; }\n"
    digest = hashlib.sha256(body.encode()).hexdigest()
    return dict(method="GET", endpoint=ROLE_PAGE_CSS, user="synthetic-course-owner@example.test", http_status=200,
                content_type="text/css", body=body, sha256=digest, installed_sha256=digest)


def receipt(evidence, name):
    return next(check for check in evidence["checks"] if check["name"] == name)


def synthetic_report():
    required = [n for values in REQUIRED_JOURNEYS.values() for n in values]
    checks = [{"name": n, "status": "pass"} for n in required]
    for check in checks:
        name = check["name"]
        if name == "role-page-api-authorization":
            check["observation"] = authorization_observation()
        elif name == "role-page-css-delivery":
            check["observation"] = css_observation()
        elif name.startswith("role-page-api-"):
            page = name.removeprefix("role-page-api-")
            check["observation"] = page_observation(page, *REQUIRED_ROLE_PAGES[page])
    checks.extend(
        {"name": "synthetic-other-%04d" % i, "status": "pass"}
        for i in range(MIN_NATIVE_CHECKS - len(checks))
    )
    return dict(
        commit=COMMIT,
        status="pass",
        runtime_kind="Frappe/MariaDB/Redis/HTTP",
        production="REJECT",
        checks=checks,
    )


class FinalHostedAcceptanceTest(unittest.TestCase):
    def test_complete_synthetic_report_never_approves_real_operation(self):
        summary = verify_report(synthetic_report(), COMMIT)
        self.assertEqual(summary["native_checks_passed"], MIN_NATIVE_CHECKS)
        self.assertEqual(set(summary["journeys"]), set(REQUIRED_JOURNEYS))
        self.assertEqual(summary["production_authorization"], "REJECT")
        self.assertEqual(summary["real_owner_windows"], "NOT_VERIFIED")
        self.assertEqual(summary["owner_backup_restore"], "HOLD")
        self.assertEqual(summary["journeys"]["role_pages"], {"status": "PASS", "required_receipts": 10})

    def test_missing_journey_is_a_failure_even_when_all_other_checks_pass(self):
        evidence = synthetic_report()
        evidence["checks"][0]["name"] = "synthetic-replacement"
        with self.assertRaisesRegex(ValueError, "Missing executed placement journeys"):
            verify_report(evidence, COMMIT)

    def test_failed_check_is_not_masked_by_a_green_top_level(self):
        evidence = synthetic_report()
        evidence["checks"][10]["status"] = "fail"
        with self.assertRaisesRegex(ValueError, "did not pass"):
            verify_report(evidence, COMMIT)

    def test_wrong_commit_rejected(self):
        with self.assertRaisesRegex(ValueError, "different commit"):
            verify_report(synthetic_report(), "b" * 40)

    def test_wrong_runtime_or_release_claim_rejected(self):
        for key, value in (
            ("runtime_kind", "static-tests-only"),
            ("production", "APPROVED"),
            ("status", "running"),
        ):
            evidence = synthetic_report()
            evidence[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_report(evidence, COMMIT)

    def test_duplicate_receipts_rejected(self):
        evidence = synthetic_report()
        evidence["checks"][1] = copy.deepcopy(evidence["checks"][0])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            verify_report(evidence, COMMIT)

    def test_partial_report_rejected(self):
        evidence = synthetic_report()
        evidence["checks"] = evidence["checks"][:MIN_NATIVE_CHECKS - 1]
        with self.assertRaisesRegex(ValueError, "incomplete"):
            verify_report(evidence, COMMIT)

    def test_every_page_receipt_is_required_even_with_624_passes(self):
        for page in REQUIRED_ROLE_PAGES:
            evidence = synthetic_report()
            receipt(evidence, "role-page-api-" + page)["name"] = "projection-only-" + page
            evidence["checks"].extend({"name": f"padding-{i}", "status": "pass"}
                                      for i in range(624 - len(evidence["checks"])))
            with self.subTest(page=page), self.assertRaisesRegex(ValueError, "Missing executed role_pages"):
                verify_report(evidence, COMMIT)

    def test_legacy_projection_only_624_report_is_rejected(self):
        evidence = synthetic_report()
        evidence["checks"] = [check for check in evidence["checks"] if not check["name"].startswith("role-page-")]
        evidence["checks"].extend({"name": f"legacy-padding-{i}", "status": "pass"}
                                  for i in range(624 - len(evidence["checks"])))
        with self.assertRaisesRegex(ValueError, "Missing executed role_pages"):
            verify_report(evidence, COMMIT)

    def test_every_page_requires_observed_http_docs_and_assets(self):
        for page in REQUIRED_ROLE_PAGES:
            for bad in (None, {}, {"message": {"desk": page, "sections": []}}):
                evidence = synthetic_report()
                receipt(evidence, "role-page-api-" + page)["observation"] = bad
                with self.subTest(page=page, observation=bad), self.assertRaisesRegex(ValueError, "Page API"):
                    verify_report(evidence, COMMIT)

    def test_wrong_page_api_endpoint_identity_method_or_status_rejected(self):
        for page in REQUIRED_ROLE_PAGES:
            for key, bad in (
                ("endpoint", "toefl_house.desk.reception.work"),
                ("endpoint", "/api/method/toefl_house.desk.reception.work"),
                ("endpoint", "/api/method/frappe.desk.page.getpage"),
                ("endpoint", "/api/method/frappe.desk.desk_page.get"),
                ("user", "Administrator"), ("user", "synthetic-outsider@example.test"),
                ("page", "th-missing-page"), ("method", "POST"), ("http_status", 302),
            ):
                evidence = synthetic_report()
                receipt(evidence, "role-page-api-" + page)["observation"][key] = bad
                with self.subTest(page=page, key=key, bad=bad), self.assertRaisesRegex(ValueError, "Page API"):
                    verify_report(evidence, COMMIT)

    def test_page_output_must_be_top_level_docs(self):
        for bad_docs in (None, [], {}, [None], [{"doctype": "Student"}], [{}, {}]):
            evidence = synthetic_report()
            observation = receipt(evidence, "role-page-api-th-reception-desk")["observation"]
            observation["message"] = {"docs": observation.pop("docs")}
            observation["docs"] = bad_docs
            with self.subTest(docs=bad_docs), self.assertRaisesRegex(ValueError, "Page API"):
                verify_report(evidence, COMMIT)

    def test_wrong_returned_page_and_empty_or_incomplete_script_rejected(self):
        for page in REQUIRED_ROLE_PAGES:
            for key, bad in (
                ("doctype", "Student"), ("name", "th-wrong-page"), ("page_name", "th-wrong-page"),
                ("script", None), ("script", ""), ("script", " \n\t"),
                ("script", "frappe.provide('toefl_house.role_desks');"),
            ):
                evidence = synthetic_report()
                receipt(evidence, "role-page-api-" + page)["observation"]["docs"][0][key] = bad
                with self.subTest(page=page, key=key, bad=bad), self.assertRaisesRegex(ValueError, "Page API"):
                    verify_report(evidence, COMMIT)

    def test_each_required_script_marker_is_verified(self):
        page = "th-reception-desk"
        for marker in ("toefl_house.role_desks", "frappe.pages", "on_page_load", page,
                       REQUIRED_ROLE_PAGES[page][1], ROLE_PAGE_CSS):
            evidence = synthetic_report()
            doc = receipt(evidence, "role-page-api-" + page)["observation"]["docs"][0]
            doc["script"] = doc["script"].replace(marker, "removed")
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, "Page API script/assets"):
                verify_report(evidence, COMMIT)

    def test_authorization_and_css_receipts_are_mandatory(self):
        for name in ("role-page-api-authorization", "role-page-css-delivery"):
            evidence = synthetic_report()
            receipt(evidence, name)["name"] = "replacement"
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Missing executed role_pages"):
                verify_report(evidence, COMMIT)

    def test_authorization_requires_all_guest_outsider_cross_role_cells_and_controls(self):
        original = authorization_observation()
        self.assertEqual(len(original["denials"]), 56)
        self.assertEqual(len(original["controls"]), 12)
        for key in ("controls", "denials"):
            for index in range(len(original[key])):
                evidence = synthetic_report()
                receipt(evidence, "role-page-api-authorization")["observation"][key].pop(index)
                with self.subTest(key=key, index=index), self.assertRaisesRegex(ValueError, "Incomplete Page API authorization"):
                    verify_report(evidence, COMMIT)

    def test_authorization_does_not_accept_route_errors_csrf_or_leaked_assets(self):
        for key, bad in (("http_status", 404), ("http_status", 405), ("http_status", 500),
                         ("exc_type", "CSRFTokenError"), ("exc_type", "FileNotFoundError"),
                         ("docs", [{"doctype": "Page", "script": "leaked"}])):
            evidence = synthetic_report()
            receipt(evidence, "role-page-api-authorization")["observation"]["denials"][0][key] = bad
            with self.subTest(key=key, bad=bad), self.assertRaisesRegex(ValueError, "Page API authorization denial"):
                verify_report(evidence, COMMIT)
        for key in ("controls", "denials"):
            evidence = synthetic_report()
            rows = receipt(evidence, "role-page-api-authorization")["observation"][key]
            rows.append(copy.deepcopy(rows[0]))
            with self.subTest(duplicate=key), self.assertRaisesRegex(ValueError, "duplicate Page API"):
                verify_report(evidence, COMMIT)

    def test_css_delivery_requires_real_matching_css(self):
        for key, bad in (("http_status", 404), ("content_type", "text/html"), ("body", ""),
                         ("body", "<html>.th-page .th-section</html>"), ("body", ".unrelated {}"),
                         ("sha256", "0" * 64), ("installed_sha256", "0" * 64),
                         ("endpoint", "/assets/missing.css")):
            evidence = synthetic_report()
            receipt(evidence, "role-page-css-delivery")["observation"][key] = bad
            with self.subTest(key=key, bad=bad), self.assertRaisesRegex(ValueError, "CSS"):
                verify_report(evidence, COMMIT)


class NativeRolePageHttpTest(unittest.TestCase):
    def test_runner_and_report_agree_on_all_eight_audiences_and_endpoints(self):
        self.assertEqual(NATIVE_ROLE_PAGE_API, ROLE_PAGE_API)
        self.assertEqual(NATIVE_ROLE_PAGE_CSS, ROLE_PAGE_CSS)
        self.assertEqual(len(ROLE_PAGE_CASES), 8)
        actual = {page: ("synthetic-" + label.replace("_", "-") + "@example.test", projection)
                  for page, (label, projection) in ROLE_PAGE_CASES.items()}
        self.assertEqual(actual, REQUIRED_ROLE_PAGES)

    def test_collector_calls_getpage_with_name_and_reads_docs(self):
        for page, (user, projection) in REQUIRED_ROLE_PAGES.items():
            expected = page_observation(page, user, projection)
            session = Mock()
            session.get.return_value = Mock(status_code=200)
            session.get.return_value.json.return_value = {"docs": expected["docs"]}
            with self.subTest(page=page):
                self.assertEqual(role_page_api_observation(session, "http://synthetic", page, user), expected)
                session.get.assert_called_once_with("http://synthetic" + ROLE_PAGE_API, params={"name": page},
                                                    headers={"Accept": "application/json"}, timeout=30, allow_redirects=False)

    def test_collector_rejects_projection_only_empty_script_and_wrong_docs(self):
        page = "th-reception-desk"
        user, projection = REQUIRED_ROLE_PAGES[page]
        valid = {"docs": page_observation(page, user, projection)["docs"]}
        invalid = [{"message": {"desk": page, "sections": []}}, {"message": valid}, {"docs": []}]
        for key, value in (("script", ""), ("name", "th-wrong-page"), ("page_name", "th-wrong-page")):
            payload = copy.deepcopy(valid)
            payload["docs"][0][key] = value
            invalid.append(payload)
        for payload in invalid:
            session = Mock()
            session.get.return_value = Mock(status_code=200)
            session.get.return_value.json.return_value = payload
            with self.subTest(payload=payload), self.assertRaises(AssertionError):
                role_page_api_observation(session, "http://synthetic", page, user)

    def test_identity_must_be_the_logged_in_synthetic_audience(self):
        session = Mock()
        session.get.return_value = Mock(status_code=200)
        session.get.return_value.json.return_value = {"message": "Administrator"}
        with self.assertRaisesRegex(AssertionError, "identity mismatch"):
            role_page_identity(session, "http://synthetic", "synthetic-receptionist@example.test")

    def test_css_collector_requires_http_css_equal_to_installed_bytes(self):
        expected = css_observation()
        body = expected["body"].encode()
        session = Mock()
        response = Mock(status_code=200, content=body, headers={"Content-Type": "text/css; charset=utf-8"})
        session.get.return_value = response
        self.assertEqual(role_page_css_observation(session, "http://synthetic/", expected["user"], body), expected)
        session.get.assert_called_once_with("http://synthetic" + ROLE_PAGE_CSS, timeout=30, allow_redirects=False)
        with self.assertRaisesRegex(AssertionError, "differs"):
            role_page_css_observation(session, "http://synthetic", expected["user"], b"stale asset")
        response.headers["Content-Type"] = "text/html"
        with self.assertRaisesRegex(AssertionError, "content type"):
            role_page_css_observation(session, "http://synthetic", expected["user"], body)


class NativeStaticWiringTest(unittest.TestCase):
    def _load_wsgi(self, sites_path=None):
        """Check wrapper wiring without importing Frappe or starting a server."""
        class PassThrough:
            def __init__(self, application, exports):
                self.application = application
                self.exports = exports

            def __call__(self, environ, start_response):
                return self.application(environ, start_response)

        def request_application(environ, start_response):
            start_response("200 OK", [])
            return [environ.get("HTTP_X_FRAPPE_SITE_NAME", environ["HTTP_HOST"]).encode()]

        frappe = ModuleType("frappe")
        app = ModuleType("frappe.app")
        app._site = None
        app.application = request_application
        frappe.app = app
        frappe.init = Mock()
        frappe.destroy = Mock()
        frappe.conf = {"allow_tests": 1, "toefl_house_synthetic_only": 1}
        frappe.get_app_path = Mock(return_value=str(Path(__file__).resolve().parents[2]
                                                   / "apps/toefl_house/toefl_house/public/css/th_design_system.css"))
        build = ModuleType("frappe.build")
        build.setup = Mock()
        build.make_asset_dirs = Mock()
        frappe.build = build
        middlewares = ModuleType("frappe.middlewares")
        middlewares.StaticDataMiddleware = Mock(side_effect=PassThrough)
        shared_data = ModuleType("werkzeug.middleware.shared_data")
        shared_data.SharedDataMiddleware = Mock(side_effect=PassThrough)
        modules = {"frappe": frappe, "frappe.app": app, "frappe.build": build, "frappe.middlewares": middlewares,
                   "werkzeug": ModuleType("werkzeug"), "werkzeug.middleware": ModuleType("werkzeug.middleware"),
                   "werkzeug.middleware.shared_data": shared_data}
        env = {"SITE_NAME": "must-not-pin.localhost"}
        if sites_path is not None:
            env["SITES_PATH"] = str(sites_path)
        source = Path(__file__).resolve().parents[2] / "tools/native/native_wsgi.py"
        spec = importlib.util.spec_from_file_location("native_wsgi_contract", source)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules), patch.dict(os.environ, env, clear=True):
            spec.loader.exec_module(module)
        return module, app, shared_data.SharedDataMiddleware, middlewares.StaticDataMiddleware

    def test_assets_and_public_files_wrap_in_order_using_the_active_sites_root(self):
        root = Path(__file__).resolve().parents[2]
        for sites_path in (None, root / ".foundation/isolated-restore-bench/sites"):
            with self.subTest(sites_path=sites_path):
                module, app, shared, static = self._load_wsgi(sites_path)
                expected = os.path.abspath(str(sites_path) if sites_path is not None else ".")
                self.assertEqual(module.sites_path, expected)
                shared.assert_called_once_with(app.application, {"/assets": os.path.join(expected, "assets")})
                static.assert_called_once_with(module.application.application, {"/files": expected})
                self.assertIs(module.application.application.application, app.application)
                self.assertIsNone(app._site)

    def test_wrapper_preserves_both_synthetic_hosts_restore_host_and_site_header(self):
        module, app, _, _ = self._load_wsgi()
        for host in ("placement-test.localhost", "placement-second.localhost", "placement-restore.localhost"):
            environ = {"HTTP_HOST": host, "PATH_INFO": "/api/method/ping"}
            original = dict(environ)
            with self.subTest(host=host):
                self.assertEqual(module.application(environ, Mock()), [host.encode()])
                self.assertEqual(environ, original)
                self.assertIsNone(app._site)
        environ = {"HTTP_HOST": "127.0.0.1:18000", "HTTP_X_FRAPPE_SITE_NAME": "placement-second.localhost"}
        self.assertEqual(module.application(environ, Mock()), [b"placement-second.localhost"])

    def test_native_asset_setup_links_public_sources_and_checks_delivered_path_bytes(self):
        for exists, contents in ((True, [b"css", b"css"]), (True, [b"stale", b"css"]), (False, [])):
            module, _, _, _ = self._load_wsgi()
            frappe = module.frappe
            with self.subTest(exists=exists, contents=contents), patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), \
                    patch.dict(sys.modules, {"frappe": frappe, "frappe.build": frappe.build}), \
                    patch.object(Path, "is_file", return_value=exists), patch.object(Path, "read_bytes", side_effect=contents):
                if exists and contents[0] == contents[1]:
                    module.setup_assets("placement-test.localhost")
                else:
                    with self.assertRaisesRegex(RuntimeError, "does not expose"):
                        module.setup_assets("placement-test.localhost")
            frappe.init.assert_called_once_with(site="placement-test.localhost", sites_path=module.sites_path)
            frappe.build.setup.assert_called_once_with()
            frappe.build.make_asset_dirs.assert_called_once_with()
            frappe.destroy.assert_called_once_with()

    def test_native_asset_setup_refuses_non_synthetic_sites(self):
        module, _, _, _ = self._load_wsgi()
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            with self.assertRaisesRegex(RuntimeError, "restricted"):
                module.setup_assets("customer.localhost")
        module.frappe.init.assert_not_called()

    def test_both_gunicorn_starts_use_native_wsgi_without_changing_restore_cwd(self):
        source = Path(__file__).resolve().parents[2] / "tools/native/run_native.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        starts = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "Popen":
                continue
            if node.args and isinstance(node.args[0], ast.List):
                args = node.args[0].elts
                if any(isinstance(arg, ast.Constant) and arg.value == "native_wsgi:application" for arg in args):
                    starts.append(node)
        self.assertEqual(len(starts), 2)
        expected_path = ast.dump(ast.parse("str(ROOT/'tools/native')", mode="eval").body)
        cwd_expressions = set()
        for start in starts:
            args = start.args[0].elts
            index = next(i for i, arg in enumerate(args) if isinstance(arg, ast.Constant) and arg.value == "--pythonpath")
            self.assertEqual(ast.dump(args[index + 1]), expected_path)
            cwd_expressions.add(ast.dump(next(kw.value for kw in start.keywords if kw.arg == "cwd")))
        self.assertEqual(cwd_expressions, {ast.dump(ast.parse(expr, mode="eval").body)
                                          for expr in ("benchdir/'sites'", "restore_sites")})
        text = source.read_text(encoding="utf-8")
        self.assertNotIn("frappe.app:application", text)
        self.assertLess(text.index("run('setup-native-static-assets'"), text.index("native_wsgi:application"))
        self.assertLess(text.index("run('setup-restored-native-static-assets'"), text.rindex("native_wsgi:application"))


if __name__ == "__main__":
    unittest.main()
