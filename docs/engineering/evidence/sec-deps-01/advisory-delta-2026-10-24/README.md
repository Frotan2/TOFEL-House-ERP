# SEC-DEPS-01 advisory delta — 2026-10-24

## GHSA-xmj3-9gf7-h52w: setuptools Windows-only wheel installation path

The pinned Payments application requires `setuptools==80.9.0`. This version
matches the public advisory, whose vulnerable code path is **native Windows**
`setuptools.wheel.Wheel.install_as_egg` acting on malicious
`.dist-info/namespace_packages.txt` metadata. An attacker may influence a
path used for creating a fixed-content `__init__.py` outside the requested
destination; the attacker cannot choose its contents.

**The TOEFL House shipped customer appliance does not run that code on Windows.**
The application's Python runtime executes inside Docker's Linux container,
built from `python:3.14.7-slim-bookworm`; the customer's native Windows side
runs the allowlisted VBS, PowerShell and CMD launchers and Docker commands,
not a Windows Python interpreter or setuptools wheel installer. The host CI
for the Foundation inventory runs on `ubuntu-24.04`. Scope is limited to
the *customer product's installed application*, not arbitrary third-party
software that might independently be installed on an owner's Windows PC.

This is a package- and advisory-specific `NOT_REACHABLE` assessment, **not
an assertion that setuptools 80.9.0 is globally secure**. An attempted
upgrade to setuptools 84.1.0 violated the pinned Payments requirement and
failed the real `python-dependency-check` in run
[40076515818](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40076515818).
Run [40077009661](https://github.com/Frotan2/TOFEL-House-ERP/actions/runs/40077009661)
reached the hosted advisory scanner after compatible Python dependency checks
and reported only this setuptools finding and seven npm findings.

The regression `tests/security/test_setuptools_windows_boundary_2026_10_24.py`
must fail if a Windows native Python payload enters the customer package or
the Docker base ceases to be Linux. Reassess this disposition immediately if
the product ever ships a native Windows Python runtime, installs Python wheels
outside Docker, changes the OS for the provider/hosted runtime, or adds
host-side setuptools use.

Other SEC-DEPS-01 findings remain open. No production release or backup/recovery
authorization is implied by this narrow assessment.

## Sources

- [GitHub Security Advisory](https://github.com/advisories/GHSA-xmj3-9gf7-h52w)
- [Issue #38](https://github.com/Frotan2/TOFEL-House-ERP/issues/38)
- `product/app.Dockerfile`, `tools/release/create_customer_package.py`,
  `product/windows/Install TOEFL House ERP.cmd`, and
  `.github/workflows/foundation-runtime.yml`
