# Frontend candidate review: measured verdict, 2026-09-25

Dated verdict record. History is not rewritten; a later re-measurement is a
new dated record.

Run `36114770675` at commit `8918403`, on the active validation branch.
Published evidence: check run "Foundation frontend candidate evidence",
report SHA-256 `587f6e54a669fb40e190b53992e42f828c337051de531bf32f598b0cdc5b9dbd`
(verified against the decoded payload).

## 1. Why this was previously unreadable

The comparison wrote its diagnosis only to `result.json` inside an artifact
that EOFs from the review environment, and printed nothing to the step log.
Twelve consecutive runs therefore failed with `Process completed with exit
code 1` and no recorded cause. See
[`hosted-step-diagnostics-2026-09-25.md`](hosted-step-diagnostics-2026-09-25.md).

## 2. Measured result

| | baseline | candidate |
|---|---|---|
| npm advisory entries | 57 | 23 |
| dependency constraint issues | 3 | 0 |

- Advisories removed: **35**
- Advisories introduced: **1**
- Application source unchanged between profiles: **true**
- `frappe_ui` source unchanged between profiles: **true**
- Production pins changed: **false** (by construction)

The candidate achieves its stated objective: all three dependency constraint
issues resolve, and advisory count falls by 60%.

## 3. What remains, and why

The 23 residual advisories span six packages. Five of the six are documented,
reasoned exclusions in
`docs/engineering/evidence/phase-2/frontend-resolution-proposal.json`:

| package | entries | documented reason |
|---|---|---|
| `vite` | 15 | **not documented as an exclusion** |
| `showdown` | 3 | no patched release; maintained parser/editor migration needed |
| `rollup` | 2 | 2.80.0 violates Vite 2.9.x upper bound `<2.78.0`; retained rather than forced |
| `esbuild` | 1 | 0.25.x outside Vite 2.9.x `^0.14.27` |
| `@tiptap/core` | 1 | 3.30.4 requires matching pm/editor ecosystem; no isolated override |
| `@tiptap/extension-link` | 1 | peers require core/pm `^2.7.0`, unlike locked 2.2.3 |

`vite` carries the large majority and is **not** covered by any recorded
exclusion, so the recorded engineering rationale does not currently account
for it. This is the gap between the proposal's stated reasoning and the
measured residual.

## 4. The introduced advisory

The candidate removes 35 advisories and introduces one:

`https://github.com/advisories/GHSA-93m4-6634-74q7` — `vite`, moderate.

Both profiles carry 15 `vite` advisories; the candidate pin (2.9.18) swaps one
`vite` advisory for another rather than clearing the set. Severity mix in the
candidate's `vite` set: 2 high, 11 moderate, 2 low.

## 5. Disposition

**Not adopted; gate remains red; nothing weakened.**

`docs/engineering/RELEASE-GAP-MAP.md` §1.5 records that this candidate review
fails and the candidate is not adopted, that no credible official candidate can
pass this gate yet, and that the gate "was not weakened, waived or
reinterpreted". The red status is therefore the intended record of a verified
rejection, not an unresolved defect, and the job was deliberately left red.

Two facts in this record are decision-relevant for the Owner and were not
previously written down anywhere reachable:

1. the residual is concentrated in `vite`, which the proposal's exclusion
   rationale does not cover;
2. the candidate introduces one advisory (`GHSA-93m4-6634-74q7`) while
   removing 35.

Clearing this gate requires an upstream major-version migration (Vite beyond
the 2.x line, plus the `showdown` parser/editor migration already recorded),
which changes production dependency inputs. That is an Owner adoption
decision, not an engineering fix, and no RPO/RTO, retention or acceptance
threshold is asserted here.
