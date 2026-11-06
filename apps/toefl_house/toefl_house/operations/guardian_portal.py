"""Guardian self-service portal — strictly scoped, consent-gated, privacy-aware.

Verified relationships, age-appropriate privacy, consent where required,
revocation, and record-level authorization. Every read is allow-listed
and scoped by verified guardian→student linkage + valid consent +
branch isolation. Query manipulation or predictable IDs cannot bypass.

Prerequisites:
- TH Portal Configuration: guardian_portal_enabled must be true
- Session user must have exactly one Guardian doc (per SEC-GUARDIAN-01)
- Each child is linked via Student Guardian (parenttype=Student)
- User Permissions on Guardian/Student/Customer must be exact
- Guardian lifecycle policy may require consent evidence/expiry
- Revoked or expired consent immediately denies access

No guardian can view another guardian's children; no student finance/
contact/private files are exposed beyond the allow-list.

Age-appropriate privacy: students >=18 require explicit consent for
any guardian access; students <18 allow guardian access but finance
and attendance details are still consent-gated when policy says so.
"""
import frappe
from datetime import datetime, timedelta

from toefl_house.operations import portal_policy
from toefl_house.operations.portal_dates import with_solar_date

_fallback_consents = []  # offline in-memory consents when frappe stub not fully wired

# Allow-listed fields for guardian projection (subset of student portal + guardian-specific)
GUARDIAN_FIELDS = {
    "Student": ["name", "student_name", "student_email_id", "date_of_birth", "customer"],
    "Course Schedule": ["name", "student_group", "course", "room", "schedule_date", "from_time", "to_time", "th_session_status"],
    "Student Attendance": ["name", "student", "student_group", "course_schedule", "date", "status"],
    "Assessment Result": ["name", "student", "assessment_plan", "grade", "posting_date"],
    "Fees": ["name", "student", "program", "academic_year", "grand_total", "outstanding_amount", "due_date"],
    "Sales Invoice": ["name", "customer", "grand_total", "outstanding_amount", "due_date", "status"],
    # "audience" must be fetched: without it the announcement filter
    # below cannot distinguish audiences and every announcement reads
    # as "All" — student-only announcements leaked to guardians.
    "TH Portal Announcement": ["name", "title", "message", "publish_date", "audience"],
}

CONSENT_DOCTYPE = "TH Guardian Consent"
ANNOUNCEMENT_DOCTYPE = "TH Portal Announcement"

# Absolute bound for a single scoped portal read; see student_portal.
PORTAL_FETCH_MAX = 5000
PORTAL_PAGE_MAX = 200
# A guardian with more than this many verified child links is
# pathological; past it the read raises instead of silently dropping
# children (the old limit_page_length=200 silently truncated).
VERIFIED_CHILDREN_MAX = 200
# Consent history per (guardian, student) pair; past it the read
# raises instead of silently missing an Active row (revocation) or
# the newest state.
CONSENT_ROWS_MAX = 500


def _page_params(limit, offset, default, maximum=PORTAL_PAGE_MAX):
    """Validate paging arguments. Returns (limit, offset) as ints."""
    if limit is None:
        limit = default
    if isinstance(limit, bool):
        raise frappe.ValidationError("limit must be a whole number")
    if isinstance(limit, float):
        if not limit.is_integer():
            raise frappe.ValidationError("limit must be a whole number")
        limit = int(limit)
    try:
        limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise frappe.ValidationError("limit must be a whole number") from exc
    if limit < 1 or limit > maximum:
        raise frappe.ValidationError(
            "limit must be between 1 and %d" % maximum)
    if offset is None:
        offset = 0
    if isinstance(offset, bool):
        raise frappe.ValidationError("offset must be a whole number")
    if isinstance(offset, float):
        if not offset.is_integer():
            raise frappe.ValidationError("offset must be a whole number")
        offset = int(offset)
    try:
        offset = int(offset)
    except (TypeError, ValueError) as exc:
        raise frappe.ValidationError("offset must be a whole number") from exc
    if offset < 0:
        raise frappe.ValidationError("offset must not be negative")
    return (limit, offset)


def _fetch_scoped(doctype, filters, fields, order_by=None):
    """Fetch a scoped portal read, bounded but never silently truncated.

    Requests PORTAL_FETCH_MAX + 1 rows and raises when more exist; the
    caller pages through the returned rows with limit/offset. A failed
    read raises (fail-closed) — callers never turn it into [].
    """
    rows = frappe.get_all(doctype, filters=filters, fields=fields,
                          order_by=order_by,
                          limit_page_length=PORTAL_FETCH_MAX + 1)
    if len(rows) > PORTAL_FETCH_MAX:
        raise frappe.ValidationError(
            "%s exceeds the supported total of %d records; narrow the "
            "scope or contact an administrator" % (doctype, PORTAL_FETCH_MAX))
    return rows


def _page(rows, limit, offset):
    return list(rows)[offset:offset + limit]


def _require_portal_enabled():
    if not portal_policy.is_portal_enabled("guardian_portal"):
        raise frappe.PermissionError("Guardian portal is disabled — Owner approval required")


def _now():
    try:
        return frappe.utils.now_datetime()
    except Exception:
        return datetime.now().isoformat(sep=" ", timespec="seconds")


def _today():
    try:
        return frappe.utils.today()
    except Exception:
        return datetime.now().date().isoformat()


def _get_guardian_for_user(user):
    """Resolve the unique Guardian for a user. Fail-closed."""
    try:
        rows = frappe.get_all(
            "Guardian",
            filters={"user": user},
            fields=["name"],
            limit=2,
        )
        if len(rows) == 1:
            return rows[0]["name"]
        return None
    except Exception:
        return None


def _get_verified_children(guardian):
    """Return verified student names for a guardian via Student Guardian links.

    A failed read of the links raises (fail-closed). A failed per-student
    verification read also raises: silently dropping that child would
    hide an outage as "no such child". A student row that no longer
    exists, or has no customer, is still skipped — that is genuinely
    no verifiable membership, not a read failure. More than
    VERIFIED_CHILDREN_MAX links raises instead of silently truncating
    the guardian's children.
    """
    links = frappe.get_all(
        "Student Guardian",
        filters={"guardian": guardian, "parenttype": "Student", "parentfield": "guardians"},
        fields=["parent"],
        limit_page_length=VERIFIED_CHILDREN_MAX + 1,
    )
    if len(links) > VERIFIED_CHILDREN_MAX:
        raise frappe.ValidationError(
            "Guardian has more than %d verified child links; narrow the "
            "scope or contact an administrator" % VERIFIED_CHILDREN_MAX)
    names = []
    for l in links:
        p = l.get("parent")
        if p:
            names.append(p)
    # Deduplicate, verify each Student still exists and has customer
    verified = []
    for s in set(names):
        st = frappe.db.get_value("Student", s, ["name", "customer"], as_dict=True)
        if st and st.get("customer"):
            verified.append(st["name"])
        elif st and not st.get("customer"):
            # Without customer, guardian scope is incomplete per SEC-GUARDIAN-01
            continue
    return verified


def _student_age_years(student):
    """Return student's age in years, or None if birth date unavailable."""
    try:
        dob = frappe.db.get_value("Student", student, "date_of_birth")
        if not dob:
            return None
        dob_str = str(dob)
        try:
            dob_d = datetime.strptime(dob_str, "%Y-%m-%d").date()
        except ValueError:
            try:
                dob_d = datetime.fromisoformat(dob_str).date()
            except Exception:
                return None
        today = datetime.strptime(_today(), "%Y-%m-%d").date()
        age = today.year - dob_d.year - ((today.month, today.day) < (dob_d.month, dob_d.day))
        return age
    except Exception:
        return None


def _all_consents(guardian, student):
    """All consent rows for a (guardian, student) pair, newest first.

    Bounded at CONSENT_ROWS_MAX + 1 with a raise past it: a 50-row cap
    silently missed older rows, so revocation could leave an Active
    authorization alive while claiming to be immediate.
    """
    rows = frappe.db.get_all(
        CONSENT_DOCTYPE,
        filters={"guardian": guardian, "student": student},
        fields=["name", "status", "consent_date", "expiry_date",
                "evidence_type", "revoked_at", "approved_by", "approved_on"],
        order_by="creation desc",
        limit_page_length=CONSENT_ROWS_MAX + 1)
    if len(rows) > CONSENT_ROWS_MAX:
        raise frappe.ValidationError(
            "Consent history exceeds the supported total of %d rows; "
            "contact an administrator" % CONSENT_ROWS_MAX)
    return rows


def _get_consent(guardian, student):
    """Only persistent verified consent counts; process memory is not proof.

    Select the Active row, not merely the newest: a newer Pending row (new
    evidence lodged) or a newer Revoked row must never hide a still-Active
    authorization, and revocation must not be able to "revoke" a Pending
    row while the Active row survives. When no Active row exists, return
    the newest row so callers still see the latest state.
    """
    rows = _all_consents(guardian, student)
    if not rows:
        return None
    for row in rows:
        if row.get("status") == "Active":
            return row
    return rows[0]


def _is_consent_valid(guardian, student, policy_terms=None):
    """Whether consent is currently valid (not revoked, not expired, evidence ok).

    If policy_terms has no governing version, fall back to requiring explicit
    consent for any guardian access (fail-closed).
    """
    consent = _get_consent(guardian, student)
    if not consent:
        return False
    # Pending evidence is not authorization. Only staff-approved Active
    # consent can authorize child-grade, attendance or finance disclosures.
    if consent.get("status") != "Active":
        return False
    if not consent.get("approved_by") or not consent.get("approved_on"):
        return False
    if consent.get("revoked_at"):
        return False
    # Expiry check
    expiry = consent.get("expiry_date")
    if not expiry:
        return False
    try:
        expiry_date = datetime.strptime(str(expiry)[:10], "%Y-%m-%d").date()
        current = datetime.strptime(_today(), "%Y-%m-%d").date()
        if expiry_date < current:
            return False
    except (TypeError, ValueError):
        return False

    # Evidence check against policy consented evidence kind
    if policy_terms:
        required = policy_terms.get("consent_evidence")
        if required:
            ev = consent.get("evidence_type")
            if required == "Both" and ev not in ("Both",):
                # Must be Both when policy says Both
                if ev != "Both":
                    return False
            elif required == "Link" and ev not in ("Link", "Both"):
                return False
            elif required == "Attachment" and ev not in ("Attachment", "Both"):
                return False

    # Check consent window: consent must be within delegation_window_days of today
    try:
        cdate = str(consent.get("consent_date") or "")
        if cdate and policy_terms and policy_terms.get("delegation_window_days"):
            window = int(policy_terms["delegation_window_days"])
            c_d = datetime.strptime(cdate, "%Y-%m-%d").date()
            today_d = datetime.strptime(_today(), "%Y-%m-%d").date()
            if (today_d - c_d).days > window:
                return False
    except (TypeError, ValueError):
        return False

    return True


def _governing_guardian_terms():
    # A policy-read failure raises (fail-closed, C-12): swallowing it
    # to {} silently drops the evidence-type and delegation-window
    # checks in _is_consent_valid. "No governing policy" is not an
    # error — governing_guardian_lifecycle() itself returns {} then —
    # so only a genuinely raised error reaches the caller.
    from toefl_house.operations.guardian_lifecycle import governing_guardian_lifecycle
    return governing_guardian_lifecycle()


def _can_access(guardian, student):
    """Full authorization check for a guardian to access a student's records.

    Checks: verified relationship + consent valid + not revoked + age privacy.
    Returns (allowed: bool, reason: str).
    """
    verified = _get_verified_children(guardian)
    if student not in verified:
        return (False, "No verified guardian relationship for this student")
    # Fail closed for every age. No hard-coded age, no guardian self-approval;
    # staff must verify consent under the approved guardian lifecycle policy.
    terms = _governing_guardian_terms()
    if not _is_consent_valid(guardian, student, terms):
        return (False, "A current, staff-approved guardian consent is required")
    return (True, "Authorized")


def _assert_guardian_scope(user, requested_student=None):
    """Verify guardian identity + optional record-level authorization.

    Returns (guardian_name, verified_children) after checks.
    If requested_student is supplied, additionally checks _can_access.
    """
    if user in (None, "Guest"):
        raise frappe.PermissionError("Authentication required")
    # The foundation guardian scope control is a hard prerequisite;
    # missing imports or runtime errors must never silently grant access.
    from foundation_security.guards import validate_guardian_scope
    validate_guardian_scope()
    guardian = _get_guardian_for_user(user)
    if not guardian:
        raise frappe.PermissionError("No guardian profile found for this account")
    if "Guardian" not in frappe.get_roles(user):
        raise frappe.PermissionError("Guardian role is required")
    children = _get_verified_children(guardian)
    if not children:
        raise frappe.PermissionError("No verified child membership for this guardian")
    if requested_student is not None:
        if not isinstance(requested_student, str) or not requested_student.strip():
            raise frappe.ValidationError("Student is required")
        allowed, reason = _can_access(guardian, requested_student.strip())
        if not allowed:
            raise frappe.PermissionError(f"Access denied for {requested_student}: {reason}")
    return (guardian, children)


def _require_authorized_child(user, student):
    """A child-specific endpoint must never turn a missing ID into a query."""
    if not isinstance(student, str) or not student.strip():
        raise frappe.ValidationError("Student is required")
    student = student.strip()
    _assert_guardian_scope(user, requested_student=student)
    return student


# ---- Public portal endpoints ----

@frappe.whitelist()
def get_my_children():
    """Return the guardian's verified children (minimal, no grades/finances)."""
    _require_portal_enabled()
    user = frappe.session.user
    guardian, children = _assert_guardian_scope(user)
    result = []
    for s in children:
        # A failed read must raise, never degrade to an empty student_name
        # that masquerades as a nameless child (C-12). A missing row
        # (deleted between the scope check and this read) raises
        # explicitly instead of failing later with a bare TypeError.
        row = frappe.db.get_value("Student", s, ["name", "student_name"], as_dict=True)
        if not row:
            raise RuntimeError(f"Student record {s} could not be read")
        result.append({"name": row["name"], "student_name": row.get("student_name") or ""})
    return result


@frappe.whitelist()
def get_child_schedule(student=None, limit=100, offset=0):
    _require_portal_enabled()
    user = frappe.session.user
    student = _require_authorized_child(user, student)
    limit, offset = _page_params(limit, offset, 100)
    # Resolve child's enrolled groups. A failed read must raise, never
    # return [] masquerading as "no classes" (C-12). An empty roster is
    # genuinely no data and still returns [].
    roster = _fetch_scoped(
        "Student Group Student",
        filters={"student": student, "active": 1},
        fields=["parent"],
    )
    group_names = [r["parent"] for r in roster if r.get("parent")]
    if not group_names:
        return []
    schedules = _fetch_scoped(
        "Course Schedule",
        filters={"student_group": ["in", group_names]},
        fields=GUARDIAN_FIELDS["Course Schedule"],
        order_by="schedule_date asc",
    )
    return with_solar_date(_page(schedules, limit, offset), "schedule_date", "schedule_date_shamsi")


@frappe.whitelist()
def get_child_attendance(student=None, limit=100, offset=0):
    _require_portal_enabled()
    user = frappe.session.user
    student = _require_authorized_child(user, student)
    limit, offset = _page_params(limit, offset, 100)
    # A failed read must raise, never return [] masquerading as
    # "no attendance" (C-12).
    rows = _fetch_scoped(
        "Student Attendance",
        filters={"student": student, "docstatus": 1},
        fields=GUARDIAN_FIELDS["Student Attendance"],
        order_by="date desc",
    )
    return with_solar_date(_page(rows, limit, offset), "date", "date_shamsi")


@frappe.whitelist()
def get_child_grades(student=None, limit=100, offset=0):
    """Approved grades only. Still requires valid consent."""
    _require_portal_enabled()
    user = frappe.session.user
    student = _require_authorized_child(user, student)
    limit, offset = _page_params(limit, offset, 100)
    # A failed read must raise, never return [] masquerading as
    # "no grades" (C-12).
    rows = _fetch_scoped(
        "Assessment Result",
        filters={"student": student, "docstatus": 1},
        fields=GUARDIAN_FIELDS["Assessment Result"],
        order_by="posting_date desc",
    )
    return _page(rows, limit, offset)


@frappe.whitelist()
def get_child_fees(student=None, limit=50, offset=0):
    """Fee balances — only for verified child with valid consent."""
    _require_portal_enabled()
    user = frappe.session.user
    student = _require_authorized_child(user, student)
    limit, offset = _page_params(limit, offset, 50)
    # A failed read must raise, never return empty fees/invoices
    # masquerading as "nothing owed" (C-12).
    fees = _fetch_scoped(
        "Fees",
        filters={"student": student, "docstatus": 1},
        fields=GUARDIAN_FIELDS["Fees"],
    )
    # A Customer is often shared by siblings or the same guardian.
    # Invoice access is permitted ONLY when the native invoice has a
    # direct Student link and that link matches this verified child.
    # When the Sales Invoice doctype has no student field there is
    # simply nothing to show; any other read failure raises.
    invoices = []
    if frappe.get_meta("Sales Invoice").has_field("student"):
        customer = frappe.db.get_value("Student", student, "customer")
        if customer:
            invoices = _fetch_scoped(
                "Sales Invoice",
                filters={"customer": customer, "student": student,
                         "docstatus": 1},
                fields=GUARDIAN_FIELDS["Sales Invoice"])
    return {"fees": _page(fees, limit, offset),
            "invoices": _page(invoices, limit, offset)}


@frappe.whitelist()
def get_announcements_for_guardian(limit=50, offset=0):
    _require_portal_enabled()
    user = frappe.session.user
    _assert_guardian_scope(user)
    limit, offset = _page_params(limit, offset, 50)
    # A failed read raises (C-12): an outage must never render as
    # "no announcements".
    rows = _fetch_scoped(
        ANNOUNCEMENT_DOCTYPE,
        filters={"status": "Published"},
        fields=GUARDIAN_FIELDS[ANNOUNCEMENT_DOCTYPE],
        order_by="publish_date desc",
    )
    allowed = []
    for r in rows:
        aud = (r.get("audience") or "All").strip().lower()
        if aud in ("all", "guardians", "guardian", "family"):
            allowed.append(r)
    return _page(allowed, limit, offset)


# ---- Consent management ----

@frappe.whitelist(methods=["POST"])
def record_consent(student, evidence_type="Link", attachment=None, link_reference=None):
    """Guardian records consent for a child. Validated against policy.

    A guardian can only record consent for their verified children.
    Evidence type must satisfy the governing guardian lifecycle policy.
    """
    _require_portal_enabled()
    user = frappe.session.user
    # Consent creation only requires verified relationship, not existing consent
    guardian = _get_guardian_for_user(user)
    if not guardian:
        raise frappe.PermissionError("No guardian profile found for this account")
    verified = _get_verified_children(guardian)
    if student not in verified:
        raise frappe.PermissionError("No verified guardian relationship for this student")

    terms = _governing_guardian_terms()
    if not terms or not terms.get("consent_evidence") or not terms.get("consent_expiry_days"):
        raise frappe.ValidationError("The Course Owner must activate a guardian consent policy first")
    if terms.get("consent_evidence"):
        required = terms["consent_evidence"]
        if required == "Both" and evidence_type != "Both":
            raise frappe.ValidationError("This policy requires Both Link and Attachment evidence")
        if required == "Link" and evidence_type not in ("Link", "Both"):
            raise frappe.ValidationError("This policy requires Link evidence")
        if required == "Attachment" and evidence_type not in ("Attachment", "Both"):
            raise frappe.ValidationError("This policy requires Attachment evidence")

    try:
        expiry_days = int(terms["consent_expiry_days"])
    except (TypeError, ValueError) as exc:
        raise frappe.ValidationError("Invalid configured consent expiry policy") from exc
    if expiry_days <= 0:
        raise frappe.ValidationError("Configured consent expiry must be positive")

    consent_date = _today()
    try:
        c_d = datetime.strptime(consent_date, "%Y-%m-%d").date()
        expiry_date = (c_d + timedelta(days=expiry_days)).isoformat()
    except Exception:
        expiry_date = None

    doc_data = {
        "doctype": CONSENT_DOCTYPE,
        "guardian": guardian,
        "student": student,
        "consent_date": consent_date,
        "expiry_date": expiry_date,
        "evidence_type": evidence_type,
        "attachment": attachment or "",
        "link_reference": link_reference or "",
        "status": "Pending",
        "recorded_by": user,
    }
    # A guardian may lodge evidence, never approve their own evidence.
    # The owning staff member reviews Pending and makes it Active in the
    # protected native consent record. Persistence errors are not success.
    doc = frappe.get_doc(doc_data)
    doc.insert(ignore_permissions=True)
    return {"name": doc.name, "guardian": guardian, "student": student,
            "consent_date": consent_date, "expiry_date": expiry_date,
            "status": "Pending", "evidence_type": evidence_type}


@frappe.whitelist(methods=["POST"])
def approve_guardian_consent(request_key, consent):
    """Owner-only, idempotent approval after independent evidence review.

    Submitting guardian evidence never authorizes disclosure. This command
    persists a separate staff approval and a hash-chained audit receipt.
    """
    from toefl_house.configuration.audit import execute
    from toefl_house.policy import digest

    if not isinstance(consent, str) or not consent.strip():
        raise frappe.ValidationError("A pending guardian consent is required")

    def work(actor):
        row = frappe.db.get_value(
            CONSENT_DOCTYPE, consent,
            ["name", "guardian", "student", "status", "evidence_type",
             "link_reference", "attachment", "expiry_date", "recorded_by"],
            as_dict=True, for_update=True)
        if not row or row.status != "Pending":
            raise frappe.ValidationError("Only a pending guardian consent can be approved")
        if row.recorded_by == actor:
            raise frappe.PermissionError("The evidence submitter cannot approve themselves")
        if row.student not in _get_verified_children(row.guardian):
            raise frappe.PermissionError("The guardian/student relationship is not verified")
        if row.evidence_type in ("Link", "Both") and not row.link_reference:
            raise frappe.ValidationError("The consent link evidence has not been supplied")
        if row.evidence_type in ("Attachment", "Both") and not row.attachment:
            raise frappe.ValidationError("The consent attachment evidence has not been supplied")
        if not row.expiry_date or str(row.expiry_date) < _today():
            raise frappe.ValidationError("The consent must have a valid future expiry date")
        terms = _governing_guardian_terms()
        if not terms or not terms.get("consent_evidence"):
            raise frappe.ValidationError("An active guardian policy must govern approval")
        required = terms.get("consent_evidence")
        if required == "Both" and row.evidence_type != "Both":
            raise frappe.ValidationError("The approved policy requires both evidence kinds")
        if required == "Link" and row.evidence_type not in ("Link", "Both"):
            raise frappe.ValidationError("The approved policy requires link evidence")
        if required == "Attachment" and row.evidence_type not in ("Attachment", "Both"):
            raise frappe.ValidationError("The approved policy requires attachment evidence")
        before_hash = digest([row.name, row.guardian, row.student, row.status])
        doc = frappe.get_doc(CONSENT_DOCTYPE, row.name)
        doc.status = "Active"
        doc.approved_by = actor
        doc.approved_on = _now()
        doc.save(ignore_permissions=True)
        result = {"name": doc.name, "status": "Active", "approved_by": actor}
        return result, {"target": doc.name, "before_hash": before_hash,
                        "after_hash": digest([doc.name, doc.guardian, doc.student,
                                               doc.status, doc.approved_by,
                                               str(doc.approved_on)])}

    return execute("approve_guardian_consent", request_key, {"consent": consent}, work)


@frappe.whitelist(methods=["POST"])
def revoke_consent(student, reason=""):
    """Revoke guardian consent for a child. Revocation is immediate and audit-logged."""
    _require_portal_enabled()
    user = frappe.session.user
    guardian = _get_guardian_for_user(user)
    if not guardian:
        raise frappe.PermissionError("No guardian profile found for this account")
    verified = _get_verified_children(guardian)
    if student not in verified:
        raise frappe.PermissionError("No verified guardian relationship for this student")

    # Revoke EVERY non-Revoked row for this (guardian, student). Revoking
    # only the newest row could leave an older Active authorization alive
    # (e.g. a newer Pending row created by freshly lodged evidence), so
    # revocation would claim to be immediate while authorization survived.
    # Filter in Python rather than with a ("!=", ...) database filter so
    # the row set is exactly the pair's rows in every read path. The
    # read is bounded at CONSENT_ROWS_MAX with a raise past it — a
    # 50-row cap silently left rows beyond the page unrevoked.
    consent_rows = [
        row for row in _all_consents(guardian, student)
        if row.get("status") != "Revoked"]
    if not consent_rows:
        raise frappe.ValidationError("No active consent found to revoke")
    # The returned receipt names the Active row when one exists, else
    # the newest non-Revoked row. (Naming _get_consent's row directly
    # could name an already-Revoked newest row and raise after the
    # other rows were revoked; the primary here is always a row this
    # call revokes.)
    primary = _get_consent(guardian, student)
    primary_name = (primary or {}).get("name")
    if primary_name not in {row["name"] for row in consent_rows}:
        primary_name = consent_rows[0]["name"]
    revoked = None
    for row in consent_rows:
        doc = frappe.get_doc(CONSENT_DOCTYPE, row["name"])
        if doc.status == "Revoked":
            continue
        doc.status = "Revoked"
        doc.revoked_at = _now()
        doc.revoked_by = user
        doc.revocation_reason = reason or "Guardian requested revocation"
        doc.save(ignore_permissions=True)
        if row["name"] == primary_name:
            revoked = doc
    if revoked is None:
        raise frappe.ValidationError("No active consent found to revoke")
    return {"name": revoked.name, "status": "Revoked",
            "revoked_at": revoked.revoked_at}


@frappe.whitelist()
def get_consent_status(student=None):
    """Return consent status for a child."""
    _require_portal_enabled()
    user = frappe.session.user
    guardian = _get_guardian_for_user(user)
    if not guardian:
        raise frappe.PermissionError("No guardian profile found")
    if "Guardian" not in frappe.get_roles(user):
        raise frappe.PermissionError("Guardian role required")
    verified = _get_verified_children(guardian)
    if student is not None:
        if student not in verified:
            raise frappe.PermissionError("No verified relationship for this student")
        consent = _get_consent(guardian, student)
        if not consent:
            return {"student": student, "has_consent": False, "status": "None"}
        valid = _is_consent_valid(guardian, student, _governing_guardian_terms())
        return {"student": student, "has_consent": valid, "status": consent.get("status"), "expiry_date": consent.get("expiry_date")}
    # Return all children statuses
    result = []
    for s in verified:
        consent = _get_consent(guardian, s)
        valid = _is_consent_valid(guardian, s, _governing_guardian_terms())
        result.append({"student": s, "has_consent": valid, "status": (consent or {}).get("status") or "None"})
    return result
