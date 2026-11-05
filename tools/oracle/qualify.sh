#!/usr/bin/env bash
# Disposable native GitHub runner only. Use the deployable Compose file.
set -euo pipefail
[[ ${GITHUB_ACTIONS:-} == true && $(uname -m) == aarch64 ]]
stack=$(mktemp -d "${RUNNER_TEMP:?}/oracle-ci.XXXXXXXX")
cp product/oracle/{docker-compose.yml,Caddyfile} "$stack/"
cd "$stack"
export ERP_APP_IMAGE=toefl-house-erp-app:arm64 PUBLIC_ADDRESS=localhost
mkdir -p data/{secrets,sites,logs,activation}
umask 077
python3 -c 'import pathlib,secrets; pathlib.Path("data/secrets/db.env").write_text("MARIADB_ROOT_PASSWORD=" + secrets.token_urlsafe(48) + "\n")'
# On the private CI host, substitute only the issuer and bind ports to loopback.
sed -i '/^[[:space:]]*issuer acme {$/,/^[[:space:]]*}$/c\        issuer internal' Caddyfile
cat >ci.yml <<'YAML'
services:
  proxy:
    ports: !override
      - "127.0.0.1:443:443"
      - "127.0.0.1:80:80"
YAML
compose=(docker compose -f docker-compose.yml -f ci.yml)
"${compose[@]}" up -d --no-build --wait --wait-timeout 1200
"${compose[@]}" exec -T proxy cat /data/caddy/pki/authorities/local/root.crt > ca.pem
for phase in boot restart; do
  if [[ $phase == restart ]]; then
    "${compose[@]}" stop
    "${compose[@]}" up -d --no-build --wait --wait-timeout 600
  fi
  # Read the synthetic credential through the service user, never into logs.
  "${compose[@]}" exec -T -u frappe web cat /home/frappe/bench/sites/toeflhouse.localhost/private/first-run-credentials.txt |
    python3 "$GITHUB_WORKSPACE/tools/oracle/session_probe.py" ca.pem
  "${compose[@]}" ps --status running --services | sort > running.txt
  diff -u <(printf '%s\n' db proxy redis-cache redis-queue scheduler socketio web worker | sort) running.txt
done
