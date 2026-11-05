"""Authorize synthetic native checks without pretending a local run is hosted CI.

A local manifest is explicit operator authorization, not independent proof of
fresh Docker storage. The Windows orchestrator must inspect the actual project,
mounts and volumes before mounting it read-only. This helper never creates a
site, changes flags, activates production, or writes the authorization file.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat


LOCAL_SCOPE = "LOCAL WINDOWS DOCKER SYNTHETIC ONLY"
SCHEMA = "toefl-house-local-native-acceptance/1"
SITES_PATH = "/home/frappe/bench/sites"
EVIDENCE_ROOT = "/tmp/local-windows-evidence"
SITES = ("placement-test.localhost", "placement-second.localhost")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
MAX_MANIFEST_BYTES = 16 * 1024
MANIFEST_KEYS = {"schema", "scope", "source_revision", "checker_revision", "production_authorization",
                 "sites_path", "evidence_root", "docker_project", "sites", "isolation"}
ISOLATION = {"fresh_project": True, "fresh_databases": True,
             "existing_volumes_reused": False, "all_host_mounts_under_root": True}


def _refuse(reason):
    raise RuntimeError("Local native acceptance refused: " + reason)


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _refuse("duplicate manifest key")
        result[key] = value
    return result


def _read_manifest(path):
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        _refuse("manifest must be an absolute regular read-only file")
    try:
        entry = path.lstat()
        if not stat.S_ISREG(entry.st_mode):
            _refuse("manifest must be a regular file")
        if os.access(path, os.W_OK):
            _refuse("manifest is writable by the checker")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if ((entry.st_dev, entry.st_ino) != (before.st_dev, before.st_ino)
                    or not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_MANIFEST_BYTES):
                _refuse("manifest size or file type is invalid")
            raw = stream.read(MAX_MANIFEST_BYTES + 1)
            after = os.fstat(stream.fileno())
        if len(raw) > MAX_MANIFEST_BYTES or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            _refuse("manifest changed while reading")
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except (OSError, UnicodeError, ValueError):
        _refuse("manifest could not be read safely")
    return document, hashlib.sha256(raw).hexdigest()


def _validate_output(path):
    if path.exists() or path.is_symlink():
        _refuse("native report already exists")
    if not path.parent.is_dir() or any(p.is_symlink() for p in path.parents):
        _refuse("evidence directory must exist without symlink parents")


def _validate_document(document, environ, cwd):
    if not isinstance(document, dict) or set(document) != MANIFEST_KEYS:
        _refuse("manifest fields differ from the supported schema")
    for key, expected in (("schema", SCHEMA), ("scope", LOCAL_SCOPE), ("production_authorization", "REJECT"),
                          ("sites_path", SITES_PATH), ("evidence_root", EVIDENCE_ROOT)):
        if document.get(key) != expected:
            _refuse("manifest scope or path is not authorized")
    if str(cwd) != SITES_PATH:
        _refuse("checker must run from the isolated product sites directory")
    for key, variable in (("source_revision", "TOEFL_HOUSE_ACCEPTANCE_SOURCE_REVISION"),
                          ("checker_revision", "TOEFL_HOUSE_ACCEPTANCE_CHECKER_REVISION")):
        value = document[key]
        if not isinstance(value, str) or not HEX40.fullmatch(value) or environ.get(variable) != value:
            _refuse("source or checker revision is not bound to the manifest")
    if not isinstance(document["docker_project"], str) or not re.fullmatch(
            r"th-qual-win-[a-z0-9]+(?:-[a-z0-9]+)*", document["docker_project"]):
        _refuse("Docker project is not a local qualification project")
    isolation = document["isolation"]
    if (not isinstance(isolation, dict) or set(isolation) != set(ISOLATION)
            or any(isolation[key] is not expected for key, expected in ISOLATION.items())):
        _refuse("fresh isolated storage has not been explicitly attested")
    sites = document["sites"]
    if not isinstance(sites, dict) or set(sites) != set(SITES):
        _refuse("only the two dedicated synthetic sites are authorized")
    databases = []
    for item in sites.values():
        if not isinstance(item, dict) or set(item) != {"database"}:
            _refuse("site database authorization is malformed")
        database = item["database"]
        if not isinstance(database, str) or not re.fullmatch(r"syn_[a-z0-9_]{1,59}", database):
            _refuse("database must have a dedicated synthetic name")
        databases.append(database)
    if len(set(databases)) != len(SITES):
        _refuse("synthetic sites must use distinct databases")
    if environ.get("PLACEMENT_REPORT") != EVIDENCE_ROOT + "/native-checks.json":
        _refuse("native report must use the dedicated evidence destination")


@dataclass(frozen=True)
class AcceptanceContext:
    source_revision: str
    checker_revision: str | None = None
    manifest_path: Path | None = None
    manifest_sha256: str | None = None
    document: dict | None = None

    @property
    def local(self):
        return self.manifest_path is not None

    def metadata(self):
        if not self.local:
            return {}
        return {"execution_context": LOCAL_SCOPE, "checker_revision": self.checker_revision,
                "docker_project": self.document["docker_project"], "manifest_sha256": self.manifest_sha256,
                "isolation_evidence": "Operator authorization; Docker mounts/volumes require separate inspection"}

    def guard_connection(self, frappe, site, sites_path):
        """Validate merged Frappe configuration before opening each DB connection."""
        if not self.local:
            return
        document, digest = _read_manifest(self.manifest_path)
        if digest != self.manifest_sha256 or document != self.document:
            _refuse("manifest changed after authorization")
        if (str(sites_path) != SITES_PATH or str(frappe.local.sites_path) != SITES_PATH
                or site not in SITES or frappe.local.site != site):
            _refuse("connection target is not an authorized synthetic site")
        conf = frappe.conf
        database = document["sites"][site]["database"]
        if (conf.get("db_name") != database or conf.get("db_type") != "mariadb"
                or conf.get("db_host") != "db" or type(conf.get("db_port", 3306)) is not int
                or conf.get("db_port", 3306) != 3306 or conf.get("db_socket")
                or conf.get("db_user") not in (None, "", database)):
            _refuse("database identity or endpoint differs from the dedicated manifest")
        if any(type(conf.get(key)) is not int or conf[key] != 1 for key in (
                "allow_tests", "toefl_house_synthetic_only")):
            _refuse("both explicit integer synthetic test flags are required")
        active = conf.get("toefl_house_production_active")
        if (active is not None and (type(active) not in (int, bool) or active != 0)
                or conf.get("toefl_house_production_site")):
            _refuse("production configuration is forbidden")
        from toefl_house.security import SYNTHETIC, site_mode
        if site_mode() != SYNTHETIC:
            _refuse("site mode must remain synthetic")


def execution_context(environ=None, cwd=None):
    environ = os.environ if environ is None else environ
    manifest = environ.get("TOEFL_HOUSE_LOCAL_ACCEPTANCE_MANIFEST")
    if "TOEFL_HOUSE_LOCAL_ACCEPTANCE_MANIFEST" not in environ:
        if environ.get("GITHUB_ACTIONS") != "true":
            raise RuntimeError("Hosted CI or explicit local synthetic authorization is required")
        return AcceptanceContext(source_revision=environ["GITHUB_SHA"])
    if not isinstance(manifest, str) or not manifest:
        _refuse("an explicit manifest path is required")
    path = Path(manifest)
    document, digest = _read_manifest(path)
    _validate_document(document, environ, Path.cwd() if cwd is None else cwd)
    _validate_output(Path(environ["PLACEMENT_REPORT"]))
    return AcceptanceContext(document["source_revision"], document["checker_revision"], path, digest, document)
