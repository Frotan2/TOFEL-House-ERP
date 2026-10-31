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

# Only the updater's private request and transaction state may be repaired
# for the unprivileged engine. Never recursively chown mounted customer sites
# or logs before independent host observation: that would change site metadata
# before any migration authorization, even when the engine later refuses.
# Unreadable customer storage must fail closed, not be silently rewritten.
chown -R frappe:frappe /update 2>/dev/null || true
chown -R frappe:frappe /update-state 2>/dev/null || true

# A root-owned broker exposes only fixed GET observations. The frappe engine
# cannot open the raw Docker socket; the broker verifies that permission before
# listening. No API URL or mutating operation exists in its protocol.
python3 /product/update_host.py --serve &
observer_pid=$!
trap 'kill "$observer_pid" 2>/dev/null || true' EXIT HUP INT TERM
attempt=0
while [ ! -f /run/th-update-observer.ready ]; do
    if ! kill -0 "$observer_pid" 2>/dev/null || [ "$attempt" -ge 50 ]; then
        exit 5
    fi
    attempt=$((attempt + 1))
    sleep 0.1
done
set +e
su -s /bin/sh frappe -c 'exec python3 /product/update_engine.py --request /update/request.json --response /update/response.json --state-dir /update-state'
engine_exit=$?
kill "$observer_pid" 2>/dev/null || true
wait "$observer_pid" 2>/dev/null || true
exit "$engine_exit"
