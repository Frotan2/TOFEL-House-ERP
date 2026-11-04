#!/usr/bin/env bash
# Import one reviewed synthetic image from GitHub's native ARM64 build.
set -euo pipefail
if [[ $# != 2 || ! $2 =~ ^[0-9a-f]{40}$ || $(uname -m) != aarch64 ]]; then
  echo 'Usage on native Linux ARM64: bash import-image.sh ARCHIVE REVIEWED_SOURCE_COMMIT' >&2
  exit 2
fi
archive=$(realpath -e -- "$1")
revision=$2
repo=Frotan2/TOFEL-House-ERP
signer="$repo/.github/workflows/oracle-arm64-build.yml"
gh attestation verify "$archive" --repo "$repo" --signer-workflow "$signer" --source-digest "$revision" --deny-self-hosted-runners >/dev/null
zstd --test --quiet -- "$archive"
zstd --decompress --stdout -- "$archive" | docker image load
tag="toefl-house-erp-oracle-test:$revision"
identity=$(docker image inspect --format '{{.Os}}/{{.Architecture}} {{ index .Config.Labels "org.toefl-house.source-revision" }} {{.Id}}' "$tag")
read -r platform source id <<< "$identity"
[[ $platform == linux/arm64 && $source == "$revision" && $id =~ ^sha256:[0-9a-f]{64}$ ]]
# Bind the site's Compose reference to the verified image config ID.
docker tag "$id" "toefl-house-erp-oracle-test:${id#sha256:}"
printf 'ERP_APP_IMAGE=toefl-house-erp-oracle-test:%s\n' "${id#sha256:}"
