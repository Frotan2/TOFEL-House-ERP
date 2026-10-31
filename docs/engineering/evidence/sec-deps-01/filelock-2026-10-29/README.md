# SEC-DEPS-01 — filelock fixed-version overlay (2026-10-29)

**Status: remediation committed, runtime qualification PENDING.** This record is source and external advisory evidence, not a claim that a rebuilt product passed hosted or Owner acceptance. The review and mitigation were prompted by actual hosted Foundation job [40801322291](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40801322291) on `ab7a0209b855b86e1f4d2f4502d8d06c51d0afb1`.

## Precise CI failure

The Foundation job completed site provisioning, restore and multiple browser/security probes, then `hosted-full-stack-dependency-audit` failed with:

```
STACK-ADVISORY-UNTRIAGED (matches=2; full set):
py:filelock@3.20.3 GHSA-69hj-f68j-2879,
py:filelock@3.20.3 GHSA-8mx5-7m5m-r77g
```

The advisories are not treated as waived, unreachable, accepted, or false positives.

- [GHSA-69hj-f68j-2879](https://github.com/tox-dev/filelock/security/advisories/GHSA-69hj-f68j-2879): Unix lock-path file truncation/permission alteration. The upstream advisory states affected `<=4.2.0`, fixed in `4.2.1`.
- [GHSA-8mx5-7m5m-r77g](https://github.com/tox-dev/filelock/security/advisories/GHSA-8mx5-7m5m-r77g): Windows lock-file ACL/mode weakness. Affected releases also include the previous 3.x pin; upstream fixed in `4.2.1`.
- [PyPI filelock 4.2.4](https://pypi.org/project/filelock/4.2.4/) confirms 2026-10-19 publication, verified provenance, and Python `>=3.11`.

## Code changes (all same release candidate)

- `tools/foundation/secure_frappe_python.py`: the immutable SHA-256-checked Frappe source overlay now replaces the single exact `filelock~=3.20.1` declaration with `filelock~=4.2.4`. This is necessary because the pinned Frappe source otherwise still requires a **3.x** release; merely installing filelock 4.x would make `pip check` fail. The overlay refuses upstream SHA drift, duplicate anchors, or unreviewed edits and verifies installed `filelock==4.2.4`.
- `tools/native/run_native.py`, `tools/foundation/runtime_install.py`, `product/app.Dockerfile`: all three paths install the **same exact 4.2.4** release into the isolated application bench venv and refresh the modified Frappe package metadata before checks.
- `tests/security/test_python_advisory_pins_2026_10_24.py` and `tests/security/test_frappe_python_security_2026_10_22.py`: pin parity, exact reviewed metadata rewrite, required runtime versions and all three install paths are asserted by tests.

This is a *major* package-version change, scoped to the application Python virtual environment and guarded by Frappe source hashes. No Frappe/ERPNext/Education/HRMS source commit is changed; no old advisory baseline is silently rewritten; advisory scanning remains fail-closed for any other findings.

## Qualification required before calling this fixed in the product

1. Run the owned Python/Node suite including both modified security regression modules.
2. Run complete disposable database-backed Native lifecycle, including `uv pip check`, Frappe native document/permission and financial tests, restart and migrations.
3. Run the complete Foundation security/browser workflow and independently confirm `hosted-full-stack-dependency-audit` no longer reports either `filelock` advisory, while all other advisory gates remain unchanged.
4. Run Product Image and Windows Package Smoke on the **same exact candidate code** and independently inspect the package's installed filelock version, Frappe dependency consistency, source and image hashes.
5. Verify no runtime API regression in applications using `FileLock` despite the major package uplift. A green build alone is not full functional evidence.

Keep **PRODUCTION REJECT / TEST PACKAGE — NO REAL DATA** until those gates, real Owner Windows recovery and explicit acceptance pass.
