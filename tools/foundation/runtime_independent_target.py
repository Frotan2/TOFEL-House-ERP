"""Target half of independent-system recovery: recover on a different machine.

Runs in a *separate* GitHub Actions job, which means a separate ephemeral virtual
machine with its own filesystem, its own containers and its own volumes. Nothing
is shared with the source job except the uploaded backup artifact. Independence is
verified rather than assumed: the source job records its host identity, and this
probe fails closed if the hostname or the kernel boot id match, because that would
mean both halves ran on the same live system.

The source site was destroyed by ``bench drop-site`` before this job started, so
what is recovered here is the only remaining copy of that state.

This probe builds its own pinned Bench from scratch at the same source revisions
the source system used, restores the database plus the public and private file
archives through the native ``bench restore``, and then proves recovery in four
separate dimensions:

1. Payload integrity - the transferred archives match the digests the source
   recorded, so nothing was corrupted or substituted in transit.
2. Database recovery - records created only on the source system are present with
   matching names and content.
3. File recovery - the private and public files are on disk with matching SHA-256
   digests, and their File documents and privacy flags survived.
4. Application usability - a live Gunicorn process behind an nginx front proxy
   configured as the pinned bench template configures it: session login, an API
   read of a source-created record, authenticated downloads of both files, an
   anonymous public download, and the private file still denied to anonymous
   callers.

No site config and no key material travels with the payload, so the target site
runs under its own freshly generated encryption key. What that costs is recorded
explicitly rather than hidden, because it is the concrete evidence that external
key custody is a separate required capability.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from bench_bootstrap import (  # noqa: E402
    MARIADB_CONTAINER, REDIS_CACHE_CONTAINER, REDIS_QUEUE_CONTAINER,
    Probe, build_bench, cleanup, clone_pinned_sources, install_mariadb_client,
    load_components, machine_identity, new_site, require_hosted_runner,
    sha256_file, start_services, wait_mariadb_healthy,
)

SITE = "recovered.localhost"
PAYLOAD = ROOT / ".foundation/independent-recovery/payload"
BACKEND_PORT = "127.0.0.1:8000"
PROXY_PORT = "127.0.0.1:8080"
#: Payload files expected from the source system.
EXPECTED_PAYLOAD = ("database.sql.gz", "manifest.json", "private-files.tar",
                    "public-files.tar", "source-identity.json")


def independence_verdict(source_host, target_host):
    """Compare the two halves' recorded host identities.

    Two separate GitHub Actions jobs get two separate ephemeral VMs, so the
    hostname and the per-boot kernel identifier must both differ. If either
    matches, the "independent" recovery is not independent and the probe must
    fail rather than report a weaker result as a stronger one.
    """
    differing = {
        "hostname": source_host.get("hostname") != target_host.get("hostname"),
        "kernel_boot_id": source_host.get("kernel_boot_id") != target_host.get("kernel_boot_id"),
        "runner_name": source_host.get("runner_name") != target_host.get("runner_name"),
        "job": source_host.get("job") != target_host.get("job"),
    }
    verdict = {
        "source_hostname": source_host.get("hostname"),
        "target_hostname": target_host.get("hostname"),
        "source_job": source_host.get("job"),
        "target_job": target_host.get("job"),
        "source_run_id": source_host.get("run_id"),
        "target_run_id": target_host.get("run_id"),
        "hostname_differs": differing["hostname"],
        "kernel_boot_id_differs": differing["kernel_boot_id"],
        "runner_name_differs": differing["runner_name"],
        "job_differs": differing["job"],
        "shared_filesystem": False,
        "shared_containers": False,
        "shared_volumes": False,
        "shared_backup_channel": "github-actions-artifact-only",
    }
    verdict["independent"] = bool(verdict["hostname_differs"]
                                  and verdict["kernel_boot_id_differs"])
    return verdict


def payload_digests(names=EXPECTED_PAYLOAD):
    """Digest every expected payload file, failing if one is absent."""
    observed = {}
    for name in names:
        path = PAYLOAD / name
        if not path.is_file():
            raise RuntimeError("Backup payload is missing " + name)
        observed[name] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    extra = sorted(p.name for p in PAYLOAD.iterdir() if p.name not in set(names))
    if extra:
        raise RuntimeError("Unexpected files arrived with the payload: " + str(extra))
    return observed


def nginx_conf(lab, bench_dir):
    """Front-proxy config following the pinned bench nginx template.

    ``root`` at the sites directory with ``try_files /<site>/public/$uri
    @webserver`` is how bench serves public files statically while routing
    everything else - including ``/private/files/``, which Frappe gates on
    permissions - to the application. The site is resolved from a whitelist of
    the Host header rather than trusting client-supplied routing.
    """
    return f"""pid {lab}/nginx.pid;
error_log {lab}/nginx-error.log;
events {{ worker_connections 128; }}
http {{
 include /etc/nginx/mime.types;
 access_log off;
 client_body_temp_path {lab}/nginx-body;
 proxy_temp_path {lab}/nginx-proxy;
 map $host $foundation_site {{ default ''; {SITE} {SITE}; }}
 server {{
  listen {PROXY_PORT};
  root {bench_dir}/sites;
  if ($foundation_site = '') {{ return 444; }}
  location /assets/ {{ alias {bench_dir}/sites/assets/; }}
  location ~* ^/files/.*.(htm|html|svg|xml) {{
   add_header Content-disposition "attachment";
   try_files /{SITE}/public/$uri @webserver;
  }}
  location / {{
   try_files /{SITE}/public/$uri @webserver;
  }}
  location @webserver {{
   proxy_http_version 1.1;
   proxy_set_header X-Frappe-Site-Name $foundation_site;
   proxy_set_header Host $http_host;
   proxy_set_header X-Use-X-Accel-Redirect True;
   proxy_read_timeout 120;
   proxy_redirect off;
   proxy_pass http://{BACKEND_PORT};
  }}
 }}
}}
"""


def main() -> int:
    require_hosted_runner()
    components = load_components()
    lab = Path(os.environ["RUNNER_TEMP"]) / "foundation-independent-target"
    lab.mkdir(mode=0o700)
    evidence = ROOT / ".foundation/independent-target-evidence"

    passwords = [secrets.token_urlsafe(32) for _ in range(3)]
    root_password, db_password, admin_password = passwords

    report = {
        "artifact_name": "target-result.json",
        "scope": ("Recovery of a destroyed source site onto a genuinely independent execution "
                  "environment; synthetic data only"),
        "role": "target",
        "site": SITE,
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "commit": os.environ.get("GITHUB_SHA"),
        "ref": os.environ.get("GITHUB_REF"),
        "status": "running",
        "checks": [],
        "mocks_or_simulations_used": False,
        "machine_identity": machine_identity(),
    }
    probe = Probe(report, evidence, lab)
    for value in passwords:
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
        identity = json.loads((PAYLOAD / "source-identity.json").read_text())
        report["independence"] = independence_verdict(identity["machine_identity"],
                                                      report["machine_identity"])
        if not report["independence"]["independent"]:
            raise RuntimeError(
                "Both halves ran on the same live system, so this is not an independent "
                "recovery: " + json.dumps(report["independence"]))

        # Integrity across the artifact transfer, against what the source recorded.
        transferred = payload_digests()
        for label in ("database.sql.gz", "private-files.tar", "public-files.tar"):
            if transferred[label]["sha256"] != identity["backup_sha256"][label]:
                raise RuntimeError("Transferred " + label + " does not match the source digest")
            if transferred[label]["bytes"] != identity["backup_bytes"][label]:
                raise RuntimeError("Transferred " + label + " size does not match the source")
            transferred[label]["matches_source_record"] = True
        report["payload_integrity"] = transferred
        report["source_site_was_destroyed_before_recovery"] = True

        start_services(probe, components, secret_file)
        report["mariadb_health"] = wait_mariadb_healthy(probe)
        install_mariadb_client(probe)
        report["target_revisions"] = clone_pinned_sources(
            probe, components, source_dir, ("frappe", "erpnext"))
        if report["target_revisions"] != identity["source_revisions"]:
            raise RuntimeError("Target rebuilt from different source revisions than the source: "
                               + json.dumps({"target": report["target_revisions"],
                                             "source": identity["source_revisions"]}))
        bench = build_bench(probe, components, lab, source_dir, bench_dir, python_bin)
        new_site(probe, bench, bench_dir, SITE, root_password, db_password, admin_password,
                 label="new-empty-site-on-independent-system")

        # cwd MUST be the bench directory, matching the backup. frappe's
        # extract_files untars with --strip 2 into sites/<this site>, so the
        # archive's sites/<source site>/... prefix is stripped and the files land
        # under the recovered site even though its name differs from the source's.
        probe.run("restore-database-and-files",
                  [str(bench), "--site", SITE, "restore", str(PAYLOAD / "database.sql.gz"),
                   "--db-root-password", root_password, "--admin-password", admin_password,
                   "--with-public-files", str(PAYLOAD / "public-files.tar"),
                   "--with-private-files", str(PAYLOAD / "private-files.tar")],
                  cwd=bench_dir, timeout=1800)
        probe.run("restore-migrate", [str(bench), "--site", SITE, "migrate"],
                  cwd=bench_dir, timeout=1800)
        report["restored_into_a_separate_database"] = True
        # ``bench restore`` accepts ``--encryption-key``, and it is deliberately
        # not used. Supplying it would require the source key to travel with the
        # artifact in plaintext, which the secret policy forbids. Recorded here so
        # the resulting limitation is a documented decision, not an oversight.
        report["encryption_key_not_supplied_to_restore"] = {
            "native_option_available": "--encryption-key",
            "used": False,
            "reason": ("Plaintext key material must not travel through an artifact, so the "
                       "recovered site runs under its own generated key and fields the source "
                       "encrypted stay intact but undecryptable here."),
        }

        apps = probe.run("list-apps-on-recovered-site",
                         [str(bench), "--site", SITE, "list-apps"], cwd=bench_dir, quiet=True)
        report["recovered_apps"] = [line.strip() for line in apps.splitlines() if line.strip()]
        # Assert against the raw output: list-apps formatting is not contractual,
        # but an installed app must appear in it.
        for app in identity["installed_apps"]:
            if app not in apps:
                raise RuntimeError("Application " + app + " did not survive the recovery; "
                                   "list-apps reported: " + apps)

        os.environ["FOUNDATION_INDEPENDENT_MANIFEST"] = str(PAYLOAD / "manifest.json")
        os.environ["FOUNDATION_INDEPENDENT_REPORT"] = str(evidence / "verify-result.json")
        probe.run("verify-database-and-file-recovery",
                  [str(bench_dir / "env/bin/python"),
                   str(ROOT / "tools/foundation/runtime_independent_data.py"),
                   "verify", SITE], cwd=bench_dir / "sites")
        verified = json.loads((evidence / "verify-result.json").read_text())
        if verified["status"] != "pass":
            raise RuntimeError("Recovered state did not match the source manifest")
        report["recovery_verification"] = verified["checks"]
        limitation = next(check["observation"] for check in verified["checks"]
                          if check["name"].startswith("source-encrypted-field"))
        report["encrypted_field_limitation"] = limitation

        # Live application usability through a production-shaped HTTP stack.
        launch("web-backend", [bench_dir / "env/bin/gunicorn", "--bind", BACKEND_PORT,
                               "--workers", "2", "frappe.app:application"], bench_dir / "sites")
        probe.run("nginx-install",
                  ["sudo", "apt-get", "install", "-y", "--no-install-recommends", "nginx"])
        proxy_conf = lab / "nginx.conf"
        probe.write(proxy_conf, nginx_conf(lab, bench_dir))
        probe.run("nginx-config-check", ["nginx", "-t", "-c", str(proxy_conf)])
        launch("public-proxy", ["nginx", "-c", str(proxy_conf), "-g", "daemon off;"], lab)

        os.environ["FOUNDATION_ADMIN_PASSWORD"] = admin_password
        os.environ["FOUNDATION_INDEPENDENT_BASE_URL"] = "http://" + PROXY_PORT
        os.environ["FOUNDATION_INDEPENDENT_USABILITY_REPORT"] = str(evidence / "usability-result.json")
        probe.run("prove-recovered-application-usable-over-http",
                  [str(bench_dir / "env/bin/python"),
                   str(ROOT / "tools/foundation/runtime_independent_usability.py"), SITE],
                  cwd=bench_dir / "sites", timeout=900)
        usability = json.loads((evidence / "usability-result.json").read_text())
        if usability["status"] != "pass":
            raise RuntimeError("Recovered application was not usable over HTTP")
        report["usability"] = usability["checks"]

        report["status"] = "pass"
        report["not_proven_by_this_probe"] = [
            "Recovery onto a different cloud provider, region or physical datacentre",
            "Restoring with the source encryption key, so decryption of source-encrypted "
            "fields needs separately controlled external key custody",
            "Recovery time and recovery point objectives, which need an owner-selected target",
            "Off-site or air-gapped backup storage, retention and rotation",
            "TLS termination and the Tailscale boundary, exercised separately",
            "Any production workload, since all data here is synthetic",
        ]
        print("Independent-system recovery verified: database, files, apps and live HTTP usability")
    except Exception as exc:
        report["status"] = "fail"
        report["failure"] = probe.redact(str(exc))[-4000:]
        print(report["failure"], file=sys.stderr)
    finally:
        for name, process, stream, log_path in reversed(processes):
            try:
                if process.poll() is None:
                    os.killpg(process.pid, 15)
                process.wait(timeout=20)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, 9)
                except OSError:
                    pass
            finally:
                stream.close()
                try:
                    probe.write(evidence / (name + "-log.txt"), probe.redact(log_path.read_text()))
                except OSError:
                    pass
        secret_file.unlink(missing_ok=True)
        (evidence / "target-result.json").write_text(
            probe.redact(json.dumps(report, indent=2)) + "\n")
        cleanup((MARIADB_CONTAINER, REDIS_QUEUE_CONTAINER, REDIS_CACHE_CONTAINER))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
