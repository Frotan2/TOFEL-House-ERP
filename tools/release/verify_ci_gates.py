"""Require the latest canonical CI workflows on the exact customer-release SHA.

Default mode is read-only and polls for up to 900 seconds (configurable to
3,600 seconds for the full 60-minute native/foundation jobs). --ensure-started is
the explicitly authorized orchestration mode: dispatch only absent workflows,
after resolving the supplied GitHub branch/tag ref to the expected commit.
Neither mode reruns, cancels, publishes, or modifies repository files.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


REQUIRED_WORKFLOWS = (
    ".github/workflows/owned-suite.yml",
    ".github/workflows/native-lifecycle.yml",
    ".github/workflows/foundation-runtime.yml",
    ".github/workflows/windows-customer-package.yml",
)
PENDING_STATUSES = {"queued", "in_progress", "waiting", "pending", "requested"}
POLL_INTERVAL = 15
API_ROOT = "https://api.github.com"
HEX40 = re.compile(r"^[0-9a-fA-F]{40}$")
EVIDENCE_SCHEMA = "toefl-house-ci-gates/1"
EVIDENCE_SCOPE = "HOSTED ENGINEERING GATES ONLY - NOT OWNER OR PRODUCTION ACCEPTANCE"
MAX_EVIDENCE_BYTES = 1024 * 1024


class GateQueryError(RuntimeError):
    """A safe, fixed-message API/configuration failure."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the authentication header to a redirected endpoint.
        return None


# Module-level seam for tests; production uses stdlib HTTPS with redirects off.
urlopen = build_opener(_NoRedirect()).open


def _positive_int(value) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).isdigit() or int(value) <= 0:
        raise ValueError("invalid run identifier")
    return int(value)


def _sha(value: str) -> str:
    if not isinstance(value, str) or not HEX40.fullmatch(value):
        raise ValueError("a full 40-character expected commit SHA is required")
    return value.lower()


def evaluate_gate_runs(runs, expected_sha, current_run_id) -> dict:
    """Pure report: passed, pending (including missing), or failed.

    Latest means creation time, then run ID and attempt. updated_at is never
    used: completion or rerun of an older run cannot hide a newer failure.
    Only completed/success qualifies. Duplicate contradictory records and
    malformed metadata for a relevant run fail closed.
    """
    expected_sha = _sha(expected_sha)
    current = _positive_int(current_run_id) if current_run_id not in (None, "") else None
    if not isinstance(runs, (list, tuple)) or any(not isinstance(run, dict) for run in runs):
        raise ValueError("workflow runs must be a list of API run objects")
    selected = {}
    invalid = set()
    for run in runs:
        path = run.get("path")
        if path not in REQUIRED_WORKFLOWS or str(run.get("head_sha", "")).lower() != expected_sha:
            continue
        try:
            run_id = _positive_int(run.get("id"))
            if run_id == current:
                continue
            attempt = _positive_int(run.get("run_attempt", 1))
            created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
            if created.tzinfo is None:
                raise ValueError("run creation timestamp lacks timezone")
            key = (created.astimezone(timezone.utc), run_id, attempt)
        except (KeyError, TypeError, ValueError, AttributeError):
            invalid.add(path)
            continue
        previous = selected.get(path)
        if previous is None or key > previous[0]:
            selected[path] = (key, run)
        elif key == previous[0] and (run.get("status"), run.get("conclusion")) != (
                previous[1].get("status"), previous[1].get("conclusion")):
            invalid.add(path)

    gates = []
    for path in REQUIRED_WORKFLOWS:
        gate = {"workflow": path, "status": "pending", "reason": "missing", "run_id": None, "run_attempt": None}
        if path in invalid:
            gate.update(status="failed", reason="invalid_run_metadata")
        elif path in selected:
            _, run = selected[path]
            gate.update(run_id=int(run["id"]), run_attempt=int(run.get("run_attempt", 1)))
            if run.get("status") == "completed":
                if run.get("conclusion") == "success":
                    gate.update(status="passed", reason="completed_success")
                else:
                    gate.update(status="failed", reason="completed_without_success")
            elif isinstance(run.get("status"), str) and run["status"] in PENDING_STATUSES:
                gate.update(status="pending", reason="incomplete")
            else:
                gate.update(status="failed", reason="invalid_run_status")
        gates.append(gate)
    status = "failed" if any(g["status"] == "failed" for g in gates) else (
        "passed" if all(g["status"] == "passed" for g in gates) else "pending")
    return {"expected_sha": expected_sha, "status": status, "gates": gates}


def _repository(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value or "") or any(
            part in {".", ".."} for part in value.split("/")):
        raise ValueError("GITHUB_REPOSITORY must be owner/repository")
    return value


def validate_gate_evidence(evidence: dict, expected_sha: str) -> dict:
    """Validate the portable, non-secret evidence embedded in a customer kit.

    This validates the receipt's shape and exact-SHA binding. The receipt is
    produced only after ``evaluate_gate_runs`` has queried GitHub successfully;
    it is not a substitute for that online check or for human acceptance.
    """
    expected_sha = _sha(expected_sha)
    if not isinstance(evidence, dict) or evidence.get("schema") != EVIDENCE_SCHEMA:
        raise ValueError("invalid CI gate evidence schema")
    repository = _repository(evidence.get("repository", ""))
    if evidence.get("source_revision") != expected_sha or evidence.get("status") != "passed":
        raise ValueError("CI gate evidence does not pass on the exact source revision")
    if evidence.get("production_authorization") != "REJECT" or evidence.get("scope") != EVIDENCE_SCOPE:
        raise ValueError("CI gate evidence is missing its non-authorization boundary")
    created = evidence.get("generated_utc")
    try:
        timestamp = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        raise ValueError("CI gate evidence timestamp is invalid") from None
    if timestamp.tzinfo is None:
        raise ValueError("CI gate evidence timestamp lacks timezone")
    rows = evidence.get("gates")
    if not isinstance(rows, list) or len(rows) != len(REQUIRED_WORKFLOWS):
        raise ValueError("CI gate evidence must contain all four workflows")
    by_path = {}
    seen_run_ids = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("workflow") in by_path:
            raise ValueError("CI gate evidence contains a malformed or duplicate workflow")
        path = row.get("workflow")
        if path not in REQUIRED_WORKFLOWS:
            raise ValueError("CI gate evidence contains an unexpected workflow")
        try:
            run_id = _positive_int(row.get("run_id"))
            _positive_int(row.get("run_attempt"))
        except ValueError:
            raise ValueError("CI gate evidence contains an invalid run identifier") from None
        if run_id in seen_run_ids:
            raise ValueError("CI gate evidence reuses one run for multiple workflows")
        seen_run_ids.add(run_id)
        expected_url = f"https://github.com/{repository}/actions/runs/{run_id}"
        if (row.get("status") != "passed" or row.get("reason") != "completed_success"
                or row.get("run_url") != expected_url):
            raise ValueError("CI gate evidence contains an unqualified workflow receipt")
        by_path[path] = row
    if set(by_path) != set(REQUIRED_WORKFLOWS):
        raise ValueError("CI gate evidence is incomplete")
    return evidence


def make_gate_evidence(report: dict, repository: str) -> dict:
    """Convert a just-queried passing report into a portable release receipt."""
    repository = _repository(repository)
    if not isinstance(report, dict) or report.get("status") != "passed":
        raise ValueError("only a passing exact-SHA gate report can become release evidence")
    rows = []
    for gate in report.get("gates", []):
        if not isinstance(gate, dict):
            raise ValueError("malformed CI gate report")
        row = dict(gate)
        try:
            run_id = _positive_int(row.get("run_id"))
        except ValueError:
            raise ValueError("passing CI gate report lacks a run identifier") from None
        row["run_url"] = f"https://github.com/{repository}/actions/runs/{run_id}"
        rows.append(row)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "repository": repository,
        "source_revision": report.get("expected_sha"),
        "status": "passed",
        "scope": EVIDENCE_SCOPE,
        "production_authorization": "REJECT",
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "gates": rows,
    }
    return validate_gate_evidence(evidence, report.get("expected_sha", ""))


def write_gate_evidence(path: Path, evidence: dict, expected_sha: str) -> None:
    """Write a new evidence file without replacing an existing receipt."""
    if not isinstance(path, Path):
        raise ValueError("CI gate evidence output must be a filesystem path")
    validate_gate_evidence(evidence, expected_sha)
    if not path.parent.is_dir() or path.exists() or path.is_symlink():
        raise ValueError("CI gate evidence output must be a new file in an existing directory")
    payload = (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(payload) > MAX_EVIDENCE_BYTES:
        raise ValueError("CI gate evidence exceeds the size limit")
    created = False
    try:
        with path.open("xb") as handle:
            created = True
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        if created:
            path.unlink(missing_ok=True)
        raise GateQueryError("could not write CI gate evidence without overwriting an existing file") from None


def _api_json(repository: str, suffix: str, token: str, *, method="GET", body=None, timeout=30):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(API_ROOT + "/repos/" + _repository(repository) + suffix, data=data, method=method,
                      headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2026-03-10", "User-Agent": "customer-release-ci-gates",
                               "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read(16 * 1024 * 1024 + 1)
        if len(payload) > 16 * 1024 * 1024:
            raise GateQueryError("GitHub API response exceeds the size limit")
        return json.loads(payload) if payload else None
    except HTTPError as exc:
        # Never emit response bodies, URLs, headers, or arbitrary exception text.
        code = exc.code
        exc.close()
        raise GateQueryError(f"GitHub API request failed (HTTP {code}); check Actions permissions") from None
    except (URLError, OSError, UnicodeError, json.JSONDecodeError):
        raise GateQueryError("GitHub API request failed or returned malformed JSON") from None


def fetch_gate_runs(repository: str, expected_sha: str, token: str, *, deadline=None) -> list[dict]:
    """Fetch every page; an incomplete/search-truncated response cannot qualify."""
    expected_sha = _sha(expected_sha)
    runs = []
    for page in range(1, 11):
        timeout = 30
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise GateQueryError("CI gate polling deadline expired")
            timeout = min(timeout, remaining)
        query = urlencode({"head_sha": expected_sha, "per_page": 100, "page": page})
        payload = _api_json(repository, "/actions/runs?" + query, token, timeout=timeout)
        if (not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list)
                or not isinstance(payload.get("total_count"), int) or isinstance(payload["total_count"], bool)
                or not 0 <= payload["total_count"] <= 1000
                or any(not isinstance(run, dict) for run in payload["workflow_runs"])):
            raise GateQueryError("GitHub workflow run listing is malformed or exceeds the complete-search limit")
        batch = payload["workflow_runs"]
        runs.extend(batch)
        if len(runs) >= payload["total_count"]:
            return runs
        if not batch:
            raise GateQueryError("GitHub workflow run listing is incomplete")
    raise GateQueryError("GitHub workflow run pagination did not complete")


def verify_dispatch_ref(repository: str, expected_sha: str, ref: str, token: str) -> str:
    """Resolve a fully qualified branch/tag, peeling annotated tags to commits."""
    if (not isinstance(ref, str) or not re.fullmatch(r"refs/(?:heads|tags)/[^\x00-\x20]+", ref)
            or ".." in ref or "@{" in ref):
        raise ValueError("--ensure-started requires a full GITHUB_REF under refs/heads/ or refs/tags/")
    payload = _api_json(repository, "/git/ref/" + quote(ref.removeprefix("refs/"), safe="/"), token)
    for _ in range(8):
        obj = payload.get("object") if isinstance(payload, dict) else None
        if not isinstance(obj, dict) or not isinstance(obj.get("sha"), str) or not HEX40.fullmatch(obj["sha"]):
            raise GateQueryError("GitHub ref resolution returned malformed metadata")
        if obj.get("type") == "commit":
            if obj["sha"].lower() != _sha(expected_sha):
                raise GateQueryError("GitHub ref moved away from the expected SHA; no workflows dispatched")
            return ref
        if obj.get("type") != "tag":
            raise GateQueryError("GitHub ref does not resolve to a commit")
        payload = _api_json(repository, "/git/tags/" + obj["sha"], token)
    raise GateQueryError("GitHub annotated tag resolution exceeded the depth limit")


def ensure_gate_runs_started(repository: str, expected_sha: str, current_run_id, ref: str, token: str) -> dict:
    runs = fetch_gate_runs(repository, expected_sha, token)
    report = evaluate_gate_runs(runs, expected_sha, current_run_id)
    if any(g["reason"] == "invalid_run_metadata" for g in report["gates"]):
        raise GateQueryError("Cannot dispatch from ambiguous workflow run metadata")
    missing = [g["workflow"] for g in report["gates"] if g["reason"] == "missing"]
    dispatched = []
    if missing:
        # Preserve the namespace (heads/tags) when dispatching. Never use a SHA
        # or an ambiguous short name as a substitute for the validated ref.
        for path in missing:
            verified_ref = verify_dispatch_ref(repository, expected_sha, ref, token)
            filename = quote(path.rsplit("/", 1)[1], safe="")
            _api_json(repository, "/actions/workflows/" + filename + "/dispatches", token,
                      method="POST", body={"ref": verified_ref})
            dispatched.append(path)
    return {"expected_sha": _sha(expected_sha), "status": "started" if dispatched else "present",
            "dispatched": dispatched}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ensure-started", action="store_true", help="dispatch only missing canonical gates; do not wait")
    parser.add_argument("--timeout", type=int, default=900, help="polling deadline in seconds (1-3600; default 900)")
    parser.add_argument("--ref", default=os.environ.get("GITHUB_REF", ""), help="full branch/tag ref for --ensure-started")
    parser.add_argument("--output", type=Path, help="write the final passing receipt to a new JSON file")
    args = parser.parse_args(argv)
    try:
        if args.ensure_started and args.output is not None:
            raise ValueError("--output is available only after all gates pass, not with --ensure-started")
        if args.output is not None and (not args.output.parent.is_dir()
                                       or args.output.exists() or args.output.is_symlink()):
            raise ValueError("--output must be a new file in an existing directory")
        if not 1 <= args.timeout <= 3600:
            raise ValueError("--timeout must be between 1 and 3600 seconds")
        token = os.environ.get("GH_TOKEN", "")
        if not token:
            raise ValueError("GH_TOKEN is required")
        repository = _repository(os.environ.get("GITHUB_REPOSITORY", ""))
        sha = _sha(os.environ.get("GITHUB_SHA", ""))
        current = os.environ.get("GITHUB_RUN_ID", "")
        if current:
            _positive_int(current)
        if args.ensure_started:
            print(json.dumps(ensure_gate_runs_started(repository, sha, current, args.ref, token), sort_keys=True), flush=True)
            return 0
        deadline = time.monotonic() + args.timeout
        while True:
            report = evaluate_gate_runs(fetch_gate_runs(repository, sha, token, deadline=deadline), sha, current)
            print(json.dumps(report, sort_keys=True), flush=True)
            if report["status"] == "failed":
                return 1
            if report["status"] == "passed":
                if time.monotonic() > deadline:
                    return 1
                if args.output is not None:
                    evidence = make_gate_evidence(report, repository)
                    write_gate_evidence(args.output, evidence, sha)
                return 0
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                print("CI gates timed out; dispatch missing workflows on the exact SHA before releasing", file=sys.stderr)
                return 1
            time.sleep(min(POLL_INTERVAL, remaining))
    except (ValueError, GateQueryError) as exc:
        print("CI gate verification failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
