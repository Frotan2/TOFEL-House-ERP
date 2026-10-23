"""Serve native qualification assets without pinning a disposable site.

Gunicorn runs from the active sites root, including the isolated restore
root after restart. Keep Frappe's Host/header site selection intact and use
the same static middleware order as frappe.app.application_with_statics.
"""
import os
from pathlib import Path
import sys

import frappe.app
from frappe.middlewares import StaticDataMiddleware
from werkzeug.middleware.shared_data import SharedDataMiddleware


sites_path = os.path.abspath(os.environ.get("SITES_PATH", "."))
application = SharedDataMiddleware(frappe.app.application, {"/assets": os.path.join(sites_path, "assets")})
application = StaticDataMiddleware(application, {"/files": sites_path})


def setup_assets(site):
    """Link unbundled app public assets in this disposable sites root."""
    if os.environ.get("GITHUB_ACTIONS") != "true" or site not in (
        "placement-test.localhost", "placement-second.localhost", "placement-restore.localhost",
    ):
        raise RuntimeError("Native asset setup is restricted to hosted synthetic sites")
    from frappe import build

    frappe.init(site=site, sites_path=sites_path)
    try:
        if frappe.conf.get("allow_tests") != 1 or frappe.conf.get("toefl_house_synthetic_only") != 1:
            raise RuntimeError("Native asset setup requires a synthetic-only test site")
        # Unlike bundle(), these pinned build helpers only prepare public-path
        # links. No yarn build, compiled assets, or customer-site reset occurs.
        build.setup()
        build.make_asset_dirs()
        installed_css = Path(frappe.get_app_path("toefl_house", "public", "css", "th_design_system.css"))
        served_css = Path(sites_path) / "assets/toefl_house/css/th_design_system.css"
        if not served_css.is_file() or served_css.read_bytes() != installed_css.read_bytes():
            raise RuntimeError("Native static root does not expose the installed role Page CSS")
    finally:
        frappe.destroy()


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--setup-assets":
        raise SystemExit("Usage: native_wsgi.py --setup-assets SYNTHETIC_SITE")
    setup_assets(sys.argv[2])
    print("Native public asset links and role Page CSS verified")
