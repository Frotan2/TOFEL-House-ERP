"""Three authenticated POST commands; no candidate, file or result endpoint."""
import json
import frappe
from toefl_house.policy import canonical, digest, request_digest, validate_content, validate_family, validate_request_key
from toefl_house.security import authorize, command
from toefl_house.transactions import run_with_retry

ITEM = "TH Placement Item Revision"
KEY = "TH Placement Key Revision"
OP = "TH Placement Operation"
AUDIT = "TH Placement Audit Event"


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
    actor = authorize("Placement Publisher" if kind == "publish" else "Placement Author")
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
