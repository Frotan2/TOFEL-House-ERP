#!/usr/bin/env bash
# Create a fresh, isolated synthetic Oracle staging state and start it.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$ROOT"

if [[ "$(uname -s)" != Linux || "$(uname -m)" != aarch64 ]]; then
  printf '%s\n' 'This staging target requires native Linux ARM64. No files were changed.' >&2
  exit 2
fi
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  printf '%s\n' 'Docker Engine and the Compose plugin are required. No files were changed.' >&2
  exit 2
fi
if [[ ! -f .env || -L .env ]]; then
  printf '%s\n' 'Create a private .env from .env.example and set the approved address and verified image digest. No files were changed.' >&2
  exit 2
fi
if [[ "$(stat -c '%a' .env)" != 600 ]]; then
  printf '%s\n' '.env permissions must be 600. No files were changed.' >&2
  exit 2
fi

SETTINGS="$(python3 - <<'PY'
import ipaddress
import re
from pathlib import Path

values = {}
for raw in Path('.env').read_text(encoding='utf-8').splitlines():
    line = raw.strip()
    if not line or line.startswith('#'):
        continue
    key, separator, value = line.partition('=')
    if not separator or key not in {'PUBLIC_ADDRESS', 'ERP_APP_IMAGE'} or key in values:
        raise SystemExit('The private .env file has unsupported or duplicate entries. No files were changed.')
    values[key] = value.strip()
address = values.get('PUBLIC_ADDRESS', '')
image = values.get('ERP_APP_IMAGE', '')
if not address or address.startswith('REPLACE_') or any(c in address for c in '/:@?#'):
    raise SystemExit('Set PUBLIC_ADDRESS to the approved public IP or DNS name. No files were changed.')
try:
    ip = ipaddress.ip_address(address)
except ValueError:
    labels = address.rstrip('.').split('.')
    if len(labels) < 2 or any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', part)
                              for part in labels):
        raise SystemExit('PUBLIC_ADDRESS is not a public IP or valid DNS name. No files were changed.')
else:
    if not ip.is_global or ip.version != 4:
        raise SystemExit('PUBLIC_ADDRESS must be a globally routable IPv4 address. No files were changed.')
if not re.fullmatch(r'ghcr\.io/frotan2/tofel-house-erp(?::[A-Za-z0-9._-]+)?@sha256:[0-9a-f]{64}', image, re.I):
    raise SystemExit('ERP_APP_IMAGE must be a reviewed TOEFL House GHCR image pinned by sha256. No files were changed.')
print(address)
print(image)
PY
 )"
mapfile -t CLOUD_SETTINGS <<< "$SETTINGS"
export PUBLIC_ADDRESS="${CLOUD_SETTINGS[0]}"
export ERP_APP_IMAGE="${CLOUD_SETTINGS[1]}"

MARKER='data/.oracle-cloud-staging-v1'
DB_VOLUME='toefl-house-cloud-staging-db-data'
for path in data data/sites data/logs data/secrets data/activation; do
  if [[ -L "$path" ]]; then
    printf '%s\n' 'A cloud data path is linked. Refusing to mount linked or shared host data.' >&2
    exit 2
  fi
done
if [[ -e data && ! -f "$MARKER" ]]; then
  printf '%s\n' 'The cloud data folder exists without its staging marker. Refusing to reuse or change it.' >&2
  exit 2
fi
if [[ ! -e data ]] && docker volume inspect "$DB_VOLUME" >/dev/null 2>&1; then
  printf '%s\n' 'The staging database volume already exists but its local marker is absent. Refusing to generate new credentials.' >&2
  exit 2
fi
if [[ -e data/sites/toeflhouse.localhost/site_config.json ]] && ! docker volume inspect "$DB_VOLUME" >/dev/null 2>&1; then
  echo 'Existing site has no matching staging database volume. Recover into an isolated target.' >&2
  exit 2
fi
if docker volume inspect "$DB_VOLUME" >/dev/null 2>&1 && [[ ! -s data/sites/toeflhouse.localhost/site_config.json ]]; then
  echo 'Existing database volume has no matching site configuration. Preserve it for recovery.' >&2
  exit 2
fi
docker info >/dev/null
docker compose -f docker-compose.yml --project-name toefl-house-cloud-staging config --no-env-resolution --quiet
docker pull --platform linux/arm64 "$ERP_APP_IMAGE"
if [[ "$(docker image inspect "$ERP_APP_IMAGE" --format '{{.Os}}/{{.Architecture}}')" != linux/arm64 ]]; then
  printf '%s\n' 'The pinned application image is not Linux/ARM64. No cloud data was changed.' >&2
  exit 2
fi

if [[ ! -e data ]]; then
  install -d -m 700 data data/sites data/logs data/secrets data/activation
  python3 - <<'PY'
import os
from pathlib import Path
import secrets

secrets_path = Path('data/secrets/db.env')
fd = os.open(secrets_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w', encoding='ascii') as stream:
    stream.write('MARIADB_ROOT_PASSWORD=' + secrets.token_urlsafe(48) + '\n')
marker = Path('data/.oracle-cloud-staging-v1')
fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w', encoding='ascii') as stream:
    stream.write('synthetic-staging-only\n')
PY
elif [[ ! -f data/secrets/db.env || -L data/secrets/db.env || ! -f "$MARKER" || -L "$MARKER" ]]; then
  printf '%s\n' 'The staging data or credential markers are missing or linked. Refusing repair or secret regeneration.' >&2
  exit 2
fi
if [[ "$(stat -c '%a' data/secrets/db.env)" != 600 || "$(stat -c '%a' "$MARKER")" != 600 ]]; then
  printf '%s\n' 'Cloud staging secrets/marker must have mode 600. Refusing startup.' >&2
  exit 2
fi
python3 - <<'PY'
import re
from pathlib import Path

content = Path('data/secrets/db.env').read_text(encoding='ascii')
if not re.fullmatch(r'MARIADB_ROOT_PASSWORD=[A-Za-z0-9_-]{48,}\n', content):
    raise SystemExit('The cloud database secret is malformed. Refusing startup.')
if Path('data/.oracle-cloud-staging-v1').read_text(encoding='ascii') != 'synthetic-staging-only\n':
    raise SystemExit('The cloud staging marker is invalid. Refusing startup.')
PY

docker compose -f docker-compose.yml --project-name toefl-house-cloud-staging config --quiet
docker compose -f docker-compose.yml --project-name toefl-house-cloud-staging up --detach --pull always
printf '%s\n' 'Started the isolated synthetic Oracle staging stack. Confirm HTTPS, service health, and the backup/recovery gate before any operational use.'
