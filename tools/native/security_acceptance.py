#!/usr/bin/env python3
"""Synthetic-site acceptance of the installed Office 365 and WeasyPrint seams.

Only run in hosted, throwaway Native benches with explicit synthetic-site flags.
No real account, configuration, backup, secret, or Microsoft endpoint is used.
All created documents are rolled back before the process exits.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import patch


def check_device_grant_boundary() -> None:
    """Exercise the real Frappe grant allowlist after successful authentication."""
    from frappe.oauth import OAuthWebRequestValidator
    from oauthlib.openid.connect.core.endpoints.pre_configured import Server

    class Validator(OAuthWebRequestValidator):
        def authenticate_client(self, request, *args, **kwargs):
            request.client = SimpleNamespace(client_id="synthetic-public-client")
            return True

        def client_authentication_required(self, request, *args, **kwargs):
            return True

        def save_bearer_token(self, *args, **kwargs):
            raise AssertionError("Device grant reached token persistence")

    server = Server(Validator())
    for suffix in ("", "&device_code=bogus"):
        _headers, body, status = server.create_token_response(
            "https://synthetic.invalid/token", http_method="POST",
            body="grant_type=urn:ietf:params:oauth:grant-type:device_code"
                 "&client_id=synthetic-public-client" + suffix)
        response = json.loads(body)
        assert status == 400 and response["error"] == "unauthorized_client"
        assert "access_token" not in response and "refresh_token" not in response
    print("OAuth device-code grant: missing/bogus codes denied before token creation PASS")


def check_authenticated_client_binding() -> None:
    """Real OAuthlib/Frappe validator: an authenticated client cannot switch IDs."""
    from frappe.oauth import OAuthWebRequestValidator
    from oauthlib.openid.connect.core.endpoints.pre_configured import Server

    saved = []

    class Validator(OAuthWebRequestValidator):
        def authenticate_client(self, request, *args, **kwargs):
            request.client = SimpleNamespace(client_id="synthetic-authenticated-client")
            return True

        def client_authentication_required(self, request, *args, **kwargs):
            return True

        def validate_user(self, username, password, client, request, *args, **kwargs):
            request.user = SimpleNamespace(name="synthetic-oauth-user")
            return True

        def validate_scopes(self, client_id, scopes, client, request, *args, **kwargs):
            return scopes == ["synthetic_scope"]

        def save_bearer_token(self, token, request, *args, **kwargs):
            saved.append(request.client.client_id)

    server = Server(Validator())
    common = "grant_type=password&username=synthetic&password=synthetic&scope=synthetic_scope"
    _headers, body, status = server.create_token_response(
        "https://synthetic.invalid/token", http_method="POST",
        body=common + "&client_id=synthetic-foreign-client")
    response = json.loads(body)
    assert status in (400, 401) and "error" in response
    assert "access_token" not in response and not saved
    _headers, body, status = server.create_token_response(
        "https://synthetic.invalid/token", http_method="POST",
        body=common + "&client_id=synthetic-authenticated-client")
    assert status == 200 and "access_token" in json.loads(body)
    assert saved == ["synthetic-authenticated-client"]
    print("OAuth authenticated client binding: mismatched ID denied; matching control passed")


def check_realtime_pattern_dependency_boundary() -> None:
    """The executed Node dependency graph must not acquire glob/minimatch."""
    import re
    import frappe

    root = Path(frappe.__file__).resolve().parent.parent
    ingress = Path(__file__).resolve().parents[2] / "product" / "web.cjs"
    ingress_imports = re.findall(r'''require\(["']([^"']+)["']\)''', ingress.read_text())
    assert ingress_imports and all(name.startswith("node:") for name in ingress_imports), (
        "Product ingress acquired a non-builtin Node dependency; reassess build-only exclusions")
    files = [root / "socketio.js", root / "node_utils.js"]
    files.extend((root / "realtime").rglob("*.js"))
    seeds = set()
    builtins = {"fs", "path", "dns", "http", "https", "url", "util",
                "events", "stream", "buffer", "crypto", "net", "tls"}
    for file in files:
        for name in re.findall(r'''require\(["']([^"']+)["']\)''', file.read_text()):
            if not name.startswith((".", "node:")) and name not in builtins:
                seeds.add(name)

    def resolve(name, parent):
        for folder in (parent, *parent.parents):
            manifest = folder / "node_modules" / name / "package.json"
            if manifest.is_file():
                return manifest
        raise AssertionError("Executed Node dependency cannot be resolved: " + name)

    pending = [resolve(name, root) for name in seeds]
    seen = set()
    while pending:
        manifest = pending.pop().resolve()
        if manifest in seen:
            continue
        seen.add(manifest)
        data = json.loads(manifest.read_text())
        assert data["name"] not in {"glob", "minimatch"}, (
            "Build-only pattern dependency entered the executed Node graph")
        pending.extend(resolve(name, manifest.parent)
                       for name in data.get("dependencies", {}))
    assert seeds and seen
    print(f"Node realtime dependency boundary: {len(seen)} runtime packages exclude glob/minimatch")


def main() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "1":
        raise RuntimeError("Hosted synthetic runner only")
    # Do not even open a site connection outside the ephemeral Native bench.
    runner_temp = os.environ.get("RUNNER_TEMP")
    if (not runner_temp or Path.cwd().resolve() !=
            (Path(runner_temp) / "placement-runtime/bench/sites").resolve()):
        raise RuntimeError("Refusing non-disposable site path")
    import frappe
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from frappe.utils import oauth
    from frappe.utils.weasyprint import PrintFormatGenerator, download_pdf, get_html
    from toefl_house import social_login

    check_device_grant_boundary()
    check_authenticated_client_binding()
    check_realtime_pattern_dependency_boundary()
    frappe.init(site="placement-test.localhost", sites_path=str(Path.cwd()))
    frappe.connect()
    try:
        if not (frappe.conf.allow_tests == 1 and frappe.conf.toefl_house_synthetic_only == 1):
            raise RuntimeError("Synthetic-site guard missing")
        frappe.set_user("Administrator")
        todo = frappe.get_doc({"doctype": "ToDo", "description": "SYNTHETIC SECURITY PRINT"})
        todo.insert(ignore_permissions=True)
        fmt = frappe.get_doc({"doctype": "Print Format", "name": "SYNTHETIC Security PDF",
                              "doc_type": "ToDo", "standard": "No",
                              "print_format_builder_beta": 1,
                              "format_data": json.dumps({"sections": []})})
        fmt.insert(ignore_permissions=True)
        # Native qualification intentionally installs with --skip-assets. The
        # print template's include_style() otherwise calls .get() on the absent
        # asset manifest, and with an empty manifest it falls back to the
        # unresolved root path "/print_format.bundle.css". That path is not a
        # packaged asset, so the offline PDF policy correctly denies it and
        # refuses the otherwise-incomplete PDF (hosted run 38498528739:
        # PDFResourceDenied at the first authorized download_pdf). Map the
        # bundle name to a stylesheet that is packaged in the pinned Frappe
        # source tree instead, so the real renderer fetches a real local asset
        # through the same policy. Do not return an empty manifest here, and
        # do not teach the policy to tolerate a missing bundle: a genuinely
        # unavailable stylesheet must still fail closed. Product-image CI
        # separately builds and checks the real hashed bundle.
        frappe.local.preload_assets = {"style": [], "script": []}
        synthetic_assets = {"print_format.bundle.css": "/assets/frappe/css/tree.css"}
        with patch("frappe.utils.get_assets_json", return_value=synthetic_assets):
            # Both whitelisted helper paths and the direct constructor execute the
            # installed, hash-verified vendor guard against a *real* synthetic doc.
            preview = get_html("ToDo", todo.name, fmt.name)
            assert "<html" in preview.lower(), "Authorized preview was not rendered"
            download_pdf("ToDo", todo.name, fmt.name)
            pdf = frappe.local.response.filecontent
            assert isinstance(pdf, bytes) and pdf.startswith(b"%PDF"), "Authorized PDF was not rendered"
            assert "<html" in PrintFormatGenerator(fmt.name, todo).get_html_preview().lower()
            assert "<html" in fmt.get_html(todo.name).lower()  # Print Format method path
            fmt.download_pdf(todo.name)
            assert frappe.local.response.filecontent.startswith(b"%PDF")
            # Execute the *installed* vendor render_pdf path with real WeasyPrint.
            # No mocked HTML constructor or HTTP server: any default fetch/DNS is
            # a failure. Main HTML, CSS imports, images, attachments and overlays
            # must all hit the same offline resource policy.
            from toefl_house.pdf_resources import PDFResourceDenied
            hostile = (
                '<img src="http://127.0.0.1:9/private">',
                '<img src="http://169.254.169.254/latest/meta-data/">',
                '<img src="file:///etc/passwd">',
                '<style>@import url("https://external.example.test/redirect");</style>',
                '<style>p { background: url("file:///etc/passwd") }</style><p>test</p>',
                '<link rel="attachment" href="file:///etc/passwd">',
                '<img src="data:image/svg+xml;base64,PHN2Zy8+">',
                '<img src="/private/files/unauthorized.png">',
            )
            # WeasyPrint 68 (the pinned version) has no weasyprint.urls.urlopen:
            # its default fetcher is the URLFetcher class (hosted rerun of the
            # first fix failed here with AttributeError from patch()). Guard
            # that class's fetch method instead; our policy is a plain callable
            # and never goes through URLFetcher, so any call to it is a
            # default-fetch escape.
            with (patch("weasyprint.urls.URLFetcher.fetch", side_effect=AssertionError("Default PDF fetch attempted")) as network,
                  patch("socket.getaddrinfo", side_effect=AssertionError("PDF DNS attempted")) as dns):
                for payload in hostile:
                    generator = PrintFormatGenerator(fmt.name, todo)
                    with (patch.object(generator, "get_main_html", return_value=f"<html><body>{payload}</body></html>"),
                          patch.object(generator, "get_header_footer_html", return_value=(None, None))):
                        try:
                            generator.render_pdf()
                        except PDFResourceDenied:
                            pass
                        else:
                            raise AssertionError("Hostile PDF resource was not rejected")
                # An external image in each overlay must not escape the policy.
                for header, footer in (("header", None), (None, "footer")):
                    generator = PrintFormatGenerator(fmt.name, todo)
                    def overlay(tag):
                        return (f'<html><body><{tag}><img src="http://localhost/private"></{tag}></body></html>'
                                if tag else None)
                    with (patch.object(generator, "get_main_html", return_value="<html><body><p>Valid PDF</p></body></html>"),
                          patch.object(generator, "get_header_footer_html", return_value=(overlay(header), overlay(footer)))):
                        try:
                            generator.render_pdf()
                        except PDFResourceDenied:
                            pass
                        else:
                            raise AssertionError("PDF overlay bypassed resource policy")
                network.assert_not_called()
                dns.assert_not_called()
                # Legitimate packaged resources must still render through the
                # same policy, with no network or DNS: a packaged stylesheet
                # (whose @font-face entries point at packaged font files), a
                # packaged font used by the text, and a packaged SVG image.
                generator = PrintFormatGenerator(fmt.name, todo)
                valid_payload = (
                    '<html><head><link rel="stylesheet" '
                    'href="/assets/frappe/css/fonts/inter/inter.css">'
                    '<style>p { font-family: Inter; }</style></head>'
                    '<body><p>Valid packaged PDF</p>'
                    '<img width="50" height="50" src="/assets/frappe/images/frappe-framework-logo.svg">'
                    '</body></html>'
                )
                with (patch.object(generator, "get_main_html", return_value=valid_payload),
                      patch.object(generator, "get_header_footer_html", return_value=(None, None))):
                    valid_pdf = generator.render_pdf()
                assert isinstance(valid_pdf, bytes) and valid_pdf.startswith(b"%PDF"), (
                    "Legitimate packaged PDF resources were rejected"
                )
                network.assert_not_called()
                dns.assert_not_called()
            # Direct construction cannot bypass authorization even when the doc
            # carries an ignore_permissions flag, as some internal jobs do.
            frappe.set_user("Guest")
            todo.flags.ignore_permissions = True
            try:
                PrintFormatGenerator(fmt.name, todo)
            except frappe.PermissionError:
                pass
            else:
                raise AssertionError("Guest bypassed WeasyPrint constructor guard")
            todo.flags.ignore_permissions = False
            for label, call in (("preview", lambda: get_html("ToDo", todo.name, fmt.name)),
                                ("PDF", lambda: download_pdf("ToDo", todo.name, fmt.name)),
                                ("Print Format preview", lambda: fmt.get_html(todo.name)),
                                ("Print Format PDF", lambda: fmt.download_pdf(todo.name))):
                try:
                    call()
                except frappe.PermissionError:
                    pass
                else:
                    raise AssertionError(f"Guest reached {label} WeasyPrint path")
            frappe.set_user("Administrator")

        # Exercise the pinned Bench PyJWT/cryptography versions, not only the
        # separate test-only venv. This never requests Microsoft's real JWKS.
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        tid = "12345678-1234-1234-1234-123456789abc"
        now = int(time.time())
        claims = {"tid": tid, "sub": "synthetic-subject",
                  "iss": f"https://sts.windows.net/{tid}/",
                  "aud": "synthetic-client", "iat": now, "exp": now + 300,
                  # Deliberately unrelated provider email: it must never select
                  # or auto-link the local account.
                  "email": "attacker-controlled@example.test"}
        signed = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "synthetic"})
        with patch.object(jwt, "PyJWKClient") as jwks:
            jwks.return_value.get_signing_key_from_jwt.return_value.key = private_key.public_key()
            verified = social_login.verify_office365_id_token(signed, "synthetic-client", tid)
            assert verified["tid"] == tid and verified["sub"] == "synthetic-subject"
            wrong = jwt.encode(claims, other_key, algorithm="RS256", headers={"kid": "synthetic"})
            try:
                social_login.verify_office365_id_token(wrong, "synthetic-client", tid)
            except jwt.InvalidSignatureError:
                pass
            else:
                raise AssertionError("Office 365 accepted a token with the wrong signature")

            session = SimpleNamespace(access_token_response=SimpleNamespace(
                text=json.dumps({"id_token": signed})))
            flow = SimpleNamespace(get_auth_session=lambda **kwargs: session)
            calls = []
            linked_user = SimpleNamespace(
                name="staff@example.test",
                enabled=1,
                get_social_login_userid=lambda provider: "synthetic-subject",
            )
            with (patch.dict(frappe.conf, {"office_365_tenant_id": tid}),
                  patch.object(oauth, "get_oauth2_flow", return_value=flow),
                  patch.object(oauth, "get_redirect_uri", return_value="https://synthetic.example.test/cb"),
                  patch.object(oauth, "get_oauth_keys", return_value={"client_id": "synthetic-client"}),
                  patch.object(oauth, "login_oauth_user", side_effect=lambda *a, **k: calls.append((a, k))),
                  patch.object(frappe, "get_all", return_value=[{"parent": "staff@example.test"}]),
                  patch.object(frappe, "get_doc", return_value=linked_user)):
                social_login.login_via_office365("synthetic-code", "synthetic-state")
                assert len(calls) == 1 and calls[0][1]["state"] == "synthetic-state"
                assert calls[0][0][0]["email"] == "staff@example.test", (
                    "Provider email was used instead of the pre-linked local account"
                )
                assert calls[0][0][0]["email"] != claims["email"]

                # A valid signed identity that is not linked must not auto-link
                # or create a local user based on its email/UPN claim.
                with patch.object(frappe, "get_all", return_value=[]):
                    try:
                        social_login.login_via_office365("synthetic-code", "synthetic-state")
                    except frappe.PermissionError:
                        pass
                    else:
                        raise AssertionError("Unlinked Office 365 identity was auto-linked")
                assert len(calls) == 1, "Unlinked identity established a login"

                # Ambiguous duplicate links and disabled local users also fail closed.
                with patch.object(frappe, "get_all", return_value=[
                    {"parent": "staff@example.test"}, {"parent": "other@example.test"}
                ]):
                    try:
                        social_login.login_via_office365("synthetic-code", "synthetic-state")
                    except frappe.PermissionError:
                        pass
                    else:
                        raise AssertionError("Ambiguous Office 365 identity was accepted")
                assert len(calls) == 1

                disabled_user = SimpleNamespace(
                    name="staff@example.test",
                    enabled=0,
                    get_social_login_userid=lambda provider: "synthetic-subject",
                )
                with patch.object(frappe, "get_doc", return_value=disabled_user):
                    try:
                        social_login.login_via_office365("synthetic-code", "synthetic-state")
                    except frappe.PermissionError:
                        pass
                    else:
                        raise AssertionError("Disabled local user authenticated through Office 365")
                assert len(calls) == 1

                session.access_token_response.text = json.dumps({"id_token": wrong})
                try:
                    social_login.login_via_office365("synthetic-code", "synthetic-state")
                except frappe.PermissionError:
                    pass
                else:
                    raise AssertionError("Office 365 callback accepted an invalid signature")
                assert len(calls) == 1, "Rejected callback established a login"

                # A validly signed token from another tenant must be refused.
                other_tid = "87654321-4321-4321-4321-cba987654321"
                other_claims = dict(claims, tid=other_tid, iss=f"https://sts.windows.net/{other_tid}/")
                session.access_token_response.text = json.dumps({
                    "id_token": jwt.encode(other_claims, private_key, algorithm="RS256", headers={"kid": "synthetic"})})
                with patch.dict(frappe.conf, {"office_365_tenant_id": tid}):
                    try:
                        social_login.login_via_office365("synthetic-code", "synthetic-state")
                    except frappe.PermissionError:
                        pass
                    else:
                        raise AssertionError("Office 365 accepted a token from another tenant")
                assert len(calls) == 1, "Foreign-tenant token established a login"

                # Without an owner-configured tenant every login is refused.
                session.access_token_response.text = json.dumps({"id_token": signed})
                with patch.dict(frappe.conf):
                    frappe.conf.pop("office_365_tenant_id", None)
                    try:
                        social_login.login_via_office365("synthetic-code", "synthetic-state")
                    except frappe.PermissionError:
                        pass
                    else:
                        raise AssertionError("Office 365 login accepted without a configured tenant")
                assert len(calls) == 1, "Unconfigured tenant established a login"

        # A11: the authorization code and login state must not reach an Error Log.
        # Control first: the same request context WITHOUT the wrapper must store them,
        # so this check is sensitive to the exposure it guards. Then the real wrapper
        # runs with a failing provider and the stored metadata is read back.
        from types import SimpleNamespace as _Request
        from frappe.utils.error import log_error as _log_error
        code_value, state_value = "SYNTH-A11-CODE-7f3a", "SYNTH-A11-STATE-9c1e"
        saved_request = getattr(frappe.local, "request", None)
        saved_form = getattr(frappe.local, "form_dict", None)

        def _snapshot_metadata():
            doc = _log_error(title="A11 synthetic snapshot", defer_insert=False)
            stored = str(frappe.db.get_value("Error Log", doc.name, "metadata") or "")
            frappe.delete_doc("Error Log", doc.name, force=True, ignore_permissions=True)
            return stored

        try:
            frappe.local.request = _Request(
                method="GET", path="/api/method/toefl_house.social_login.login_via_office365",
                referrer=None)
            frappe.local.form_dict = frappe._dict(code=code_value, state=state_value)
            control = _snapshot_metadata()
            assert code_value in control and state_value in control, (
                "A11 control: the request context did not reproduce the exposure")

            frappe.local.form_dict = frappe._dict(code=code_value, state=state_value)
            with patch.object(oauth, "get_oauth2_flow", side_effect=RuntimeError("synthetic provider failure")):
                try:
                    social_login.login_via_office365(code_value, state_value)
                except frappe.PermissionError:
                    pass
                else:
                    raise AssertionError("A11 control: failing provider was accepted")
            redacted = _snapshot_metadata()
            assert "method" in redacted and "form_dict" in redacted, "A11: snapshot lacks request metadata"
            assert code_value not in redacted and state_value not in redacted, (
                "A11: authorization code or state reached Error Log metadata")
        finally:
            frappe.local.request = saved_request
            frappe.local.form_dict = saved_form
        print("Synthetic site: authorized PDF/preview, guarded direct constructor, identity-bound Office 365 callback PASS; A11 callback secrets absent from Error Log PASS")
    finally:
        frappe.db.rollback()  # discard only this process's synthetic documents
        frappe.destroy()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # The hosted job truncates retained logs. Emit only an exception type
        # and code-frame names/line numbers, never site values or token text.
        import traceback
        frames = traceback.extract_tb(exc.__traceback__)[-8:]
        path = ",".join(f"{Path(frame.filename).name}:{frame.name}:{frame.lineno}" for frame in frames)
        print(f"SECURITY-SITE-ACCEPTANCE-FAILED {type(exc).__name__} frames={path}", flush=True)
        raise SystemExit(1) from None
