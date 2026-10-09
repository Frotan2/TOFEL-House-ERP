"""Qualification-only, stdin-secret wrapper around product/bootstrap.py.

The pinned Frappe ``_new_site`` implementation remains the site-creation
authority. This adapter exists so CI can pass ephemeral DB/admin credentials
to that same native API without putting them in Bench's child argv.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product"))
import bootstrap  # noqa: E402


def main(argv=None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments:
        sys.stderr.write("Native site setup refused: credentials must be supplied on stdin.\n")
        return 2
    try:
        raw = sys.stdin.read(64 * 1024 + 1)
        if len(raw.encode("utf-8")) > 64 * 1024:
            raise ValueError
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError
        site = payload.get("site")
        if not isinstance(site, str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", site):
            raise ValueError
        for field in ("db_root_password", "admin_password", "db_password"):
            if not isinstance(payload.get(field), str) or not payload[field]:
                raise ValueError
        bench_dir = Path(os.environ["SITE_BENCH_DIR"])
        site_python = Path(os.environ["SITE_PYTHON"])
        host = payload.get("db_host", "127.0.0.1")
        port = payload.get("db_port", 3306)
        if (not isinstance(host, str) or not host
                or isinstance(port, bool) or not isinstance(port, int)
                or not 1 <= port <= 65535):
            raise ValueError
        set_default = payload.get("set_default_site", False)
        if not isinstance(set_default, bool):
            raise ValueError
        db_name = payload.get("db_name")
        if (db_name is not None and (not isinstance(db_name, str)
                or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", db_name))):
            raise ValueError

        bootstrap.BENCH_DIR = bench_dir
        bootstrap.ENV_PYTHON = site_python
        bootstrap.create_site(
            site,
            payload["db_root_password"],
            payload["admin_password"],
            payload["db_password"],
            db_host=host,
            db_port=port,
            db_type="mariadb",
            mariadb_user_host_login_scope="%",
            set_default_site=set_default,
            db_name=db_name,
        )
    except Exception:
        sys.stderr.write(
            "Native Frappe site creation failed; sensitive diagnostics were withheld.\n")
        return 1
    sys.stdout.write("Native Frappe site creation completed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
