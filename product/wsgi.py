"""Gunicorn entry for the single-site desktop product.

frappe.app.init_request resolves the site as ``_site`` or the
X-Frappe-Site-Name header or the request Host. The Owner browses
http://127.0.0.1:8000, whose host is not a site name, so without a pin every
request fails (product-image run 36758667184). This sets the same module
global that frappe's own ``bench serve --site`` sets (frappe.app.serve).

The module-level ``frappe.app.application`` is the bare request handler:
frappe only wraps the /assets and /files static middlewares on its own
``bench serve`` path (application_with_statics, called from serve()). A WSGI
app serving it unwrapped 404s every asset and file even though the files
exist under sites/assets — the login page's client bundle included, so the
page rendered but login silently did nothing (product-image run
37507203811: bundle present on the served path, still 404). Wrap the same
two middlewares here, in the same order, resolving the sites path exactly as
frappe does (SITES_PATH env, defaulting to the process cwd — the entrypoint
chdirs to the sites directory before exec'ing gunicorn).
"""
import os

import frappe.app
from frappe.middlewares import StaticDataMiddleware
from werkzeug.middleware.shared_data import SharedDataMiddleware

frappe.app._site = os.environ.get("SITE_NAME", "toeflhouse.localhost")

application = frappe.app.application
sites_path = os.path.abspath(os.environ.get("SITES_PATH", "."))
if not os.environ.get("NO_STATICS"):
    application = SharedDataMiddleware(application, {"/assets": os.path.join(sites_path, "assets")})
    application = StaticDataMiddleware(application, {"/files": sites_path})
