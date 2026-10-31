"""Final hosted acceptance report must not confuse CI success with release."""
import ast
import copy
from datetime import date
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

from tools.native.final_acceptance_report import (
    MIN_NATIVE_CHECKS, REQUIRED_JOURNEYS, REQUIRED_ROLE_PAGES,
    ROLE_PAGE_API, ROLE_PAGE_CSS, ROLE_PAGE_EXTRA_CONTROLS, verify_report,
)
from tools.native.native_checks import (
    BOOK_INVOICE_API, BOOK_PAYMENT_API, BOOK_PAYMENT_BUILDER, BOOK_RETURN_BUILDER, BOOK_SUBMIT_API,
    CONFIGURATION_API, CONFIGURATION_DENIED_USERS, CONFIGURATION_SECTIONS,
    ROLE_PAGE_API as NATIVE_ROLE_PAGE_API,
    ROLE_PAGE_CASES,
    ROLE_PAGE_CSS as NATIVE_ROLE_PAGE_CSS,
    configuration_http_observation, native_book_http_cycle,
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


def configuration_observation(denied=False):
    result = dict(method="GET", endpoint=CONFIGURATION_API)
    if denied:
        result["denials"] = [dict(user=user, http_status=403, exc_type="PermissionError", docs=[], message=None)
                             for user in CONFIGURATION_DENIED_USERS]
    else:
        sections = []
        for sid in sorted(CONFIGURATION_SECTIONS):
            kind = "facts" if sid in ("operations", "student-guardian") else "queue"
            sections.append(dict(id=sid, title=sid, kind=kind, **{"facts" if kind == "facts" else "items": []}))
        result.update(user="synthetic-course-owner@example.test", http_status=200,
                      message=dict(desk="th-configuration", sections=sections))
    return result


def book_reconciliation_observation():
    accounts = dict(cash="Cash - SYN", receivable="Debtors - SYN", income="Sales - SYN")
    documents = dict(sale="SYN-BOOK-INVOICE", payment="SYN-BOOK-RECEIVE", **{"return": "SYN-BOOK-CREDIT"}, refund="SYN-BOOK-REFUND")
    stages = {key: dict(zip(("cash", "customer", "stock_qty", "stock_value"), values)) for key, values in (
        ("baseline", (1000, 0, 12, 2100)), ("sale", (1000, 600, 10, 1750)),
        ("payment", (1600, 0, 10, 1750)), ("return", (1600, -600, 12, 2100)), ("refund", (1000, 0, 12, 2100)),
    )}
    gl = {}
    for key, postings in (("sale", (("receivable", 600), ("income", -600))),
                          ("payment", (("cash", 600), ("receivable", -600))),
                          ("return", (("income", 600), ("receivable", -600))),
                          ("refund", (("receivable", 600), ("cash", -600)))):
        gl[key] = [dict(company="SYN Company", voucher_type="Sales Invoice" if key in ("sale", "return") else "Payment Entry",
                        voucher_no=documents[key], account=accounts[role], debit=max(value, 0), credit=max(-value, 0),
                        party_type="Customer" if role == "receivable" else None,
                        party="SYN Customer" if role == "receivable" else None, is_cancelled=0) for role, value in postings]
    payments = {}
    for key, kind, source, target, reference, allocated in (
        ("payment", "Receive", "receivable", "cash", "sale", 600), ("refund", "Pay", "cash", "receivable", "return", -600),
    ):
        payments[key] = dict(payment_type=kind, paid_from=accounts[source], paid_to=accounts[target],
                             paid_amount=600, received_amount=600, party_type="Customer", party="SYN Customer",
                             references=[dict(reference_doctype="Sales Invoice", reference_name=documents[reference],
                                              allocated_amount=allocated)])
    stock = {key: [dict(voucher_no=documents[key], item_code="SYN Book", warehouse="SYN Warehouse", is_cancelled=0,
                        actual_qty=qty, stock_value_difference=value)]
             for key, qty, value in (("sale", -2, -350), ("return", 2, 350))}
    return dict(user="synthetic-book-seller@example.test", company="SYN Company", currency="AFN", customer="SYN Customer",
                item="SYN Book", warehouse="SYN Warehouse", amount=600, quantity=2, unit_price=300, unit_cost=175,
                accounts=accounts, documents=documents, document_status=dict.fromkeys(documents, 1),
                invoice_totals={"sale": 600, "return": -600}, outstanding={"sale": 0, "return": 0},
                stages=stages, gl_entries=gl, stock_entries=stock, payment_details=payments)


def book_http_observation():
    reconciliation = book_reconciliation_observation()
    save_url = BOOK_INVOICE_API + "/" + reconciliation["documents"]["sale"]
    requests = [dict(stage=stage, method=method, endpoint=endpoint, http_status=200, csrf=True,
                     user="synthetic-book-seller@example.test") for stage, method, endpoint in (
        ("invoice-create", "POST", BOOK_INVOICE_API), ("invoice-save", "PUT", save_url),
        ("invoice-submit", "POST", BOOK_SUBMIT_API), ("payment-build", "GET", BOOK_PAYMENT_BUILDER),
        ("payment-create", "POST", BOOK_PAYMENT_API), ("payment-submit", "POST", BOOK_SUBMIT_API),
        ("return-build", "GET", BOOK_RETURN_BUILDER), ("return-create", "POST", BOOK_INVOICE_API),
        ("return-submit", "POST", BOOK_SUBMIT_API), ("refund-build", "GET", BOOK_PAYMENT_BUILDER),
        ("refund-create", "POST", BOOK_PAYMENT_API), ("refund-submit", "POST", BOOK_SUBMIT_API),
    )]
    counts = dict.fromkeys(("Sales Invoice", "Payment Entry", "GL Entry", "Stock Ledger Entry"), 0)
    denials = [dict(stage=stage, method=method, endpoint=endpoint, http_status=400 if stage == "csrf-create" else 403,
                   user="synthetic-book-seller@example.test" if stage == "csrf-create" else "synthetic-outsider@example.test",
                   exc_type="CSRFTokenError" if stage == "csrf-create" else "PermissionError",
                   writes_before=dict(counts), writes_after=dict(counts)) for stage, method, endpoint in (
        ("csrf-create", "POST", BOOK_INVOICE_API), ("outsider-create", "POST", BOOK_INVOICE_API),
        ("outsider-save", "PUT", save_url), ("outsider-submit", "POST", BOOK_SUBMIT_API),
        ("outsider-payment", "POST", BOOK_PAYMENT_API), ("outsider-return", "POST", BOOK_INVOICE_API),
        ("outsider-refund", "POST", BOOK_PAYMENT_API),
    )]
    return dict(transport="HTTP", requests=requests, denials=denials, reconciliation=reconciliation)


def synthetic_report():
    required = [n for values in REQUIRED_JOURNEYS.values() for n in values]
    checks = [{"name": n, "status": "pass"} for n in required]
    for check in checks:
        name = check["name"]
        if name == "role-page-api-authorization":
            check["observation"] = authorization_observation()
        elif name == "reception-native-http-cash-receipt-correction-handover":
            check["observation"] = dict(receipt="PAY-1", amended_receipt="PAY-1-1", transfer="PAY-2",
                immediate_student_reduction=100, handover_student_change=0, counter_net=0,
                main_cash_increase=100, idempotent=True, temporary_shares_removed=True,
                unauthorized_read_denied=True, second_handover_denied=True)
        elif name == "role-page-css-delivery":
            check["observation"] = css_observation()
        elif name == "role-desk-configuration-http":
            check["observation"] = configuration_observation()
        elif name == "role-desk-configuration-http-denials":
            check["observation"] = configuration_observation(denied=True)
        elif name == "book-native-return-cash-refund-reconciliation":
            check["observation"] = book_reconciliation_observation()
        elif name == "book-http-cashier-sale-payment-return-refund":
            check["observation"] = book_http_observation()
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
    def test_cash_reconciliation_cannot_be_omitted_or_double_charge_student(self):
        for field, value in (("handover_student_change", 100), ("temporary_shares_removed", False),
                             ("counter_net", 100), ("main_cash_increase", 0)):
            with self.subTest(field=field):
                evidence = synthetic_report()
                check = next(row for row in evidence["checks"] if row["name"] ==
                             "reception-native-http-cash-receipt-correction-handover")
                check["observation"][field] = value
                with self.assertRaisesRegex(ValueError, "Reception"):
                    verify_report(evidence, COMMIT)

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

    def test_every_page_receipt_is_required_even_with_full_check_count(self):
        for page in REQUIRED_ROLE_PAGES:
            evidence = synthetic_report()
            receipt(evidence, "role-page-api-" + page)["name"] = "projection-only-" + page
            evidence["checks"].extend({"name": f"padding-{i}", "status": "pass"}
                                      for i in range(MIN_NATIVE_CHECKS - len(evidence["checks"])))
            with self.subTest(page=page), self.assertRaisesRegex(ValueError, "Missing executed role_pages"):
                verify_report(evidence, COMMIT)

    def test_legacy_projection_only_624_report_is_rejected(self):
        evidence = synthetic_report()
        evidence["checks"] = [check for check in evidence["checks"] if not check["name"].startswith("role-page-")]
        evidence["checks"] = evidence["checks"][:624]
        evidence["checks"].extend({"name": f"legacy-padding-{i}", "status": "pass"}
                                  for i in range(624 - len(evidence["checks"])))
        self.assertEqual(len(evidence["checks"]), 624)
        with self.assertRaisesRegex(ValueError, "Native acceptance evidence is incomplete"):
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


class ConfigurationAndBookEvidenceTest(unittest.TestCase):
    def test_new_receipts_require_actual_observations(self):
        for name in ("role-desk-configuration-http", "role-desk-configuration-http-denials",
                     "book-native-return-cash-refund-reconciliation", "book-http-cashier-sale-payment-return-refund"):
            for missing in (True, False):
                evidence = synthetic_report()
                if missing:
                    receipt(evidence, name)["name"] = "replacement"
                else:
                    receipt(evidence, name).pop("observation")
                with self.subTest(name=name, missing=missing), self.assertRaises(ValueError):
                    verify_report(evidence, COMMIT)

    def test_configuration_collector_calls_real_rpc_and_reads_message(self):
        expected = configuration_observation()
        session = Mock()
        session.get.return_value = Mock(status_code=200)
        session.get.return_value.json.return_value = {"message": expected["message"]}
        self.assertEqual(configuration_http_observation(session, "http://synthetic", expected["user"]), expected)
        session.get.assert_called_once_with("http://synthetic" + CONFIGURATION_API,
                                            headers={"Accept": "application/json"}, timeout=30, allow_redirects=False)

    def test_configuration_positive_requires_endpoint_identity_and_real_sections(self):
        for path, bad in ((('endpoint',), ROLE_PAGE_API), (('user',), 'Administrator'),
                          (('http_status',), 302), (('message',), None), (('message', 'desk'), 'th-owner-cockpit'),
                          (('message', 'sections'), [])):
            evidence = synthetic_report()
            observed = receipt(evidence, "role-desk-configuration-http")["observation"]
            target = observed
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = bad
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "Configuration HTTP"):
                verify_report(evidence, COMMIT)

    def test_http_commerce_requires_every_step_and_strict_csrf_and_role_controls(self):
        original = book_http_observation()
        for key in ("requests", "denials"):
            for index in range(len(original[key])):
                evidence = synthetic_report()
                receipt(evidence, "book-http-cashier-sale-payment-return-refund")["observation"][key].pop(index)
                with self.subTest(key=key, index=index), self.assertRaisesRegex(ValueError, "book HTTP"):
                    verify_report(evidence, COMMIT)
        for key, index, field, bad in (
            ("requests", 0, "endpoint", "/api/method/toefl_house.finance.issue_placement_fee"),
            ("requests", 0, "method", "GET"), ("requests", 0, "csrf", False),
            ("requests", 0, "user", "Administrator"), ("requests", 0, "http_status", 302),
            ("denials", 0, "exc_type", "PermissionError"), ("denials", 1, "exc_type", "CSRFTokenError"),
            ("denials", 1, "http_status", 404), ("denials", 1, "writes_after", {"Sales Invoice": 1}),
        ):
            evidence = synthetic_report()
            receipt(evidence, "book-http-cashier-sale-payment-return-refund")["observation"][key][index][field] = bad
            with self.subTest(key=key, field=field), self.assertRaisesRegex(ValueError, "book HTTP"):
                verify_report(evidence, COMMIT)
        evidence = synthetic_report()
        receipt(evidence, "book-http-cashier-sale-payment-return-refund")["observation"]["reconciliation"]["stages"]["refund"]["cash"] = 1600
        with self.assertRaisesRegex(ValueError, "book accounting"):
            verify_report(evidence, COMMIT)

    def test_cashier_driver_uses_http_for_every_write_and_native_builders(self):
        reconciliation = book_reconciliation_observation()
        documents = reconciliation["documents"]
        cashier, outsider, frappe = Mock(), Mock(), Mock()
        cashier.headers = outsider.headers = {"X-Frappe-CSRF-Token": "unit-csrf"}
        frappe.db.count.return_value = 0
        frappe.as_json.side_effect = lambda value: json.dumps(value, default=str)

        def respond(method, url, **kwargs):
            json.dumps(kwargs.get("json"))  # requests' encoder must receive only JSON-safe native values.
            if kwargs["headers"].get("X-Frappe-CSRF-Token") == "invalid-native-cashier-csrf":
                response = Mock(status_code=400)
                response.json.return_value = {"exc_type": "CSRFTokenError"}
                return response
            payload, params = kwargs.get("json") or {}, kwargs.get("params") or {}
            if url.endswith(BOOK_PAYMENT_BUILDER):
                doc = dict(doctype="Payment Entry", payment_type="Pay" if params["dn"] == documents["return"] else "Receive")
            elif url.endswith(BOOK_RETURN_BUILDER):
                doc = dict(doctype="Sales Invoice", is_return=1)
            elif url.endswith(BOOK_SUBMIT_API):
                doc = dict(payload["doc"], docstatus=1)
            elif method == "PUT":
                doc = dict(doctype="Sales Invoice", name=documents["sale"], docstatus=0)
            else:
                key = ("refund" if payload.get("payment_type") == "Pay" else "payment") if url.endswith(BOOK_PAYMENT_API) else (
                    "return" if payload.get("is_return") else "sale")
                doc = dict(payload, name=documents[key], docstatus=0)
            response = Mock(status_code=200)
            response.json.return_value = {"data" if "/api/resource/" in url else "message": doc}
            return response

        cashier.request.side_effect = respond
        outsider.request.return_value = Mock(status_code=403)
        outsider.request.return_value.json.return_value = {"exc_type": "PermissionError"}
        context = {key: value for key, value in reconciliation.items() if key in (
            "user", "company", "customer", "currency", "item", "warehouse", "amount", "quantity", "unit_price", "unit_cost", "accounts")}
        states = [reconciliation["stages"][key] for key in ("baseline", "sale", "payment", "return", "refund")]
        with patch("tools.native.native_checks.native_book_state", side_effect=states), \
                patch("tools.native.native_checks.collect_book_reconciliation", return_value=reconciliation) as collect:
            payload = {"doctype": "Sales Invoice", "posting_date": date(2026, 10, 23),
                       "conversion_rate": Decimal("1.0"), "items": [{"item_code": "SYN Book"}]}
            observed = native_book_http_cycle(frappe, cashier, outsider, "http://synthetic", context,
                                             payload)
        self.assertEqual(len(observed["requests"]), 12)
        self.assertEqual(len(observed["denials"]), 7)
        self.assertEqual(outsider.request.call_count, 6)
        self.assertEqual(collect.call_args.args[2], documents)
        frappe.as_json.assert_called_once_with(payload)
        frappe.get_doc.assert_not_called()

    def test_configuration_denials_are_complete_and_strict(self):
        for index in range(len(CONFIGURATION_DENIED_USERS)):
            evidence = synthetic_report()
            receipt(evidence, "role-desk-configuration-http-denials")["observation"]["denials"].pop(index)
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, "Configuration HTTP"):
                verify_report(evidence, COMMIT)
        for key, bad in (("http_status", 404), ("http_status", 500), ("exc_type", "CSRFTokenError"),
                         ("message", {"desk": "th-configuration"}), ("docs", [{"doctype": "Page"}])):
            evidence = synthetic_report()
            receipt(evidence, "role-desk-configuration-http-denials")["observation"]["denials"][0][key] = bad
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "Configuration HTTP"):
                verify_report(evidence, COMMIT)

    def test_book_reconciliation_rejects_wrong_amounts_accounts_stock_cash_customer_or_refund(self):
        mutations = (
            (("amount",), 599), (("unit_price",), 301), (("quantity",), 0), (("unit_cost",), float("nan")),
            (("user",), "Administrator"), (("document_status", "refund"), 0),
            (("invoice_totals", "return"), -500), (("outstanding", "return"), -600),
            (("gl_entries", "refund"), []), (("gl_entries", "refund", 0, "account"), "Wrong account"),
            (("gl_entries", "sale", 0, "debit"), 599), (("gl_entries", "refund", 0, "party"), "Wrong customer"),
            (("gl_entries", "return", 0, "is_cancelled"), 1),
            (("stock_entries", "return", 0, "actual_qty"), 1),
            (("stock_entries", "return", 0, "stock_value_difference"), 349),
            (("stock_entries", "sale", 0, "warehouse"), "Wrong warehouse"),
            (("stages", "refund", "cash"), 1600), (("stages", "refund", "customer"), -600),
            (("stages", "refund", "stock_qty"), 10), (("stages", "refund", "stock_value"), 1750),
            (("payment_details", "refund", "payment_type"), "Receive"),
            (("payment_details", "refund", "paid_amount"), 500),
            (("payment_details", "refund", "references", 0, "reference_name"), "SYN-BOOK-INVOICE"),
            (("payment_details", "refund", "references", 0, "allocated_amount"), 600),
        )
        for path, bad in mutations:
            evidence = synthetic_report()
            target = receipt(evidence, "book-native-return-cash-refund-reconciliation")["observation"]
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = bad
            with self.subTest(path=path, bad=bad), self.assertRaisesRegex(ValueError, "book accounting"):
                verify_report(evidence, COMMIT)


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
        frappe.get_all_apps = Mock(return_value=[])
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

    def _asset_fixture(self):
        temporary = tempfile.TemporaryDirectory(prefix="native-static-sources-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        apps = root / "apps"
        for app in ("education", "toefl_house"):
            public = apps / app / app / "public/css"
            public.mkdir(parents=True)
            (public / "th_design_system.css").write_bytes(b".th-page { display: grid; }\n")
        # This triggers the old broad linker's public/node_modules side effect.
        modules = apps / "education/node_modules/fixture-package"
        modules.mkdir(parents=True)
        (modules / "index.js").write_bytes(b"module.exports = {};\n")
        (apps / "foundation_security/foundation_security").mkdir(parents=True)
        return root, apps

    def _configure_asset_apps(self, module, apps):
        module.frappe.get_all_apps.return_value = ["education", "toefl_house", "foundation_security"]
        module.frappe.get_app_path.side_effect = lambda app, *parts: str(apps / app / app / Path(*parts))

    def _public_alias_patch(self, assets, apps):
        native_symlink = Path.symlink_to

        def link(alias, public, target_is_directory=False):
            self.assertEqual(alias.parent, assets, "only immediate children of the served assets root may be linked")
            self.assertEqual(public, (apps / alias.name / alias.name / "public").resolve())
            self.assertTrue(target_is_directory)
            try:
                native_symlink(alias, public, target_is_directory=True)
            except OSError as exc:
                if os.name != "nt" or getattr(exc, "winerror", None) != 1314:
                    raise
                # Windows without the symlink privilege can still exercise the
                # real file/byte checks. Linux CI uses actual directory links.
                shutil.copytree(public, alias)

        return patch.object(Path, "symlink_to", autospec=True, side_effect=link)

    def _app_snapshot(self, apps):
        snapshot = {}
        for path in [apps, *sorted(apps.rglob("*"))]:
            stat = path.lstat()
            content = (os.readlink(path) if path.is_symlink() else path.read_bytes() if path.is_file() else None)
            snapshot[path.relative_to(apps).as_posix()] = (stat.st_mode, stat.st_ino, stat.st_mtime_ns, content)
        return snapshot

    def test_native_asset_setup_only_links_active_roots_without_app_tree_mutation(self):
        root, apps = self._asset_fixture()
        before = self._app_snapshot(apps)
        for directory, site in (("bench/sites", "placement-test.localhost"),
                                ("isolated-restore-bench/sites", "placement-restore.localhost")):
            sites = root / directory
            sites.mkdir(parents=True)
            module, _, _, _ = self._load_wsgi(sites)
            self._configure_asset_apps(module, apps)
            with self.subTest(site=site), patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), \
                    self._public_alias_patch(sites / "assets", apps) as link:
                module.setup_assets(site)
                module.setup_assets(site)
            self.assertEqual(link.call_count, 2, "repeated setup must preserve existing public aliases")
            self.assertEqual((sites / "assets/toefl_house/css/th_design_system.css").read_bytes(),
                             (apps / "toefl_house/toefl_house/public/css/th_design_system.css").read_bytes())
            self.assertTrue((sites / "assets/education/css/th_design_system.css").is_file())
            self.assertFalse((sites / "assets/foundation_security").exists())
            self.assertEqual(self._app_snapshot(apps), before)
            self.assertFalse((apps / "education/education/public/node_modules").is_symlink())
            module.frappe.build.setup.assert_not_called()
            module.frappe.build.make_asset_dirs.assert_not_called()
            self.assertEqual(module.frappe.destroy.call_count, 2)

    def test_native_asset_setup_preserves_preexisting_public_node_modules_link(self):
        root, apps = self._asset_fixture()
        existing = apps / "education/education/public/node_modules"
        try:
            existing.symlink_to(apps / "education/node_modules", target_is_directory=True)
        except OSError as exc:
            if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
                self.skipTest("Windows symlink privilege unavailable; Linux CI covers preexisting link preservation")
            raise
        before = self._app_snapshot(apps)
        module, _, _, _ = self._load_wsgi(root / "bench/sites")
        self._configure_asset_apps(module, apps)
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), self._public_alias_patch(root / "bench/sites/assets", apps):
            module.setup_assets("placement-test.localhost")
        self.assertEqual(self._app_snapshot(apps), before)
        self.assertTrue(existing.is_symlink())

    def test_native_asset_setup_still_rejects_missing_and_stale_css(self):
        for condition in ("missing-installed", "missing-served", "stale-served"):
            root, apps = self._asset_fixture()
            sites = root / "bench/sites"
            installed = apps / "toefl_house/toefl_house/public/css/th_design_system.css"
            served = sites / "assets/toefl_house/css/th_design_system.css"
            if condition == "missing-installed":
                installed.unlink()
            else:
                served.parent.mkdir(parents=True)
                if condition == "stale-served":
                    served.write_bytes(b"stale CSS")
            before = self._app_snapshot(apps)
            module, _, _, _ = self._load_wsgi(sites)
            self._configure_asset_apps(module, apps)
            with self.subTest(condition=condition), patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), \
                    self._public_alias_patch(sites / "assets", apps):
                with self.assertRaisesRegex(RuntimeError, "does not expose"):
                    module.setup_assets("placement-test.localhost")
            self.assertEqual(self._app_snapshot(apps), before)
            if condition == "stale-served":
                self.assertEqual(served.read_bytes(), b"stale CSS")
            module.frappe.build.make_asset_dirs.assert_not_called()
            module.frappe.destroy.assert_called_once_with()

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
