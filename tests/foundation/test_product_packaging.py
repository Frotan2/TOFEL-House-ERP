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

import codecs
import json
import os
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

    def test_every_script_the_ci_execs_in_image_is_copied_into_the_image(self):
        # Regression guard: the CI product-image steps exec scripts by exact
        # /product/... path inside the deployed image. A script the workflow
        # references but the Dockerfile never COPYs is absent from the image,
        # and the step dies with a bare "can't open file" (python exit 2) -
        # exactly how the perf-baseline step failed for several consecutive
        # runs before the gap was found.
        workflow = ROOT / ".github" / "workflows" / "product-image.yml"
        text = DOCKERFILE.read_text()
        # The build context is a .dockerignore ALLOWLIST: a script the
        # Dockerfile COPYs must also be un-ignored, or the COPY has no
        # source file and the build fails before any layer is made.
        ignore = (ROOT / ".dockerignore").read_text()
        ignore_lines = ignore.splitlines()
        self.assertIn("!docs/", ignore_lines)
        self.assertIn("docs/*", ignore_lines,
                      "only the canonical Owner ledger should enter the build context")
        self.assertIn("!docs/owner-decisions.json", ignore_lines)
        referenced = set(re.findall(r"/product/([A-Za-z0-9_.]+\.(?:py|sh))", workflow.read_text()))
        self.assertTrue(referenced, "expected /product/ script references in the workflow")
        missing_copy = [name for name in sorted(referenced)
                        if not re.search(rf"^COPY product/{re.escape(name)} /product/{re.escape(name)}$",
                                         text, flags=re.M)]
        self.assertEqual(missing_copy, [],
                         f"workflow execs in-image scripts the Dockerfile never ships: {missing_copy}")
        missing_allow = [name for name in sorted(referenced)
                         if f"!product/{name}" not in ignore.splitlines()]
        self.assertEqual(missing_allow, [],
                         f"workflow execs in-image scripts the .dockerignore allowlist excludes: {missing_allow}")

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


class DependencyPinContract(unittest.TestCase):
    """P0-3: the matrix is the single canonical pin source and every build /
    CI path binds to it — no candidate-era fields with contradictory facts."""

    MATRIX = ROOT / "docs/engineering" / "foundation-version-matrix.json"

    def test_matrix_is_the_canonical_pin_source(self):
        matrix = json.loads(self.MATRIX.read_text())
        # Candidate-era keys are gone: each was a second (often contradictory)
        # record of the same fact.
        for key in ("kind", "phase2_gate_passed", "approved_runtime_bundle",
                    "baseline_commit", "review_date", "canonical_language",
                    "host_observed", "hosted_runner_probe",
                    "hosted_installation_proof", "unresolved_pins",
                    "owned_security_extension_candidate"):
            self.assertNotIn(key, matrix, f"stale top-level key {key}")
        self.assertIn("lock_status", matrix)
        for part in matrix_parts().values():
            for key in ("status", "source_version", "runtime_imported_version", "risk"):
                self.assertNotIn(key, part, f"stale field {key}")

    def test_remaining_unlocked_inputs_are_explicitly_not_claimed_reproducible(self):
        matrix = json.loads(self.MATRIX.read_text())
        lock_status = matrix["lock_status"]
        self.assertTrue(any("python base image" in item
                            for item in lock_status["tag_pinned"]))
        self.assertTrue(any("Debian bookworm OS packages" in item
                            for item in lock_status["not_locked"]))
        self.assertTrue(any("resolved Python dependency set" in item
                            for item in lock_status["not_locked"]))
        workflow = (ROOT / ".github/workflows/product-image.yml").read_text()
        self.assertIn("does not turn the", workflow)
        self.assertIn("bit-for-bit reproducible image", workflow)

    def test_upstream_contradictions_are_recorded_not_hidden(self):
        parts = matrix_parts()
        # education: the tag v16.1.0 vs source 16.0.1 mismatch is an upstream
        # fact. The matrix states the runtime truth and records the mismatch
        # instead of pretending the tag and the source agree.
        self.assertEqual(parts["education"]["selected_version"], "16.0.1")
        self.assertEqual(parts["education"]["tag"], "v16.1.0")
        self.assertIn("mismatch", parts["education"]["note"].lower())

    def test_node_tarball_integrity_is_verified_end_to_end(self):
        # The Dockerfile verifies the nodejs.org tarball sha256 at build time;
        # the workflow resolves the official SHASUMS256 and asserts it against
        # the matrix pin before building; compose passes the matrix pin so the
        # owner's local build verifies too.
        text = DOCKERFILE.read_text()
        self.assertIn("ARG NODE_TARBALL_SHA256", text)
        self.assertIn("sha256sum -c", text)
        compose = COMPOSE.read_text()
        arg_value = re.search(r'NODE_TARBALL_SHA256:\s*"([^"]*)"', compose).group(1)
        pinned = next(c.get("tarball_sha256", "") for c in json.loads(self.MATRIX.read_text())["components"]
                      if c["name"] == "node")
        self.assertEqual(arg_value, pinned, "compose build arg must equal the matrix pin")
        workflow = (ROOT / ".github/workflows" / "product-image.yml").read_text()
        self.assertIn("SHASUMS256.txt", workflow)
        self.assertIn("--build-arg NODE_TARBALL_SHA256", workflow)

    def test_runner_probe_probes_the_pinned_images(self):
        # The probe pulls the exact digest-pinned images the product runs —
        # not tag guesses — so probe and product cannot diverge on which
        # image they mean.
        probe = (ROOT / "tools/foundation" / "runner_probe.py").read_text()
        self.assertIn('components["redis"]["image_digest"]', probe)
        self.assertNotIn("alpine", probe)


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

    def test_backup_launcher_uses_verified_secondary_drive_flow(self):
        cmd = (PRODUCT / "windows" / "Backup TOEFL House ERP.cmd").read_text()
        ps1 = PRODUCT / "windows" / "Backup TOEFL House ERP.ps1"
        self.assertTrue(ps1.is_file())
        self.assertIn("ExecutionPolicy Bypass", cmd)
        self.assertIn("Backup TOEFL House ERP.ps1", cmd)
        body = ps1.read_text()
        self.assertIn("Win32_LogicalDisk", body)
        self.assertIn("DriveType=3", body)
        self.assertIn("FreeSpace -gt 1073741824", body)
        self.assertIn("DeviceID -ne $sourceDrive", body)
        self.assertIn("encrypt_backup", body)
        self.assertIn('"/product/backup.py"', body)
        self.assertNotIn('"backup", "--with-files"', body)
        self.assertIn("database-enc.sql.gz", body)
        self.assertIn("files-enc.tar", body)
        self.assertIn("private-files-enc.tar", body)
        self.assertIn("Get-FileHash", body)
        self.assertIn("SHA256", body)
        self.assertIn("manifest.json", body)
        self.assertIn("$manifest.source_site -ne $site", body)
        self.assertIn("function Test-ExactBackupSetFiles", body)
        self.assertIn("$entries.Count -ne 5", body)
        self.assertIn("$entry.PSIsContainer", body)
        self.assertIn("ReparsePoint", body)
        self.assertIn("only manifest.json and exactly four safe encrypted payload files", body)
        self.assertIn("A plaintext Frappe site-config sidecar remains in the native backup folder", body)
        self.assertIn("$expectedTaskUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name", body)
        self.assertIn("$task.Principal.UserId", body)
        self.assertIn("$registered.Principal.UserId", body)
        self.assertIn("-LogonType Interactive", body)
        self.assertIn("$retentionPreserveAll", body)
        self.assertIn("$retentionDeleteBeyondKeep", body)
        self.assertIn("if ([string]$policy.retention_behavior -eq $retentionDeleteBeyondKeep)", body)
        self.assertIn("Owner selected preservation: no existing backup sets will be deleted.", body)
        self.assertIn("An explicit Owner backup retention behavior is required", body)
        self.assertIn("retention_behavior = [string]$policy.retention_behavior", body)
        policy_gate = body.index("if (-not $policyConfigured)")
        backup_call = body.index('"/product/backup.py"')
        retention_cleanup = body.index("Remove-ExpiredBackupSets -Root $backupRoot")
        task_verification = body.index("The Windows scheduled backup task could not be verified")
        self.assertLess(policy_gate, backup_call)
        self.assertLess(task_verification, retention_cleanup)
        launcher = (PRODUCT / "windows" / "Backup TOEFL House ERP.cmd").read_text()
        self.assertIn("explicit preserve/delete behavior", launcher)
        activation_launcher = (PRODUCT / "windows" / "Activate TOEFL House ERP.cmd").read_text()
        self.assertIn("-VerifyExisting", activation_launcher)
        self.assertIn("Do not run the backup helper while the preservation decision is unresolved", activation_launcher)
        self.assertIn("Resolve the Owner retention choice and reconcile the implementation/docs", activation_launcher)

    def test_backup_sidecar_cleanup_is_scoped_and_preserves_preexisting_material(self):
        body = (PRODUCT / "windows" / "Backup TOEFL House ERP.ps1").read_text()
        self.assertIn("$preexistingSidecars = @(Get-ChildItem", body)
        self.assertIn("Pre-existing plaintext Frappe site-config sidecars were found; they are preserved", body)
        self.assertIn("$siteConfigSidecarPath = $siteConfigSidecar.FullName", body)
        self.assertIn("Remove-Item -LiteralPath $siteConfigSidecarPath -Force", body)
        self.assertEqual(body.count("Remove-Item -LiteralPath $siteConfigSidecarPath -Force"), 1)
        self.assertNotIn("Get-ChildItem -LiteralPath $sourceDir -Filter \"*-site_config_backup*.json\" -File -ErrorAction SilentlyContinue |\n                Remove-Item", body)
        self.assertNotIn("Get-ChildItem -LiteralPath $backupRoot -Directory -Force -ErrorAction SilentlyContinue |", body[
            body.index("# Do not recursively clean any existing backup material here."):])
        self.assertIn("The current run's plaintext Frappe site-config sidecar remains", body)
        self.assertNotIn("Remove-Item -LiteralPath $recoveryConfigSourcePath", body)
        verify_at = body.index('throw "Post-write integrity verification failed for')
        sidecar_remove_at = body.index("Remove-Item -LiteralPath $siteConfigSidecarPath -Force")
        self.assertGreater(sidecar_remove_at, verify_at,
                           "only remove this run's sidecar after the committed backup set verifies")

    def test_install_generates_password_as_variable_not_literal(self):
        install = (PRODUCT / "windows" / "Install TOEFL House ERP.cmd").read_text()
        self.assertIn("NewGuid", install)  # generated on the owner's PC at install time
        self.assertIn("icacls data\\secrets /inheritance:r /grant:r", install)
        self.assertIn("*S-1-5-18:(OI)(CI)F", install)
        self.assertIn("*S-1-5-32-544:(OI)(CI)F", install)
        self.assertIn("if errorlevel 1 goto :secretaclfailed", install)
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

class LineEndingContract(unittest.TestCase):
    # Linux product inputs and app-tree text must be LF in both Git blobs and
    # physical worktrees; Windows cmd.exe launchers deliberately remain CRLF.
    # Git attributes protect fresh checkouts, but do not rewrite an existing
    # worktree when attributes are added. The installer/Repair normalizer and
    # the Windows stale-checkout job cover that separate case.
    # A CRLF entrypoint shebang becomes `/bin/sh\r` and previously caused
    # `exec /product/entrypoint.sh: no such file or directory` at container boot.
    def test_gitattributes_pins_both_sides(self):
        text = (ROOT / ".gitattributes").read_text()
        self.assertIn("* text=auto eol=lf", text)
        self.assertIn("apps/** text=auto eol=lf", text)
        self.assertIn("product/*.py text eol=lf", text)
        self.assertIn("*.sh text eol=lf", text)
        self.assertIn("*.cmd text eol=crlf", text)
        self.assertIn("*.bat text eol=crlf", text)

    def test_existing_worktree_normalizer_is_wired_before_build_and_repair(self):
        normalizer_path = PRODUCT / "windows" / "Normalize Product Sources.ps1"
        self.assertTrue(normalizer_path.is_file(), "existing Windows worktrees need a physical normalizer")
        normalizer = normalizer_path.read_text()
        for invariant in ("product\\app.Dockerfile", "product\\docker-compose.yml",
                          ".dockerignore", r'Replace("`r`n", "`n").Replace("`r", "`n")',
                          "UTF8Encoding", "WriteAllBytes", "exit 10", "ReparsePoint",
                          "Repository root is a link/junction", "Add-SourceFiles $path $files",
                          "Multiline Dockerfile COPY syntax is unsupported"):
            self.assertIn(invariant, normalizer)
        self.assertIn("Normalize Product Sources.ps1",
                      (PRODUCT / "windows" / "Install TOEFL House ERP.cmd").read_text())
        repair = (PRODUCT / "windows" / "Repair TOEFL House ERP.cmd").read_text()
        self.assertIn("Normalize Product Sources.ps1", repair)
        self.assertIn('if "%NORMALIZE_STATUS%"=="10" goto :rebuildimage', repair)
        self.assertIn("org.toefl-house.source-eol:lf-v1", repair)
        self.assertIn('LABEL org.toefl-house.source-eol="lf-v1"', DOCKERFILE.read_text())
        self.assertIn("docker compose build", repair)
        workflow = (ROOT / ".github/workflows/product-image.yml").read_text()
        self.assertIn("windows-worktree-eol:", workflow)
        self.assertIn("git config core.autocrlf true", workflow)
        self.assertIn('if ($before -notmatch "w/crlf")', workflow)
        self.assertIn("$copyMatches.Count -ne $copyLines.Count", workflow)
        self.assertIn("0xEF, 0xBB, 0xBF", workflow)
        self.assertIn('if (-not $staleText.Contains("`r`n"))', workflow)
        self.assertIn("Windows normalized physical-byte EOL contract", workflow)
        self.assertIn("Windows normalized stale-worktree packaging suite", workflow)
        self.assertIn(".Replace('" + chr(92) + "', '/')", workflow)
        self.assertIn("if ($normalizerExit -ne 10)", workflow)
        self.assertGreaterEqual(workflow.count("if ($LASTEXITCODE -ne 0)"), 2)
        # The source normalizer must never be given runtime-state paths as
        # sources; the Dockerfile COPY allowlist is its only traversed tree.
        self.assertIn("product/data is never", normalizer)
        self.assertNotIn("docker system prune", repair.lower())
        self.assertNotIn("volume prune", repair.lower())

    def test_no_shell_script_contains_cr_bytes(self):
        # The docker build consumes the worktree, so the worktree bytes are
        # the build input; and the committed blob is what a fresh Windows
        # checkout (core.autocrlf=true) fetches. Both must be LF-only.
        for sh in sorted(ROOT.rglob("*.sh")):
            self.assertNotIn(b"\r", sh.read_bytes(), f"{sh} must be LF-only")
        blob = subprocess.run(
            ["git", "show", "HEAD:product/entrypoint.sh"],
            cwd=ROOT, capture_output=True, check=True).stdout
        self.assertNotIn(b"\r", blob, "entrypoint.sh blob must be LF-only")

    def test_build_context_allowlist_stays_lf(self):
        # .dockerignore defines the build context (it keeps product/data/ -
        # live site data, backups, secrets - OUT of the image). A trailing
        # CR on a pattern line makes that pattern match nothing, so the
        # file must be LF in every worktree, pinned like *.sh.
        self.assertNotIn(b"\r", (ROOT / ".dockerignore").read_bytes(),
                         ".dockerignore must be LF-only")
        self.assertIn(".dockerignore text eol=lf",
                      (ROOT / ".gitattributes").read_text())

    def test_dockerfile_copy_sources_are_cr_free(self):
        # Audit the complete Dockerfile COPY allowlist, including app trees:
        # the build context is the current worktree, while i/lf is the Git
        # blob/index side. Both must be LF so a fresh Windows checkout and a
        # stale checkout repaired by the host normalizer build identical bytes.
        text = DOCKERFILE.read_text()
        copy_rows = re.findall(r"(?m)^COPY\s+(\S+)\s+(\S+)\s*$", text)
        sources = {source for source, _destination in copy_rows}
        expected = {
            "apps/toefl_house", "apps/foundation_security",
            "docs/owner-decisions.json",
            "product/bootstrap.py", "product/activate.py", "product/restore.py",
            "product/backup.py", "product/native_gpg.py", "product/native_db.py",
            "product/wsgi.py", "product/entrypoint.sh", "product/perf_baseline.py",
        }
        self.assertEqual(sources, expected, "audit any new Dockerfile COPY source")
        self.assertEqual(len(copy_rows), len(expected), "COPY syntax must stay source/destination only")

        text_suffixes = {
            ".py", ".sh", ".js", ".json", ".css", ".md", ".txt", ".toml",
            ".yaml", ".yml", ".html", ".xml", ".csv", ".svg", ".jinja", ".jinja2",
        }
        copy_files = set()
        for source in sources:
            path = ROOT / source
            self.assertTrue(path.exists(), f"Dockerfile COPY source missing: {source}")
            if path.is_dir():
                for item in path.rglob("*"):
                    if not item.is_file() or "__pycache__" in item.parts or item.suffix == ".pyc":
                        continue  # explicitly excluded by .dockerignore
                    copy_files.add(item)
            else:
                copy_files.add(path)

        audited_tracked = []
        bom_prefixes = (codecs.BOM_UTF8, codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE,
                        codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)
        for path in sorted(copy_files):
            raw = path.read_bytes()
            self.assertFalse(raw.startswith(bom_prefixes),
                             f"{path.relative_to(ROOT)} must not have a Unicode BOM")
            is_text = path.suffix.lower() in text_suffixes
            if not is_text:
                try:
                    raw.decode("utf-8")
                    is_text = True
                except UnicodeDecodeError:
                    is_text = False  # an actual binary asset is not a script
            if not is_text:
                continue
            self.assertNotIn(b"\r", raw,
                             f"{path.relative_to(ROOT)} must be LF-only in the Docker build context")
            raw.decode("utf-8")  # reject non-UTF-8 source before Docker can bake it in
            relative = path.relative_to(ROOT).as_posix()
            tracked = subprocess.run(
                ["git", "ls-files", "--error-unmatch", "--", relative],
                cwd=ROOT, capture_output=True, check=False).returncode == 0
            if tracked:
                audited_tracked.append(relative)

        if audited_tracked:
            result = subprocess.run(
                ["git", "ls-files", "--eol", "--", *sorted(audited_tracked)],
                cwd=ROOT, capture_output=True, text=True, check=True).stdout
            eol_by_path = {}
            for line in result.splitlines():
                prefix, rel = line.split("\t", 1)
                eol_by_path[rel] = prefix.split()
            for relative in audited_tracked:
                eol = eol_by_path.get(relative)
                self.assertIsNotNone(eol, f"git ls-files --eol omitted {relative}")
                self.assertGreaterEqual(len(eol), 2, f"unexpected git EOL status: {relative}: {eol}")
                self.assertIn(eol[0], ("i/lf", "i/none"),
                              f"repository/index blob is not LF: {relative}: {eol}")
                self.assertIn(eol[1], ("w/lf", "w/none"),
                              f"physical worktree is not LF: {relative}: {eol}")
                self.assertIn("eol=lf", eol[2:],
                              f"Git must pin LF for future checkouts: {relative}: {eol}")

        # The build allowlist and Dockerfile are also read directly by Docker
        # on Windows. Pin and check their blobs/worktrees, not just scripts.
        for relative in (".gitattributes", ".dockerignore", "product/app.Dockerfile",
                         "product/docker-compose.yml"):
            raw = (ROOT / relative).read_bytes()
            self.assertFalse(raw.startswith(bom_prefixes),
                             f"{relative} must not have a Unicode BOM")
            self.assertNotIn(b"\r", raw, f"{relative} must be LF-only")
            eol_line = subprocess.run(
                ["git", "ls-files", "--eol", "--", relative], cwd=ROOT,
                capture_output=True, text=True, check=True).stdout.strip()
            prefix = eol_line.split("\t", 1)[0].split()
            self.assertIn(prefix[0], ("i/lf", "i/none"), relative)
            self.assertIn(prefix[1], ("w/lf", "w/none"), relative)
            self.assertIn("eol=lf", prefix[2:], relative)

        # The Docker build also has an in-image fail-closed guard. The host
        # test above proves context bytes; this contract ensures corrupted
        # bytes cause a build error instead of being baked into the image.
        dockerfile = DOCKERFILE.read_text()
        self.assertIn("LF/BOM contract violation", dockerfile)
        self.assertIn('startswith(b"#!/bin/sh\\n")', dockerfile)
        self.assertGreaterEqual(dockerfile.count('startswith(b"#!/usr/bin/env python3\\n")'), 4)

        # Exact kernel-visible interpreter lines prevent a CRLF shebang from
        # becoming /bin/sh\r or /usr/bin/env python3\r inside Docker.
        self.assertEqual((PRODUCT / "entrypoint.sh").read_bytes().splitlines(keepends=True)[0],
                         b"#!/bin/sh\n")
        for name in ("bootstrap.py", "activate.py", "restore.py", "backup.py", "perf_baseline.py"):
            self.assertEqual((PRODUCT / name).read_bytes().splitlines(keepends=True)[0],
                             b"#!/usr/bin/env python3\n", name)



class CmdParserSafetyContract(unittest.TestCase):
    # 2026-09-30: three independent real Windows runs aborted with
    # ") was unexpected at this time" because the delivered .cmd bytes
    # broke cmd's multi-line parenthesized-block parser. Two permanent
    # guards: .gitattributes pins eol=crlf for *.cmd (Git delivery), and
    # every script uses the proven linear flow - no multi-line
    # parenthesized blocks, no FOR commands - so the scripts also parse
    # correctly when delivered as a GitHub ZIP (blob bytes, i.e. LF).
    # Paren text inside top-level `echo`/`rem` lines is legal (it only
    # breaks blocks, and blocks are forbidden), so the checks target the
    # block-opening command words.
    BLOCK_OPENERS = ("if", "for", "call", "choose")

    @staticmethod
    def _unquoted_paren_balance(line: str) -> int:
        balance, in_quote = 0, False
        for ch in line:
            if ch == '"':
                in_quote = not in_quote
            elif not in_quote:
                balance += 1 if ch == "(" else -1 if ch == ")" else 0
        return balance

    def test_all_cmd_files_use_uniform_crlf_in_the_worktree(self):
        for cmd in SCRIPTS:
            raw = cmd.read_bytes()
            self.assertTrue(raw.endswith(b"\r\n"), f"{cmd.name} must end with CRLF")
            lines = raw.split(b"\n")
            self.assertTrue(all(line.endswith(b"\r") for line in lines[:-1]),
                            f"{cmd.name}: mixed line endings")

    def test_no_multiline_parenthesized_blocks_and_no_for(self):
        for cmd in SCRIPTS:
            text = cmd.read_text().replace("\r\n", "\n")
            for lineno, line in enumerate(text.split("\n"), 1):
                stripped = line.strip()
                word = stripped.split(" ", 1)[0].lower()
                if word == "for":
                    self.fail(f"{cmd.name}:{lineno}: FOR commands are "
                              f"forbidden (cmd's FOR parser is quote-blind): {stripped[:60]}")
                if word in self.BLOCK_OPENERS:
                    self.assertEqual(self._unquoted_paren_balance(line), 0,
                                     f"{cmd.name}:{lineno}: multi-line "
                                     f"parenthesized block: {stripped[:60]}")

    def test_every_goto_target_exists(self):
        for cmd in SCRIPTS:
            text = cmd.read_text().replace("\r\n", "\n")
            lines = text.split("\n")
            labels = set()
            for line in lines:
                m = re.match(r"\s*:([A-Za-z_][A-Za-z0-9_]*)", line)
                if m:
                    labels.add(m.group(1))
            for lineno, line in enumerate(lines, 1):
                for target in re.findall(r"(?i)goto\s+:([A-Za-z_][A-Za-z0-9_]*)", line):
                    self.assertIn(target, labels,
                                  f"{cmd.name}:{lineno}: goto :{target} has no label")


class ImageRecreationContract(unittest.TestCase):
    def test_app_services_share_a_stable_image_tag(self):
        # A source update must reach the running product: compose builds
        # one stable tag, and `up -d` then recreates exactly the
        # containers whose image changed. The digest-pinned db/redis
        # images never change, and none of this touches the db-data volume.
        text = COMPOSE.read_text()
        self.assertIn("name: toefl-house-erp", text)
        for svc in ("web", "worker", "scheduler", "socketio"):
            block = re.search(rf"^  {svc}:\n((?:    .*\n|\n)+?)(?=^  \S|\Z)",
                              text, flags=re.M).group(1)
            self.assertIn("image: toefl-house-erp-app:local", block, svc)

    def test_daily_launcher_reuses_the_reviewed_image_without_rebuild(self):
        start = (PRODUCT / "windows" / "Start TOEFL House ERP.cmd").read_text()
        self.assertIn("docker compose up -d --no-build", start)
        self.assertNotIn("docker compose build", start)

    def test_missing_db_env_has_a_guided_path(self):
        # If data\secrets\db.env is missing, every compose command fails
        # with an incomprehensible env_file error. The launcher and the
        # recovery path must detect it and tell the operator exactly what
        # is safe to do (running the installer with an EXISTING database
        # would write a password that does not match the volume).
        for name in ("Start", "Repair"):
            text = (PRODUCT / "windows" / f"{name} TOEFL House ERP.cmd").read_text()
            self.assertIn("db.env", text, name)
            self.assertIn(":nosecret", text, name)
            self.assertIn(":nosecretfresh", text, name)
            self.assertIn("toefl-house-erp_db-data", text, name)

    def test_db_is_not_published_to_the_host(self):
        text = COMPOSE.read_text()
        db_block = re.search(r"^  db:\n((?:    .*\n|\n)+?)(?=^  \S|\Z)",
                             text, flags=re.M).group(1)
        self.assertNotIn("ports:", db_block, "the database must stay "
                                             "inside the compose network")
        self.assertIn("db-data:/var/lib/mysql", db_block)

    def test_startup_waits_are_bounded_and_fail_fast(self):
        # A crash-looping web service must not make the launcher wait
        # forever: every wait loop must terminate into the :failed
        # diagnosis after a bounded number of tries.
        for name in ("Start", "Repair"):
            text = (PRODUCT / "windows" / f"{name} TOEFL House ERP.cmd").read_text()
            text = text.replace("\r\n", "\n")  # parse endings-insensitively
            loop = re.search(r"(?ms)^:waitready$(.*?)^:ready$", text).group(1)
            self.assertIn("READY_TRIES", loop, f"{name}: ready wait must be bounded")
            self.assertIn("goto :failed", loop, f"{name}: bounded wait must fail fast")
        start = (PRODUCT / "windows" / "Start TOEFL House ERP.cmd").read_text()
        start = start.replace("\r\n", "\n")
        daemon = re.search(r"(?ms)^\s*:waitdaemon$(.*?)^:up$", start).group(1)
        self.assertIn("DAEMON_TRIES", daemon, "Start: daemon wait must be bounded")
        self.assertIn("goto :failed", daemon, "Start: daemon wait must fail fast")


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
            if name == "bootstrap":
                self.assertIn('restart: "no"', block,
                              "the one-shot initializer must not run detached after web startup")
                continue
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
            self.assertIn("docker compose logs --tail 5 bootstrap web", failed, name)
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

    def test_product_first_boot_preserves_failure_diagnostics(self):
        # Workflow logs are not always reachable from the qualification
        # environment. Keep the long encrypted lifecycle step wrapped so a
        # failed command still emits selected output and its non-secret
        # checkpoint as GitHub annotations, without weakening its exit gate.
        workflow = (ROOT / ".github/workflows/product-image.yml").read_text()
        start = workflow.index("First boot, encrypted backup/restore and guarded site-mode activation")
        end = workflow.index("Browser UI acceptance", start)
        step = workflow[start:end]
        self.assertIn("tools/foundation/annotated_step.py", step)
        self.assertIn("Product image first-boot failure", step)
        self.assertIn('checkpoint="public-key site-config recovery and sidecar safety"', step)
        self.assertIn("TOEFL_FIRST_BOOT", step)

        upgrade_start = workflow.index("Upgrade/rollback rehearsal")
        upgrade_end = workflow.index("Performance baseline", upgrade_start)
        upgrade_step = workflow[upgrade_start:upgrade_end]
        self.assertIn("tools/foundation/annotated_step.py", upgrade_step)
        self.assertIn("Product upgrade/rollback failure", upgrade_step)
        self.assertIn('checkpoint="native encrypted database and files restore"', upgrade_step)
        self.assertIn('site re-activation failed with exit', upgrade_step)
        self.assertIn("TOEFL_UPGRADE_REHEARSAL", upgrade_step)

    def test_browser_asset_failure_emits_safe_static_route_diagnostics(self):
        workflow = (ROOT / ".github/workflows/product-image.yml").read_text()
        browser_start = workflow.index("Browser UI acceptance (real headless Chromium, real login flow)")
        browser_end = workflow.index("Multi-user tailnet contract", browser_start)
        browser = workflow[browser_start:browser_end]
        self.assertIn("container_asset_http=", browser)
        self.assertIn("target.is_file()", browser)
        self.assertIn("static_root_exists=", browser)
        self.assertIn("::error title=Asset route diagnostic::", browser)
        self.assertIn("-e PYTHONPATH=/product", browser)
        self.assertNotIn("error.err", browser)
        debug_start = browser.index('asset_debug="$(docker compose exec')
        debug_end = browser.index('                  exit 1', debug_start)
        diagnostics = browser[debug_start:debug_end]
        self.assertNotIn("Password:", diagnostics)
        self.assertNotIn("site_config.json", diagnostics)

    def test_tailnet_diagnostics_never_emit_session_credentials(self):
        # A previous qualification annotation included a live synthetic sid and
        # CSRF token. Retain useful presence/cache summaries only; never log
        # raw Set-Cookie values, session rows or full sessiondata.
        workflow = (ROOT / ".github/workflows/product-image.yml").read_text()
        login_start = workflow.index("          def login(username, password, host=None):")
        diagnostic_start = workflow.index("          def session_diag(sid):", login_start)
        progress_start = workflow.index('          progress("admin password present:', diagnostic_start)
        login = workflow[login_start:diagnostic_start]
        diagnostic = workflow[diagnostic_start:progress_start]
        self.assertIn("cookie_names", login)
        self.assertNotIn("[c[:40] for c in cookies]", login)
        self.assertNotIn("text[:300]", login)
        self.assertNotIn("cookies))", login)
        self.assertNotIn('print("::error::" + probe.strip()', diagnostic)
        self.assertNotIn("'db_sessions': rows", diagnostic)
        self.assertNotIn("'probe_sid': sid", diagnostic)
        self.assertNotIn("sessiondata': r", diagnostic)
        self.assertIn("session_data_keys", diagnostic)
        self.assertIn("session_has_csrf", diagnostic)
        self.assertIn("Tailnet session diagnostics", diagnostic)
        self.assertIn("{key: data.get(key) for key in fields}", diagnostic)
        self.assertNotIn("::error::", diagnostic)

    def test_workflow_and_windows_use_the_safe_native_backup_adapter(self):
        workflow = (ROOT / ".github/workflows/product-image.yml").read_text()
        windows_backup = (PRODUCT / "windows" / "Backup TOEFL House ERP.ps1").read_text()
        adapter = (PRODUCT / "backup.py").read_text()
        gpg_transport = (PRODUCT / "native_gpg.py").read_text()
        db_transport = (PRODUCT / "native_db.py").read_text()
        self.assertEqual(workflow.count("web /product/backup.py"), 2)
        self.assertIn('"web", "/product/backup.py"', windows_backup)
        self.assertIn('"02:30", 3, "Preserve all valid backup sets", recovery_public_key', workflow)
        self.assertIn('d["retention_behavior"] == "Preserve all valid backup sets"', workflow)
        self.assertGreaterEqual(workflow.count('"retention_behavior": policy["retention_behavior"]'), 2)
        self.assertNotIn("backup --with-files", workflow)
        self.assertNotIn('"backup", "--with-files"', windows_backup)
        self.assertIn("backups.scheduled_backup(", adapter)
        self.assertIn("backups.delete_temp_backups = lambda", adapter)
        self.assertIn("backup_encryption_key", adapter)
        self.assertIn("--passphrase-fd", gpg_transport)
        self.assertIn("subprocess.run(arguments", gpg_transport)
        self.assertIn("safe_mariadb_credential_transport", adapter)
        self.assertIn("--defaults-extra-file=", db_transport)
        self.assertIn("os.fchmod(descriptor, 0o600)", db_transport)
        self.assertIn("os.link(temporary, destination", adapter)

    def test_product_workflow_masks_secrets_and_suppresses_credential_read_output(self):
        workflow = (ROOT / ".github/workflows/product-image.yml").read_text()
        self.assertNotIn("${cred:0:300}", workflow)
        self.assertNotIn("${cred:0:400}", workflow)
        self.assertIn("command output suppressed because it may contain credentials", workflow)
        self.assertNotIn("chmod 777 data/sites data/logs data/secrets", workflow)
        self.assertIn("chmod 750 data/secrets", workflow)
        self.assertIn("chmod 640 data/secrets/db.env", workflow)
        for variable in ("cred_password", "admin_cred", "backup_encryption_key",
                         "admin_password", "db_password", "admin_pw", "db_root_pw"):
            self.assertIn('echo "::add-mask::$%s"' % variable, workflow)
        first_boot_start = workflow.index("First boot, encrypted backup/restore")
        browser_start = workflow.index("Browser UI acceptance", first_boot_start)
        first_boot = workflow[first_boot_start:browser_start]
        restore_use = first_boot.index('RESTORE_DB_ROOT_PASSWORD="$db_password"')
        self.assertLess(first_boot.index('echo "::add-mask::$admin_password"'), restore_use)
        self.assertLess(first_boot.index('echo "::add-mask::$db_password"'), restore_use)
        self.assertIn('web /product/restore.py', first_boot)
        self.assertIn('python3 - <<\'PY\' | docker compose run', first_boot)
        for argument in ("--db-root-password", "--admin-password", "--encryption-key"):
            self.assertNotIn(argument, workflow)

    def test_product_restore_replaces_file_trees_and_checks_both_scopes(self):
        # Pinned Frappe restore uses tar extraction into existing paths, so a
        # real snapshot rehearsal must stage the old trees, extract into clean
        # public/private targets, and prove both restored and post-backup file
        # state. Keep the human restore ceremony consistent with that behavior.
        workflow = (ROOT / ".github/workflows/product-image.yml").read_text()
        runbook = (ROOT / "docs/engineering/LAUNCH-RUNBOOK.md").read_text()
        self.assertIn('restore_stage="$site_root/private/.ci-restore-files-$GITHUB_RUN_ID"', workflow)
        self.assertIn('restore_stage="$site/private/.ci-restore-files-upgrade-$GITHUB_RUN_ID"', workflow)
        self.assertIn('mv "$files_dir" "$restore_stage/$scope-files"', workflow)
        self.assertIn('product-image-restore-marker.txt', workflow)
        self.assertIn('upgrade-restore-marker.txt', workflow)
        self.assertIn('post-backup-upgrade-marker.txt', workflow)
        self.assertIn("test ! -e \"$1\"", workflow)
        self.assertIn('restored_file" = "$file_marker"', workflow)
        self.assertIn('restored_file" = "$upgrade_file_marker"', workflow)
        self.assertIn('rm -rf -- "$restore_stage"', workflow)
        self.assertIn("it does not remove files absent from the", runbook)
        self.assertIn('stage="$site/private/$RESTORE_STAGE_NAME"', runbook)
        self.assertIn('mv "$files" "$stage/$scope-files"', runbook)
        self.assertIn("umask 077", runbook)
        self.assertIn("docker compose exec -T web sh -eu -c 'rm -rf", runbook)

        # Both rehearsals must stage the old trees after quiescing writers and
        # before the destructive native restore invocation.
        first_stage = workflow.index('restore_stage="$site_root/private/.ci-restore-files-')
        first_stop = workflow.rfind("docker compose stop web worker scheduler socketio", 0, first_stage)
        first_restore = workflow.index("web /product/restore.py", first_stage)
        first_start = workflow.index("docker compose up -d --no-build", first_restore)
        self.assertGreaterEqual(first_stop, 0)
        self.assertLess(first_stop, first_stage)
        self.assertLess(first_stage, first_restore)
        self.assertLess(first_restore, first_start)
        upgrade_stage = workflow.index('restore_stage="$site/private/.ci-restore-files-upgrade-')
        upgrade_stop = workflow.rfind("docker compose stop web worker scheduler socketio", 0, upgrade_stage)
        upgrade_restore = workflow.index("web /product/restore.py", upgrade_stage)
        upgrade_start = workflow.index("docker compose up -d --no-build", upgrade_restore)
        self.assertGreaterEqual(upgrade_stop, 0)
        self.assertLess(upgrade_stop, upgrade_stage)
        self.assertLess(upgrade_stage, upgrade_restore)
        self.assertLess(upgrade_restore, upgrade_start)


class EntrypointContract(unittest.TestCase):
    def test_one_shot_bootstrap_finishes_before_web_and_root_secret_is_isolated(self):
        compose = COMPOSE.read_text()
        bootstrap = re.search(r"^  bootstrap:\n(.*?)(?=^  [^ \n]+:\n)",
                              compose, flags=re.M | re.S).group(1)
        web = re.search(r"^  web:\n(.*?)(?=^  [^ \n]+:\n)",
                        compose, flags=re.M | re.S).group(1)
        self.assertIn('entrypoint: ["python3", "/product/bootstrap.py"]', bootstrap)
        self.assertIn("source: ./data/secrets/db.env", bootstrap)
        self.assertIn("condition: service_completed_successfully", web)
        self.assertNotIn("source: ./data/secrets/db.env", web)
        self.assertNotIn("./data/secrets:/run/secrets", web)
        self.assertNotIn("./data/secrets/db.env", web)
        self.assertIn("./data/activation:/run/activation:ro", web)
        self.assertNotIn("/run/secrets", web)

        entrypoint = (PRODUCT / "entrypoint.sh").read_text()
        self.assertNotIn("bootstrap.py", entrypoint)
        self.assertIn("exec /home/frappe/bench/env/bin/gunicorn", entrypoint)
        bootstrap_source = (PRODUCT / "bootstrap.py").read_text()
        self.assertIn("input=payload", bootstrap_source)
        self.assertIn("capture_output=True", bootstrap_source)
        self.assertNotIn("--db-root-password", bootstrap_source)


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
            assets = sites / "assets"
            (assets / "js").mkdir(parents=True)
            (assets / "css").mkdir()
            self.assertFalse(bootstrap.assets_present(sites))
            (assets / "assets.json").write_text("{}", encoding="utf-8")
            self.assertTrue(bootstrap.assets_present(sites))

    def test_built_assets_are_merged_into_the_static_root(self):
        # Regression (product-image run 37497135855): `bench build` left
        # education's hashed bundle in apps/education/education/public/dist/js/
        # while sites/assets/assets.json referenced it, so the login page 404d
        # /assets/education/dist/js/education.bundle.NS2O3ZWO.js and the frappe
        # global never loaded — login silently did nothing.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apps = root / "apps"
            # standard nested layout apps/<name>/<name>/public (every bundled app)
            edu = apps / "education" / "education" / "public"
            (edu / "dist" / "js").mkdir(parents=True)
            (edu / "dist" / "js" / "education.bundle.NS2O3ZWO.js").write_text("built")
            (edu / "js").mkdir(parents=True)
            (edu / "js" / "education.bundle.js").write_text("plain")
            # the education app's own Vite build creates a top-level
            # apps/education/public/ (outDir ../education/public/frontend);
            # it must not shadow the real nested package public (run 37503724237)
            shadow = apps / "education" / "public" / "frontend"
            shadow.mkdir(parents=True)
            (shadow / "vite-artifact.js").write_text("vite")
            frappe = apps / "frappe" / "frappe" / "public"
            (frappe / "js").mkdir(parents=True)
            (frappe / "js" / "frappe.bundle.js").write_text("core")
            # a top-level layout must work too
            top = apps / "toefl_house" / "public"
            top.mkdir(parents=True)
            (top / "site.css").write_text("css")
            sites = root / "sites"
            (sites / "assets" / "js").mkdir(parents=True)
            (sites / "assets" / "assets.json").write_text(json.dumps({
                "education.bundle.js": "/assets/education/dist/js/education.bundle.NS2O3ZWO.js",
            }), encoding="utf-8")
            (sites / "assets" / "education").mkdir(parents=True)
            self.assertEqual(bootstrap.manifest_assets_missing(sites),
                             ["education/dist/js/education.bundle.NS2O3ZWO.js"])
            self.assertEqual(sorted(bootstrap.public_assets_missing(sites, apps)),
                             sorted(["education/dist/js/education.bundle.NS2O3ZWO.js",
                                     "education/js/education.bundle.js",
                                     "frappe/js/frappe.bundle.js",
                                     "toefl_house/site.css"]))
            self.assertEqual(sorted(bootstrap.sync_built_assets(sites, apps)),
                             ["education", "frappe", "toefl_house"])
            self.assertEqual((sites / "assets" / "education" / "dist" / "js"
                              / "education.bundle.NS2O3ZWO.js").read_text(), "built")
            self.assertFalse((sites / "assets" / "education" / "frontend"
                              / "vite-artifact.js").exists(),
                             "the shadow top-level public must not be the sync source")
            self.assertEqual(
                json.loads((sites / "assets" / "assets.json").read_text()),
                {"education.bundle.js": "/assets/education/dist/js/education.bundle.NS2O3ZWO.js"})
            self.assertEqual(bootstrap.public_assets_missing(sites, apps), [])
            self.assertEqual(bootstrap.manifest_assets_missing(sites), [])
            # idempotent: a complete volume copies nothing
            self.assertEqual(bootstrap.sync_built_assets(sites, apps), [])

    def test_partial_asset_volume_is_repaired_on_next_boot(self):
        # A volume that crashed mid-build keeps sites/assets half-populated;
        # the next boot must detect and heal it, never ask the owner to wipe
        # persistent data.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apps = root / "apps"
            edu = apps / "education" / "education" / "public"
            (edu / "dist" / "js").mkdir(parents=True)
            (edu / "dist" / "js" / "education.bundle.NS2O3ZWO.js").write_text("built")
            sites = root / "sites"
            (sites / "assets" / "js").mkdir(parents=True)
            (sites / "assets" / "education").mkdir(parents=True)
            self.assertEqual(bootstrap.sync_built_assets(sites, apps), ["education"])
            (sites / "assets" / "education" / "dist" / "js" / "education.bundle.NS2O3ZWO.js").unlink()
            self.assertEqual(bootstrap.public_assets_missing(sites, apps),
                             ["education/dist/js/education.bundle.NS2O3ZWO.js"])
            self.assertEqual(bootstrap.sync_built_assets(sites, apps), ["education"])
            self.assertEqual(bootstrap.public_assets_missing(sites, apps), [])
        body = (PRODUCT / "bootstrap.py").read_text()[
            (PRODUCT / "bootstrap.py").read_text().index("def bootstrap("):]
        self.assertLess(body.index("sync_built_assets(SITES_DIR)"),
                        body.index("public_assets_missing(SITES_DIR)"))

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
        # Readiness must never accept an HTTP error page. Install uses a
        # fail-closed curl probe; the daily/recovery launchers use the Docker
        # web healthcheck, whose probe is itself curl --fail.
        install = (PRODUCT / "windows" / "Install TOEFL House ERP.cmd").read_text()
        self.assertIn("curl --fail --silent http://127.0.0.1:8000/ ", install)
        for name in ("Start", "Repair"):
            text = (PRODUCT / "windows" / f"{name} TOEFL House ERP.cmd").read_text()
            self.assertIn("State.Health.Status", text, name)
            self.assertIn('findstr /x /c:"healthy"', text, name)

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

    def test_wsgi_wraps_the_static_middlewares_like_frappe_serve(self):
        # Regression (product-image run 37507203811): frappe.app.application
        # is the bare request handler; the /assets and /files middlewares are
        # only wrapped on the `bench serve` path. Our gunicorn app served it
        # unwrapped, so every asset 404d even though the files existed under
        # sites/assets (the login client bundle included, so login silently
        # did nothing). wsgi.py must apply the same two middlewares, in the
        # same order frappe's application_with_statics uses.
        wsgi = (PRODUCT / "wsgi.py").read_text()
        self.assertIn("SharedDataMiddleware", wsgi)
        self.assertIn("StaticDataMiddleware", wsgi)
        self.assertIn('frappe.app.application', wsgi)
        assets = wsgi.index("SharedDataMiddleware(application")
        files = wsgi.index("StaticDataMiddleware(application")
        self.assertLess(assets, files)
        self.assertIn('"/assets": os.path.join(sites_path, "assets")', wsgi)
        self.assertIn('"/files": sites_path', wsgi)
        # the sites path must resolve the way the entrypoint expects
        # (gunicorn runs with cwd = the sites directory)
        self.assertIn('os.environ.get("SITES_PATH", ".")', wsgi)
        entry = (PRODUCT / "entrypoint.sh").read_text()
        self.assertLess(entry.index("cd /home/frappe/bench/sites"),
                        entry.index("exec /home/frappe/bench/env/bin/gunicorn"))

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
            if os.name == "nt":
                # The container creates the credential file atomically with
                # restrictive permissions before any password bytes are written.
                source = Path(bootstrap.__file__).read_text(encoding="utf-8")
                self.assertIn("os.O_EXCL", source)
                self.assertIn("0o600", source)
            else:
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
       on CRLF: a stale or ZIP-provided LF checkout can still occur because
       Git attributes do not retroactively rewrite existing worktrees; the
       block parser folds
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
        # Owner-machine lifecycle is explicit and ordered: install -> first
        # boot -> login -> Start -> Stop -> Start again -> Repair -> browser
        # access -> persistence. Backup/restore are separate, explicitly held
        # Owner gates rather than being represented as completed lifecycle steps.
        expected = {1: "install", 2: "first boot", 3: "login", 5: "start",
                    6: "stop", 7: "start", 8: "repair",
                    9: "browser access", 10: "persistence"}
        titles = {int(n): title.lower() for n, title in headers}
        self.assertIn("start again", titles[7])
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

    def test_lifecycle_and_separate_backup_restore_gates_carry_numbered_evidence(self):
        text = self.DOC.read_text(encoding="utf-8")
        for n in range(1, 14):
            self.assertIn(f"Evidence {n}", text,
                          f"Owner validation lacks numbered evidence item {n}")
        self.assertIn("Backup and restore — separate mandatory Owner gate", text)
        self.assertIn("Task Scheduler Library", text)
        self.assertIn("Tailscale/private-exposure", text)
        self.assertIn("WebSocket handshake", text)
        self.assertIn("UNVERIFIED / HOLD", text)

    def test_gate_open_statement_and_single_failure_path(self):
        text = self.DOC.read_text(encoding="utf-8")
        self.assertIn("OPEN", text)
        self.assertIn("If something fails", text)
        # Exactly one end-user recovery path: the Repair script; no other .cmd
        # fallback may be prescribed on failure.
        tail = text[text.index("## If something fails"):]
        self.assertIn("Repair TOEFL House ERP.cmd", tail)
        self.assertNotIn("Install TOEFL House ERP.cmd", tail)


class DesktopRuntimeReliabilityContract(unittest.TestCase):
    """The end-user scripts must declare the whole stack ready, not just HTTP.

    A prior acceptance run exposed the exact gap: web+db were reachable while
    worker/socketio were still down. The daily Start path must not report
    success in that state, and Repair must have a real success path after the
    Docker daemon check.
    """

    def test_non_web_app_services_bypass_product_bootstrap_entrypoint(self):
        # worker/socketio must execute their own long-running process directly.
        # The bootstrap service alone mounts /run/bootstrap-secrets/db.env;
        # inheriting the wrong image entrypoint causes worker restart loops.
        text = COMPOSE.read_text()
        worker = re.search(r"^  worker:\n(.*?)(?=^  \S)", text, flags=re.M | re.S).group(1)
        socketio = re.search(r"^  socketio:\n(.*?)(?=^  \S)", text, flags=re.M | re.S).group(1)
        self.assertIn('entrypoint: ["/build/tools/bin/bench"]', worker)
        self.assertIn('command: ["worker", "--queue", "short,default,long"]', worker)
        self.assertIn('entrypoint: ["node"]', socketio)
        self.assertIn('command: ["apps/frappe/socketio.js"]', socketio)

    def test_core_services_wait_for_web_health(self):
        text = COMPOSE.read_text()
        for service in ("worker", "socketio", "scheduler"):
            block = re.search(rf"^  {service}:\n(.*?)(?=^  \S)", text, flags=re.M | re.S)
            self.assertIsNotNone(block, service)
            body = block.group(1)
            self.assertIn("condition: service_healthy", body,
                          f"{service} must wait for the web healthcheck before starting")

    def test_redis_readiness_is_explicit(self):
        text = COMPOSE.read_text()
        for service in ("redis-queue", "redis-cache"):
            block = re.search(rf"^  {re.escape(service)}:\n(.*?)(?=^  \S)", text, flags=re.M | re.S)
            self.assertIsNotNone(block, service)
            body = block.group(1)
            self.assertIn("redis-cli", body)
            self.assertIn("healthcheck:", body)
        web = re.search(r"^  web:\n(.*?)(?=^  \S)", text, flags=re.M | re.S).group(1)
        self.assertIn("redis-queue:\n        condition: service_healthy", web)
        self.assertIn("redis-cache:\n        condition: service_healthy", web)

    def test_start_and_repair_require_healthy_web(self):
        for name in ("Start", "Repair"):
            text = (PRODUCT / "windows" / f"{name} TOEFL House ERP.cmd").read_text()
            self.assertIn("State.Health.Status", text)
            self.assertIn('findstr /x /c:"healthy"', text)

    def test_start_does_not_rebuild_on_every_daily_launch(self):
        text = (PRODUCT / "windows" / "Start TOEFL House ERP.cmd").read_text()
        self.assertIn("docker compose up -d --no-build", text)
        self.assertNotIn("docker compose build", text)
        for name in ("worker", "socketio", "scheduler"):
            self.assertIn(f"toefl-house-erp-{name}", text)
        self.assertIn("services did not all become ready within 10 minutes", text)

    def test_repair_has_reachable_success_path_after_docker_check(self):
        text = (PRODUCT / "windows" / "Repair TOEFL House ERP.cmd").read_text()
        self.assertIn("if errorlevel 1 goto :daemondown", text)
        self.assertIn("goto :repair", text)
        self.assertIn(":repair", text)
        self.assertIn("if not exist data\\secrets\\db.env goto :nosecret", text)
        self.assertIn("docker compose up -d --no-build", text)
        self.assertIn("services did not all become ready within 50 minutes", text)

    def test_failure_diagnostics_include_all_core_runtime_services(self):
        for name in ("Start", "Repair"):
            text = (PRODUCT / "windows" / f"{name} TOEFL House ERP.cmd").read_text()
            for service in ("web", "worker", "socketio", "scheduler"):
                self.assertIn(service, text)


if __name__ == "__main__":
    unittest.main()
