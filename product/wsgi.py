"""Gunicorn entry for the single-site desktop product.

frappe.app.init_request resolves the site as ``_site`` or the
X-Frappe-Site-Name header or the request Host. The Owner browses
http://127.0.0.1:8000, whose host is not a site name, so without a pin every
request fails (product-image run 36758667184). This sets the same module
global that frappe's own ``bench serve --site`` sets (frappe.app.serve).
"""
import os

import frappe.app

frappe.app._site = os.environ.get("SITE_NAME", "toeflhouse.localhost")
application = frappe.app.application
