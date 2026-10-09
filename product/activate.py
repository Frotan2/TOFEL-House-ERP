#!/usr/bin/env python3
"""Owner-operated site-mode switch (not production release authorization).

Runs inside the ``web`` container and performs the guarded lifecycle
procedure from docs/engineering/LAUNCH-RUNBOOK.md so the Owner double-clicks
instead of typing Bench/Docker commands. It changes no release gate:

* The trust boundary stays server file access — the operational-mode triple is
  written to site_config.json from inside the container, never over HTTP.
* Release authorization remains REJECT until independently qualified evidence
  and Owner/non-engineering gates pass; PRODUCTION site mode is not approval.
* Every hard gate is verified against the app's own resolver
  (toefl_house.security.site_mode / record_synthetic_flag / policy mirror).
* Any failed gate restores the pre-activation site_config backup, so the
  site ends REFUSED rather than half-activated.

Commands:
  status                          print the current site mode
  activate --confirm SITE         runbook steps 0-6 (refuses without a fresh backup)
  deactivate --confirm SITE       runbook step 8 (rollback to REFUSED)
  fee-item --confirm SITE CODE    runbook step 7 (existing native Item only)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

BENCH_DIR = Path(os.environ.get("BENCH_DIR", "/home/frappe/bench"))
SITES_DIR = BENCH_DIR / "sites"
SITE_NAME = os.environ.get("SITE_NAME", "toeflhouse.localhost")
ENV_PYTHON = BENCH_DIR / "env" / "bin" / "python"

SYNTHETIC_SITES = {"placement-test.localhost", "placement-second.localhost"}
ACTIVE_KEY = "toefl_house_production_active"
SITE_KEY = "toefl_house_production_site"
FEE_ITEM_KEY = "toefl_house_placement_fee_item"
SYNTHETIC_KEYS = ("toefl_house_synthetic_only", "allow_tests")
BACKUP_MAX_AGE_SECONDS = 24 * 3600
PRICE_LIST = "TOEFL House Standard"
PRODUCTION_AUTHORIZATION = "REJECT"
ACTIVATION_DIR = Path(os.environ.get("TOEFL_HOUSE_ACTIVATION_DIR", "/run/activation"))
BACKUP_RECEIPT_PATH = ACTIVATION_DIR / "backup-receipt.json"
EXPECTED_BACKUP_ROLES = {
    "database": "-database-enc.sql.gz",
    "public_files": "-files-enc.tar",
    "private_files": "-private-files-enc.tar",
    "recovery_config": "-site-config.gpg",
}
RETENTION_PRESERVE_ALL = "Preserve all valid backup sets"
RETENTION_DELETE_BEYOND_KEEP = "Delete valid older sets beyond keep count"
EXPECTED_RETENTION_BEHAVIORS = frozenset({
    RETENTION_PRESERVE_ALL,
    RETENTION_DELETE_BEYOND_KEEP,
})


class Refused(Exception):
    """A precondition or gate failed; the message is shown to the Owner."""


# -- pure helpers (unit-tested offline) ------------------------------------

def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise Refused("backup receipt has no UTC creation time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Refused("backup receipt has an invalid UTC creation time") from exc
    if parsed.tzinfo is None:
        raise Refused("backup receipt creation time must include a timezone")
    return parsed.astimezone(timezone.utc)


def read_backup_receipt(path: Path | None = None) -> dict | None:
    path = path or BACKUP_RECEIPT_PATH
    if not path.is_file():
        return None
    try:
        if path.stat().st_size > 64 * 1024:
            raise Refused("backup receipt is unexpectedly large")
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Refused:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Refused("backup receipt is unreadable") from exc
    if not isinstance(value, dict):
        raise Refused("backup receipt must be a JSON object")
    return value


def _validate_backup_receipt(site: str, receipt: object, now: float,
                             backup_dir: Path | None = None) -> dict:
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
        raise Refused("a current verified encrypted backup receipt is required")
    if receipt.get("source_site") != site:
        raise Refused("backup receipt belongs to a different site")
    if receipt.get("encrypted") is not True or receipt.get("verified") is not True:
        raise Refused("backup receipt does not prove encryption and verification")
    if receipt.get("automation_ready") is not True:
        raise Refused("Owner backup schedule and retention are not configured")

    source_drive = receipt.get("source_drive")
    backup_drive = receipt.get("backup_drive")
    if not isinstance(source_drive, str) or not re.fullmatch(r"[A-Za-z]:", source_drive):
        raise Refused("backup receipt has no valid local source drive")
    if not isinstance(backup_drive, str) or not re.fullmatch(r"[A-Za-z]:", backup_drive):
        raise Refused("backup receipt has no valid separate local backup drive")
    if source_drive.upper() == backup_drive.upper():
        raise Refused("backup must be on a separate local drive")

    created = _parse_utc(receipt.get("created_utc"))
    age = datetime.fromtimestamp(now, timezone.utc) - created
    if age.total_seconds() < -300:
        raise Refused("backup receipt timestamp is in the future")
    if age.total_seconds() > BACKUP_MAX_AGE_SECONDS:
        raise Refused("a verified encrypted backup from the last 24 hours is required")

    backup_set = receipt.get("backup_set")
    if (not isinstance(backup_set, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", backup_set)):
        raise Refused("backup receipt has an invalid backup-set identity")
    manifest_hash = receipt.get("manifest_sha256")
    if not isinstance(manifest_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", manifest_hash):
        raise Refused("backup receipt has no valid manifest digest")
    if not re.fullmatch(r"[a-f0-9]{64}", str(receipt.get("policy_hash", ""))):
        raise Refused("backup receipt has no current Owner backup-policy identity")
    if not re.fullmatch(r"[a-f0-9]{64}", str(receipt.get("recovery_key_sha256", ""))):
        raise Refused("backup receipt has no public recovery-key identity")
    schedule = receipt.get("schedule_time")
    if not isinstance(schedule, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", schedule):
        raise Refused("backup receipt has no valid Owner-selected nightly schedule")
    retention = receipt.get("retention_versions")
    if isinstance(retention, bool) or not isinstance(retention, int) or retention < 2:
        raise Refused("backup receipt has no valid multi-version retention policy")
    retention_behavior = receipt.get("retention_behavior")
    if (not isinstance(retention_behavior, str)
            or retention_behavior not in EXPECTED_RETENTION_BEHAVIORS):
        raise Refused("backup receipt has no explicit Owner-approved retention behavior")
    if receipt.get("task_name") != "TOEFL House ERP Backup":
        raise Refused("Windows scheduled backup task is not attested")

    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(EXPECTED_BACKUP_ROLES):
        raise Refused("backup receipt does not contain the complete encrypted backup set")
    artifact_dir = backup_dir or SITES_DIR / site / "private" / "backups"
    try:
        plaintext_sidecar = next(artifact_dir.glob("*-site_config_backup*.json"), None)
    except OSError as exc:
        raise Refused("could not inspect the native backup folder for plaintext site-config sidecars") from exc
    if plaintext_sidecar is not None:
        raise Refused("a plaintext Frappe site-config backup sidecar remains in the native backup folder")
    by_role = {}
    for item in artifacts:
        if not isinstance(item, dict):
            raise Refused("backup receipt contains an invalid artifact entry")
        role = item.get("role")
        if not isinstance(role, str) or role not in EXPECTED_BACKUP_ROLES or role in by_role:
            raise Refused("backup receipt contains an unexpected or duplicate artifact")
        expected_name = backup_set + EXPECTED_BACKUP_ROLES[role]
        if item.get("name") != expected_name:
            raise Refused("backup receipt artifact name does not match its role")
        expected_hash = item.get("sha256")
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_hash):
            raise Refused(f"backup receipt has no valid SHA-256 digest for {role}")
        size = item.get("bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise Refused(f"backup receipt has an invalid size for {role}")
        path = artifact_dir / expected_name
        if path.is_symlink() or not path.is_file():
            raise Refused(f"verified backup artifact is missing or unsafe: {expected_name}")
        if path.stat().st_size != size or _digest_file(path) != expected_hash:
            raise Refused(f"verified backup artifact changed after receipt: {expected_name}")
        by_role[role] = item
    if set(by_role) != set(EXPECTED_BACKUP_ROLES):
        raise Refused("backup receipt is missing an encrypted database or files artifact")
    return receipt


def validate_receipt_policy(receipt: dict, policy: object) -> None:
    if not isinstance(policy, dict) or policy.get("configured") is not True:
        raise Refused("the Course Owner must configure the nightly backup schedule and retention policy")
    for receipt_key in (
            "policy_hash", "schedule_time", "retention_versions",
            "retention_behavior", "recovery_key_sha256"):
        if receipt.get(receipt_key) != policy.get(receipt_key):
            raise Refused("verified backup does not match the current Owner backup policy")


def check_preconditions(site: str, config: dict, receipt: object, now: float,
                        backup_dir: Path | None = None) -> None:
    if site in SYNTHETIC_SITES:
        raise Refused(f"{site} is a qualification hostname and can never be the production site")
    if config.get("db_type", "mariadb") != "mariadb":
        raise Refused("the site does not run on MariaDB")
    for stale in SYNTHETIC_KEYS:
        if stale in config:
            raise Refused(f"test flag {stale} is present in site_config; this site is not a clean production site")
    _validate_backup_receipt(site, receipt, now, backup_dir)


def with_activation(config: dict, site: str) -> dict:
    updated = dict(config)
    updated[ACTIVE_KEY] = 1
    updated[SITE_KEY] = site
    return updated


def without_activation(config: dict) -> dict:
    return {key: value for key, value in config.items() if key not in (ACTIVE_KEY, SITE_KEY)}


def with_synthetic_flags(config: dict) -> dict:
    updated = dict(config)
    for key in SYNTHETIC_KEYS:
        updated[key] = 1
    return updated


def validate_fee_item_code(code: str) -> str:
    code = (code or "").strip()
    if not code or len(code) > 140:
        raise Refused("the Item code is empty or too long")
    if code.startswith("SYN-") or code.startswith("SYNTHETIC"):
        raise Refused("test-fixture Item codes are not accepted on the production site")
    return code


# -- site access -------------------------------------------------------------

def config_path(site: str) -> Path:
    return SITES_DIR / site / "site_config.json"


def read_config(site: str) -> dict:
    try:
        value = json.loads(config_path(site).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Refused("site_config.json is missing or unreadable") from exc
    if not isinstance(value, dict):
        raise Refused("site_config.json must be a JSON object")
    return value


def write_config(site: str, config: dict) -> None:
    path = config_path(site)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise Refused(f"could not safely write site_config.json: {exc}") from exc


def backup_config(site: str) -> Path:
    # private/ is on the host bind mount; unique private-mode snapshots prevent
    # quick activate/deactivate cycles from overwriting their own recovery copy.
    source = config_path(site)
    target_dir = SITES_DIR / site / "private"
    if not source.is_file():
        raise Refused("site_config.json is missing; cannot preserve activation state")
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    target = target_dir / (
        f"site_config.json.{stamp}-{time.time_ns() % 1_000_000_000:09d}.bak")
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as output, source.open("rb") as original:
            shutil.copyfileobj(original, output)
        os.chmod(target, 0o600)
    except OSError as exc:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise Refused(f"could not safely preserve site_config.json: {exc}") from exc
    return target


def list_backups(site: str) -> list[tuple[str, float]]:
    folder = SITES_DIR / site / "private" / "backups"
    if not folder.is_dir():
        return []
    return [(entry.name, entry.stat().st_mtime) for entry in folder.iterdir() if entry.is_file()]


PROBE = r"""
import json, sys
import frappe
frappe.init(site=sys.argv[1], sites_path=".")
frappe.connect()
from toefl_house import security, policy
from toefl_house.operations.owner_configuration import current_backup_policy
result = {"mode": security.site_mode(), "backup_policy": current_backup_policy()}
try:
    result["flag"] = security.record_synthetic_flag()
except Exception:
    result["flag"] = None
if result["mode"] == security.PRODUCTION:
    mirror = True
    for bad in ("SYN-PLACE-1", "SYNTHETIC-X"):
        try:
            policy.validate_family(bad, 1, production=True)
            mirror = False
        except ValueError:
            pass
    try:
        policy.validate_family("FALL-2026-A", 1, production=True)
    except ValueError:
        mirror = False
    result["mirror"] = mirror
if len(sys.argv) > 2:
    code = sys.argv[2]
    result["item"] = bool(frappe.db.exists("Item", code))
    rate = frappe.db.get_value("Item Price", {"item_code": code, "price_list": sys.argv[3],
                                              "selling": 1}, "price_list_rate")
    result["rate"] = float(rate or 0)
frappe.destroy()
print("PROBE" + json.dumps(result))
"""


def probe(site: str, *extra: str) -> dict:
    try:
        completed = subprocess.run(
            [str(ENV_PYTHON), "-c", PROBE, site, *extra], cwd=SITES_DIR,
            text=True, capture_output=True, check=False)
    except Exception:
        raise Refused("site-mode probe could not start; sensitive diagnostics were withheld") from None
    if completed.returncode:
        raise Refused("site-mode probe failed; sensitive diagnostics were withheld")
    for line in completed.stdout.splitlines():
        if line.startswith("PROBE"):
            try:
                return json.loads(line[len("PROBE"):])
            except json.JSONDecodeError:
                raise Refused("site-mode probe returned invalid data; sensitive diagnostics were withheld") from None
    raise Refused("could not read the site mode; sensitive diagnostics were withheld")


# -- commands -----------------------------------------------------------------

def require_confirm(site: str, confirm: str | None) -> None:
    if confirm != site:
        raise Refused(f"confirmation must be the site name ({site})")


def activate(site: str, log=print) -> None:
    config = read_config(site)
    receipt = read_backup_receipt()
    check_preconditions(site, config, receipt, time.time())
    baseline = probe(site)
    validate_receipt_policy(receipt, baseline.get("backup_policy"))
    if baseline["mode"] == "PRODUCTION":
        log("Already activated: site mode is PRODUCTION. Nothing changed.")
        return
    if baseline["mode"] != "REFUSED":
        raise Refused(f"site mode is {baseline['mode']}, expected REFUSED before activation")
    saved = backup_config(site)
    log(f"Saved current settings to {saved.name}")
    try:
        write_config(site, with_activation(config, site))
        state = probe(site)
        if state["mode"] != "PRODUCTION" or state["flag"] != 0 or not state.get("mirror"):
            raise Refused(f"activation gates failed: {state}")
        write_config(site, with_synthetic_flags(read_config(site)))
        mixed = probe(site)["mode"]
        write_config(site, {k: v for k, v in read_config(site).items() if k not in SYNTHETIC_KEYS})
        if mixed != "REFUSED":
            raise Refused(f"mixed-mode check failed: resolved {mixed}, expected REFUSED")
        if probe(site)["mode"] != "PRODUCTION":
            raise Refused("site did not return to PRODUCTION after the mixed-mode check")
    except Exception:
        shutil.copy2(saved, config_path(site))
        log("Activation FAILED; previous settings restored (site stays REFUSED).")
        raise
    log("All gates passed: site mode PRODUCTION, production stamps, fixtures refused, "
        "mixed mode refused.")


def deactivate(site: str, log=print) -> None:
    saved = backup_config(site)
    log(f"Saved current settings to {saved.name}")
    try:
        write_config(site, without_activation(read_config(site)))
        mode = probe(site)["mode"]
        if mode != "REFUSED":
            raise Refused(f"after deactivation the site resolved {mode}, expected REFUSED")
    except Exception:
        # Same contract as activation: a failed verification must not leave
        # the site in an ambiguous state. Restore the saved settings, so the
        # site deterministically returns to the state it had before this
        # attempt (still ACTIVE) and the owner can inspect and retry.
        shutil.copy2(saved, config_path(site))
        log("Deactivation FAILED verification; previous settings restored (site stays ACTIVE).")
        raise
    log("Deactivated: site mode REFUSED.")


def set_fee_item(site: str, code: str, log=print) -> None:
    code = validate_fee_item_code(code)
    if probe(site)["mode"] != "PRODUCTION":
        raise Refused("activate the site first")
    state = probe(site, code, PRICE_LIST)
    if not state.get("item"):
        raise Refused(f"Item {code} does not exist; Finance must create it in ERPNext first")
    if state.get("rate", 0) <= 0:
        raise Refused(f"Item {code} has no positive selling rate on the '{PRICE_LIST}' price list")
    backup_config(site)
    config = read_config(site)
    config[FEE_ITEM_KEY] = code
    write_config(site, config)
    log(f"Placement fee Item set to {code}.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("status", "activate", "deactivate", "fee-item"))
    parser.add_argument("--confirm")
    parser.add_argument("code", nargs="?")
    args = parser.parse_args(argv)
    site = SITE_NAME
    try:
        if args.command == "status":
            state = probe(site)
            backup_policy = state.get("backup_policy") or {"status": "NOT CONFIGURED"}
            print(f"Site operational mode: {state['mode']}")
            print(f"Production authorization: {PRODUCTION_AUTHORIZATION}")
            print(f"Owner backup policy: {backup_policy.get('status', 'NOT CONFIGURED')}")
            return 0
        require_confirm(site, args.confirm)
        if args.command == "activate":
            activate(site)
        elif args.command == "deactivate":
            deactivate(site)
        else:
            set_fee_item(site, args.code or "")
    except Refused as error:
        print(f"REFUSED: {error}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
