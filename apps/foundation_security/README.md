# Foundation Security (qualification candidate)

Generic, reversible Frappe security extension; **not approved for production**.
No DocTypes, custom fields, Student/Customer duplicates, or TOEFL functionality.

Why native configuration alone is insufficient:
- Frappe permits role-based reads when User Permission rows disappear.
- The tested Education website session renders a missing CSRF token until one is initialized.

Supported hooks validate native Student/Customer scope on login and every authenticated
HTTP request and initialize the native session CSRF token. Missing/expanded rules,
ambiguous links, unsafe settings and existing per-user document shares deny access.
Administrator remains a trusted configuration authority. Guardian/staff combinations and
realtime authorization remain outside this initial guard's acceptance proof.

Required native settings: disable public signup; skip automatic Student user creation;
strict User Permissions; disable document sharing; site `disable_website_cache=1` to
prevent caching a session-specific token in Education's rendered HTML. This disables
website HTML caching, not Redis, workers or their cache functionality.

Provision with the Student role inactive; establish exact native Student/Customer rules,
then activate. Users may not remove or widen their own User Permission rules. No
provisioning UI or institution-specific provisioning service is implemented here.

The validation workflow installs with supported Bench `get-app --soft-link --skip-assets`
and `install-app`. Removal is the supported `uninstall-app foundation_security`; doing so
removes these guards and invalidates this security qualification. It is not a secure rollback.

## 0.2 qualification candidate (not production approval)

Guardian requests now derive exact Guardian/Student/Customer scopes from native links,
including multiple children. Missing, expanded or stale scopes and inherited shares
fail closed at login and every HTTP request. Mixed Student/Guardian roles must satisfy
both boundaries; broader mixed-role usability remains unqualified.

The app's Frappe realtime entry point replaces unchecked subscriptions and wraps the
pinned Socket.IO in-process adapter's broadcast boundary. Each delivery rechecks the
native HTTP session and document permission or exact native RQ job site/user ownership.
No identity or task ownership table is introduced. Unknown/broad/combined rooms are
denied, not inferred safe. Namespace broadcasts target only explicitly checked socket
IDs, preventing a new membership from racing into an authorized packet.

This deliberately disables broad site/website/doctype announcements, unchecked task
subscriptions and open-in-editor. There are availability/UX costs; this is not a claim
of transparent compatibility with every upstream realtime feature. Cluster adapters,
acknowledged broadcasts and new upstream app handlers need separate qualification.
Only the pinned Frappe/Socket.IO contract is tested. HTTP/proxy origin protection must
also be qualified before public exposure; post-auth resource checks do not replace it.
