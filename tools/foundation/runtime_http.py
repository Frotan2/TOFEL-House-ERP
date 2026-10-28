"""HTTP login, restored-site access and negative student-isolation probes.

Only synthetic sites on the loopback-bound hosted runner. No live third-party
system, fuzzing, exploitation or write operations beyond ordinary test-user login.
"""
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.parse import quote


def main():
    import requests
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Requires isolated Actions runner")
    records = json.loads(Path(os.environ["FOUNDATION_BUSINESS_REPORT"]).read_text())["records"]
    output = Path(os.environ["FOUNDATION_HTTP_REPORT"])
    report = {"scope": "Real HTTP on synthetic loopback-only sites", "status": "running", "checks": [], "phase2_gate_passed": False}
    base = "http://127.0.0.1:8000"

    def check(name, function):
        started = time.monotonic()
        try:
            observation = function()
            report["checks"].append({"name": name, "status": "pass", "observation": observation, "seconds": round(time.monotonic() - started, 3)})
        except Exception as exc:
            # Never persist request headers, session cookies or response bodies.
            report["checks"].append({"name": name, "status": "fail", "exception": type(exc).__name__, "message": str(exc)[:500]})
        output.write_text(json.dumps(report, indent=2) + "\n")

    def login(site, user, password):
        session = requests.Session()
        session.headers["Host"] = site
        response = session.post(base + "/api/method/login", data={"usr": user, "pwd": password}, timeout=30)
        assert response.status_code == 200, f"Login HTTP {response.status_code}"
        response = session.get(base + "/api/method/frappe.auth.get_logged_user", timeout=30)
        assert response.status_code == 200 and response.json().get("message") == user, "Authenticated identity mismatch"
        return session

    for attempt in range(60):
        try:
            response = requests.get(base + "/login", headers={"Host": "foundation.localhost"}, timeout=3)
            if response.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(1)
    else:
        report["status"] = "fail"
        report["failure"] = "Backend login page did not become ready within startup window"
        output.write_text(json.dumps(report, indent=2) + "\n")
        return 1
    report["startup_readiness_polls"] = attempt + 1
    # SEC-DEPS-01: before nginx is installed, the Engine.IO listener binds to
    # FRAPPE_SOCKETIO_PORT (loopback 19000) rather than the legacy public 9000.
    # The post-nginx realtime-edge-exposure-probe exercises the public edge at
    # 9000; this pre-proxy check validates the direct node listener so that
    # the isolation test still pins websocket upgrade availability before the
    # proxy is configured.
    socketio_port = int(os.environ.get("FRAPPE_SOCKETIO_PORT", "9000"))
    def realtime_handshake():
        response = requests.get(f"http://127.0.0.1:{socketio_port}/socket.io/", params={"EIO": "4", "transport": "polling"},
                                headers={"Host": "foundation.localhost", "Origin": "http://foundation.localhost:8000"}, timeout=30)
        assert response.status_code == 200 and response.text.startswith("0{"), f"Engine.IO handshake HTTP {response.status_code}"
        packet = json.loads(response.text[1:])
        assert packet.get("sid") and "websocket" in packet.get("upgrades", [])
        return {"protocol": "Engine.IO 4", "handshake": True, "event_authorization_validated": False, "direct_port": socketio_port}
    check("realtime-transport-handshake", realtime_handshake)
    sessions = {}
    for site in ("foundation.localhost", "restore.localhost"):
        def admin_probe(site=site):
            session = login(site, "Administrator", os.environ["FOUNDATION_ADMIN_PASSWORD"])
            sessions[site] = session
            response = session.get(base + "/api/resource/Student/" + quote(records["students"][0], safe=""), timeout=30)
            assert response.status_code == 200 and response.json()["data"]["name"] == records["students"][0], "Restored/source Student HTTP read failed"
            return {"site": site, "authenticated_identity": "Administrator", "student_read": True}
        check(site + "-admin-login-and-student", admin_probe)

    students = {}
    for label in ("alpha", "beta"):
        def student_login(label=label):
            students[label] = login("foundation.localhost", f"validation-{label}@example.test", os.environ["FOUNDATION_TEST_PASSWORD"])
            return {"identity": f"validation-{label}@example.test"}
        check(label + "-student-login", student_login)
    if "alpha" in students and "beta" in students:
        own, other = records["students"]
        def own_read():
            response = students["alpha"].get(base + "/api/resource/Student/" + quote(own, safe=""), timeout=30)
            assert response.status_code == 200 and response.json()["data"]["name"] == own, f"Own Student read HTTP {response.status_code}"
            return {"http_status": response.status_code}
        check("student-own-record-allowed", own_read)

        def other_read():
            response = students["alpha"].get(base + "/api/resource/Student/" + quote(other, safe=""), timeout=30)
            disclosed = response.status_code == 200 and response.json().get("data", {}).get("name") == other
            report["other_student_record_disclosed"] = disclosed
            assert response.status_code in (403, 404), f"Other Student read expected denial, received HTTP {response.status_code}; target document returned={disclosed}"
            return {"http_status": response.status_code}
        check("student-other-record-denied", other_read)

        def portal_read():
            response = students["alpha"].get(base + "/api/method/education.education.api.get_student_context", params={"student": other}, timeout=30)
            assert response.status_code in (403, 404), f"Other Student portal RPC expected denial, received HTTP {response.status_code}"
            return {"http_status": response.status_code}
        check("student-other-portal-context-denied", portal_read)

        def file_read(label, allowed):
            response = students[label].get(base + records["private_file_url"], timeout=30)
            if allowed:
                assert response.status_code == 200 and hashlib.sha256(response.content).hexdigest() == records["private_file_sha256"], "Own private attachment read/hash failed"
            else:
                disclosed = response.status_code == 200 and hashlib.sha256(response.content).hexdigest() == records["private_file_sha256"]
                report["other_student_private_file_disclosed"] = disclosed
                assert response.status_code in (403, 404), f"Other Student private file expected denial, received HTTP {response.status_code}; expected bytes returned={disclosed}"
            return {"http_status": response.status_code}
        check("student-own-private-file-allowed", lambda: file_read("alpha", True))
        check("student-other-private-file-denied", lambda: file_read("beta", False))
    report["status"] = "pass" if all(c["status"] == "pass" for c in report["checks"]) else "fail"
    output.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
