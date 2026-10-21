#!/bin/sh
# TOEFL House ERP desktop product — universal service entrypoint.
#
# Runs as root (via docker-compose user: root) to fix Windows bind-mount
# ownership, then drops to the frappe user for all service work. Bench and
# gunicorn never run as root. This is the single entrypoint for every app
# service: bootstrap, web, worker, scheduler, socketio.
#
# Windows bind-mount problem:
#   Docker Desktop on Windows does not map host file ownership to Linux
#   container UIDs. Directories bind-mounted from the Windows host
#   (./data/sites, ./data/logs) appear inside the container with ownership
#   that the frappe user (UID 1000) cannot write to. The entrypoint chowns
#   them as root first, then drops privileges for all actual work.
set -eu

SERVICE="${1:-web}"

# Fix ownership of Windows bind-mounted directories as root. chown is
# best-effort: on some mount types it is a no-op, in which case the
# subsequent frappe-user work surfaces a clear permission error rather than
# silently failing. We never use chmod 0777 — that would expose customer
# data to every local account on the Windows host.
chown -R frappe:frappe /home/frappe/bench/sites /home/frappe/bench/logs 2>/dev/null || true

# Drop to the frappe user for all service execution. su -s /bin/sh keeps the
# process as a direct child of the entrypoint so signals propagate cleanly.
# Root is only used for the chown above; nothing after this point runs as root.
run_frappe() {
    su -s /bin/sh frappe -c "$*"
}

case "$SERVICE" in
    bootstrap)
        # One-shot site initialization: waits for services, seeds sites/,
        # creates the site, installs apps, migrates, builds assets, enables
        # scheduler. Runs once as a Compose one-shot (restart: "no").
        exec run_frappe 'python3 /product/bootstrap.py'
        ;;
    web)
        # Wait for database and Redis, then reconcile static assets after any
        # interrupted build, then start gunicorn. The working directory is
        # /home/frappe/bench/sites so frappe.app resolves sites from there.
        run_frappe 'python3 -c "import sys; sys.path.insert(0, \"/product\"); from bootstrap import wait_for_endpoints; wait_for_endpoints()"'
        run_frappe 'python3 -c "import sys; sys.path.insert(0, \"/product\"); from bootstrap import ensure_web_assets; ensure_web_assets()"'
        exec run_frappe 'cd /home/frappe/bench/sites && exec /home/frappe/bench/env/bin/gunicorn --bind 0.0.0.0:8000 --workers 2 --timeout 120 --pythonpath /product wsgi:application'
        ;;
    worker)
        # Background job worker. Runs after web is healthy.
        exec run_frappe '/build/tools/bin/bench --site toeflhouse.localhost worker --queue short,default,long'
        ;;
    scheduler)
        # Scheduled jobs scheduler. Runs after web is healthy.
        exec run_frappe '/build/tools/bin/bench --site toeflhouse.localhost schedule'
        ;;
    socketio)
        # Socket.IO realtime server. Runs after web is healthy.
        exec run_frappe 'node apps/frappe/socketio.js'
        ;;
    *)
        echo "Unknown service: $SERVICE" >&2
        exit 1
        ;;
esac
