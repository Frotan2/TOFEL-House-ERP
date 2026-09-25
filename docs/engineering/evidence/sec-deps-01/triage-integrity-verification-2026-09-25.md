# SEC-DEPS-01 triage integrity verification

Date: 2026-09-25. Read-only audit; no value was changed.

## Why this was checked

The Foundation runtime run `36114770663` reports
`stack_dependency_audit.status: "pass"` while listing real OSV findings
(GHSA/PYSEC records against `pdfkit` 1.0.0, `pypdf` 6.15.0 and others). On its
face that reads like a gate that stopped gating, so the mechanism was traced
end to end.

## Finding: the pass is triage-based and fail-closed

`tools/foundation/audit_stack.py:180` records the change in basis:
"status now depends on triage, not raw counts". The verdict is
`advisory_triage.overall_status`, which returns `"pass"` only when **no
finding is untriaged and no finding is open**.

`triage_python` and `triage_npm` both fail closed:

* a finding with no triage record gets `disposition = "REGRESSION"`,
  `pass = False`, and is appended to `untriaged`, which forces
  `overall_status` to `"fail"`;
* only dispositions in `CLOSED_DISPOSITIONS` (`MITIGATED`, `NOT_REACHABLE`,
  `BUILD_ONLY`, `DEV_ONLY`, `INSTALL_ONLY`, `BROWSER_SELF_DENIAL`) count as
  closed;
* `OWNER_DECISION_REQUIRED` and `BLOCKED` are in `OPEN_DISPOSITIONS` and stay
  failures.

So a newly disclosed advisory, or one whose triage lapses, turns the audit red
rather than passing silently. `tests/security/test_advisory_triage.py` pins
both directions: `test_a_brand_new_advisory_is_a_regression` drives a fabricated
critical advisory through `triage_npm` and asserts `REGRESSION` and
`overall_status == "fail"`; `test_known_advisory_carries_evidence` asserts a
closed finding (`ws` / `GHSA-3h5v-q93c-6h6q`, `MITIGATED`) carries
`runtime_disposition_evidence`. Five tests, passing.

The per-finding analysis backing the dispositions is
[`per-finding-remediation-analysis-2026-09-23.json`](per-finding-remediation-analysis-2026-09-23.json):
102 advisory matches across 40 packages, classified by reachability, with the
official upgrade path verified by parsing `yarn.lock` at each tagged release.

**Conclusion: the `pass` is earned, not defaulted. Nothing was weakened.**

## The apparent contradiction, and why it must not be "fixed"

`d8_validate.py` emits `"sec_deps": "UPSTREAM-BLOCKED / REJECT"`, which looks
inconsistent with a passing dependency audit. It is not a derivation from
that audit — it is a pinned release posture that the validator enforces:

```python
if matrix.get("security_dependency_state") != "UPSTREAM-BLOCKED / REJECT":
    raise ContractError("SEC-DEPS-01 must remain UPSTREAM-BLOCKED / REJECT")
```

The distinction is deliberate and load-bearing:

* the **stack audit** answers a technical question — is every finding triaged
  and closed by mitigation or by proof of non-reachability? It passes.
* **SEC-DEPS-01 as a release gate** answers whether the resolved upstream
  dependency set is acceptable. It remains REJECT, because clearing it needs
  an upstream major-version migration and owner decisions, not a triage
  disposition.

Wiring `sec_deps` to the audit result would silently flip the release posture
from REJECT to accepted on the strength of a non-reachability argument, which
is precisely the reinterpretation `docs/engineering/RELEASE-GAP-MAP.md` §1.5
forbids ("This gate was not weakened, waived or reinterpreted").

**Do not make `sec_deps` follow the audit.**

## Verification method

Code read only; no dependency, lockfile or supported-version boundary was
modified, and no disposition was added or altered.
