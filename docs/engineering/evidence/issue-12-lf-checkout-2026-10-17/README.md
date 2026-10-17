# Issue #12: LF checkout proof and the packaging contract (2026-10-17)

Scope: the Windows line-ending defect in Issue #12. Tested on Linux, using fresh clones configured the way a Windows Git checkout is. Not tested: a real Windows machine, Docker build, and runtime. Those stay owner-run.

## Fresh clone with Windows-style settings

Commands (run from scratch clones of the session branch at `178a467`):

    git -c core.autocrlf=true clone --branch arena/dff19152-tofel-house-erp file:///<repo> <dir>
    git -c core.autocrlf=true -c core.eol=crlf clone --branch arena/dff19152-tofel-house-erp file:///<repo> <dir>
    git ls-files --eol

Result, same for both configurations:

| Class | Count |
|---|---|
| `w/lf` text files | 419 |
| `w/crlf` files (all seven are `product/windows/*.cmd`, which `.gitattributes` requires as CRLF) | 7 |
| files with CR outside the `.cmd` exception | **0** |

`product/perf_baseline.py`, `product/activate.py`, `product/app.Dockerfile`, and `.dockerignore` are all `w/lf`. That is the Issue #12 symptom, which is now absent from a fresh checkout.

## Full suite on that checkout

- `python -m unittest discover -s tests -t .` on the fresh `core.autocrlf=true` clone: **1363 tests, OK**.
- `ruff check .` (ruff 0.16.8, the CI version): **clean**.
- Venv: `pip install --only-binary=:all: --require-hashes -r tests/security/requirements-ci.txt`.

## Why an existing checkout can still show CRLF

Git attributes apply to future checkouts. They do not rewrite a worktree that was materialized before the attribute existed. This is stated in `.gitattributes`. The packaging contract covers that case in three places:

1. `product/windows/Normalize Product Sources.ps1` is run by `Install TOEFL House ERP.cmd` and `Repair TOEFL House ERP.cmd` before any build. Its file list comes from the Dockerfile `COPY` sources, plus `.gitattributes`, `.dockerignore`, `product/app.Dockerfile`, and `product/docker-compose.yml`. `product/perf_baseline.py` is a `COPY` source (`app.Dockerfile` line 118).
2. `app.Dockerfile` runs a build-time check that the copied text sources contain no CR bytes.
3. `tests/foundation/test_product_packaging.py` checks the normalizer wiring (`test_existing_worktree_normalizer_is_wired_before_build_and_repair`) and that the Dockerfile copy sources are CR-free (`test_dockerfile_copy_sources_are_cr_free`).

The PowerShell normalizer itself was **not executed** here (PowerShell is not available in the sandbox). Its behaviour is covered only by the static wiring tests.

## Local repository state repaired during this check (not a product defect)

When this check started, the local session branch in the working repository pointed at `7c847da` (`main`), and the index was at `main`. The worktree itself matched the remote session tip exactly: 502 of 502 tracked blobs matched `origin/arena/dff19152-tofel-house-erp` (`178a467`), with no missing and no extra files. The repair was `git reset --mixed origin/arena/dff19152-tofel-house-erp`, which moves the branch pointer and index and keeps the worktree. Nothing was discarded. Afterwards `git status` was clean and HEAD matched the remote. A tar of the pre-repair worktree was kept in scratch space.

## What this does not close

- Docker Compose, the image build, and the runtime health checks for web, socketio, worker, and scheduler.
- Owner-run Windows lifecycle (install, repair, reboot, interrupted recovery).
- Configuration-plane runtime wiring.

Issue #12 therefore remains open.
