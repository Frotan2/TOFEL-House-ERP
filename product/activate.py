#!/usr/bin/env python3
"""One-time production activation of the desktop product (LAUNCH-RUNBOOK UX layer).

Runs inside the ``web`` container and performs exactly the runbook
procedure (docs/engineering/LAUNCH-RUNBOOK.md steps 0-6 and 8) so the Owner
double-clicks instead of typing Bench/Docker commands. It changes no gate:

* The trust boundary stays server file access — the activation triple is
  written to site_config.json from inside the container, never over HTTP.
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
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

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


class Refused(Exception):
    """A precondition or gate failed; the message is shown to the Owner."""


# -- pure helpers (unit-tested offline) ------------------------------------

def check_preconditions(site: str, config: dict, backups: list[tuple[str, float]], now: float) -> None:
    if site in SYNTHETIC_SITES:
        raise Refused(f"{site} is a qualification hostname and can never be the production site")
    if config.get("db_type", "mariadb") != "mariadb":
        raise Refused("the site does not run on MariaDB")
    for stale in SYNTHETIC_KEYS:
        if stale in config:
            raise Refused(f"test flag {stale} is present in site_config; this site is not a clean production site")
    fresh = [name for name, mtime in backups
             if name.endswith("-database.sql.gz") and now - mtime <= BACKUP_MAX_AGE_SECONDS]
    if not fresh:
        raise Refused("no database backup from the last 24 hours; "
                      "double-click 'Backup TOEFL House ERP.cmd' first, then run activation again")


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
    with open(config_path(site)) as handle:
        return json.load(handle)


def write_config(site: str, config: dict) -> None:
    path = config_path(site)
    temporary = path.with_suffix(".json.tmp")
    with open(temporary, "w") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


def backup_config(site: str) -> Path:
    # private/ is on the host bind mount, so the copy survives container rebuilds.
    target = SITES_DIR / site / "private" / f"site_config.json.{time.strftime('%Y%m%d-%H%M%S')}.bak"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config_path(site), target)
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
result = {"mode": security.site_mode()}
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
    completed = subprocess.run([str(ENV_PYTHON), "-c", PROBE, site, *extra], cwd=SITES_DIR,
                               text=True, capture_output=True, check=False)
    for line in completed.stdout.splitlines():
        if line.startswith("PROBE"):
            return json.loads(line[len("PROBE"):])
    raise Refused(f"could not read the site mode: {(completed.stdout + completed.stderr)[-800:]}")


# -- commands -----------------------------------------------------------------

def require_confirm(site: str, confirm: str | None) -> None:
    if confirm != site:
        raise Refused(f"confirmation must be the site name ({site})")


def activate(site: str, log=print) -> None:
    config = read_config(site)
    check_preconditions(site, config, list_backups(site), time.time())
    baseline = probe(site)
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
    write_config(site, without_activation(read_config(site)))
    mode = probe(site)["mode"]
    if mode != "REFUSED":
        raise Refused(f"after deactivation the site resolved {mode}, expected REFUSED")
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
            print(f"Site {site}: {probe(site)['mode']}")
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
