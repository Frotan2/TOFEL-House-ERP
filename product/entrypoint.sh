#!/bin/sh
# TOEFL House ERP desktop product — web container entrypoint.
# 1) Run the idempotent first-run bootstrap (site, apps, migrations, assets).
# 2) Start the web server (gunicorn, loopback inside the compose network;
#    compose publishes it on the Windows host at 127.0.0.1:8000 only).
set -eu

echo "[toefl-house-erp] starting; first run can take a while (site setup, app install, migrations, asset build)"
python3 /product/bootstrap.py

echo "[toefl-house-erp] bootstrap complete; starting web server"
# frappe.app resolves sites from the sites/ directory (hosted parity: the
# qualification harness launches gunicorn with cwd=<bench>/sites).
cd /home/frappe/bench/sites
exec /home/frappe/bench/env/bin/gunicorn \
  --bind 0.0.0.0:8000 \
  --workers 2 \
  --timeout 120 \
  --pythonpath /product \
  wsgi:application
