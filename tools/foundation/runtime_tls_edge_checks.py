"""Exercise the TLS edge as a real client, from inside the bench environment.

Two independent TLS clients are used on purpose. ``openssl s_client`` is the
protocol-level instrument: it reports the negotiated version and cipher, the
verification return code, and - when a version is refused - the alert the listener
sent. Python's own ``ssl`` module is a second implementation, so a result that
depends on one client's quirks cannot pass unnoticed. Both verify the private CA,
both refuse an unrelated one, and both refuse a hostname mismatch.

The functional half then crosses the same edge with ``requests``: ping, login, the
``Secure`` flag on the session cookie, the pinned template's security headers, and
the file privacy boundary that independent recovery proved over plaintext - here
proven again over TLS, including that a private file still reaches the client only
through ``X-Accel-Redirect`` to nginx's ``internal`` location.

Frappe sets ``Secure`` on the session cookie because ``frappe.auth`` derives it from
``frappe.local.request.scheme`` (auth.py, pin 988e54f3: ``if not secure and
hasattr(frappe.local, "request"): secure = frappe.local.request.scheme == "https"``).
The ``ProxyFix`` wrapper that would set that scheme from ``X-Forwarded-Proto`` lives
in app.py's werkzeug dev-server block, so it does not apply under Gunicorn; what
does apply is Gunicorn's own ``secure_scheme_headers``, whose default maps
``X-FORWARDED-PROTO: https`` and whose default ``forwarded_allow_ips`` is
``127.0.0.1,::1``. The proxy therefore has to send that header from a trusted
address, and this check is what proves the whole chain works rather than assuming it.

Only synthetic credentials and synthetic content are used. The admin password is
read from the environment and never written to the result.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

import tls_edge as edge  # noqa: E402

SITE = edge.EDGE_HOST
WRONG_HOST = edge.WRONG_HOST
PRIVATE_FILE = "tls-edge-private.txt"
PUBLIC_FILE = "tls-edge-public.txt"


def pem_to_der_sha256(path):
    """Digest a PEM certificate's DER body, without any third-party dependency."""
    text = Path(path).read_text()
    body = "".join(line.strip() for line in text.splitlines()
                   if line.strip() and not line.strip().startswith("-----"))
    return hashlib.sha256(base64.b64decode(body)).hexdigest()


def peer_certificate_sha256(host, port, cafile):
    """Connect with Python's own TLS stack and digest the certificate served."""
    context = ssl.create_default_context(cafile=str(cafile))
    with socket.create_connection((host, int(port)), timeout=30) as plain:
        with context.wrap_socket(plain, server_hostname=host) as secure:
            negotiated = {"protocol": secure.version(), "cipher": secure.cipher()[0]}
            der = secure.getpeercert(binary_form=True)
    return hashlib.sha256(der).hexdigest(), negotiated


#: Protocol ranges offered through Python's own TLS stack. ``ssl.TLSVersion.SSLv3``
#: exists as a member but OpenSSL 3 cannot offer it, so SSLv3 stays unofferable.
PYTHON_PROTOCOL_RANGES = {
    "TLSv1.2": ("TLSv1_2", "TLSv1_2"),
    "TLSv1.3": ("TLSv1_3", "TLSv1_3"),
    "TLSv1": ("TLSv1", "TLSv1"),
    "TLSv1.1": ("TLSv1_1", "TLSv1_1"),
}


def python_tls_attempt(host, port, minimum_name, maximum_name):
    """Offer a pinned protocol range using Python's TLS stack.

    Python sets the version bounds through OpenSSL's C API
    (``SSL_CTX_set_min_proto_version``), which is not subject to the distribution's
    ``openssl.cnf`` policy. That policy is exactly what stops ``s_client`` from
    offering TLS 1.0 or 1.1 on a hardened image - and a client that never opens a
    socket cannot show that the listener refused anything. This is therefore the
    client that can actually observe the refusal, and it is a second independent
    implementation rather than a workaround layered on the first.
    """
    import warnings

    minimum = getattr(ssl.TLSVersion, minimum_name)
    maximum = getattr(ssl.TLSVersion, maximum_name)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # The protocol version is what is under test here, not the chain: the chain and
    # hostname are verified separately, with verification turned on.
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            context.minimum_version = minimum
            context.maximum_version = maximum
            with socket.create_connection((host, int(port)), timeout=30) as plain:
                with context.wrap_socket(plain, server_hostname=host) as secure:
                    return {"client": "python ssl", "negotiated": secure.version(),
                            "cipher": secure.cipher()[0], "error": None,
                            "offered_range": [minimum_name, maximum_name]}
    except Exception as exc:  # noqa: BLE001 - the refusal text is the evidence
        return {"client": "python ssl", "negotiated": None, "cipher": None,
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "offered_range": [minimum_name, maximum_name]}


def parse_python_attempt(attempt):
    """Express a Python TLS attempt in the same shape the openssl parser returns.

    The refusal text Python raises (``tlsv1 alert protocol version``) carries the
    same alert the listener sent, so the shared parser attributes it identically
    instead of a second, divergent classification being invented here.
    """
    if attempt["negotiated"]:
        report = edge.parse_s_client(
            f"New, {attempt['negotiated']}, Cipher is {attempt['cipher']}\n"
            f"Verify return code: 0 (ok)\n")
        report["protocol"] = attempt["negotiated"]
        report["protocol_found"] = True
    else:
        report = edge.parse_s_client(attempt["error"] or "")
    report["client"] = "python ssl"
    report["python_error"] = attempt["error"]
    return report


def effective_observation(*reports):
    """Pick the observation that actually says something about the listener.

    A negotiated cipher is server evidence; so is a refusal the server caused. An
    attempt the client could not make is not, and is only used if nothing better
    exists - which leaves the verdict NOT PROVEN rather than quietly passing.
    """
    for report in reports:
        if report.get("cipher_found"):
            return report, report.get("client") or "openssl s_client"
    for report in reports:
        if report.get("refusal_attributable_to_server") is True:
            return report, report.get("client") or "openssl s_client"
    return reports[0], "neither client produced server-attributable evidence"


def s_client(port, *, protocol=None, cafile=None, verify_hostname=None, openssl_conf=None):
    """One ``openssl s_client`` attempt, with stdout and stderr combined.

    The refusal evidence lives on stderr (``tlsv1 alert protocol version``) while
    the negotiation summary is on stdout, so both are needed to parse honestly.

    ``openssl_conf`` points at a relaxed client configuration. It is used only for
    the protocols the listener is supposed to refuse: a distribution's default
    OpenSSL policy forbids offering TLS 1.0 and 1.1 at all, and a client that never
    opens a socket cannot show that the SERVER refused anything. Relaxing the client
    is what makes the server's refusal observable. It is recorded per attempt so no
    reader mistakes a relaxed client for a relaxed server, and the allowed-protocol
    and trust-control attempts stay on the distribution default.
    """
    command = edge.s_client_command(port, protocol=protocol, cafile=cafile,
                                    verify_hostname=verify_hostname, servername=SITE)
    environment = dict(os.environ)
    if openssl_conf:
        environment["OPENSSL_CONF"] = str(openssl_conf)
    completed = subprocess.run(command, capture_output=True, text=True, timeout=90,
                               input="", env=environment, check=False)
    return {
        "command": command,
        "exit_code": completed.returncode,
        "relaxed_client_policy": bool(openssl_conf),
        "output": (completed.stdout or "") + (completed.stderr or ""),
    }


def main() -> int:
    if os.environ.get("GITHUB_ACTIONS") != "true" or SITE not in sys.argv[1:]:
        raise SystemExit("Disposable hosted TLS-edge site only")

    import requests

    certs = Path(os.environ["FOUNDATION_TLS_EDGE_CERTS"])
    http_port = os.environ["FOUNDATION_TLS_EDGE_HTTP_PORT"]
    https_port = os.environ["FOUNDATION_TLS_EDGE_HTTPS_PORT"]
    manifest = json.loads(Path(os.environ["FOUNDATION_TLS_EDGE_MANIFEST"]).read_text())
    result_path = Path(os.environ["FOUNDATION_TLS_EDGE_CHECKS_RESULT"])
    admin = os.environ["FOUNDATION_ADMIN_PASSWORD"]

    ca = certs / "ca.pem"
    unrelated = certs / "unrelated-ca.pem"
    server_pem = certs / "server.pem"
    https_origin = f"https://{SITE}:{https_port}"
    http_origin = f"http://{SITE}:{http_port}"

    result = {
        "scope": ("Client-side verification of a real TLS edge in front of a live Frappe site; "
                  "synthetic data only"),
        "site": SITE, "https_origin": https_origin, "http_origin": http_origin,
        "status": "running", "checks": [], "verdicts": {},
    }

    def write():
        result_path.write_text(json.dumps(result, indent=2) + "\n")

    def check(name, fn, *, expected_failure=False):
        """Run one check. ``expected_failure`` records a required refusal."""
        try:
            observation = fn()
        except Exception as exc:
            record = {"name": name, "status": "fail", "exception": type(exc).__name__,
                      "message": str(exc)[:400]}
            if expected_failure:
                record["status"] = "required-failure"
                record["expected"] = True
                result["checks"].append(record)
                write()
                return {"failed_as_required": True, "exception": type(exc).__name__,
                        "message": str(exc)[:300]}
            result["checks"].append(record)
            result["status"] = "fail"
            write()
            raise
        if expected_failure:
            result["checks"].append({
                "name": name, "status": "fail", "expected": True,
                "message": "A required refusal did not happen; the boundary is not enforced"})
            result["status"] = "fail"
            write()
            raise AssertionError(name + " was expected to fail and did not")
        result["checks"].append({"name": name, "status": "pass", "observation": observation})
        write()
        return observation

    def _resolution():
        address = socket.gethostbyname(SITE)
        if address != "127.0.0.1":
            raise AssertionError(SITE + " resolves to " + address + ", not the listener address")
        return {"resolved_to": address,
                "note": ("A real name resolution entry was added for this run, so clients "
                         "perform genuine SNI and genuine hostname verification rather than "
                         "connecting to an IP with a Host header.")}

    check("edge-hostname-resolves-to-the-listener", _resolution)

    def _ping():
        deadline = time.monotonic() + 240
        attempts = 0
        last = None
        while time.monotonic() < deadline:
            attempts += 1
            try:
                response = requests.get(https_origin + "/api/method/ping",
                                        verify=str(ca), timeout=15)
                last = response.status_code
                if response.status_code == 200:
                    return {"reachable_over_tls": True, "attempts": attempts,
                            "http_status": 200,
                            "ping_message": response.json().get("message"),
                            "certificate_verified_against": str(ca)}
            except Exception as exc:  # noqa: BLE001 - the reason is recorded, not guessed
                last = type(exc).__name__ + ": " + str(exc)[:160]
            time.sleep(3)
        raise AssertionError("Edge did not answer ping over TLS within 240s; last=" + str(last))

    check("site-answers-ping-over-tls", _ping)

    def _served_certificate():
        served, negotiated = peer_certificate_sha256(SITE, https_port, ca)
        issued = pem_to_der_sha256(server_pem)
        if served != issued:
            raise AssertionError("The certificate served is not the one issued: served="
                                 + served + " issued=" + issued)
        return {"served_certificate_sha256": served, "issued_certificate_sha256": issued,
                "match": True, "python_tls_negotiated": negotiated,
                "note": ("Digests the DER the listener actually presented, so a stale or "
                         "substituted certificate cannot pass.")}

    check("served-certificate-is-the-one-issued", _served_certificate)

    def _python_tls_controls():
        """The same three controls, from a second independent TLS client."""
        _, negotiated = peer_certificate_sha256(SITE, https_port, ca)
        accepted = {"verifies_with_the_private_ca": True, "negotiated": negotiated}

        def unrelated_attempt():
            peer_certificate_sha256(SITE, https_port, unrelated)

        def wrong_name_attempt():
            context = ssl.create_default_context(cafile=str(ca))
            with socket.create_connection((SITE, int(https_port)), timeout=30) as plain:
                with context.wrap_socket(plain, server_hostname=WRONG_HOST):
                    pass

        unrelated_error = None
        try:
            unrelated_attempt()
        except ssl.SSLCertVerificationError as exc:
            unrelated_error = str(exc)[:200]
        wrong_name_error = None
        try:
            wrong_name_attempt()
        except ssl.SSLCertVerificationError as exc:
            wrong_name_error = str(exc)[:200]

        accepted["refuses_an_unrelated_ca"] = unrelated_error is not None
        accepted["unrelated_ca_error"] = unrelated_error
        accepted["refuses_a_hostname_mismatch"] = wrong_name_error is not None
        accepted["hostname_mismatch_error"] = wrong_name_error
        if not accepted["refuses_an_unrelated_ca"]:
            raise AssertionError("Python's TLS client accepted a certificate from an "
                                 "unrelated CA")
        if not accepted["refuses_a_hostname_mismatch"]:
            raise AssertionError("Python's TLS client accepted a certificate whose name did "
                                 "not match the requested host")
        return accepted

    check("independent-tls-client-agrees-on-all-three-controls", _python_tls_controls)

    def _protocol_matrix():
        # A relaxed client policy, used only for the refusal attempts.
        relaxed = certs.parent / "openssl-relaxed.cnf"
        relaxed.write_text(edge.PERMISSIVE_OPENSSL_CONF)
        attempts = {}
        excerpts = {}
        for protocol in edge.ALLOWED_PROTOCOLS + edge.OFFERABLE_REFUSED_PROTOCOLS:
            relax = protocol in edge.OFFERABLE_REFUSED_PROTOCOLS
            attempt = s_client(https_port, protocol=protocol, cafile=ca, verify_hostname=SITE,
                               openssl_conf=relaxed if relax else None)
            from_openssl = edge.parse_s_client(attempt["output"])
            from_openssl["exit_code"] = attempt["exit_code"]
            from_openssl["relaxed_client_policy"] = attempt["relaxed_client_policy"]
            from_openssl["client"] = "openssl s_client"
            low, high = PYTHON_PROTOCOL_RANGES[protocol]
            python_attempt = python_tls_attempt(SITE, https_port, low, high)
            from_python = parse_python_attempt(python_attempt)
            parsed, source = effective_observation(from_openssl, from_python)
            parsed["observed_through"] = source
            parsed["openssl_observation"] = {
                "outcome": ("ACCEPTED" if from_openssl.get("cipher_found") else "not negotiated"),
                "protocol": from_openssl.get("protocol"),
                "refusal_reason": from_openssl.get("refusal_reason"),
                "server_attributable": from_openssl.get("refusal_attributable_to_server"),
                "relaxed_client_policy": attempt["relaxed_client_policy"],
            }
            parsed["python_observation"] = {
                "negotiated": python_attempt["negotiated"],
                "cipher": python_attempt["cipher"],
                "error": python_attempt["error"],
                "server_attributable": from_python.get("refusal_attributable_to_server"),
            }
            attempts[protocol] = parsed
            # Artifacts from a hosted run are not always retrievable, so the raw
            # negotiation text travels in the published evidence: without it a
            # NOT OBSERVABLE outcome cannot be diagnosed.
            excerpts[protocol] = {
                "exit_code": attempt["exit_code"],
                "relaxed_client_policy": attempt["relaxed_client_policy"],
                "output_excerpt": attempt["output"][-900:],
                "observed_through": source,
                "python_error": python_attempt["error"],
                "python_negotiated": python_attempt["negotiated"],
            }
        for protocol in edge.UNOFFERABLE_PROTOCOLS:
            # OpenSSL 3 has no -ssl3 flag: the attempt would exit with a usage error
            # and never open a socket, which is not evidence about the listener.
            attempts[protocol] = edge.parse_s_client("")
            attempts[protocol]["client_cannot_attempt"] = True
            attempts[protocol]["refusal_attributable_to_server"] = None
            attempts[protocol]["refusal_reason"] = edge.UNOFFERABLE_REASON
            excerpts[protocol] = {"attempted": False, "reason": edge.UNOFFERABLE_REASON}

        verdict = edge.protocol_policy_verdict(attempts,
                                               unofferable=edge.UNOFFERABLE_PROTOCOLS)
        result["verdicts"]["tls_protocol_policy"] = verdict
        result["verdicts"]["tls_protocol_attempts"] = excerpts
        if verdict["verdict"] != "POLICY ENFORCED":
            raise AssertionError("TLS protocol policy not enforced: " + json.dumps(
                {"reason": verdict["reason"],
                 "outcomes": {k: v["outcome"] for k, v in verdict["per_protocol"].items()},
                 "excerpts": {k: v.get("output_excerpt", "")[-400:] for k, v in excerpts.items()}}))
        return {"policy": verdict["verdict"], "reason": verdict["reason"],
                "outcomes": {k: v["outcome"] for k, v in verdict["per_protocol"].items()},
                "observed_refusals": verdict["observed_refusals"],
                "not_offerable_by_any_client": verdict["not_offerable_by_any_client"],
                "ciphers": {k: v.get("cipher") for k, v in attempts.items()},
                "relaxed_client_policy_used_for": sorted(
                    k for k, v in attempts.items() if v.get("relaxed_client_policy")),
                "note": ("The client policy was relaxed only to offer the refused protocols; "
                         "the listener's own policy is unchanged and is what rejected them.")}

    check("tls-protocol-policy-enforced-at-the-listener", _protocol_matrix)

    def _trust_matrix():
        with_ca = edge.parse_s_client(s_client(https_port, cafile=ca,
                                               verify_hostname=SITE)["output"])
        without = edge.parse_s_client(s_client(https_port, cafile=unrelated,
                                               verify_hostname=SITE)["output"])
        wrong_name = edge.parse_s_client(s_client(https_port, cafile=ca,
                                                  verify_hostname=WRONG_HOST)["output"])
        verdict = edge.trust_verdict(with_ca, without, wrong_name)
        result["verdicts"]["certificate_verification"] = verdict
        if verdict["verdict"] != "VERIFICATION ENFORCED":
            raise AssertionError("Certificate verification not enforced: " + json.dumps(verdict))
        chain = subprocess.run(edge.verify_chain_command(certs), capture_output=True,
                               text=True, timeout=60, check=False)
        if chain.returncode != 0:
            raise AssertionError("openssl verify rejected the issued certificate: "
                                 + (chain.stdout + chain.stderr)[:300])
        verdict["chain_verifies_independent_of_the_handshake"] = True
        return {"verdict": verdict["verdict"],
                "verify_return_code_with_ca": verdict["verify_return_code_with_ca"],
                "verify_return_code_with_unrelated_ca": verdict["verify_return_code_without_ca"],
                "verify_return_code_on_hostname_mismatch":
                    verdict["wrong_name_verify_return_code"],
                "chain_verifies_independent_of_the_handshake": True,
                "trust_anchor_note": verdict["trust_anchor_note"]}

    check("certificate-verification-enforced", _trust_matrix)

    def _redirect():
        response = requests.get(http_origin + "/api/method/ping", allow_redirects=False,
                                timeout=20)
        location = response.headers.get("Location", "")
        if response.status_code != 301:
            raise AssertionError("Plaintext listener returned " + str(response.status_code)
                                 + " instead of a 301 redirect")
        if not location.startswith("https://" + SITE):
            raise AssertionError("Plaintext redirect does not target this edge over TLS: "
                                 + location)
        return {"plaintext_status": 301, "location": location,
                "redirects_to_tls": True,
                "body_bytes": len(response.content),
                "note": ("The plaintext listener answers with a redirect only. It holds no "
                         "proxy_pass and no try_files, so there is no second route to the "
                         "application that bypasses TLS.")}

    check("plaintext-listener-redirects-to-https", _redirect)

    def _headers():
        response = requests.get(https_origin + "/api/method/ping", verify=str(ca), timeout=20)
        hsts = edge.parse_hsts(response.headers.get("Strict-Transport-Security"))
        if not hsts["well_formed"]:
            raise AssertionError("No well-formed HSTS header: "
                                 + str(response.headers.get("Strict-Transport-Security")))
        if hsts["max_age"] != edge.HSTS_MAX_AGE:
            raise AssertionError("HSTS max-age is " + str(hsts["max_age"]) + ", not the pinned "
                                 "template's " + str(edge.HSTS_MAX_AGE))
        if not hsts["include_subdomains"] or not hsts["preload"]:
            raise AssertionError("HSTS is missing includeSubDomains or preload: " + hsts["raw"])
        security = {name: response.headers.get(name) for name in
                    ("X-Frame-Options", "X-Content-Type-Options", "X-XSS-Protection",
                     "Referrer-Policy")}
        missing = sorted(name for name, value in security.items() if not value)
        return {"hsts": hsts, "hsts_matches_pinned_template": True,
                "security_headers": security,
                "security_headers_missing": missing,
                "server_header": response.headers.get("Server")}

    check("hsts-and-security-headers-sent-over-tls", _headers)

    session = requests.Session()

    def _login():
        response = session.post(https_origin + "/api/method/login", verify=str(ca),
                                data={"usr": "Administrator", "pwd": admin}, timeout=60)
        if response.status_code != 200:
            raise AssertionError("Login over TLS returned " + str(response.status_code)
                                 + ": " + response.text[:200])
        user = session.get(https_origin + "/api/method/frappe.auth.get_logged_user",
                           verify=str(ca), timeout=60).json()
        if user.get("message") != "Administrator":
            raise AssertionError("Session is not authenticated as Administrator")
        raw_cookies = response.raw.headers.getlist("Set-Cookie") if hasattr(
            response.raw.headers, "getlist") else [response.headers.get("Set-Cookie", "")]
        sid_headers = [value for value in raw_cookies if value.startswith("sid=")]
        if not sid_headers:
            raise AssertionError("No sid cookie was set by the login response")
        sid_header = sid_headers[0]
        secure_flag = "secure" in [part.strip().lower() for part in sid_header.split(";")[1:]]
        cookie = next((c for c in session.cookies if c.name == "sid"), None)
        if not secure_flag:
            raise AssertionError("The session cookie was set over TLS without the Secure flag: "
                                 + sid_header[:160])
        return {"login_http_status": 200, "logged_in_as": user["message"],
                "sid_cookie_secure_flag": secure_flag,
                "sid_cookie_secure_attribute_parsed": bool(cookie and cookie.secure),
                "sid_cookie_httponly": "httponly" in sid_header.lower(),
                "set_cookie_flags": [part.strip() for part in sid_header.split(";")[1:]],
                "scheme_propagation": ("Gunicorn's default secure_scheme_headers maps "
                                       "X-FORWARDED-Proto=https and its default "
                                       "forwarded_allow_ips is 127.0.0.1,::1, so the proxy "
                                       "header the pinned template sends is what makes "
                                       "frappe.auth mark the cookie Secure.")}

    check("authenticated-session-over-tls-with-secure-cookie", _login)

    private_url = manifest["files"][PRIVATE_FILE]["file_url"]
    public_url = manifest["files"][PUBLIC_FILE]["file_url"]

    def _private_denied_anonymously():
        anonymous = requests.Session()
        response = anonymous.get(https_origin + private_url, verify=str(ca), timeout=60,
                                 allow_redirects=False)
        if response.status_code == 200:
            raise AssertionError("A private file was served over TLS without authentication")
        return {"private_url": private_url, "anonymous_status": response.status_code,
                "denied_without_a_session": True, "bytes_returned": len(response.content)}

    check("private-file-denied-anonymously-over-tls", _private_denied_anonymously)

    def _public_served_anonymously():
        anonymous = requests.Session()
        response = anonymous.get(https_origin + public_url, verify=str(ca), timeout=60)
        if response.status_code != 200:
            raise AssertionError("The public file was not served anonymously over TLS; status="
                                 + str(response.status_code))
        digest = hashlib.sha256(response.content).hexdigest()
        expected = manifest["files"][PUBLIC_FILE]["content_sha256"]
        if digest != expected:
            raise AssertionError("Anonymously served public content differs from the manifest")
        return {"public_url": public_url, "anonymous_status": 200,
                "served_sha256": digest, "matches_manifest": True,
                "served_by": "nginx-static-public-directory"}

    check("public-file-served-anonymously-over-tls", _public_served_anonymously)

    def _private_served_to_session():
        """The X-Accel-Redirect path, over TLS.

        A private file is never readable from the public directory; frappe responds
        with an X-Accel-Redirect to /protected/<site-relative path> and nginx serves
        it from an ``internal`` location. Without that location the request 500s,
        which is exactly what independent recovery hit before it was fixed.
        """
        response = session.get(https_origin + private_url, verify=str(ca), timeout=60)
        if response.status_code != 200:
            raise AssertionError("A private file was not served to an authenticated session "
                                 "over TLS; status=" + str(response.status_code))
        digest = hashlib.sha256(response.content).hexdigest()
        expected = manifest["files"][PRIVATE_FILE]["content_sha256"]
        if digest != expected:
            raise AssertionError("Privately served content differs from the manifest")
        return {"private_url": private_url, "authenticated_status": 200,
                "served_sha256": digest, "matches_manifest": True,
                "served_via": "X-Accel-Redirect to an nginx internal location",
                "content_type": response.headers.get("Content-Type")}

    check("private-file-served-to-authenticated-session-over-tls", _private_served_to_session)

    def _plaintext_never_serves_bytes():
        """The boundary must not have a plaintext side door."""
        observations = {}
        for label, url in (("ping", "/api/method/ping"), ("private_file", private_url),
                           ("public_file", public_url)):
            response = requests.get(http_origin + url, allow_redirects=False, timeout=20)
            if response.status_code == 200:
                raise AssertionError("The plaintext listener served application bytes for "
                                     + label + " instead of redirecting")
            observations[label] = {"status": response.status_code,
                                   "location": response.headers.get("Location"),
                                   "body_bytes": len(response.content)}
        return {"all_plaintext_requests_redirected": True, "observations": observations,
                "note": ("No application response - not even the public file that nginx would "
                         "otherwise serve statically - is available over plaintext.")}

    check("plaintext-listener-never-serves-application-bytes", _plaintext_never_serves_bytes)

    result["status"] = "pass"
    write()
    print("TLS edge verified by two independent clients; privacy boundary holds over TLS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
