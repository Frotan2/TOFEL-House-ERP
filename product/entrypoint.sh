#!/bin/sh
# TOEFL House ERP desktop product — web container entrypoint.
# Site initialization and migrations complete in the one-shot bootstrap
# service before Compose starts this long-lived web process. This container
# receives only the read-only activation receipt, never the MariaDB root file.
set -eu

echo "[toefl-house-erp] bootstrap completed; checking database and Redis readiness"
# Compose dependencies gate ordinary starts; this retry also covers Docker
# daemon restarts, where Compose's service_completed_successfully ordering is
# not re-evaluated. It uses no credentials and does not run migrations.
python3 -c 'import sys; sys.path.insert(0, "/product"); from bootstrap import wait_for_endpoints; wait_for_endpoints()'
# Restore and interrupted-build recovery can mutate the shared sites volume
# after the one-shot bootstrap has completed. Reconcile and verify the served
# asset tree at every web start before exposing the login page.
python3 -c 'import sys; sys.path.insert(0, "/product"); from bootstrap import ensure_built_assets; ensure_built_assets()'
echo "[toefl-house-erp] dependencies and static assets verified; starting web server"
# frappe.app resolves sites from the sites/ directory (hosted parity: the
# qualification harness launches gunicorn with cwd=<bench>/sites).
cd /home/frappe/bench/sites
exec /home/frappe/bench/env/bin/gunicorn \
  --bind 0.0.0.0:8000 \
  --workers 2 \
  --timeout 120 \
  --pythonpath /product \
  wsgi:application
