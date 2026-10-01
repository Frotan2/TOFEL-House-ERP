#!/usr/bin/env python3
"""In-image performance baseline (finding 9: measured, not policy).

Records request latencies for the product's primary surfaces against the
live site, from inside the web container. The owner has set no performance
target, so these numbers are a baseline record, not a pass/fail gate: this
script has no thresholds and never fails on slowness (it only fails when it
cannot reach the site at all).

Surfaces (SAMPLES repetitions each; min/median/max in ms):
  * site-root           GET / - the unauthenticated site response
  * login               POST /api/method/login - the authentication round
                        trip (Administrator, from the first-run credentials)
  * authenticated-read  frappe.client.get_count on Student - an
                        authenticated request with a small database read
  * reception-desk      the reception desk work endpoint - the owner's
                        primary desk surface; measured only when
                        PERF_DESK_USER / PERF_DESK_PASSWORD name a staff
                        account holding a desk role

Run inside the web container:  python3 /product/perf_baseline.py
"""
from __future__ import annotations

import json
import os
import statistics
import re
import time
import urllib.error
import urllib.parse
import urllib.request

SITE = "toeflhouse.localhost"
CREDENTIALS = f"/home/frappe/bench/sites/{SITE}/private/first-run-credentials.txt"
SAMPLES = 5
BASE = "http://127.0.0.1:8000"
DESK_ENDPOINT = "toefl_house.desk.reception.work"


def timed_call(path: str, *, data=None, session=None, csrf=None):
    """One timed request. Returns (ms, response_text, new_sid_or_None).

    Non-2xx responses are captured, not raised: the baseline records a
    non-ok surface with the server's body instead of dying mid-run (an
    unexpected refusal is a measurement result, and the per-surface 'ok'
    flag is what reports it).
    """
    url = BASE + path
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    headers = {}
    if session:
        headers["Cookie"] = "sid=" + session
    if csrf:
        headers["X-Frappe-CSRF-Token"] = csrf
    request = urllib.request.Request(url, data=body, headers=headers)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            text = response.read().decode()
            cookies = response.headers.get_all("Set-Cookie") or []
    except urllib.error.HTTPError as error:
        text = error.read().decode()
        cookies = []
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    # The Set-Cookie header is "sid=<value>; attrs..."; the cookie VALUE is
    # what a Cookie header must carry ("sid=<value>"). Keeping the "sid="
    # prefix doubled it to "sid=sid=<value>", which resolves to no session
    # (guest fallback) and would time the wrong (denied) path.
    sid = next((c.split(";", 1)[0].split("=", 1)[1] for c in cookies if c.startswith("sid=")), None)
    return elapsed_ms, text, sid


def fetch_csrf_token(session: str) -> str:
    """One-time, unmeasured desk load for the session CSRF token.

    Frappe mints a per-session CSRF token at session creation; the desk
    page carries it in its HTML, and unsafe (POST) requests on a session
    that carries a token must send it back. A browser does exactly this
    dance before its first form post - so does this baseline, otherwise
    the authenticated read would time the CSRF wall instead of the read.
    """
    request = urllib.request.Request(BASE + "/desk", headers={"Cookie": "sid=" + session})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            html = response.read().decode()
    except urllib.error.HTTPError:
        return ""
    m = re.search(r'frappe\.csrf_token = "([^"]+)"', html)
    return m.group(1) if m else ""


def surface(name: str, call) -> dict:
    samples = []
    last_text = ""
    for _ in range(SAMPLES):
        elapsed_ms, text, _ = call()
        samples.append(elapsed_ms)
        last_text = text
    entry = {
        "min_ms": round(min(samples), 1),
        "median_ms": round(statistics.median(samples), 1),
        "max_ms": round(max(samples), 1),
        "samples": len(samples),
    }
    try:
        payload = json.loads(last_text)
        entry["ok"] = isinstance(payload, dict) and "exc_info" not in payload
        if not entry["ok"]:
            entry["error"] = str(payload)[:200]
    except ValueError:
        entry["ok"] = "exc_info" not in last_text
    return entry


def main() -> int:
    admin_pw = next(
        line.split("Password:", 1)[1].strip()
        for line in open(CREDENTIALS)
        if "Password:" in line
    )

    surfaces: dict = {}
    admin_sid = None

    surfaces["site-root"] = surface("site-root", lambda: timed_call("/"))

    def login_call():
        result = timed_call("/api/method/login", data={"usr": "Administrator", "pwd": admin_pw})
        nonlocal admin_sid
        if result[2]:
            admin_sid = result[2]
        return result

    surfaces["login"] = surface("login", login_call)
    if admin_sid is None:
        raise SystemExit("login did not return a session")

    # The authenticated read is a POST, so it must carry the session CSRF
    # token a browser would (see fetch_csrf_token).
    admin_csrf = fetch_csrf_token(admin_sid)

    surfaces["authenticated-read"] = surface(
        "authenticated-read",
        lambda: timed_call(
            "/api/method/frappe.client.get_count",
            data={"doctype": "Student"}, session=admin_sid, csrf=admin_csrf,
        ),
    )

    desk_user = os.environ.get("PERF_DESK_USER", "")
    desk_pw = os.environ.get("PERF_DESK_PASSWORD", "")
    if desk_user and desk_pw:
        desk_sid = None

        def desk_login_call():
            nonlocal desk_sid
            result = timed_call("/api/method/login", data={"usr": desk_user, "pwd": desk_pw})
            if result[2]:
                desk_sid = result[2]
            return result

        surfaces["desk-login"] = surface("desk-login", desk_login_call)
        if desk_sid is not None:
            surfaces["reception-desk"] = surface(
                "reception-desk",
                lambda: timed_call("/api/method/" + DESK_ENDPOINT, session=desk_sid),
            )
        else:
            surfaces["reception-desk"] = {"ok": False, "error": "desk login failed"}
    else:
        surfaces["reception-desk"] = {"skipped": "no PERF_DESK_USER/PERF_DESK_PASSWORD provided"}

    report = {
        "site": SITE,
        "samples_per_surface": SAMPLES,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "surfaces": surfaces,
        "note": "measured, not policy: no owner performance target exists (ACCEPTANCE.md finding 9)",
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
