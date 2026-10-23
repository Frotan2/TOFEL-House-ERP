# Owner Cockpit Frappe Page asset path incident — 2026-10-23

**Observed on real Owner Windows:** authenticated `/app/th-owner-cockpit`
caused `FileNotFoundError: apps/toefl_house/toefl_house/operations/page/th_owner_cockpit`
inside `frappe.core.doctype.page.page.Page.load_assets()`. The Home/Desk
screen and login worked; neither proves all role desks function.

**Root cause:** all eight role-desk source directories/files had hyphenated
names, while Frappe uses `scrub(Page.name)` (underscores) for its on-disk
directory, script, CSS and HTML lookup. The Page URL/name in JSON **must stay
hyphenated**, and the security-gated `page_js` hook must continue to key
on the hyphenated Page name.

**Fix:** rename exactly eight directories and their JSON filenames to
underscore-based paths without changing the Page records, roles, routes, hook
registry, projection permissions or data. No customer data migration or
reset is part of this fix.

**Why CI missed it:** prior native checks verified role-desk **endpoints**
but never called `frappe.desk.desk_page.get` to load assets for the eight
role desks. Add hosted native Page.get tests for each real audience, plus a
full-tree contract ensuring all standard Page JSON source paths match
`scrub(name)`. Both must pass on an actual assembled product image.

**Deployment:** a GitHub desktop source update alone does **not** replace the
running Docker image. Owner's machine had approximately 11.8 GiB available
during preflight, and real backup/recovery is in HOLD. **Do not** delete
the site's files, named database volume, credentials or existing installation,
or launch an unapproved destructive rebuild just to test the new page paths.
A supported space/backup/rebuild/migration/rollback plan and actual Owner
manual re-test are required. No assertion of production readiness.
