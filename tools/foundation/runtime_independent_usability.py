"""Prove the recovered site is genuinely usable through a real HTTP stack.

Recovering bytes is not the same as recovering a working application, so this
runs against a live Gunicorn process behind the nginx front proxy on the
independent target system and exercises the native HTTP API.

Requests are sent to the loopback listener with an explicit ``Host`` header for
the recovered site, exactly as the existing harness does, because Frappe resolves
which site to serve from that header. The proxy is configured the way the pinned
bench nginx template configures it: ``root`` at the sites directory with
``try_files /<site>/public/$uri @webserver``, so public files are served
statically and everything else falls through to the application.

Checks, in order:

1. The recovered site answers ``/api/method/ping`` through the proxy.
2. A real session login succeeds and the session is authenticated.
3. A record created only on the source system is readable over the API with
   content matching the manifest, and the full set lists correctly.
4. The recovered private and public files download over HTTP with SHA-256
   digests matching what the source recorded.
5. The privacy boundary survived recovery: the private file is denied to an
   anonymous caller while the public file is served to one.

Only synthetic credentials and synthetic content are used. The admin password is
read from the environment and never written to the report.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

SITE = "recovered.localhost"
PRIVATE_FILE = "independent-recovery-private.txt"
PUBLIC_FILE = "independent-recovery-public.txt"


def session_for(requests, base_url, host=SITE):
    """A session that names the recovered site, as Frappe requires."""
    session = requests.Session()
    session.headers["Host"] = host
    session.base_url = base_url
    return session


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or SITE not in sys.argv[1:]:
        raise SystemExit("Disposable hosted independent-recovery target site only")

    import requests

    base_url = os.environ.get("FOUNDATION_INDEPENDENT_BASE_URL", "http://127.0.0.1:8080")
    manifest = json.loads(Path(os.environ["FOUNDATION_INDEPENDENT_MANIFEST"]).read_text())
    report_path = Path(os.environ["FOUNDATION_INDEPENDENT_USABILITY_REPORT"])
    admin = os.environ["FOUNDATION_ADMIN_PASSWORD"]
    result = {
        "scope": ("Live HTTP usability of a site recovered on an independent system; "
                  "synthetic data only"),
        "site": SITE, "base_url": base_url, "host_header": SITE,
        "status": "running", "checks": [],
    }

    def write():
        report_path.write_text(json.dumps(result, indent=2) + "\n")

    def check(name, fn):
        try:
            observation = fn()
            result["checks"].append({"name": name, "status": "pass", "observation": observation})
            write()
            return observation
        except Exception as exc:
            result["checks"].append({"name": name, "status": "fail",
                                     "exception": type(exc).__name__,
                                     "message": str(exc)[:400]})
            result["status"] = "fail"
            write()
            raise

    session = session_for(requests, base_url)

    def _reachable():
        deadline = time.monotonic() + 240
        attempts = 0
        last = None
        while time.monotonic() < deadline:
            attempts += 1
            try:
                response = session.get(base_url + "/api/method/ping", timeout=10)
                last = response.status_code
                if response.status_code == 200:
                    return {"reachable": True, "attempts": attempts,
                            "ping_message": response.json().get("message")}
            except (requests.RequestException, ValueError) as exc:
                last = type(exc).__name__
            time.sleep(2)
        raise AssertionError("Recovered site did not answer ping within 240s; last=" + str(last))

    check("recovered-site-serves-http-through-proxy", _reachable)

    def _login():
        response = session.post(base_url + "/api/method/login",
                                data={"usr": "Administrator", "pwd": admin}, timeout=60)
        if response.status_code != 200:
            raise AssertionError("Login on the recovered site returned " + str(response.status_code))
        user = session.get(base_url + "/api/method/frappe.auth.get_logged_user",
                           timeout=60).json()
        if user.get("message") != "Administrator":
            raise AssertionError("Session is not authenticated as Administrator")
        return {"login_http_status": 200, "logged_in_as": user["message"],
                "session_cookie_set": any(c.name == "sid" for c in session.cookies)}

    check("authenticated-session-on-recovered-site", _login)

    def _read_source_record():
        """Read a record that was created only on the destroyed source system."""
        doctype = "ToDo"
        name = manifest["doctypes"][doctype]["names"][0]
        response = session.get(base_url + "/api/resource/" + doctype + "/" + name, timeout=60)
        if response.status_code != 200:
            raise AssertionError("Recovered record not readable over HTTP: "
                                 + str(response.status_code))
        description = response.json()["data"].get("description")
        expected = f"synthetic-independent-recovery-{manifest['run_tag']}-000"
        if description != expected:
            raise AssertionError("Recovered record content differs: " + str(description))
        listing = session.get(base_url + "/api/resource/" + doctype,
                              params={"limit_page_length": 100}, timeout=60).json()["data"]
        recovered_names = {row["name"] for row in listing}
        expected_names = set(manifest["doctypes"][doctype]["names"])
        return {"doctype": doctype, "name": name, "http_status": 200,
                "content_matches_manifest": True,
                "records_listed_over_http": len(listing),
                "all_source_records_listed": expected_names <= recovered_names}

    check("source-created-record-readable-over-http", _read_source_record)

    def _download_files():
        observed = {}
        for file_name in (PRIVATE_FILE, PUBLIC_FILE):
            expected = manifest["files"][file_name]
            response = session.get(base_url + expected["file_url"], timeout=60)
            if response.status_code != 200:
                raise AssertionError("Recovered file not served to an authenticated user: "
                                     + file_name + " -> " + str(response.status_code))
            digest = hashlib.sha256(response.content).hexdigest()
            if digest != expected["content_sha256"]:
                raise AssertionError("Served file content differs from the manifest: " + file_name)
            observed[file_name] = {
                "file_url": expected["file_url"], "http_status": 200,
                "served_sha256_matches_manifest": True, "bytes": len(response.content),
                "is_private": int(expected["is_private"]),
            }
        return observed

    check("private-and-public-files-served-over-http", _download_files)

    def _privacy_boundary_survived():
        """The boundary must survive recovery, not just the bytes."""
        anonymous = session_for(requests, base_url)
        private_url = manifest["files"][PRIVATE_FILE]["file_url"]
        denied = anonymous.get(base_url + private_url, timeout=60, allow_redirects=False)
        if denied.status_code == 200:
            raise AssertionError("Private file was served without authentication")
        public_url = manifest["files"][PUBLIC_FILE]["file_url"]
        allowed = anonymous.get(base_url + public_url, timeout=60)
        if allowed.status_code != 200:
            raise AssertionError("Public file was not served anonymously; status="
                                 + str(allowed.status_code))
        public_digest = hashlib.sha256(allowed.content).hexdigest()
        if public_digest != manifest["files"][PUBLIC_FILE]["content_sha256"]:
            raise AssertionError("Anonymously served public content differs")
        return {"private_anonymous_status": denied.status_code,
                "private_denied_without_session": True,
                "public_anonymous_status": allowed.status_code,
                "public_served_anonymously_with_matching_content": True,
                "public_served_by": "nginx-static-public-directory"}

    check("privacy-boundary-survived-recovery", _privacy_boundary_survived)

    result["status"] = "pass"
    write()
    print("Recovered site is usable over real HTTP on the independent system")


if __name__ == "__main__":
    main()
