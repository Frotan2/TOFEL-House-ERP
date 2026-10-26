"""Real Chromium role desk qualification against a disposable product image.

The fixture is never shipped in the image or customer kit. The initial-login
check separately covers the fresh setup wizard; these checks use native wizard
setup and isolated, minimal-role users to exercise the actual eight desk clients.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


CASES = (
    ("th-reception-desk", "reception", "Reception", "reception.work", "TOEFL House Reception Desk"),
    ("th-academic-desk", "academic", "Academic Manager", "academic.work", "TOEFL House Academic Desk"),
    ("th-finance-desk", "finance", "Finance Manager", "finance.work", "TOEFL House Finance Desk"),
    ("th-operations-desk", "operations", "General Manager", "operations.work", "TOEFL House Operations Desk"),
    ("th-owner-cockpit", "owner", "Course Owner", "owner.cockpit", "TOEFL House Owner Cockpit"),
    ("th-academic-setup", "owner", "Course Owner", "setup.work", "TOEFL House Academic Setup"),
    ("th-teacher-desk", "teacher", "Instructor", "teacher.work", "TOEFL House Teacher Desk"),
    ("th-configuration", "owner", "Course Owner", "configuration.work", "TOEFL House Configuration"),
)
PAGE_API = "/api/method/frappe.desk.desk_page.getpage"


def require_hosted():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "1":
        raise RuntimeError("Role browser qualification is restricted to disposable hosted CI")


def prepare():
    require_hosted()
    # This is a separate CI helper copied into /tmp, never an installed app.
    if Path.cwd() != Path("/home/frappe/bench/sites"):
        raise RuntimeError("Refusing a non-product CI fixture path")
    password = os.environ.get("BROWSER_UI_PASSWORD", "")
    if len(password) < 20:
        raise RuntimeError("A private synthetic test password is required")
    import frappe
    from toefl_house.security import REFUSED, site_mode

    frappe.init(site="toeflhouse.localhost", sites_path=str(Path.cwd()))
    frappe.connect()
    try:
        if site_mode() != REFUSED or frappe.conf.get("toefl_house_production_active"):
            raise RuntimeError("The disposable product site must remain deactivated")
        if frappe.is_setup_complete() or any(frappe.db.count(doctype) for doctype in (
            "Company", "Student", "Student Applicant", "Sales Invoice", "Payment Entry",
        )):
            raise RuntimeError("Browser setup requires the fresh, empty CI site")
        if any(frappe.db.exists("User", f"browser-{actor}@example.test") for actor in {c[1] for c in CASES}):
            raise RuntimeError("Refusing to replace existing browser fixture users")
        frappe.set_user("Administrator")
        if not frappe.is_setup_complete():
            from frappe.desk.page.setup_wizard.setup_wizard import setup_complete
            from toefl_house.finance.shamsi import (
                fiscal_year_bounds, gregorian_to_shamsi,
            )
            solar_year = gregorian_to_shamsi(frappe.utils.getdate())[0]
            fy_start, fy_end = fiscal_year_bounds(solar_year)
            # The real Afghanistan test company must never use a Jan-Dec
            # fiscal year simply because the CI host is Gregorian.
            setup_complete({
                "language": "English", "timezone": "Asia/Kabul", "country": "Afghanistan",
                "currency": "AFN", "company_name": "SYN Browser Institute", "company_abbr": "SBI",
                "chart_of_accounts": "Standard", "fy_start_date": fy_start.isoformat(),
                "fy_end_date": fy_end.isoformat(), "enable_telemetry": 0, "setup_demo": 0,
            })
        if not frappe.is_setup_complete():
            raise RuntimeError("Native synthetic setup did not complete")
        for actor, role in sorted({(c[1], c[2]) for c in CASES}):
            frappe.get_doc({
                "doctype": "User", "email": f"browser-{actor}@example.test",
                "first_name": "Synthetic " + actor, "enabled": 1, "send_welcome_email": 0,
                "new_password": password, "roles": [{"role": role}],
            }).insert()
        frappe.db.commit()
        frappe.clear_cache()
        print("Prepared six minimal-role synthetic browser accounts; operational mode remains REFUSED")
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        frappe.destroy()


def qualify(base_url: str, destination: Path):
    require_hosted()
    url = urlsplit(base_url)
    if url.scheme != "http" or url.hostname != "127.0.0.1" or url.port != 8000 or url.path:
        raise ValueError("Browser qualification requires the loopback CI product endpoint")
    password = os.environ["BROWSER_UI_PASSWORD"]
    sha = os.environ["GITHUB_SHA"]
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("A full source revision is required")
    destination.mkdir(parents=True, exist_ok=False)
    report = {"commit": sha, "status": "running", "scope": "SYNTHETIC CHROMIUM ROLE DESKS",
              "production_authorization": "REJECT", "desks": []}
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for slug, actor, role, method, title in CASES:
                    context = browser.new_context(viewport={"width": 1440, "height": 1000})
                    page = context.new_page()
                    errors, failed_assets, console_errors = [], [], []
                    page.on("console", lambda msg: console_errors.append(str(msg.text)[:220])
                            if msg.type == "error" else None)
                    page.on("pageerror", lambda error: errors.append({
                        "message": str(error), "stack": error.stack or "",
                    }))

                    def check_response(response):
                        path = urlsplit(response.url).path
                        if path.startswith("/assets/") and response.request.resource_type in ("script", "stylesheet"):
                            if response.status >= 400:
                                failed_assets.append({"path": path, "status": response.status})

                    def check_failure(request):
                        path = urlsplit(request.url).path
                        if path.startswith("/assets/") and request.resource_type in ("script", "stylesheet"):
                            failed_assets.append({"path": path, "failure": request.failure})

                    page.on("response", check_response)
                    page.on("requestfailed", check_failure)
                    try:
                        page.goto(base_url + "/login", wait_until="domcontentloaded", timeout=120_000)
                        page.locator("#login_email").fill(f"browser-{actor}@example.test")
                        page.locator("#login_password").fill(password)
                        page.wait_for_function("typeof frappe !== 'undefined' && typeof frappe.call === 'function'")
                        page.locator(".for-login .form-login .btn-login[type=submit]").click()
                        page.wait_for_url("**/desk**", timeout=90_000)
                        # Navigate through the live router so Page.getpage loads
                        # and executes the installed page script in Chromium.
                        page.wait_for_function("typeof frappe !== 'undefined' && typeof frappe.set_route === 'function'")
                        # /desk navigation can complete before Frappe's first
                        # Desktop page has actually become visible. Wait for
                        # the initial SPA surface before requesting our route,
                        # otherwise a late initial render can hide the desk.
                        page.wait_for_function("""() => document.readyState === 'complete' &&
                            Array.from(document.querySelectorAll('.page-content'))
                                .some(e => e.getClientRects().length > 0 &&
                                           getComputedStyle(e).visibility !== 'hidden')""",
                            timeout=60_000)
                        with page.expect_response(lambda r: urlsplit(r.url).path == PAGE_API, timeout=60_000) as page_reply:
                            with page.expect_response(lambda r: urlsplit(r.url).path == "/api/method/toefl_house.desk." + method,
                                                      timeout=60_000) as desk_reply, page.expect_response(
                                lambda r: urlsplit(r.url).path == "/api/method/toefl_house.desk.available", timeout=60_000,
                            ) as registry_reply:
                                page.evaluate("slug => frappe.set_route(slug)", slug)
                        page_response = page_reply.value
                        page_data = page_response.json()
                        assert page_response.status == 200, (slug, "Page API", page_response.status)
                        assert len(page_data.get("docs", [])) == 1 and page_data["docs"][0]["name"] == slug, (slug, "wrong Page")
                        response = desk_reply.value
                        payload = response.json().get("message")
                        assert response.status == 200 and isinstance(payload, dict) and payload.get("desk") == slug, (slug, "desk RPC", response.status)
                        registry = registry_reply.value
                        assert registry.status == 200 and registry.json().get("message", {}).get("desks"), (slug, "desk navigation")
                        desk = page.locator(".th-page:visible")
                        desk.wait_for(state="visible", timeout=30_000)
                        heading = desk.locator(".th-page-title")
                        heading.wait_for(state="visible")
                        assert heading.inner_text() == title, (slug, "mounted title")
                        desk.locator(".th-desk-sections .th-section").first.wait_for(state="visible")
                        page.wait_for_function("Array.from(document.styleSheets).some(s => s.href && new URL(s.href).pathname === '/assets/toefl_house/css/th_design_system.css')")
                        sections = desk.locator(".th-desk-sections .th-section").count()
                        assert sections == len(payload["sections"]) and sections > 0, (slug, "sections", sections)
                        assert not desk.locator(".th-desk-sections .th-alert-title").count(), (slug, "error state")
                        assert not errors, (slug, "JavaScript exceptions", errors)
                        assert not failed_assets, (slug, "failed assets", failed_assets)
                        identity = context.request.get(base_url + "/api/method/frappe.auth.get_logged_user")
                        assert identity.status == 200 and identity.json().get("message") == f"browser-{actor}@example.test"
                        # A healthy Engine.IO listener alone missed the broken
                        # same-origin route and container-local auth callback.
                        page.wait_for_function("""typeof frappe !== 'undefined' &&
                            frappe.realtime && frappe.realtime.socket &&
                            frappe.realtime.socket.connected === true""", timeout=30_000)
                        page.screenshot(path=str(destination / f"{slug}.png"), full_page=True)
                        report["desks"].append({"page": slug, "role": role, "status": "pass", "sections": sections,
                                                "page_api_status": 200, "desk_rpc_status": 200,
                                                "javascript_errors": 0, "failed_assets": 0,
                                                "authenticated_realtime_connected": True})
                        print("PASS Chromium " + slug, flush=True)
                    except Exception:
                        report["status"] = "fail"
                        report["failed_page"] = slug
                        # Safe, synthetic diagnostic: never log credentials,
                        # cookie, token, Student data, raw network bodies.
                        # Fail closed, preserve the screenshot and a bounded
                        # route/JS state report for actual product repair.
                        try:
                            detail = page.evaluate("""slug => ({
                                path: location.pathname,
                                hash: location.hash,
                                route: typeof frappe !== 'undefined' &&
                                       typeof frappe.get_route === 'function'
                                    ? frappe.get_route().map(String).slice(0, 4) : [],
                                pageHook: typeof frappe !== 'undefined' &&
                                    frappe.pages && frappe.pages[slug]
                                    ? typeof frappe.pages[slug].on_page_load : 'missing',
                                mounted: document.querySelectorAll('.th-page').length,
                                visible: [...document.querySelectorAll('.th-page')]
                                    .filter(e => !!(e.offsetWidth || e.offsetHeight ||
                                                    e.getClientRects().length)).length,
                                bodies: document.querySelectorAll('.page-content').length,
                                hiddenAncestors: (() => {
                                    const node = document.querySelector('.th-page');
                                    const values = [];
                                    let e = node;
                                    for (let i = 0; e && i < 10; i++, e = e.parentElement) {
                                        const style = getComputedStyle(e);
                                        values.push({
                                            tag: e.tagName.toLowerCase(),
                                            classes: String(e.className || '').slice(0, 140),
                                            display: style.display,
                                            visibility: style.visibility,
                                            hasRect: e.getClientRects().length > 0
                                        });
                                    }
                                    return values;
                                })(),
                                title: document.title.slice(0, 120)
                            })""", slug)
                            report["failure_diagnostic"] = detail
                            report["javascript_error_types"] = [
                                (e["message"].split(":")[0])[:80] for e in errors[-5:]]
                            report["console_error_types"] = [
                                x.split(":")[0][:80] for x in console_errors[-5:]]
                            report["failed_assets"] = failed_assets[-8:]
                            print("ROLE-DESK FAILURE (synthetic): " +
                                  json.dumps(report["failure_diagnostic"]), flush=True)
                            if report["javascript_error_types"]:
                                print("JS errors: " +
                                      json.dumps(report["javascript_error_types"]), flush=True)
                            if report["console_error_types"]:
                                print("Console errors: " +
                                      json.dumps(report["console_error_types"]), flush=True)
                            if failed_assets:
                                print("Asset failures: " +
                                      json.dumps(failed_assets[-8:]), flush=True)
                        except Exception:
                            report["failure_diagnostic"] = {"status": "probe-unavailable"}
                        page.screenshot(path=str(destination / f"{slug}-failure.png"), full_page=True)
                        raise
                    finally:
                        if len(report["desks"]) < len(CASES) and errors:
                            print("Browser JavaScript exception types observed; see failing check")
                        context.close()
            finally:
                browser.close()
        report["status"] = "pass"
    finally:
        (destination / "role-desks.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("browser-role-evidence"))
    args = parser.parse_args()
    if args.prepare:
        prepare()
    else:
        qualify(args.base_url, args.output)


if __name__ == "__main__":
    main()
