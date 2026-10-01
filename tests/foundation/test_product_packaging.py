"""Contract for the one-click desktop product layer under product/.

The layer has one job: wrap the already-reviewed, matrix-pinned runtime into a
zero-CLI Windows launch experience. These tests fail closed whenever the
wrapper drifts from that job: pins must equal the foundation version matrix
(single source of truth), exposures must stay loopback-only, no literal secret
may appear in any shipped script, and the first-run bootstrap logic must stay
idempotent against the proven hosted app order. The image build / Windows run
itself is NOT EXECUTED in this engineering environment (no Docker daemon, no
Windows) and is labelled as such in the README; these tests are the in-sandbox
verified slice.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "product"
sys.path.insert(0, str(PRODUCT))

import bootstrap  # noqa: E402


def matrix_parts():
    matrix = json.loads((ROOT / "docs/engineering/foundation-version-matrix.json").read_text())
    return {c["name"]: c for c in matrix["components"]}


COMPOSE = PRODUCT / "docker-compose.yml"
DOCKERFILE = PRODUCT / "app.Dockerfile"
SCRIPTS = sorted((PRODUCT / "windows").glob("*.cmd"))


class PinParityContract(unittest.TestCase):
    def test_compose_service_images_match_matrix_digests(self):
        parts = matrix_parts()
        text = COMPOSE.read_text()
        self.assertIn(parts["mariadb"]["image_digest"], text)
        self.assertEqual(text.count(parts["redis"]["image_digest"]), 2)

    def test_dockerfile_arg_defaults_match_matrix(self):
        parts = matrix_parts()
        text = DOCKERFILE.read_text()

        def arg(name):
            match = re.search(rf"^ARG {name}=(\S+)$", text, flags=re.M)
            self.assertIsNotNone(match, f"missing ARG {name}")
            return match.group(1)

        self.assertEqual(arg("PYTHON_VERSION"), parts["python"]["selected_version"])
        self.assertEqual(arg("NODE_VERSION"), parts["node"]["selected_version"])
        self.assertEqual(arg("YARN_VERSION"), parts["yarn"]["selected_version"])
        self.assertEqual(arg("BENCH_VERSION"), parts["bench"]["selected_version"])
        self.assertEqual(arg("UV_VERSION"), parts["uv"]["selected_version"])
        self.assertEqual(arg("FRAPPE_COMMIT"), parts["frappe"]["commit"])
        self.assertEqual(arg("ERPNEXT_COMMIT"), parts["erpnext"]["commit"])
        self.assertEqual(arg("EDUCATION_COMMIT"), parts["education"]["commit"])
        self.assertEqual(arg("PAYMENTS_COMMIT"), parts["payments"]["commit"])
        self.assertEqual(arg("HRMS_COMMIT"), parts["hrms"]["commit"])

    def test_dockerfile_verifies_every_pinned_commit_after_checkout(self):
        text = DOCKERFILE.read_text()
        self.assertIn("rev-parse HEAD", text)
        self.assertIn("checkout --detach FETCH_HEAD", text)

    def test_bench_operations_run_as_non_root_user(self):
        # Production failure of record (real Windows E2E + hosted diagnostic
        # probe, 2026-09-30): bench's own guard (bench/cli.py change_uid)
        # logs "You should not run this command as root" and sys.exit(1)
        # whenever a bench command runs with euid 0 and no frappe_user in
        # config — the build's `bench init` RUN died after exactly one WARN
        # line. The image must create the frappe user BEFORE the first bench
        # invocation and keep it as the effective user through the entrypoint
        # (bootstrap.py also drives bench at container start).
        text = DOCKERFILE.read_text()
        lines = text.splitlines()
        directives = [(i, ln.strip()) for i, ln in enumerate(lines)
                      if ln.strip() and not ln.strip().startswith("#")]
        def first(pred, msg):
            for i, ln in directives:
                if pred(ln):
                    return i
            raise AssertionError(msg)
        # Join Dockerfile line continuations into logical commands.
        logical, buf, buf_start = [], "", None
        for i, raw in enumerate(lines):
            if raw.strip().startswith("#"):
                continue
            if buf:
                buf += raw.rstrip("\\").rstrip()
                if not raw.rstrip().endswith("\\"):
                    logical.append((buf_start, buf))
                    buf = ""
                continue
            if not raw.strip():
                continue
            if raw.rstrip().endswith("\\"):
                buf, buf_start = raw.rstrip("\\").rstrip(), i
            else:
                logical.append((i, raw.strip()))
        def first_logical(pred, msg):
            for i, ln in logical:
                if pred(ln):
                    return i
            raise AssertionError(msg)
        useradd_i = first_logical(lambda ln: ln.startswith("RUN useradd")
                                  and "/home/frappe" in ln
                                  and "chown -R frappe:frappe /build" in ln,
                                  "frappe user creation + /build ownership missing")
        user_frappe_i = first(lambda ln: ln == "USER frappe", "USER frappe missing")
        bench_init_i = first_logical(lambda ln: ln.startswith("RUN") and "bench init" in ln,
                                     "bench init RUN missing")
        self.assertLess(useradd_i, user_frappe_i)
        self.assertLess(user_frappe_i, bench_init_i)
        for i, ln in directives:
            if i > bench_init_i and ln.startswith("USER "):
                self.assertEqual("USER frappe", ln,
                                 "bench hard-exits as root; the image must "
                                 "stay on the frappe user for runtime")
        # The frozen-lockfile yarn config lives in the frappe user's HOME so
        # yarn classic honors it for every later `yarn install` bench runs
        # (regardless of cwd) — pinned lockfile behavior tightened, never
        # relaxed.
        self.assertIn("> /home/frappe/.yarnrc", text)
        self.assertNotIn("> /build/.yarnrc", text)


class DesktopContract(unittest.TestCase):
    def test_host_exposure_is_loopback_only(self):
        text = COMPOSE.read_text()
        ports_block = re.findall(r'ports:\n((?:\s+- .+\n)+)', text)
        self.assertTrue(ports_block, "compose has no ports to validate")
        for block in ports_block:
            for published in re.findall(r'"(.+?:\d+:\d+)"', block):
                self.assertTrue(published.startswith("127.0.0.1:"), published)

    def test_no_published_database_port(self):
        # MariaDB must never be reachable from the Windows host network.
        text = COMPOSE.read_text()
        match = re.search(r'^  db:\n(.*?)(?=^  \S)', text, flags=re.M | re.S)
        self.assertIsNotNone(match)
        self.assertNotIn("ports:", match.group(1))

    def test_no_literal_secrets_anywhere_in_product_layer(self):
        # Sensitive keys (db/admin/root passwords) must never carry a literal
        # value: scripts must use variables (%DBPW%, $ENV{...}) and the runtime
        # secret file is generated on the owner's PC, never shipped.
        sensitive = re.compile(r'(?i)(MARIADB_ROOT_PASSWORD|MYSQL_ROOT_PASSWORD'
                               r'|DB_ROOT_PASSWORD|ADMIN_PASSWORD|DB_PASSWORD)\s*[:=]\s*([^\s&|>]+)')
        for path in PRODUCT.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in (".cmd", ".yml", ".yaml", ".env", ".sh") and "Dockerfile" not in path.name:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in sensitive.finditer(text):
                value = match.group(2).strip("'\"")
                self.assertTrue(
                    value.startswith(("%", "$")) or value.upper().startswith(("[", "{")),
                    f"literal-looking secret value in {path.name}: {match.group(0)[:60]}")
        self.assertFalse((PRODUCT / "data").exists(), "runtime data must be generated on the owner's PC")
        self.assertFalse((PRODUCT / "secrets").exists())
        self.assertFalse(list(PRODUCT.rglob("db.env")))

    def test_install_generates_password_as_variable_not_literal(self):
        install = (PRODUCT / "windows" / "Install TOEFL House ERP.cmd").read_text()
        self.assertIn("NewGuid", install)  # generated on the owner's PC at install time
        self.assertIn("MARIADB_ROOT_PASSWORD=%DBPW%", install)

    def test_windows_scripts_are_zero_typing_and_self_locating(self):
        names = {p.name for p in SCRIPTS}
        self.assertEqual(names, {"Install TOEFL House ERP.cmd", "Start TOEFL House ERP.cmd",
                                 "Stop TOEFL House ERP.cmd", "Backup TOEFL House ERP.cmd",
                                 "Repair TOEFL House ERP.cmd", "Activate TOEFL House ERP.cmd",
                                 "Deactivate TOEFL House ERP.cmd"})
        for path in SCRIPTS:
            text = path.read_text()
            self.assertIn('cd /d "%~dp0.."', text, path.name)
            self.assertNotIn("wsl ", text, path.name)  # Docker Desktop owns WSL2, users never touch it
        install = (PRODUCT / "windows" / "Install TOEFL House ERP.cmd").read_text()
        self.assertIn("docker compose build", install)
        self.assertIn("docker compose up -d", install)
        self.assertIn("first-run-credentials.txt", install.lower())

class RecoveryContract(unittest.TestCase):
    def test_every_service_recovers_after_a_daemon_restart(self):
        # The desktop product must come back whole after a Docker Desktop
        # (daemon) restart: services with `on-failure` that were cleanly
        # stopped by the daemon shutdown do not restart, while
        # `unless-stopped` services do. A mixed state (web up, worker/scheduler
        # /socketio down) is a half-dead product. `compose down` (the Stop
        # script) is an explicit stop, which unless-stopped still honors.
        import re as _re
        text = COMPOSE.read_text()
        services = _re.findall(r"^  (\S+):\n", text, flags=_re.M)
        service_blocks = dict(_re.findall(r"^  (\S+):\n((?:    .*\n|\n)+?)(?=^  \S|\Z)", text, flags=_re.M))
        for name in services:
            block = service_blocks.get(name, "")
            if "image:" not in block and "build:" not in block:
                continue  # top-level volumes section
            self.assertIn("restart: unless-stopped", block,
                          f"service {name} must use unless-stopped so a Docker "
                          "Desktop restart recovers it")
            self.assertNotIn("restart: on-failure", block, name)

    def test_failure_paths_show_a_human_readable_diagnosis(self):
        # When Start/Repair cannot finish, the window shows which service is
        # not up (compose ps) and the last application log lines, plus what
        # each state usually means — the operator must not need Docker
        # knowledge to report the problem.
        for name in ("Start", "Repair"):
            text = (PRODUCT / "windows" / f"{name} TOEFL House ERP.cmd").read_text()
            failed = text[text.index(":failed"):]
            self.assertIn("docker compose ps", failed, name)
            self.assertIn("docker compose logs --tail 5 web", failed, name)
            self.assertIn("database is not ready", failed, name)

    def test_runbook_documents_the_tailnet_multi_user_contract(self):
        # The owner deployment (D13/D15) is central server + Tailscale; the
        # runbook is the single place that states the exact supported setup,
        # and the product stays loopback-only underneath it.
        runbook = (ROOT / "docs/engineering/LAUNCH-RUNBOOK.md").read_text()
        self.assertIn("Multi-user access (central server + Tailscale)", runbook)
        self.assertIn("tailscale serve --bg 8000", runbook)
        self.assertIn("Funnel", runbook)  # the document must warn it stays off
        self.assertIn("no public port", runbook.lower())
        self.assertIn("Restore from backup (operator)", runbook)


class EntrypointContract(unittest.TestCase):
    def test_entrypoint_running_sequence_is_bootstrap_then_gunicorn(self):
        text = (PRODUCT / "entrypoint.sh").read_text()
        self.assertLess(text.index("python3 /product/bootstrap.py"),
                        text.index("exec /home/frappe/bench/env/bin/gunicorn"))


class BootstrapLogicContract(unittest.TestCase):
    def test_missing_apps_keeps_proven_hosted_order(self):
        self.assertEqual(list(bootstrap.APP_ORDER),
                         ["erpnext", "education", "payments", "hrms", "foundation_security", "toefl_house"])
        installed = ["erpnext", "foundation_security"]
        self.assertEqual(bootstrap.missing_apps(installed),
                         ["education", "payments", "hrms", "toefl_house"])
        self.assertEqual(bootstrap.missing_apps(list(bootstrap.APP_ORDER)), [])

    def test_parse_installed_apps_tolerates_bench_output_shapes(self):
        self.assertEqual(bootstrap.parse_installed_apps(""), [])
        self.assertEqual(bootstrap.parse_installed_apps("{}"), [])
        self.assertEqual(bootstrap.parse_installed_apps('["frappe", "erpnext"]'), ["frappe", "erpnext"])
        self.assertEqual(bootstrap.parse_installed_apps('{"albania.localhost": ["frappe", "erpnext"]}'),
                         ["frappe", "erpnext"])

    def test_idempotency_markers(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            sites = Path(tmp)
            self.assertFalse(bootstrap.site_exists("x.localhost", sites))
            (sites / "x.localhost").mkdir(parents=True)
            (sites / "x.localhost" / "site_config.json").write_text("{}")
            self.assertTrue(bootstrap.site_exists("x.localhost", sites))
            self.assertFalse(bootstrap.assets_present(sites))
            (sites / "assets" / "js").mkdir(parents=True)
            self.assertTrue(bootstrap.assets_present(sites))

    def test_empty_bind_mount_is_seeded_before_first_bench_call(self):
        # Regression (product-image run 36750900604): the empty ./data/sites
        # mount hid sites/apps.txt and the very first bench call failed.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            seed, sites = Path(tmp) / "seed", Path(tmp) / "sites"
            seed.mkdir()
            for name in ("apps.txt", "apps.json", "common_site_config.json"):
                (seed / name).write_text(f"image {name}")
            self.assertEqual(sorted(bootstrap.seed_sites(sites, seed)),
                             ["apps.json", "apps.txt", "common_site_config.json"])
            (sites / "common_site_config.json").write_text("owner runtime settings")
            (seed / "apps.txt").write_text("updated image apps")
            self.assertEqual(sorted(bootstrap.seed_sites(sites, seed)), ["apps.json", "apps.txt"])
            self.assertEqual((sites / "common_site_config.json").read_text(), "owner runtime settings")
            self.assertEqual((sites / "apps.txt").read_text(), "updated image apps")
        text = (PRODUCT / "bootstrap.py").read_text()
        body = text[text.index("def bootstrap("):]
        self.assertLess(body.index("seed_sites()"), body.index("run_bench("))
        self.assertIn("/build/sites-seed/", (PRODUCT / "app.Dockerfile").read_text())

    def test_readiness_waits_require_a_successful_page(self):
        # An HTTP error page must never count as "ready": the 127.0.0.1 site
        # bug (run 36758667184) answered errors that plain curl accepted.
        for name in ("Install", "Start", "Repair"):
            text = (PRODUCT / "windows" / f"{name} TOEFL House ERP.cmd").read_text()
            probes = [line for line in text.splitlines() if "curl " in line]
            self.assertTrue(probes, name)
            for line in probes:
                self.assertIn("curl --fail --silent http://127.0.0.1:8000/ ", line, name)

    def test_web_server_pins_the_product_site(self):
        # Regression (product-image run 36758667184): frappe resolves the site
        # from the Host header unless frappe.app._site is set; 127.0.0.1 is no
        # site name, so every Owner request failed.
        entry = (PRODUCT / "entrypoint.sh").read_text()
        self.assertIn("--pythonpath /product", entry)
        self.assertIn("wsgi:application", entry)
        self.assertNotIn("frappe.app:application", entry)
        wsgi = (PRODUCT / "wsgi.py").read_text()
        self.assertIn('frappe.app._site = os.environ.get("SITE_NAME", "toeflhouse.localhost")', wsgi)
        self.assertIn("COPY product/wsgi.py /product/wsgi.py", (PRODUCT / "app.Dockerfile").read_text())
        self.assertIn("!product/wsgi.py", (ROOT / ".dockerignore").read_text())

    def test_credentials_written_once_with_owner_permissions(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            sites = Path(tmp)
            first = bootstrap.write_credentials("x.localhost", "pw-one", sites)
            second = bootstrap.write_credentials("x.localhost", "pw-two", sites)
            self.assertEqual(first, second)
            body = first.read_text()
            self.assertIn("pw-one", body)
            self.assertNotIn("pw-two", body)  # never rotates silently
            self.assertEqual(oct(first.stat().st_mode & 0o777), "0o600")

    def test_root_password_parsing_requires_key_and_value(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            secrets_dir = Path(tmp)
            with self.assertRaises(RuntimeError):
                bootstrap.read_root_password(secrets_dir)
            (secrets_dir / "db.env").write_text("MARQB_ROOT_PASSWORD=no\n")
            with self.assertRaises(RuntimeError):
                bootstrap.read_root_password(secrets_dir)
            (secrets_dir / "db.env").write_text("MARIADB_ROOT_PASSWORD=rootpw\nOTHER=1\n")
            self.assertEqual(bootstrap.read_root_password(secrets_dir), "rootpw")


class CmdSyntaxContract(unittest.TestCase):
    """cmd.exe structure checks for the shipped .cmd scripts.

    Production failures (real Windows E2E runs of the Desktop gate,
    2026-09-30 - same diagnostic three times: `) was unexpected at this
    time.`):
    1. The installer carried multi-line parenthesized `if ( ... )` blocks.
       cmd parses such blocks with an internal read-line convention built
       on CRLF: under an LF-only checkout (possible for any clone because
       no .gitattributes pinned worktree bytes - core.autocrlf=input is a
       stock Git-for-Windows configuration profile) the block parser folds
       across the boundary and aborts at the first unbalanced `)` - the
       first such block is the Docker-missing check, which is why every
       reproduction failed "immediately".
    2. A FOR /F "usebackq" IN-command whose backquoted text contains
       parentheses is misparsed by cmd's FOR tokenizer even outside
       blocks. (Both constructs were individually fixed 2026-09-30; the
       failure class returned via checkout-dependent CRLF.)

    The executable ruling of record for the product scripts:
    * no multi-line parenthesized blocks and no FOR commands in the
      installer (its flow is fully linear: single-line IF ... GOTO);
    * `.gitattributes` pins `text eol=crlf` for *.cmd/*.bat so every
      Windows checkout materializes CRLF bytes regardless of user config;
    * balance/goto/label invariants hold for all shipped scripts;
    * secrets move via PowerShell-stdout-to-tempfile + `set /p`, never a
      FOR capture.
    """

    FOR_RE = re.compile(r"^\s*for\b", re.IGNORECASE)
    GOTO_RE = re.compile(r"\bgoto\s+:?([A-Za-z_][\w.-]*)", re.IGNORECASE)
    LABEL_RE = re.compile(r"^:([A-Za-z_][\w.-]*)\s*$")
    INSTALL = PRODUCT / "windows" / "Install TOEFL House ERP.cmd"

    @staticmethod
    def unquoted(raw):
        """Text with double-quoted spans masked. cmd's block/FOR parsers are
        quote-blind about parens, which is exactly why quoted parens inside
        those constructs must not exist; the one surviving legitimate case
        (a double-quoted argument of a plain top-level command) is masked."""
        return re.sub(r'"[^"\r\n]*"', "", raw)

    @staticmethod
    def depth_signature(lines):
        depth = 0
        for lineno, raw in enumerate(lines, start=1):
            if raw.lstrip().lower().startswith("rem "):
                continue
            u = CmdSyntaxContract.unquoted(raw)
            depth += u.count("(") - u.count(")")
            if depth < 0:
                raise AssertionError(
                    f"unbalanced parenthesized block closes early at line {lineno}: {raw!r}")
        if depth != 0:
            raise AssertionError(f"unclosed parenthesized block (final depth {depth})")

    def test_installer_flow_contains_no_multiline_blocks(self):
        # The previously failing construct class: any parenthesized IF block
        # is forbidden in the installer (the only cmd syntax whose parsing
        # depends on CR/LF assumptions and quote-blind paren matching in a
        # way we cannot reproduce or gate here).
        lines = self.INSTALL.read_text().splitlines()
        for lineno, raw in enumerate(lines, start=1):
            if raw.lstrip().lower().startswith("rem "):
                continue  # rem payloads are opaque to cmd's parser
            u = self.unquoted(raw)
            for ch in "()":
                self.assertNotIn(ch, u,
                                 f"installer line {lineno} carries a parenthesis outside a "
                                 f"double-quoted plain-command argument (parse-hazard class "
                                 f"of the 2026-09-30 production failure): {raw.strip()!r}")

    def test_product_scripts_contain_no_for_commands(self):
        for path in SCRIPTS:
            for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
                self.assertIsNone(self.FOR_RE.match(raw),
                                  f"{path.name}:{lineno}: FOR command in an end-user .cmd "
                                  f"(cmd FOR-parser regression class): {raw.strip()!r}")

    def test_windows_scripts_are_pinned_to_crlf_checkouts(self):
        attrs = (PRODUCT.parent / ".gitattributes").read_text()
        rule = [ln for ln in attrs.splitlines() if ln.strip().startswith("*.cmd")]
        self.assertTrue(rule, ".gitattributes must pin *.cmd EOL behavior")
        self.assertIn("text", rule[0].split("*.cmd", 1)[1].split())
        self.assertIn("eol=crlf", rule[0].split("*.cmd", 1)[1].split())

        for path in SCRIPTS:
            rel = path.relative_to(PRODUCT.parent)
            probe = subprocess.run(
                ["git", "check-attr", "text", "eol", "--", str(rel)],
                cwd=PRODUCT.parent, capture_output=True, text=True, check=True).stdout
            self.assertIn("eol: crlf", probe,
                          f"git must materialize CR/LF for {rel} in every worktree")

    def test_blocks_and_labels_are_well_formed(self):
        for path in SCRIPTS:
            lines = path.read_text().splitlines()
            self.depth_signature(lines)  # raises on unbalanced blocks
            labels = [m.group(1).lower() for line in lines
                      if (m := self.LABEL_RE.match(line.strip()))]
            for label in labels:
                self.assertEqual(labels.count(label), 1,
                                 f"{path.name}: duplicate label :{label}")
            targets = {t.lower() for line in lines
                       if not line.lstrip().lower().startswith("rem ")
                       for t in self.GOTO_RE.findall(self.unquoted(line))}
            for target in targets:
                if target == "eof":
                    continue
                self.assertIn(target, labels,
                              f"{path.name}: goto target missing: :{target}")

    def test_installer_secret_handoff_is_setp_from_tempfile(self):
        install_lines = (PRODUCT / "windows" / "Install TOEFL House ERP.cmd").read_text().splitlines()
        text = "\n".join(install_lines)
        # PowerShell runs exactly once, as a plain top-level command whose
        # stdout goes to the temp file (parens visible only inside its
        # double-quoted script string; never inside a FOR or a block).
        pwsh = [ln for ln in install_lines if "NewGuid" in ln]
        self.assertEqual(len(pwsh), 1)
        self.assertRegex(pwsh[0],
                         r"^powershell -NoProfile -Command \".*NewGuid.* > data\\secrets\\\.dbpw\.tmp\s*$")
        # CMD reads the value back with set /p (no cmd-visible parens,
        # no FOR), treats an empty result as failure, deletes the temp file,
        # and writes only a variable - never a literal - to db.env.
        self.assertIn("set /p DBPW=<data\\secrets\\.dbpw.tmp", text)
        self.assertIn("del data\\secrets\\.dbpw.tmp >nul 2>nul", text)
        self.assertIn("if not defined DBPW goto :failed", text)
        self.assertIn(">data\\secrets\\db.env echo MARIADB_ROOT_PASSWORD=%DBPW%", text)
        # Idempotence: an existing db.env is never regenerated.
        self.assertIn("if exist data\\secrets\\db.env goto :secretok", text)
        # No reintroduction of the FOR-based capture in the whole file.
        for raw in install_lines:
            self.assertIsNone(self.FOR_RE.match(raw))


class OwnerValidationChecklistTests(unittest.TestCase):
    """product/windows/VALIDATION.md is the single canonical, end-user-only
    release-gate evidence checklist: it must cover every DoD stage in order,
    promise no end-user typing, and state the gate stays OPEN without it.
    Assertions are structural invariants only — prose may evolve freely."""

    DOC = PRODUCT / "windows" / "VALIDATION.md"

    def test_checklist_exists_next_to_the_scripts(self):
        self.assertTrue(self.DOC.is_file())

    def test_every_gate_stage_present_in_order(self):
        text = self.DOC.read_text(encoding="utf-8")
        headers = re.findall(r"^## Step (\d+) — (.+)$", text, flags=re.MULTILINE)
        self.assertEqual([int(n) for n, _ in headers], list(range(1, 11)),
                         "exactly ten ordered validation steps required")
        # DoD order pinned step-by-step: install -> first boot -> login ->
        # (persistence probe) -> stop -> start -> backup -> repair ->
        # browser access -> persistence.
        expected = {1: "install", 2: "first boot", 3: "login", 5: "stop",
                    6: "start", 7: "backup", 8: "repair",
                    9: "browser access", 10: "persistence"}
        titles = {int(n): title.lower() for n, title in headers}
        for step, keyword in expected.items():
            self.assertIn(keyword, titles[step],
                          f"step {step} title must contain '{keyword}' (release-gate order)")

    def test_end_user_requires_no_technical_tooling(self):
        plain = self.DOC.read_text(encoding="utf-8").replace("**", "").lower()
        # The audience contract sentence lists every excluded tool.
        marker = plain.find("not need")
        self.assertNotEqual(marker, -1, "checklist must carry an explicit no-need sentence")
        window = plain[marker:marker + 300]
        for phrase in ("powershell", "wsl", "git", "python", "bench"):
            self.assertIn(phrase, window,
                          f"checklist must explicitly exclude end-user need for: {phrase}")
        self.assertNotIn("```", plain, "no code fences: the end user types nothing")

    def test_every_step_carries_numbered_evidence(self):
        text = self.DOC.read_text(encoding="utf-8")
        for n in range(1, 11):
            self.assertIn(f"Evidence {n}", text, f"step {n} lacks a numbered evidence item")

    def test_gate_open_statement_and_single_failure_path(self):
        text = self.DOC.read_text(encoding="utf-8")
        self.assertIn("OPEN", text)
        self.assertIn("If something fails", text)
        # Exactly one end-user recovery path: the Repair script; no other .cmd
        # fallback may be prescribed on failure.
        tail = text[text.index("## If something fails"):]
        self.assertIn("Repair TOEFL House ERP.cmd", tail)
        self.assertNotIn("Install TOEFL House ERP.cmd", tail)


if __name__ == "__main__":
    unittest.main()
