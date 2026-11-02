"""Privacy-scoped, preliminary walk-in intake; never creates a student or a bill.

Reception may record a visitor before they have an email, Website User or
released placement result. Later admission continues through the existing
independently approved placement path; an inquiry is not proof of admission.
All writes use operation receipts, native Branch scope, version locks and
the guarded document controller.
"""
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import frappe

from toefl_house.api import _execute
from toefl_house.command_scope import resolve_creation_branch
from toefl_house.policy import digest
from toefl_house.reception_phone import afghan_phone_variants, normalize_contact_phone
from toefl_house.security import record_synthetic_flag, require_command

DOCTYPE = "TH Reception Inquiry"
STATUSES = ("New", "Contacted", "Awaiting Placement", "Closed")
MODES = ("Undecided", "On-campus", "Online")


def _text(value, label, *, required=False, length=140):
    if not isinstance(value, str):
        raise frappe.ValidationError(f"{label} must be text")
    clean = value.strip()
    if (len(clean) > length or (required and not clean)
            or any(ord(char) < 32 for char in clean)):
        raise frappe.ValidationError(f"{label} is missing or invalid")
    return clean


def _phone(value):
    try:
        return normalize_contact_phone(value)
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc


def _study_mode(value):
    if value not in MODES:
        raise frappe.ValidationError("Choose Online, On-campus or Undecided study mode")
    return value


def _time_zone(value):
    name = _text(value, "Learner time zone", length=64)
    if not name:
        return ""
    # For global classes never silently treat a local learner's schedule as
    # Kabul time. Store an IANA timezone only when it actually resolves.
    if name.startswith(("/", ".")) or ".." in name:
        raise frappe.ValidationError("Choose a valid time zone, e.g. Asia/Kabul")
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        raise frappe.ValidationError(
            "Choose a valid time zone such as Asia/Kabul or Europe/London") from None
    return name


def _open_identity_key(branch, person_name, contact):
    """One open record for an exact name+phone+Branch, protected by a DB index.

    A name/household phone is NOT proof of person identity. The key is only a
    duplicate-warning concurrency guard; phone-less inquiries remain distinct.
    Closed inquiries release the key by storing NULL (not a shared empty string).
    """
    if not contact:
        return None
    normalized_name = " ".join(person_name.split()).casefold()
    canonical_contact = afghan_phone_variants(contact)[0]
    return "RI-" + digest(["reception-open-v1", branch, normalized_name,
                           canonical_contact])[:32]


def _result(doc):
    return {
        "name": doc.name, "person_name": doc.person_name,
        "status": doc.status, "th_branch": doc.th_branch or "",
        "study_mode": doc.get("study_mode") or "Undecided",
        "version": int(doc.version),
    }


def protect_inquiry(doc, method=None):
    """Fail-closed document lifecycle; direct CRUD cannot bypass command scope."""
    if method in ("on_trash", "before_cancel", "before_update_after_submit"):
        raise frappe.PermissionError("Reception inquiries cannot be cancelled, deleted or edited after submit")
    kind, actor = require_command(DOCTYPE)
    if kind not in {"create_walkin_inquiry", "update_walkin_inquiry", "correct_walkin_inquiry"}:
        raise frappe.PermissionError("Unauthorized reception inquiry command")
    if doc.status not in STATUSES or int(doc.version or 0) < 1:
        raise frappe.ValidationError("Invalid inquiry status or version")
    expected_open_key = (
        _open_identity_key(doc.th_branch, doc.person_name, doc.phone or "")
        if doc.status != "Closed" else None)
    if doc.get("open_identity_key") != expected_open_key:
        raise frappe.PermissionError(
            "Reception open-record uniqueness stamp does not match the verified visitor")
    if (_text(doc.person_name, "Visitor name", required=True) != doc.person_name
            or _phone(doc.phone or "") != (doc.phone or "")
            or _text(doc.program_interest or "", "Program interest") != (doc.program_interest or "")
            or _study_mode(doc.get("study_mode") or "Undecided") != (doc.get("study_mode") or "Undecided")
            or _text(doc.get("contact_country") or "", "Country", length=80) != (doc.get("contact_country") or "")
            or _time_zone(doc.get("time_zone") or "") != (doc.get("time_zone") or "")
            or _text(doc.notes or "", "Notes", length=1000) != (doc.notes or "")):
        raise frappe.ValidationError("Inquiry fields are not normalized")
    if doc.is_new():
        if (kind != "create_walkin_inquiry" or doc.status != "New"
                or int(doc.version) != 1 or doc.recorded_by != actor
                or int(doc.synthetic) != record_synthetic_flag()):
            raise frappe.PermissionError("Only the authorized first-contact command may create an inquiry")
        return
    if kind not in {"update_walkin_inquiry", "correct_walkin_inquiry"}:
        raise frappe.PermissionError("An existing inquiry cannot be created twice")
    original = frappe.db.get_value(DOCTYPE, doc.name,
        ["person_name", "phone", "program_interest", "study_mode", "contact_country",
         "time_zone", "th_branch", "recorded_by", "synthetic", "status", "version", "notes",
         "last_correction_reason", "last_corrected_by"], as_dict=True)
    if not original or original.status == "Closed" or int(doc.version) != int(original.version) + 1:
        raise frappe.ValidationError("Inquiry was changed or closed; refresh before updating")
    if kind == "correct_walkin_inquiry":
        if frappe.db.exists("TH Placement Case", {"reception_inquiry": doc.name}):
            raise frappe.PermissionError(
                "Placement already consumed this Inquiry; identity corrections need Academic Manager review")
        for key in ("program_interest", "study_mode", "contact_country", "time_zone",
                    "th_branch", "recorded_by", "synthetic", "status", "notes"):
            if (doc.get(key) or "") != (original.get(key) or ""):
                raise frappe.PermissionError(
                    "Identity correction cannot alter Branch, status, notes or original owner")
        if ((doc.person_name == original.person_name and
             (doc.phone or "") == (original.phone or "")) or
                not _text(doc.get("last_correction_reason") or "",
                          "Correction reason", required=True, length=500) or
                doc.get("last_corrected_by") != actor):
            raise frappe.ValidationError(
                "Provide changed visitor details and a recorded correction reason")
        return
    for key in ("person_name", "phone", "program_interest",
                "th_branch", "recorded_by",
                "synthetic", "last_correction_reason", "last_corrected_by"):
        if (doc.get(key) or "") != (original.get(key) or ""):
            raise frappe.PermissionError(
                "An inquiry's original identity and correction history cannot be silently rewritten")
    if original.status == "Awaiting Placement" and doc.status == "Contacted":
        # Once Placement has consumed a referral, Reception must not move
        # its status backwards and incorrectly offer another test.
        # Notes and eventual closure remain available.
        if frappe.db.exists("TH Placement Case", {"reception_inquiry": doc.name}):
            raise frappe.PermissionError(
                "This inquiry is already linked to Placement; do not move it backwards")


@frappe.whitelist(methods=["POST"])
def create_walkin_inquiry(request_key, person_name, phone="", program_interest="", branch="", notes="",
                          study_mode="Undecided", contact_country="", time_zone=""):
    """Record the person immediately; does NOT issue a fee or mark enrollment."""
    def work(actor):
        person = _text(person_name, "Visitor name", required=True)
        contact = _phone(phone)
        interest = _text(program_interest, "Program interest")
        mode = _study_mode(study_mode)
        country = _text(contact_country, "Country", length=80)
        zone = _time_zone(time_zone)
        remark = _text(notes, "Notes", length=1000)
        chosen = resolve_creation_branch(branch, actor)
        if not chosen:
            raise frappe.ValidationError("Choose a reception branch before saving the visitor")
        if not frappe.db.exists("Branch", chosen):
            raise frappe.ValidationError("Unknown reception branch")
        # A repeated visit from the same person/contact belongs in the open
        # follow-up record, not in a second incomplete admission funnel.
        # The comparison is exact and branch-local. Different family members
        # sharing one telephone remain separate people, and closed visits
        # may be followed by a new record.
        if contact and frappe.get_all(
                DOCTYPE,
                filters={"th_branch": chosen,
                         "phone": ("in", list(afghan_phone_variants(contact))),
                         "person_name": person,
                         "status": ("in", ["New", "Contacted", "Awaiting Placement"])},
                fields=["name"], limit_page_length=1):
            raise frappe.ValidationError(
                "An open inquiry already exists for this visitor and phone in this Branch; "
                "search the visitor and update the existing follow-up")
        doc = frappe.get_doc(dict(
            doctype=DOCTYPE, person_name=person, phone=contact,
            program_interest=interest, study_mode=mode,
            contact_country=country, time_zone=zone,
            th_branch=chosen or None, notes=remark, status="New", recorded_by=actor,
            open_identity_key=_open_identity_key(chosen, person, contact),
            version=1, synthetic=record_synthetic_flag()))
        try:
            doc.insert(ignore_permissions=True)
        except frappe.DuplicateEntryError as exc:
            raise frappe.ValidationError(
                "An open inquiry already exists for this visitor and phone in this Branch; "
                "search and update the existing record") from exc
        return _result(doc), dict(target=doc.name, after_hash=digest([doc.name, person, chosen]))
    return _execute("create_walkin_inquiry", request_key, {
        "person_name": person_name, "phone": phone, "program_interest": program_interest,
        "branch": branch, "notes": notes,
        "study_mode": study_mode, "contact_country": contact_country,
        "time_zone": time_zone,
    }, work)


@frappe.whitelist(methods=["POST"])
def update_walkin_inquiry(request_key, inquiry, expected_version, status, notes="",
                          study_mode=None, contact_country=None, time_zone=None):
    """Follow up a preliminary visitor with an audited optimistic revision."""
    def work(actor):
        # Frappe browser form and URL-encoded POST may transmit Int values
        # as decimal strings. Accept exactly canonical positive integers; never
        # accept booleans, signs, floats or arbitrary text.
        if type(expected_version) is int:
            version = expected_version
        elif isinstance(expected_version, str) and re.fullmatch(r"[1-9][0-9]{0,8}", expected_version):
            version = int(expected_version)
        else:
            raise frappe.ValidationError("An integer inquiry version is required")
        if version < 1 or version > 999999999:
            raise frappe.ValidationError("An integer inquiry version is required")
        if status not in STATUSES or status == "New":
            raise frappe.ValidationError("Choose a valid follow-up status")
        name = _text(inquiry, "Inquiry", required=True)
        doc = frappe.get_doc(DOCTYPE, name, for_update=True)
        if doc.status == "Closed" or int(doc.version) != version:
            raise frappe.ValidationError("Inquiry changed or is closed; refresh first")
        new_notes = _text(notes, "Notes", length=1000)
        new_mode = _study_mode(study_mode) if study_mode is not None else (
            doc.get("study_mode") or "Undecided")
        new_country = (_text(contact_country, "Country", length=80)
                       if contact_country is not None else (doc.get("contact_country") or ""))
        new_zone = (_time_zone(time_zone) if time_zone is not None
                    else (doc.get("time_zone") or ""))
        if (doc.status == status and (doc.notes or "") == new_notes
                and (doc.get("study_mode") or "Undecided") == new_mode
                and (doc.get("contact_country") or "") == new_country
                and (doc.get("time_zone") or "") == new_zone):
            raise frappe.ValidationError("Nothing changed; update the status, contact preference or follow-up note")
        doc.study_mode = new_mode
        doc.contact_country = new_country
        doc.time_zone = new_zone
        doc.status = status
        doc.open_identity_key = (
            _open_identity_key(doc.th_branch, doc.person_name, doc.phone or "")
            if status != "Closed" else None)
        doc.notes = new_notes
        doc.version += 1
        doc.save(ignore_permissions=True)
        return _result(doc), dict(target=doc.name, after_hash=digest([doc.name, doc.status, doc.version]))
    return _execute("update_walkin_inquiry", request_key, {
        "inquiry": inquiry, "expected_version": expected_version,
        "status": status, "notes": notes,
        "study_mode": study_mode, "contact_country": contact_country,
        "time_zone": time_zone,
    }, work)


@frappe.whitelist(methods=["POST"])
def correct_walkin_inquiry(request_key, inquiry, expected_version, person_name, phone="", reason=""):
    """Audit a genuine Reception typo BEFORE the inquiry is used by Placement.

    The locked Inquiry serializes against competing corrections and the
    Placement Publisher's origin lock. After a case is attached the origin is
    immutable and only an independently approved identity review may repair it.
    """
    def work(actor):
        if type(expected_version) is int:
            version = expected_version
        elif isinstance(expected_version, str) and re.fullmatch(
                r"[1-9][0-9]{0,8}", expected_version):
            version = int(expected_version)
        else:
            raise frappe.ValidationError("An integer inquiry version is required")
        if not 1 <= version <= 999999999:
            raise frappe.ValidationError("An integer inquiry version is required")
        name = _text(inquiry, "Inquiry", required=True)
        person = _text(person_name, "Visitor name", required=True)
        contact = _phone(phone)
        justification = _text(reason, "Correction reason", required=True, length=500)
        doc = frappe.get_doc(DOCTYPE, name, for_update=True)
        if doc.status == "Closed" or int(doc.version) != version:
            raise frappe.ValidationError("Inquiry changed or is closed; refresh before correcting")
        if frappe.db.exists("TH Placement Case", {"reception_inquiry": name}):
            raise frappe.PermissionError(
                "Placement already consumed this Inquiry; identity corrections need Academic Manager review")
        if doc.person_name == person and (doc.phone or "") == contact:
            raise frappe.ValidationError("Nothing to correct")
        doc.person_name = person
        doc.phone = contact
        doc.open_identity_key = _open_identity_key(doc.th_branch, person, contact)
        doc.last_correction_reason = justification
        doc.last_corrected_by = actor
        doc.version += 1
        try:
            doc.save(ignore_permissions=True)
        except frappe.DuplicateEntryError as exc:
            raise frappe.ValidationError(
                "Another open inquiry already uses these visitor details; search first") from exc
        return _result(doc), dict(
            target=doc.name,
            after_hash=digest([doc.name, doc.version, person, contact, justification]))

    return _execute("correct_walkin_inquiry", request_key, {
        "inquiry": inquiry, "expected_version": expected_version,
        "person_name": person_name, "phone": phone, "reason": reason}, work)
