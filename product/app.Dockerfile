# TOEFL House ERP desktop application image.
#
# Pins (ARG defaults) are copies of docs/engineering/foundation-version-matrix.json,
# guarded by tests/foundation/test_product_packaging.py: the build breaks out of
# contract the moment this file and the matrix disagree. Sources are fetched
# commit-pinned and rev-parse verified exactly like the hosted qualification
# runners; upstream code is never patched.
ARG PYTHON_VERSION=3.14.7
FROM python:${PYTHON_VERSION}-slim-bookworm

ARG NODE_VERSION=24.21.0
ARG YARN_VERSION=1.22.22
ARG BENCH_VERSION=5.31.0
ARG UV_VERSION=0.11.6
ARG FRAPPE_COMMIT=988e54f3c4c291e2077a83809663f123731abe76
ARG ERPNEXT_COMMIT=4048fb70e14d1843956fcdabb7c3cca75a1cbcdd
ARG EDUCATION_COMMIT=93bc7075753369457919720690f80c6d2207b5f2
ARG PAYMENTS_COMMIT=cca07d9f9392e2ea0e521c5975151db9e4b6c321
ARG HRMS_COMMIT=a4768b441cff346def505e27f2a2229ee1e05b9b
ARG FRAPPE_REPOSITORY=https://github.com/frappe/frappe
ARG ERPNEXT_REPOSITORY=https://github.com/frappe/erpnext
ARG EDUCATION_REPOSITORY=https://github.com/frappe/education
ARG PAYMENTS_REPOSITORY=https://github.com/frappe/payments
ARG HRMS_REPOSITORY=https://github.com/frappe/hrms

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates build-essential pkg-config libffi-dev libssl-dev \
    xz-utils wkhtmltopdf mariadb-client libmariadb-dev file \
    && rm -rf /var/lib/apt/lists/*
# file: the foundation's bench restore (frappe 16) identifies the backup dump
# with the `file` utility and refuses to run without it; the slim base does
# not ship it, so the runbook's restore procedure would fail on this image.
# libmariadb-dev: mysqlclient (frappe dep) builds from source and finds the
# client library via pkg-config ('Can not find valid pkg-config name').
# The hosted native path proves the same build on ubuntu runners, where the
# dev package is preinstalled; the slim base image needs it added explicitly.
# mysqlclient links against libmariadb.so, which the dev package keeps
# installed for runtime (same image is the runtime).

# Node at the exact pinned version, from the nodejs.org release tarball
# (the same upstream channel the hosted workflow's actions/setup-node uses).
# The tarball's sha256 is verified against the official nodejs.org
# SHASUMS256.txt value: the Product image workflow resolves it live and passes
# it as NODE_TARBALL_SHA256 (and asserts it against the matrix pin), and the
# compose build passes the matrix pin so the owner's local build verifies too.
ARG NODE_TARBALL_SHA256=""
RUN set -eux; \
    curl --fail --silent --show-error --location \
      "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
      -o /tmp/node.tar.xz; \
    if [ -n "${NODE_TARBALL_SHA256}" ]; then \
      echo "${NODE_TARBALL_SHA256}  /tmp/node.tar.xz" | sha256sum -c -; \
    else \
      echo "WARNING: NODE_TARBALL_SHA256 not provided; node tarball integrity NOT verified" >&2; \
    fi; \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1; \
    rm /tmp/node.tar.xz; \
    node --version; \
    npm install --global "yarn@${YARN_VERSION}"; \
    yarn --version

WORKDIR /build
ENV PATH=/build/tools/bin:$PATH
RUN python -m venv /build/tools \
    && /build/tools/bin/pip install --no-cache-dir \
      "frappe-bench==${BENCH_VERSION}" "uv==${UV_VERSION}"

# Commit-pinned upstream source checkouts (same fetch/verify sequence as
# tools/foundation/runtime_install.py and tools/native/run_native.py).
RUN set -eux; \
    for spec in \
      "frappe ${FRAPPE_REPOSITORY} ${FRAPPE_COMMIT}" \
      "erpnext ${ERPNEXT_REPOSITORY} ${ERPNEXT_COMMIT}" \
      "education ${EDUCATION_REPOSITORY} ${EDUCATION_COMMIT}" \
      "payments ${PAYMENTS_REPOSITORY} ${PAYMENTS_COMMIT}" \
      "hrms ${HRMS_REPOSITORY} ${HRMS_COMMIT}"; do \
      set -- $spec; name="$1"; repo="$2"; commit="$3"; \
      git init "/build/sources/${name}"; \
      git -C "/build/sources/${name}" remote add origin "$repo"; \
      git -C "/build/sources/${name}" fetch --depth 1 origin "$commit"; \
      git -C "/build/sources/${name}" checkout --detach FETCH_HEAD; \
      test "$(git -C "/build/sources/${name}" rev-parse HEAD)" = "$commit"; \
    done

# Owned apps from the build context (repository root): copied, then committed
# into throwaway git clones exactly like the placement export, so no app ever
# carries working-tree state and nothing mutates the operator's checkout.
COPY apps/toefl_house /build/owned/toefl_house
COPY apps/foundation_security /build/owned/foundation_security
RUN set -eux; \
    for name in toefl_house foundation_security; do \
      find "/build/owned/${name}" -name '__pycache__' -type d -prune -exec rm -rf {} + ; \
      git -C "/build/owned/${name}" init --initial-branch=operator-product; \
      git -C "/build/owned/${name}" add .; \
      git -C "/build/owned/${name}" -c user.name='TOEFL House product build' \
        -c user.email='product@localhost' commit -m 'Exact app export for product image'; \
    done

COPY product/bootstrap.py /product/bootstrap.py
COPY product/activate.py /product/activate.py
COPY product/wsgi.py /product/wsgi.py
COPY product/entrypoint.sh /product/entrypoint.sh
# The performance baseline (finding 9) runs inside the deployed image:
# the CI perf step execs it by this exact path. (Every script COPYed
# here must also be allowlisted in .dockerignore - the build context is
# an allowlist - enforced by the packaging guard in
# tests/foundation/test_product_packaging.py.)
COPY product/perf_baseline.py /product/perf_baseline.py
RUN chmod +x /product/entrypoint.sh /product/activate.py

# Local bench: frappe from the pinned source (not re-resolved), then the rest.
# Yarn Classic keeps upstream lockfiles frozen for nested installs.
#
# The bench CLI hard-refuses to run as root: bench/cli.py change_uid() logs
# "You should not run this command as root" and sys.exit(1) when the
# effective uid is 0 and no frappe_user exists in config.json — this was the
# exact failure of the first ever executed image build (real Windows E2E and
# the hosted diagnostic probe; output: single WARN line, exit 1, before any
# setup step). The hosted-qualification parity is to keep every bench
# operation as a non-root user, exactly like the runner user in the hosted
# installation path — so the frappe user exists before the FIRST bench
# invocation and stays the image's effective user through the entrypoint
# (bootstrap.py also drives bench: new-site, migrate, build).
RUN useradd --create-home --home-dir /home/frappe --shell /bin/bash frappe \
    && chown -R frappe:frappe /build
USER frappe
# /build/sources and /build/owned hold git repositories created by root in
# earlier layers; bench clones them locally (git clone <path> --origin
# upstream). Git's safe.directory guard (>=2.35.2, CVE-2022-24765) refuses
# cross-owner .git access as fatal: "detected dubious ownership in
# repository at '<path>'". The chown above keeps every checkout owned by
# the same user that reads it — no git-config exceptions anywhere.
RUN set -eux; printf '%s\n' '--install.frozen-lockfile true' '--install.non-interactive true' > /home/frappe/.yarnrc; \
    bench init /home/frappe/bench \
      --frappe-path /build/sources/frappe \
      --python "$(which python)" \
      --no-backups --skip-redis-config-generation --no-procfile --skip-assets --verbose; \
    yarn cache clean; rm -rf /home/frappe/.cache
RUN set -eux; \
    cd /home/frappe/bench; \
    for name in erpnext education payments hrms; do \
      bench get-app --skip-assets "/build/sources/${name}"; \
    done; \
    bench get-app --skip-assets /build/owned/foundation_security; \
    bench get-app --skip-assets /build/owned/toefl_house; \
    uv pip check --python /home/frappe/bench/env/bin/python; \
    mkdir -p /build/sites-seed; \
    cp sites/apps.txt sites/apps.json sites/common_site_config.json /build/sites-seed/; \
    yarn cache clean; rm -rf /home/frappe/.cache
# The compose bind mount (./data/sites) hides the bench's own sites/ files on a
# fresh install; bootstrap.py restores them from /build/sites-seed before the
# first bench call (bench resolves installed apps from sites/apps.txt).
# Package-manager caches (yarn, pip, uv) are removed in the same layer that
# created them: they are first-build-only footprint, never runtime state.

ENV BENCH_DIR=/home/frappe/bench
WORKDIR /home/frappe/bench
EXPOSE 8000 9000
ENTRYPOINT ["/product/entrypoint.sh"]
CMD []
