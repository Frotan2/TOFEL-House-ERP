"""Prove the operational TLS edge: real certificates, real policy, real clients.

Recovery (run 35170062251) and key custody (run 35179445639) proved that a
destroyed site comes back on a separate machine and that its keys come back with
it. Both reached the application over plaintext HTTP on a loopback listener. A
real deployment is not reached that way, so this probe puts the intended boundary
in front of the same live stack and exercises it as a client would.

What is built here:

* a private CA and a leaf certificate for the site hostname, issued with OpenSSL
  inside the run, with the hostname in ``subjectAltName`` because modern clients
  match the SAN and ignore the CN;
* an unrelated CA and a certificate for a different hostname, which exist only to
  be refused;
* an nginx front proxy whose TLS policy is the pinned bench template's own -
  ``ssl_protocols TLSv1.2 TLSv1.3``, ``ssl_ciphers EECDH+AESGCM:EDH+AESGCM``,
  ``ssl_ecdh_curve secp384r1``, ``ssl_session_tickets off``, HSTS at
  ``max-age=63072000; includeSubDomains; preload`` and the four accompanying
  security headers - so the evidence is about the intended production shape rather
  than a policy invented to be easy to pass;
* Gunicorn started with the pinned supervisor template's production flags.

What is then observed rather than assumed:

* the listener answers over TLS and the certificate it presents is byte-identical
  to the one issued, digested from the DER the client actually received;
* verification is load-bearing in both directions - the handshake verifies against
  the private CA, fails against an unrelated one, and fails on a hostname mismatch
  (``openssl s_client`` needs ``-verify_hostname`` for that, since it validates the
  chain only by default);
* each allowed protocol negotiates and each refused protocol is rejected by the
  *listener*, distinguished from a refusal caused by the client's own OpenSSL
  policy, which would say nothing about the boundary;
* the plaintext listener answers with a redirect and never proxies, so there is no
  second route to the application and no way for a spoofed ``X-Forwarded-Proto``
  to reach it;
* the session cookie carries ``Secure`` over TLS. That flag comes from
  ``frappe.auth`` deriving it from ``request.scheme``, which under Gunicorn is set
  by Gunicorn's own ``secure_scheme_headers`` because the ``ProxyFix`` wrapper in
  app.py belongs to the werkzeug dev-server block and does not apply here;
* the file privacy boundary survives the move to TLS: a private file is refused
  anonymously and served to an authenticated session through ``X-Accel-Redirect``
  to nginx's ``internal`` location, while the public file is served statically.

The tailnet half of the intended boundary is recorded as ENVIRONMENT-BLOCKED rather
than simulated. Joining a tailnet needs an owner-provisioned auth key and an ACL
policy, and this session has neither (repository Actions secrets return HTTP 403 to
its credential). What is genuinely observable - which addresses the listeners are
bound to, decoded from ``/proc/net/tcp`` rather than from a tool's summary - is
reported, and nothing more.
"""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from bench_bootstrap import (  # noqa: E402
    MARIADB_CONTAINER, REDIS_CACHE_CONTAINER, REDIS_QUEUE_CONTAINER,
    Probe, build_bench, cleanup, clone_pinned_sources, load_components,
    machine_identity, new_site, require_hosted_runner, start_services,
    wait_mariadb_healthy,
)
import tls_edge as edge  # noqa: E402

SITE = edge.EDGE_HOST
BACKEND_PORT = "127.0.0.1:8000"
HTTP_PORT = "127.0.0.1:8080"
HTTPS_PORT = "127.0.0.1:8443"
EVIDENCE = ROOT / ".foundation/tls-edge-evidence"

#: Gunicorn started as the pinned bench supervisor template starts it in
#: production, rather than with a minimal development invocation.
GUNICORN_PRODUCTION_FLAGS = ["--max-requests", "500", "--max-requests-jitter", "50",
                             "-t", "120", "--graceful-timeout", "30", "--preload"]


def listening_sockets():
    """Decode listening sockets straight from the kernel.

    ``ss`` and ``netstat`` are packages that may or may not be present, and they
    summarise. ``/proc`` is always there and reports what the kernel bound.
    """
    rows = []
    for name in ("tcp", "tcp6"):
        path = Path("/proc/net") / name
        if path.exists():
            rows.extend(edge.decode_proc_net_listeners(path.read_text()))
    return rows


def summarize_refusals(verdicts):
    """Surface the negative controls, tolerating a result that stopped halfway.

    A client run that fails at the protocol matrix never produces a
    certificate-verification verdict, and the summary still has to be publishable -
    a partial explanation is better than none, as long as it says it is partial.
    """
    protocol_verdict = verdicts.get("tls_protocol_policy") or {}
    per_protocol = protocol_verdict.get("per_protocol", {})
    trust = verdicts.get("certificate_verification") or {}
    summary = {
        "protocols_rejected_by_the_listener": sorted(
            name for name, entry in per_protocol.items() if entry.get("outcome") == "REFUSED"),
        "protocols_rejected_by_the_client_and_therefore_not_evidence": sorted(
            name for name, entry in per_protocol.items() if entry.get("outcome") == "NOT OBSERVABLE"),
        "protocols_with_no_evidence_at_all": sorted(
            name for name, entry in per_protocol.items() if entry.get("outcome") == "NO EVIDENCE"),
        "unrelated_ca_rejected": trust.get("verify_return_code_without_ca"),
        "hostname_mismatch_rejected": trust.get("wrong_name_verify_return_code"),
        "complete": bool(per_protocol) and bool(trust),
        "note": ("Each refusal is observed, not assumed. A refusal caused by the client's own "
                 "OpenSSL policy is listed separately, because it says nothing about the "
                 "listener. complete=false means the client run stopped before every control "
                 "was exercised."),
    }
    reasons = {name: entry.get("reason") for name, entry in per_protocol.items()
               if entry.get("reason")}
    if reasons:
        summary["client_side_refusal_reasons"] = reasons
    return summary


def main() -> int:
    require_hosted_runner()
    components = load_components()
    lab = Path(os.environ["RUNNER_TEMP"]) / "foundation-tls-edge"
    lab.mkdir(mode=0o700, parents=True, exist_ok=True)
    certs = lab / "certs"
    certs.mkdir(mode=0o700)
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    root_password = secrets.token_urlsafe(32)
    db_password = secrets.token_urlsafe(32)
    admin_password = secrets.token_urlsafe(32)

    report = {
        "artifact_name": "tls-edge-result.json",
        "scope": ("Operational TLS edge in front of a live Frappe site: a private CA and issued "
                  "leaf certificate, the pinned bench template's TLS policy, and client-side "
                  "verification by two independent TLS implementations; synthetic data only"),
        "role": "tls-edge",
        "site": SITE,
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "commit": os.environ.get("GITHUB_SHA"),
        "ref": os.environ.get("GITHUB_REF"),
        "status": "running",
        "checks": [],
        "mocks_or_simulations_used": False,
        "machine_identity": machine_identity(),
        "target_revisions": {},
        "verdicts": {},
        "listeners": {"http": HTTP_PORT, "https": HTTPS_PORT, "backend": BACKEND_PORT},
        "ports_follow_the_pinned_template": {
            "template_ports": [80, 443],
            "ports_used": [HTTP_PORT, HTTPS_PORT],
            "deviation": ("Binding 80 and 443 needs root; this probe listens on unprivileged "
                          "ports and the plaintext redirect carries the TLS port explicitly. "
                          "The port number is not part of the security claim."),
        },
    }
    probe = Probe(report, EVIDENCE, lab)
    for value in (root_password, db_password, admin_password):
        probe.mask(value)

    secret_file = lab / "db-password"
    secret_file.write_text(root_password)
    secret_file.chmod(0o600)
    bench_dir = lab / "bench"
    source_dir = lab / "sources"
    source_dir.mkdir()
    python_bin = Path(os.environ["RUNNER_TEMP"]) / "foundation-runner-probe/python/bin/python3"
    if not python_bin.exists():
        python_bin = Path(sys.executable)
    processes = []

    def launch(name, command, cwd):
        stream = (lab / (name + ".txt")).open("w")
        process = subprocess.Popen([str(part) for part in command], cwd=str(cwd),
                                   stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append((name, process, stream, lab / (name + ".txt")))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and process.poll() is None:
            time.sleep(1)
        if process.poll() is not None:
            raise RuntimeError(name + " exited immediately with " + str(process.returncode))
        return process

    try:
        start_services(probe, components, secret_file)
        report["mariadb_health"] = wait_mariadb_healthy(probe)

        report["target_revisions"] = clone_pinned_sources(
            probe, components, source_dir, ("frappe", "erpnext"))
        bench = build_bench(probe, components, lab, source_dir, bench_dir, python_bin)
        new_site(probe, bench, bench_dir, SITE, root_password, db_password, admin_password,
                 label="new-site-on-tls-edge")

        apps = probe.run("list-apps-on-edge-site",
                         [str(bench), "--site", SITE, "list-apps"], cwd=bench_dir, quiet=True)
        report["installed_apps"] = [line.strip() for line in apps.splitlines() if line.strip()]

        # --- Certificate material, generated in this run and never published ---
        for index, command in enumerate(edge.ca_commands(certs)):
            probe.run(f"generate-private-ca-step-{index}", command, cwd=certs)
        commands, meta = edge.server_cert_commands(certs, host=SITE, name="server")
        for index, command in enumerate(commands):
            probe.run(f"issue-server-certificate-step-{index}", command, cwd=certs,
                      stdin_text=meta["extensions_stdin"] if index == len(commands) - 1 else None)
        wrong_commands, wrong_meta = edge.server_cert_commands(
            certs, host=edge.WRONG_HOST, name="wrong-name")
        for index, command in enumerate(wrong_commands):
            probe.run(f"issue-wrong-name-certificate-step-{index}", command, cwd=certs,
                      stdin_text=(wrong_meta["extensions_stdin"]
                                  if index == len(wrong_commands) - 1 else None))
        # An unrelated CA is the honest "no trust anchor" control: -CAfile /dev/null
        # makes OpenSSL fail while loading the store and never attempt a handshake.
        probe.run("generate-unrelated-ca-key",
                  ["openssl", "genpkey", "-algorithm", "rsa", "-pkeyopt", "rsa_keygen_bits:2048",
                   "-out", str(certs / "unrelated-ca.key")], cwd=certs)
        probe.run("generate-unrelated-ca-certificate",
                  ["openssl", "req", "-x509", "-new", "-key", str(certs / "unrelated-ca.key"),
                   "-sha256", "-days", "2", "-out", str(certs / "unrelated-ca.pem"),
                   "-subj", "/CN=Unrelated Foundation Test CA",
                   "-addext", "basicConstraints=critical,CA:TRUE"], cwd=certs)

        probe.run("chain-verifies-against-the-private-ca",
                  edge.verify_chain_command(certs), cwd=certs)
        report["certificate_fingerprints"] = {
            "server": probe.run("server-certificate-fingerprint",
                                edge.fingerprint_command(certs, "server"), cwd=certs, quiet=True),
            "wrong_name": probe.run("wrong-name-certificate-fingerprint",
                                    edge.fingerprint_command(certs, "wrong-name"),
                                    cwd=certs, quiet=True),
        }
        cert_text = probe.run("read-server-certificate",
                              ["openssl", "x509", "-in", str(certs / "server.pem"), "-text",
                               "-noout"], cwd=certs, quiet=True)
        parsed_cert = edge.parse_certificate_text(cert_text)
        report["issued_certificate"] = {
            "common_name": parsed_cert["common_name"],
            "subject_alt_names": parsed_cert["subject_alt_names"],
            "is_ca": parsed_cert["is_ca"],
            "signature_algorithm": parsed_cert["signature_algorithm"],
            "not_after": parsed_cert["not_after"],
            "hostname_is_in_the_san": (
                "DNS:" + SITE) in parsed_cert["subject_alt_names"],
        }
        if not report["issued_certificate"]["hostname_is_in_the_san"]:
            raise RuntimeError("The issued certificate does not carry the hostname in its SAN, "
                               "so a hostname-mismatch control would prove nothing: "
                               + json.dumps(parsed_cert["subject_alt_names"]))
        for path in certs.glob("*.key"):
            path.chmod(0o600)

        # --- A real name resolution entry, so clients do genuine SNI and hostname
        # verification instead of connecting to an address with a Host header.
        hosts_script = (f"grep -q ' {SITE}$' /etc/hosts || "
                        f"echo '127.0.0.1 {SITE}' >> /etc/hosts")
        probe.run("add-edge-hostname-resolution", ["sudo", "sh", "-c", hosts_script])
        resolved = probe.run("confirm-edge-hostname-resolves", ["getent", "hosts", SITE],
                             quiet=True)
        report["hostname_resolution"] = {"entry": f"127.0.0.1 {SITE}", "getent": resolved,
                                         "resolves_to_loopback": "127.0.0.1" in resolved}
        if "127.0.0.1" not in resolved:
            raise RuntimeError("The edge hostname did not resolve to the listener: " + resolved)

        # --- Synthetic files to serve, created server-side ---
        manifest = EVIDENCE / "state-manifest.json"
        probe.run("create-synthetic-file-pair",
                  [str(bench_dir / "env/bin/python"),
                   str(ROOT / "tools/foundation/runtime_tls_edge_state.py"), "create", SITE],
                  cwd=bench_dir / "sites", timeout=600,
                  env={"FOUNDATION_TLS_EDGE_MANIFEST": str(manifest)})
        state = json.loads(manifest.read_text())
        report["synthetic_files"] = {
            name: {"file_url": entry["file_url"], "is_private": entry["is_private"],
                   "bytes": entry["bytes"], "content_sha256": entry["content_sha256"],
                   "on_disk_sha256": entry["on_disk_sha256"]}
            for name, entry in state["files"].items()}

        # --- The live stack: production-shaped Gunicorn behind the TLS proxy ---
        launch("web-backend",
               [bench_dir / "env/bin/gunicorn", "-b", BACKEND_PORT, "-w", "2",
                *GUNICORN_PRODUCTION_FLAGS, "frappe.app:application"], bench_dir / "sites")
        probe.run("nginx-install",
                  ["sudo", "apt-get", "install", "-y", "--no-install-recommends", "nginx"])
        proxy_conf = lab / "nginx-tls.conf"
        probe.write(proxy_conf, edge.nginx_tls_conf(
            lab=lab, bench_dir=bench_dir, site=SITE, http_port=8080, https_port=8443,
            backend_port=BACKEND_PORT, certificate=str(certs / "server.pem"),
            key=str(certs / "server.key")))
        probe.run("nginx-config-check", ["nginx", "-t", "-c", str(proxy_conf)])
        launch("tls-proxy", ["nginx", "-c", str(proxy_conf), "-g", "daemon off;"], lab)

        # --- Binding evidence, from the kernel, before any client trusts a tool ---
        time.sleep(3)
        rows = listening_sockets()
        shape = edge.binding_shape(rows, [8080, 8443, 8000])
        report["listener_bindings"] = shape
        for port in ("8080", "8443", "8000"):
            if not shape[port]["listening"]:
                raise RuntimeError("Listener on port " + port + " never bound; kernel state: "
                                   + json.dumps(shape))
        observed_addresses = [f"{address}:{port}" for port, entry in shape.items()
                              for address in entry["addresses"]]
        report["verdicts"]["tailscale_boundary"] = edge.tailscale_boundary_verdict(
            observed_addresses,
            auth_key_available=bool(os.environ.get("FOUNDATION_TAILNET_AUTH_KEY")),
            tailscale_binary=shutil.which("tailscale"))
        if any(entry["bound_to_every_interface"] for entry in shape.values()):
            raise RuntimeError("A listener bound to every interface, which is not the intended "
                               "boundary: " + json.dumps(shape))

        # --- Client-side verification, by two independent TLS implementations ---
        # The inner result is ingested BEFORE the failure is re-raised. `probe.run`
        # raises on a non-zero exit, so reading the file afterwards means a failing
        # client run publishes none of its own evidence - which is exactly backwards,
        # because the failure case is the only one that needs explaining. Runs
        # 35197870620 and 35214660151 both failed here and both published a report
        # whose `verdicts` held only the Tailscale boundary, so the per-protocol
        # transcripts that would have said why stayed on the ephemeral runner.
        checks_result = EVIDENCE / "tls-checks-result.json"
        client_error = None
        try:
            probe.run("verify-tls-edge-as-a-real-client",
                      [str(bench_dir / "env/bin/python"),
                       str(ROOT / "tools/foundation/runtime_tls_edge_checks.py"), SITE],
                      cwd=bench_dir / "sites", timeout=1200,
                      env={"FOUNDATION_TLS_EDGE_CERTS": str(certs),
                           "FOUNDATION_TLS_EDGE_HTTP_PORT": "8080",
                           "FOUNDATION_TLS_EDGE_HTTPS_PORT": "8443",
                           "FOUNDATION_TLS_EDGE_MANIFEST": str(manifest),
                           "FOUNDATION_TLS_EDGE_CHECKS_RESULT": str(checks_result),
                           "FOUNDATION_ADMIN_PASSWORD": admin_password})
        except Exception as exc:  # noqa: BLE001 - re-raised after the evidence is kept
            client_error = exc
        verified = None
        if checks_result.exists():
            verified = json.loads(checks_result.read_text())
            report["client_checks"] = verified["checks"]
            for key in ("tls_protocol_policy", "certificate_verification"):
                if key in verified.get("verdicts", {}):
                    report["verdicts"][key] = verified["verdicts"][key]
            report["required_refusals_observed"] = summarize_refusals(report["verdicts"])
        else:
            report["client_checks_evidence"] = (
                "ABSENT: the client probe produced no result file, so no per-protocol "
                "evidence exists to publish.")
        if client_error is not None:
            raise client_error
        if verified["status"] != "pass":
            failed = [check["name"] for check in verified["checks"] if check["status"] == "fail"]
            raise RuntimeError("TLS edge checks did not pass: " + json.dumps(failed))
        for required in ("POLICY ENFORCED", "VERIFICATION ENFORCED"):
            if required not in json.dumps(report["verdicts"]):
                raise RuntimeError("Required verdict missing from the client result: " + required)

        # --- No key material may reach the published evidence ---
        needles = ["BEGIN PRIVATE KEY", "BEGIN RSA PRIVATE KEY", "BEGIN CERTIFICATE REQUEST",
                   root_password, db_password, admin_password]
        leaks = {}
        for path in sorted(EVIDENCE.glob("*.json")):
            body = path.read_text(errors="replace")
            found = [needle if needle.startswith("BEGIN") else "[credential]"
                     for needle in needles if needle in body]
            if found:
                leaks[path.name] = found
        report["published_evidence_scan"] = {"needles_scanned": len(needles), "leaks": leaks,
                                             "clean": not leaks}
        if leaks:
            raise RuntimeError("Published evidence contains private key material or a "
                               "credential: " + json.dumps(leaks))

        report["not_proven_by_this_probe"] = [
            "A publicly trusted certificate: the CA is private and generated inside this run. It "
            "proves the chain, the hostname binding and that verification is enforced in both "
            "directions; it does not qualify a public edge and no browser would trust it",
            "A tailnet: no auth key, no registered node, no ACL evaluation and no cross-node "
            "connection. Repository Actions secrets return HTTP 403 to this session's credential, "
            "so no owner-provisioned key material is reachable. Classified ENVIRONMENT-BLOCKED "
            "rather than simulated",
            "Certificate issuance and renewal against a real ACME authority: the pinned bench "
            "template ships a letsencrypt.cfg, but issuing needs a publicly resolvable domain and "
            "control of its DNS",
            "Revocation: no CRL distribution point, no OCSP responder and no OCSP stapling",
            "Mutual TLS: no client certificate was requested or verified",
            "Ports 80 and 443 as the pinned template uses them: binding them needs root, so "
            "unprivileged ports are used and the deviation is recorded above",
            "The rate limiting the pinned template can enable (limit_conn per_host): not enabled "
            "here, so no throttling behaviour is claimed",
            "A five-application ERPNext site: the site runs frappe alone. The TLS edge is proven "
            "for a Frappe site behind the pinned nginx template; erpnext is fetched into the "
            "bench by the shared builder but not installed on this site",
            "TLS termination under load, session resumption statistics, or cipher preference "
            "behaviour across many concurrent clients",
            "Any production workload: every certificate, credential, record and file here is "
            "synthetic and generated for this run",
        ]
        report["status"] = "pass"
        print("TLS edge enforced: issued certificate verified by two independent clients, "
              "protocol policy observed at the listener, plaintext refused, Secure cookie set, "
              "and the private-file boundary intact over TLS")
    except Exception as exc:
        report["status"] = "fail"
        report["failure"] = probe.redact(str(exc))[-4000:]
        print(report["failure"], file=sys.stderr)
    finally:
        for name, process, stream, log_path in processes:
            try:
                process.terminate()
                process.wait(timeout=20)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                except OSError:
                    pass
            stream.close()
            tail = log_path.read_text(errors="replace")[-2000:] if log_path.exists() else ""
            report.setdefault("process_logs", {})[name] = probe.redact(tail)
        secret_file.unlink(missing_ok=True)
        (EVIDENCE / "tls-edge-result.json").write_text(
            probe.redact(json.dumps(report, indent=2)) + "\n")
        cleanup((MARIADB_CONTAINER, REDIS_QUEUE_CONTAINER, REDIS_CACHE_CONTAINER))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
