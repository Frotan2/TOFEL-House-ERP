#!/usr/bin/env python3
"""Migrate only the runner-created isolated restore site."""
from __future__ import annotations

import os
from pathlib import Path
import sys

RESTORE_SITE="placement-restore.localhost"


def main(argv=None) -> int:
    args=sys.argv[1:] if argv is None else argv
    if os.environ.get("GITHUB_ACTIONS")!="true":
        raise SystemExit("Hosted disposable runner only")
    if args!=[RESTORE_SITE]:
        raise SystemExit("Only the approved synthetic restore site may be migrated")
    configured=os.environ.get("PLACEMENT_RESTORE_SITES_ROOT")
    if not configured:
        raise SystemExit("Isolated restore sites root is required")
    raw=Path(configured)
    if raw.is_symlink() or not raw.is_dir():
        raise SystemExit("Isolated restore sites root is missing or unsafe")
    root=raw.resolve(strict=True)
    if Path.cwd().resolve(strict=True)!=root:
        raise SystemExit("Migration must run from the isolated restore sites root")
    site_dir=root/RESTORE_SITE
    if site_dir.is_symlink() or not (site_dir/"site_config.json").is_file():
        raise SystemExit("Isolated restore site is missing or unsafe")

    from frappe.migrate import SiteMigration
    SiteMigration().run(site=RESTORE_SITE)
    print("Isolated restore-site migration completed.")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
