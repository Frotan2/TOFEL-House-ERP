# Initial assessment policy setup — 31 October 2026

A real Owner setup blocker required each of the seven assessment facets to
create a separate, strictly later effective date. Completing a new policy could
therefore require artificial dates across a week.

The existing Course Owner-only `set_assessment_policy_version` POST command now
accepts optional `initial_facets`, containing all seven explicit facets, only
when the policy has no versions. It creates one audited initial version with
its native grading scale. It supplies no business defaults, cannot initialize
an already versioned policy, and keeps strict effective dates and history.
Calls omitting the argument preserve their original audit payload/replay hash.
The ordinary facet and carrier-version actions remain available.

Native criteria, scale grade codes, same-family level mapping and progression
targets, referenced assessment policies and approval roles are checked before
saving. Initial retake choices use the current vocabulary; old stored versions
retain their existing read semantics.

Windows MariaDB qualification on the isolated synthetic site passed one complete
version, same-key replay, existing-version refusal, foreign-family and unknown
grade refusal, non-Owner denial and legacy receipt-payload compatibility. Every
fixture record rolled back, with exact before/after table hashes equal. Source
helper evidence is retained privately under `acceptance/initial-assessment-*`;
it is not final installed-image/browser acceptance. The same genuine test now
runs in the canonical Native gate via `tools/native/initial_assessment.py`.

The existing Owner installation was not patched with this source helper. Apply
its approved assessment configuration only after the replacement image and
preserving update are qualified. Production remains NO-GO.


## Required native course and room setup

New levels now create a native integrated Course and the required Program Course
link inside the same audited Owner creation command. A new Program with no
Course could not schedule a lesson; existing Program identities and historical
curricula are not changed by this factory correction.

The Academic Setup desk now offers **Define teaching room**. The guarded Owner
command creates a new native Room with an explicit positive seating capacity
and change reason, without granting broad native write permissions. Room uses
an internal naming series; duplicate checks use its room_name, serialized under
the native Room DocType row lock. Duplicate names never overwrite capacity.
Native qualification verifies real Course links, room creation/replay, duplicate
preservation, invalid capacity refusal and non-Owner refusal, then rolls back
all fixture records. The capacity ceiling is an engineering typo guard, not a
new institute policy. Use the verified room-specific operating limit.
