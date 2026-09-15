"""Authenticated POST commands; no candidate, file or result endpoint."""
import json
import secrets
import frappe
from toefl_house import allocation, scoring
from frappe.utils import get_datetime
from toefl_house.policy import (attempt_deadline, canonical, deadline_reached, digest,
                                project_form, request_digest, validate_blueprint,
                                validate_config_code, validate_content, validate_family,
                                validate_policy, validate_request_key)
from toefl_house.security import KIND_ROLES, authorize, command
from toefl_house.transactions import run_with_retry

ITEM = "TH Placement Item Revision"
KEY = "TH Placement Key Revision"
OP = "TH Placement Operation"
AUDIT = "TH Placement Audit Event"
BLUEPRINT = "TH Placement Blueprint Revision"
POLICY = "TH Placement Policy Revision"
CASE = "TH Placement Case"
ATTEMPT = "TH Placement Attempt"
MANIFEST = "TH Placement Form Manifest"
EXPOSURE = "TH Placement Exposure"
GUARD = "TH Placement Allocation Guard"
RESPONSE = "TH Placement Response"
SCORE = "TH Placement Score"

# Synthetic-only purpose marker; other purposes are a later activation config,
# not something this increment accepts or invents.
SYNTHETIC_PURPOSE = "synthetic-placement"

CONFIG = {
    "blueprint": (BLUEPRINT, validate_blueprint),
    "policy": (POLICY, validate_policy),
}


def _content(value):
    if isinstance(value, str):
        if len(value) > 20000:
            raise frappe.ValidationError("Content exceeds request limit")
        try:
            value = json.loads(value)
        except (ValueError, TypeError) as exc:
            raise frappe.ValidationError("Invalid JSON content") from exc
    try:
        return validate_content(value)
    except (ValueError, TypeError) as exc:
        raise frappe.ValidationError(str(exc)) from exc


def _execute(kind, request_key, payload, work):
    return run_with_retry(lambda: _execute_once(kind, request_key, payload, work))


def _execute_once(kind, request_key, payload, work):
    actor = authorize(KIND_ROLES[kind])
    try:
        validate_request_key(request_key)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc
    op_name = digest([kind, request_key])
    try:
        input_hash = request_digest(payload, frappe.conf.get("encryption_key"))
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc

    def existing():
        row = frappe.db.get_value(OP, op_name, ["actor", "input_hash", "status", "result_json"], as_dict=True, for_update=True)
        if not row or row.actor != actor or row.input_hash != input_hash or row.status != "Complete":
            raise frappe.ValidationError("Idempotency key conflicts with an existing request")
        return json.loads(row.result_json)

    if frappe.db.exists(OP, op_name):
        return existing()
    with command(kind, actor):
        op = frappe.get_doc(dict(doctype=OP, name=op_name, kind=kind, actor=actor,
                                input_hash=input_hash, status="Applying", synthetic=1))
        try:
            op.insert(ignore_permissions=True)
        except frappe.DuplicateEntryError:
            return existing()
        result, event = work(actor)
        frappe.get_doc(dict(doctype=AUDIT, actor=actor, operation=op.name, synthetic=1,
                            action=kind, **event)).insert(ignore_permissions=True)
        op.status = "Complete"
        op.result_json = canonical(result)
        op.save(ignore_permissions=True)
        # Do not commit here: receipt + key + item + audit are one request transaction.
        return result


def _apply(item, content):
    for field in ("skill", "difficulty", "question_type", "prompt"):
        item.set(field, content[field])
    item.options_json = canonical(content["options"])
    item.content_hash = digest({k: v for k, v in content.items() if k != "answer"})


def _new_key(item_name, version, answer):
    return frappe.get_doc(dict(doctype=KEY, item_revision=item_name, key_version=version, answer=answer,
                               content_hash=digest([item_name, version, answer]), synthetic=1)).insert(ignore_permissions=True)


def _result(item):
    return {"name": item.name, "version": item.version, "status": item.status, "content_hash": item.content_hash}


def _locked_item(name, expected_version):
    if not isinstance(name, str) or not name or len(name) > 140 or type(expected_version) is not int:
        raise frappe.ValidationError("Item name and integer expected_version required")
    item = frappe.get_doc(ITEM, name, for_update=True)
    if item.status != "Draft" or item.version != expected_version:
        raise frappe.ValidationError("Stale revision or already published item")
    return item


@frappe.whitelist(methods=["POST"])
def create_draft(request_key, family, revision, content):
    content = _content(content)
    try:
        validate_family(family, revision)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc

    def work(actor):
        if not family.startswith("SYN-" + digest(actor)[:12].upper() + "-"):
            raise frappe.PermissionError("Synthetic family namespace must belong to the author")
        item = frappe.get_doc(dict(doctype=ITEM, family=family, revision=revision, version=1,
                                  status="Draft", synthetic=1))
        _apply(item, content)
        item.insert(ignore_permissions=True)
        key = _new_key(item.name, item.version, content["answer"])
        item.key_revision = key.name
        item.save(ignore_permissions=True)
        return _result(item), dict(item_revision=item.name, after_hash=item.content_hash, after_key=key.name)

    return _execute("create_draft", request_key, {"family": family, "revision": revision, "content": content}, work)


@frappe.whitelist(methods=["POST"])
def revise_draft(request_key, item_name, expected_version, content):
    content = _content(content)

    def work(actor):
        item = _locked_item(item_name, expected_version)
        if item.owner != actor:
            raise frappe.PermissionError("Only the author may revise a draft")
        before = item.content_hash
        before_key = item.key_revision
        item.version += 1
        key = _new_key(item.name, item.version, content["answer"])
        item.key_revision = key.name
        _apply(item, content)
        item.save(ignore_permissions=True)
        return _result(item), dict(item_revision=item.name, before_hash=before, after_hash=item.content_hash, before_key=before_key, after_key=key.name)

    return _execute("revise_draft", request_key, {"item": item_name, "version": expected_version, "content": content}, work)


@frappe.whitelist(methods=["POST"])
def publish(request_key, item_name, expected_version):
    def work(actor):
        item = _locked_item(item_name, expected_version)
        if item.owner == actor:
            raise frappe.PermissionError("Author cannot publish their own revision")
        key = frappe.get_doc(KEY, item.key_revision)
        content = {field: item.get(field) for field in ("skill", "difficulty", "question_type", "prompt")}
        content.update(options=json.loads(item.options_json), answer=key.answer)
        validated = _content(content)
        if (digest({k: v for k, v in validated.items() if k != "answer"}) != item.content_hash
                or key.item_revision != item.name
                or key.content_hash != digest([item.name, key.key_version, key.answer])):
            raise frappe.ValidationError("Content/key integrity mismatch")
        item.status = "Published"
        item.version += 1
        item.save(ignore_permissions=True)
        return _result(item), dict(item_revision=item.name, before_hash=item.content_hash, after_hash=item.content_hash, before_key=key.name, after_key=key.name)

    return _execute("publish", request_key, {"item": item_name, "version": expected_version}, work)


def _config(config):
    try:
        return CONFIG[config]
    except (KeyError, TypeError):
        raise frappe.ValidationError("Unsupported configuration type")


def _definition(config, definition):
    _, validator = _config(config)
    if isinstance(definition, str):
        if len(definition) > 20000:
            raise frappe.ValidationError("Definition exceeds request limit")
        try:
            definition = json.loads(definition)
        except (ValueError, TypeError) as exc:
            raise frappe.ValidationError("Invalid JSON definition") from exc
    try:
        return validator(definition)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc


def _config_result(doc):
    return {"name": doc.name, "config": "blueprint" if doc.doctype == BLUEPRINT else "policy",
            "version": doc.version, "status": doc.status, "content_hash": doc.content_hash}


def _locked_config(doctype, name, expected_version):
    if not isinstance(name, str) or not name or len(name) > 140 or type(expected_version) is not int:
        raise frappe.ValidationError("Config name and integer expected_version required")
    doc = frappe.get_doc(doctype, name, for_update=True)
    if doc.version != expected_version:
        raise frappe.ValidationError("Stale configuration revision")
    return doc


@frappe.whitelist(methods=["POST"])
def create_draft_config(request_key, config, code, revision, definition):
    doctype, _ = _config(config)
    definition = _definition(config, definition)
    try:
        validate_config_code(code, revision)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc

    def work(actor):
        doc = frappe.get_doc(dict(doctype=doctype, code=code, revision=revision, version=1,
                                  status="Draft", synthetic=1,
                                  definition_json=canonical(definition), content_hash=digest(definition)))
        doc.insert(ignore_permissions=True)
        return _config_result(doc), dict(target=doc.name, after_hash=doc.content_hash)

    return _execute(f"create_{config}", request_key,
                    {"config": config, "code": code, "revision": revision, "definition": definition}, work)


@frappe.whitelist(methods=["POST"])
def revise_draft_config(request_key, config, name, expected_version, definition):
    doctype, _ = _config(config)
    definition = _definition(config, definition)

    def work(actor):
        doc = _locked_config(doctype, name, expected_version)
        if doc.status != "Draft":
            raise frappe.ValidationError("Only configuration drafts can be revised")
        if doc.owner != actor:
            raise frappe.PermissionError("Only the author may revise a configuration draft")
        before = doc.content_hash
        doc.definition_json = canonical(definition)
        doc.content_hash = digest(definition)
        doc.version += 1
        doc.save(ignore_permissions=True)
        return _config_result(doc), dict(target=doc.name, before_hash=before, after_hash=doc.content_hash)

    return _execute(f"revise_{config}", request_key,
                    {"config": config, "item": name, "version": expected_version, "definition": definition}, work)


@frappe.whitelist(methods=["POST"])
def review_config(request_key, config, name, expected_version):
    doctype, _ = _config(config)

    def work(actor):
        doc = _locked_config(doctype, name, expected_version)
        if doc.status != "Draft":
            raise frappe.ValidationError("Only configuration drafts can be reviewed")
        if doc.owner == actor:
            raise frappe.PermissionError("Author cannot review their own draft")
        doc.status = "Reviewed"
        doc.review_actor = actor
        doc.version += 1
        doc.save(ignore_permissions=True)
        return _config_result(doc), dict(target=doc.name, before_hash=doc.content_hash, after_hash=doc.content_hash)

    return _execute(f"review_{config}", request_key,
                    {"config": config, "item": name, "version": expected_version}, work)


@frappe.whitelist(methods=["POST"])
def publish_config(request_key, config, name, expected_version):
    doctype, validator = _config(config)

    def work(actor):
        doc = _locked_config(doctype, name, expected_version)
        if doc.status != "Reviewed":
            raise frappe.ValidationError("Only reviewed configuration can be published")
        if doc.owner == actor:
            raise frappe.PermissionError("Author cannot publish their own revision")
        if not doc.review_actor:
            raise frappe.ValidationError("A recorded independent review is required before publication")
        if doc.review_actor == actor:
            raise frappe.PermissionError("Publication must be independent of the recorded reviewer")
        stored = json.loads(doc.definition_json)
        validator(stored)
        if digest(stored) != doc.content_hash:
            raise frappe.ValidationError("Stored definition integrity mismatch")
        doc.status = "Published"
        doc.version += 1
        doc.save(ignore_permissions=True)
        return _config_result(doc), dict(target=doc.name, before_hash=doc.content_hash, after_hash=doc.content_hash)

    return _execute(f"publish_{config}", request_key,
                    {"config": config, "item": name, "version": expected_version}, work)


@frappe.whitelist(methods=["POST"])
def retire_config(request_key, config, name, expected_version):
    doctype, _ = _config(config)

    def work(actor):
        doc = _locked_config(doctype, name, expected_version)
        if doc.status != "Published":
            raise frappe.ValidationError("Only published configuration can be retired")
        if doc.owner == actor:
            raise frappe.PermissionError("Author cannot retire their own configuration")
        doc.status = "Retired"
        doc.version += 1
        doc.save(ignore_permissions=True)
        return _config_result(doc), dict(target=doc.name, before_hash=doc.content_hash, after_hash=doc.content_hash)

    return _execute(f"retire_{config}", request_key,
                    {"config": config, "item": name, "version": expected_version}, work)


# --- Increment 3: case identity and blueprint allocation / form generation ---

def _locked_case(name):
    if not isinstance(name, str) or not name or len(name) > 140:
        raise frappe.ValidationError("Case name required")
    try:
        case = frappe.get_doc(CASE, name, for_update=True)
    except frappe.DoesNotExistError as exc:
        raise frappe.ValidationError("Case not found") from exc
    if case.status != "Open":
        raise frappe.ValidationError("Case is not open for allocation")
    return case


def _pinned_published(doctype, validator, name, expected_version, label):
    """Resolve a published configuration revision and re-verify its frozen
    meaning (status, expected version, definition validity, stored hash)."""
    if not isinstance(name, str) or not name or len(name) > 140 or type(expected_version) is not int:
        raise frappe.ValidationError(f"{label} name and integer expected_version required")
    try:
        doc = frappe.get_doc(doctype, name, for_update=True)
    except frappe.DoesNotExistError as exc:
        raise frappe.ValidationError(f"Missing {label} revision") from exc
    if doc.status != "Published":
        raise frappe.ValidationError(f"Only published {label} revisions can be allocated")
    if doc.version != expected_version:
        raise frappe.ValidationError("Stale configuration revision")
    stored = json.loads(doc.definition_json)
    validator(stored)
    if digest(stored) != doc.content_hash:
        raise frappe.ValidationError("Stored definition integrity mismatch")
    return doc, stored


@frappe.whitelist(methods=["POST"])
def create_case(request_key, subject, purpose=SYNTHETIC_PURPOSE):
    if not isinstance(subject, str) or not 3 <= len(subject) <= 140:
        raise frappe.ValidationError("Subject user reference required")
    if purpose != SYNTHETIC_PURPOSE:
        raise frappe.ValidationError("Unsupported purpose in this synthetic increment")

    def work(actor):
        if subject in ("Administrator", "Guest") or not frappe.db.get_value("User", subject, "enabled"):
            raise frappe.ValidationError("Subject must be an enabled non-privileged native user")
        if frappe.db.exists(CASE, {"subject": subject}):
            raise frappe.ValidationError("Subject already has a case in this increment")
        case = frappe.get_doc(dict(doctype=CASE, subject=subject, purpose=purpose,
                                   status="Open", synthetic=1))
        case.insert(ignore_permissions=True)
        return {"name": case.name, "subject": subject, "purpose": purpose, "status": case.status}, \
               dict(target=case.name, after_hash=digest([subject, purpose]))

    return _execute("create_case", request_key, {"subject": subject, "purpose": purpose}, work)


@frappe.whitelist(methods=["POST"])
def allocate_attempt(request_key, case, blueprint, blueprint_version, policy, policy_version):
    def work(actor):
        # Canonical lock order (spec 8): case -> allocation guard -> family
        # exposure -> result rows. The per-key operation receipt inserted by
        # _execute_once is private to this request and never a contention
        # point, so it precedes the business locks.
        # HTTP JSON keys are the public contract (case/blueprint/policy); the
        # in-process suite calls this positionally.
        case_doc = _locked_case(case)
        subject = case_doc.subject
        bp, bp_def = _pinned_published(BLUEPRINT, validate_blueprint, blueprint, blueprint_version, "blueprint")
        pol, _pol_def = _pinned_published(POLICY, validate_policy, policy, policy_version, "policy")
        sections = [dict(id=s["id"], skill=s["skill"], item_count=s["item_count"])
                    for s in bp_def["sections"]]
        # Blueprint/pool revision allocation guard (spec 5.3): serializes a
        # pool's allocation for correctness.
        guard_name = "AG-" + digest([BLUEPRINT, bp.name])[:32]
        if not frappe.db.exists(GUARD, guard_name):
            frappe.get_doc(dict(doctype=GUARD, name=guard_name, blueprint=bp.name,
                                synthetic=1)).insert(ignore_permissions=True)
        frappe.get_doc(GUARD, guard_name, for_update=True)
        # Reuse control: a family once exposed to this subject is never
        # allocated to that subject again (new item IDs do not reset family
        # history). The pool shrinks site-wide as families get exposed.
        exposed = {row.family for row in
                   frappe.get_all(EXPOSURE, filters={"subject": subject}, fields=["family"])}
        rows = frappe.get_all(ITEM, filters={"status": "Published"},
                              fields=["name", "family", "skill", "difficulty",
                                      "question_type", "options_json"])
        skill_set = {s["skill"] for s in sections}
        solver_items = []
        for row in rows:
            if row.skill not in skill_set or row.family in exposed:
                continue
            solver_items.append(dict(name=row.name, family=row.family, skill=row.skill,
                                     difficulty=row.difficulty, question_type=row.question_type,
                                     options=[o["id"] for o in json.loads(row.options_json)]))
        exposure_counts = {row.family: row.c for row in frappe.db.sql(
            "select family, count(*) as c from `tabTH Placement Exposure` group by family",
            as_dict=True)}
        # Server-generated cryptographic randomness; never client input.
        seed = secrets.token_hex(32)
        try:
            plan = allocation.allocate(sections, solver_items, seed, exposure_counts)
        except ValueError as exc:
            raise frappe.ValidationError(f"Allocation unavailable: {exc}") from exc
        # Lock the selected families' exposure rows in canonical order and
        # recheck eligibility before reserving (spec 5.3).
        selected = sorted({item["family"] for item in plan["items"]})
        for family in selected:
            frappe.db.sql("select name from `tabTH Placement Exposure` where family = %s for update",
                          (family,))
        re_exposed = {row.family for row in
                      frappe.get_all(EXPOSURE, filters={"subject": subject}, fields=["family"])}
        if re_exposed & set(selected):
            raise frappe.ValidationError(
                "Allocation unavailable: pool changed during allocation; retry with a new key")
        ordinal = frappe.db.sql(
            "select coalesce(max(ordinal), 0) + 1 from `tabTH Placement Attempt` where case_name = %s for update",
            (case_doc.name,))[0][0]
        attempt = frappe.get_doc(dict(doctype=ATTEMPT, case_name=case_doc.name, ordinal=ordinal,
                                      subject=subject, blueprint=bp.name,
                                      blueprint_version=bp.version, blueprint_hash=bp.content_hash,
                                      policy=pol.name, policy_version=pol.version,
                                      policy_hash=pol.content_hash, mode=bp_def["mode"],
                                      status="Allocated", version=1, allocated_by=actor,
                                      synthetic=1))
        attempt.insert(ignore_permissions=True)
        # Exactly one manifest per attempt; frozen question manifest. The
        # time profile is the published blueprint's section minutes (this
        # increment's items carry no per-item duration or marks).
        form = dict(plan, attempt=attempt.name, case=case_doc.name, subject=subject,
                    blueprint=bp.name, blueprint_version=bp.version,
                    policy=pol.name, policy_version=pol.version,
                    sections=[dict(s) for s in bp_def["sections"]])
        form_hash = digest(form)
        manifest = frappe.get_doc(dict(doctype=MANIFEST, attempt=attempt.name,
                                       algorithm_version=plan["algorithm"], seed=seed,
                                       pool_digest=plan["pool_digest"],
                                       form_json=canonical(form), form_hash=form_hash,
                                       status="Committed", synthetic=1))
        manifest.insert(ignore_permissions=True)
        # Reserve exposure before the commit; unique (attempt, family, event).
        for item in plan["items"]:
            frappe.get_doc(dict(doctype=EXPOSURE, attempt=attempt.name,
                                family=item["family"], subject=subject,
                                event="Reserved", synthetic=1)).insert(ignore_permissions=True)
        return {"attempt": attempt.name, "ordinal": ordinal, "status": attempt.status,
                "mode": attempt.mode, "case": case_doc.name, "subject": subject,
                "blueprint": bp.name, "blueprint_version": bp.version,
                "policy": pol.name, "policy_version": pol.version,
                "manifest": manifest.name, "form_hash": form_hash,
                "item_count": len(plan["items"])}, \
               dict(target=attempt.name, after_hash=form_hash)

    return _execute("allocate_attempt", request_key,
                    {"case": case, "blueprint": blueprint,
                     "blueprint_version": blueprint_version,
                     "policy": policy, "policy_version": policy_version}, work)


# --- Increment 4: staff-supervised Digital verify / deliver / save / seal ---

def _now():
    return frappe.utils.now_datetime()


def _iso(value):
    return get_datetime(value).strftime("%Y-%m-%d %H:%M:%S")


def _locked_session(attempt_name, expected_version):
    """Lock case then attempt (spec 8). Missing pins fail closed as operator reasons."""
    if not isinstance(attempt_name, str) or not attempt_name or len(attempt_name) > 140 \
            or type(expected_version) is not int:
        raise frappe.ValidationError("Attempt name and integer expected_version required")
    case_name = frappe.db.get_value(ATTEMPT, attempt_name, "case_name")
    if not case_name:
        raise frappe.ValidationError("Attempt not found")
    frappe.get_doc(CASE, case_name, for_update=True)
    try:
        attempt = frappe.get_doc(ATTEMPT, attempt_name, for_update=True)
    except frappe.DoesNotExistError as exc:
        raise frappe.ValidationError("Attempt not found") from exc
    if attempt.version != expected_version:
        raise frappe.ValidationError("Stale attempt revision")
    return attempt


def _require_session_operator(actor, attempt):
    if actor == attempt.allocated_by:
        raise frappe.PermissionError("Allocator cannot operate the session")
    if attempt.mode != "Digital":
        raise frappe.ValidationError("Only digital delivery is implemented in this increment")


def _advance(attempt, status, **fields):
    attempt.status = status
    attempt.version += 1
    for field, value in fields.items():
        attempt.set(field, value)
    attempt.save(ignore_permissions=True)


def _manifest_form(attempt_name):
    # Invigilator has no DocType read on the seed-bearing manifest; the
    # command loads it through the database under command context.
    row = frappe.db.get_value(MANIFEST, {"attempt": attempt_name},
                              ["name", "form_json", "form_hash"], as_dict=True)
    if not row:
        raise frappe.ValidationError("Manifest not found")
    try:
        form = json.loads(row.form_json)
    except ValueError as exc:
        raise frappe.ValidationError("Manifest form_json must be valid JSON") from exc
    if row.form_hash != digest(form):
        raise frappe.ValidationError("Stored form integrity mismatch")
    return row, form


def _occurrence_options(form, occurrence):
    if type(occurrence) is not int or occurrence < 1:
        raise frappe.ValidationError("Occurrence must be a positive integer")
    entry = next((item for item in form["items"] if item.get("order") == occurrence), None)
    if entry is None:
        raise frappe.ValidationError("Unknown occurrence")
    if entry.get("question_type") == "True False":
        return entry, {"true", "false"}
    order = entry.get("option_order")
    if not isinstance(order, list):
        raise frappe.ValidationError("Single-choice option_order required")
    return entry, set(order)


def _response_revision(attempt_name, occurrence):
    return frappe.db.sql(
        "select coalesce(max(revision), 0) from `tabTH Placement Response` "
        "where attempt = %s and occurrence = %s for update",
        (attempt_name, occurrence))[0][0]


def _seal(attempt, reason):
    _, form = _manifest_form(attempt.name)
    missing_count = 0
    for entry in form["items"]:
        current = _response_revision(attempt.name, entry["order"])
        if current == 0:
            frappe.get_doc(dict(doctype=RESPONSE, attempt=attempt.name,
                                occurrence=entry["order"], revision=1,
                                option_id="", missing=1, synthetic=1)).insert(ignore_permissions=True)
            missing_count += 1
    sealed_at = _now()
    _advance(attempt, "Sealed", sealed_at=sealed_at, seal_reason=reason)
    result = {"attempt": attempt.name, "status": attempt.status, "version": attempt.version,
              "seal_reason": reason, "sealed_at": _iso(sealed_at), "missing_count": missing_count}
    return result, dict(target=attempt.name, after_hash=digest([attempt.name, "Sealed", reason]))


@frappe.whitelist(methods=["POST"])
def verify_attempt(request_key, attempt, expected_version):
    def work(actor):
        doc = _locked_session(attempt, expected_version)
        _require_session_operator(actor, doc)
        if doc.status != "Allocated":
            raise frappe.ValidationError("Attempt is not allocated for verification")
        verified_at = _now()
        _advance(doc, "Verified", verified_by=actor, verified_at=verified_at)
        result = {"attempt": doc.name, "status": doc.status, "version": doc.version,
                  "verified_by": actor, "verified_at": _iso(verified_at)}
        return result, dict(target=doc.name, after_hash=digest([doc.name, "Verified", actor]))

    return _execute("verify_attempt", request_key,
                    {"attempt": attempt, "expected_version": expected_version}, work)


@frappe.whitelist(methods=["POST"])
def deliver_attempt(request_key, attempt, expected_version):
    def work(actor):
        doc = _locked_session(attempt, expected_version)
        _require_session_operator(actor, doc)
        if doc.status != "Verified":
            raise frappe.ValidationError("Attempt is not verified for delivery")
        _, form = _manifest_form(doc.name)
        names = [entry["item"] for entry in form["items"]]
        rows = frappe.get_all(ITEM, filters={"name": ("in", names)},
                              fields=["name", "prompt", "question_type", "options_json", "status"],
                              ignore_permissions=True)
        catalog = {}
        for row in rows:
            if row.status != "Published":
                raise frappe.ValidationError("Allocated item is no longer published")
            catalog[row.name] = dict(prompt=row.prompt, question_type=row.question_type,
                                     options=json.loads(row.options_json))
        projection = project_form(form, catalog)
        projection["mode"] = doc.mode
        bp = frappe.db.get_value(BLUEPRINT, doc.blueprint,
                                 ["content_hash", "status", "definition_json"], as_dict=True)
        if not bp or bp.content_hash != doc.blueprint_hash or bp.status != "Published":
            raise frappe.ValidationError("Pinned blueprint is no longer valid")
        bp_def = json.loads(bp.definition_json)
        validate_blueprint(bp_def)
        started = _now()
        deadline = attempt_deadline(started, bp_def["total_minutes"])
        # Convert reservation to irreversible exposure before the projection
        # is returned (spec 5.5). Reserved rows remain; Delivered is a new event.
        for family in sorted({entry["family"] for entry in form["items"]}):
            frappe.get_doc(dict(doctype=EXPOSURE, attempt=doc.name, family=family,
                                subject=doc.subject, event="Delivered",
                                synthetic=1)).insert(ignore_permissions=True)
        _advance(doc, "In Progress", started_at=started, deadline_at=deadline)
        result = {"attempt": doc.name, "status": doc.status, "version": doc.version,
                  "started_at": _iso(started), "deadline_at": _iso(deadline),
                  "item_count": len(form["items"]), "projection": projection}
        return result, dict(target=doc.name,
                            after_hash=digest([doc.name, "Delivered", result["started_at"],
                                               result["deadline_at"]]))

    return _execute("deliver_attempt", request_key,
                    {"attempt": attempt, "expected_version": expected_version}, work)


@frappe.whitelist(methods=["POST"])
def save_response(request_key, attempt, expected_version, occurrence, expected_revision,
                  option_id="", missing=0):
    def work(actor):
        doc = _locked_session(attempt, expected_version)
        _require_session_operator(actor, doc)
        if doc.status != "In Progress":
            raise frappe.ValidationError("Attempt is not in progress")
        if deadline_reached(_now(), get_datetime(doc.deadline_at)):
            return _seal(doc, "Timeout")
        if type(occurrence) is not int or type(expected_revision) is not int \
                or type(missing) is not int:
            raise frappe.ValidationError("Occurrence, expected_revision and missing must be integers")
        if missing not in (0, 1) or expected_revision < 0:
            raise frappe.ValidationError("Invalid response revision or missing flag")
        stored_option = "" if option_id is None else option_id
        _, form = _manifest_form(doc.name)
        _, allowed = _occurrence_options(form, occurrence)
        if missing:
            if stored_option not in ("", None):
                raise frappe.ValidationError("Missing responses cannot carry an option")
            stored_option = ""
        else:
            if not isinstance(stored_option, str) or stored_option not in allowed:
                raise frappe.ValidationError("Unknown option id")
        current = _response_revision(doc.name, occurrence)
        if current != expected_revision:
            raise frappe.ValidationError("Stale response revision")
        revision = current + 1
        frappe.get_doc(dict(doctype=RESPONSE, attempt=doc.name, occurrence=occurrence,
                            revision=revision, option_id=stored_option, missing=missing,
                            synthetic=1)).insert(ignore_permissions=True)
        result = {"attempt": doc.name, "occurrence": occurrence, "revision": revision,
                  "option_id": stored_option, "missing": missing, "status": doc.status}
        return result, dict(target=doc.name,
                            after_hash=digest([doc.name, occurrence, revision, stored_option, missing]))

    return _execute("save_response", request_key,
                    {"attempt": attempt, "expected_version": expected_version,
                     "occurrence": occurrence, "expected_revision": expected_revision,
                     "option_id": option_id, "missing": missing}, work)


@frappe.whitelist(methods=["POST"])
def seal_attempt(request_key, attempt, expected_version, reason):
    def work(actor):
        doc = _locked_session(attempt, expected_version)
        _require_session_operator(actor, doc)
        if doc.status != "In Progress":
            raise frappe.ValidationError("Attempt is not in progress")
        if reason not in ("Submitted", "Timeout"):
            raise frappe.ValidationError("Unsupported seal reason")
        reached = deadline_reached(_now(), get_datetime(doc.deadline_at))
        if reason == "Timeout" and not reached:
            raise frappe.ValidationError("Timeout seal requires a reached deadline")
        seal_reason = "Timeout" if reached else reason
        return _seal(doc, seal_reason)

    return _execute("seal_attempt", request_key,
                    {"attempt": attempt, "expected_version": expected_version, "reason": reason}, work)


# --- Increment 5: objective scoring of sealed Digital attempts ---

def _latest_responses(attempt_name):
    rows = frappe.db.sql(
        "select occurrence, revision, option_id, missing from `tabTH Placement Response` "
        "where attempt = %s order by occurrence asc, revision asc",
        (attempt_name,), as_dict=True)
    latest = {}
    for row in rows:
        latest[int(row.occurrence)] = dict(
            option_id=row.option_id or "", missing=int(row.missing or 0),
            revision=int(row.revision))
    return latest


def _key_catalog(form):
    names = [entry["item"] for entry in form["items"]]
    rows = frappe.get_all(ITEM, filters={"name": ("in", names)},
                          fields=["name", "key_revision", "status"],
                          ignore_permissions=True)
    if len(rows) != len(set(names)):
        raise frappe.ValidationError("Allocated item is missing")
    catalog = {}
    for row in rows:
        if row.status != "Published":
            raise frappe.ValidationError("Allocated item is no longer published")
        key = frappe.db.get_value(KEY, row.key_revision,
                                  ["answer", "key_version", "content_hash", "item_revision"],
                                  as_dict=True)
        if not key or key.item_revision != row.name:
            raise frappe.ValidationError("Key integrity mismatch")
        if key.content_hash != digest([row.name, key.key_version, key.answer]):
            raise frappe.ValidationError("Key integrity mismatch")
        catalog[row.name] = dict(answer=key.answer, key_version=key.key_version,
                                 content_hash=key.content_hash)
    return catalog


@frappe.whitelist(methods=["POST"])
def score_attempt(request_key, attempt, expected_version):
    def work(actor):
        doc = _locked_session(attempt, expected_version)
        if doc.mode != "Digital":
            raise frappe.ValidationError("Only digital objective scoring is implemented in this increment")
        if doc.status != "Sealed":
            raise frappe.ValidationError("Attempt is not sealed for scoring")
        manifest, form = _manifest_form(doc.name)
        responses = _latest_responses(doc.name)
        catalog = _key_catalog(form)
        try:
            projection = scoring.score(form, responses, catalog)
        except ValueError as exc:
            raise frappe.ValidationError(str(exc)) from exc
        revision = 1
        result_hash = digest(projection)
        row = frappe.get_doc(dict(
            doctype=SCORE, attempt=doc.name, revision=revision,
            scorer_version=scoring.SCORER_VERSION, form_hash=manifest.form_hash,
            response_digest=scoring.response_fingerprint(responses),
            key_digest=scoring.key_fingerprint(catalog),
            result_json=canonical(projection), result_hash=result_hash,
            scored_by=actor, synthetic=1))
        row.insert(ignore_permissions=True)
        _advance(doc, "Marking")
        result = {"attempt": doc.name, "status": doc.status, "version": doc.version,
                  "score": row.name, "revision": revision,
                  "scorer_version": scoring.SCORER_VERSION,
                  "presented": projection["presented"], "correct": projection["correct"],
                  "incorrect": projection["incorrect"], "missing": projection["missing"],
                  "by_skill": projection["by_skill"], "items": projection["items"]}
        return result, dict(target=doc.name, after_hash=result_hash)

    return _execute("score_attempt", request_key,
                    {"attempt": attempt, "expected_version": expected_version}, work)


@frappe.whitelist(methods=["POST"])
def review_attempt(request_key, attempt, expected_version):
    def work(actor):
        doc = _locked_session(attempt, expected_version)
        if doc.mode != "Digital":
            raise frappe.ValidationError("Only digital independent review is implemented in this increment")
        if doc.status != "Marking":
            raise frappe.ValidationError("Attempt is not marked for review")
        scored_by = frappe.db.get_value(SCORE, {"attempt": doc.name}, "scored_by")
        if not scored_by:
            raise frappe.ValidationError("Attempt has no score to review")
        if actor == scored_by:
            raise frappe.PermissionError("Scorer cannot independently review this attempt")
        reviewed_at = _now()
        _advance(doc, "Review", reviewed_by=actor, reviewed_at=reviewed_at)
        result = {"attempt": doc.name, "status": doc.status, "version": doc.version,
                  "reviewed_by": actor, "reviewed_at": _iso(reviewed_at)}
        return result, dict(target=doc.name, after_hash=digest([doc.name, "Review", actor]))

    return _execute("review_attempt", request_key,
                    {"attempt": attempt, "expected_version": expected_version}, work)
