#!/bin/sh
# TOEFL House ERP - container entrypoint for the signed update engine.
#
# The Windows updater starts this container with:
#   /product-root  the customer product folder, mounted read-only
#   /update        a private run folder holding request.json, mounted writable
#
# The engine only reads and verifies.  It never imports an image, starts a
# service, deletes customer records or rewrites storage; importing the new image
# and starting the stack stay explicit host-level steps in the Windows updater.
# The only writable state it owns is the durable engine state folder
# (/update-state), where it stores the authentication key, the authorization
# records it issues and the one-use consumption marker.  That folder is shared
# by every update run on this PC, so a replayed apply can never migrate twice.
# No credential value is read or printed here.
set -eu

if [ ! -f /update/request.json ]; then
    echo "engine.request_invalid: the update request document is absent" >&2
    exit 4
fi

# Same ownership repair as product/entrypoint.sh: Windows bind mounts do not
# carry container UIDs, so the frappe user cannot write the response file until
# root has fixed ownership.  chown is best-effort by design; if it cannot be
# applied, the engine fails closed with an unreadable response instead of
# writing outside the run folder.
chown -R frappe:frappe /home/frappe/bench/sites /home/frappe/bench/logs 2>/dev/null || true
chown -R frappe:frappe /update 2>/dev/null || true
chown -R frappe:frappe /update-state 2>/dev/null || true

exec su -s /bin/sh frappe -c 'exec python3 /product/update_engine.py --request /update/request.json --response /update/response.json --state-dir /update-state'
