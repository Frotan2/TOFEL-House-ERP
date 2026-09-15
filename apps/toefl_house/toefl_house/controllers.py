"""Owned document invariants apply even when generic writes ignore permissions."""
import frappe
import json
import re
from frappe.model.document import Document
from toefl_house.policy import (ADMISSION_OUTCOMES, ATTEMPT_TRANSITIONS, FROZEN_STATUSES,
                                digest, is_admission_transition, is_config_transition)
from toefl_house.scoring import SCORER_VERSION
from toefl_house.security import require_command, CONFIG_DOCTYPES


class ProtectedRecord(Document):
    def before_insert(self):
        require_command(self.doctype)

    def validate(self):
        require_command(self.doctype)
        if self.get("synthetic") != 1:
            raise frappe.ValidationError("Only synthetic records are supported")
        before = self.get_doc_before_save()
        if before and self.doctype in ("TH Placement Audit Event",):
            raise frappe.PermissionError("Audit events are append-only")
        if self.doctype == "TH Placement Audit Event" and bool(self.item_revision) == bool(self.target):
            raise frappe.ValidationError("Audit events must reference exactly one item or configuration target")
        if before and self.doctype == "TH Placement Operation" and before.status == "Complete":
            raise frappe.PermissionError("Completed operation receipts are immutable")
        if before and self.doctype == "TH Placement Item Revision":
            if before.status == "Published" or before.family != self.family or before.revision != self.revision or before.owner != self.owner:
                raise frappe.PermissionError("Published content and revision identity are immutable")
        if before and self.doctype == "TH Placement Key Revision":
            raise frappe.PermissionError("Key versions are append-only")
        if before and self.doctype in CONFIG_DOCTYPES:
            self._validate_config(before)

    def _validate_config(self, before):
        if before.code != self.code or before.revision != self.revision or before.owner != self.owner:
            raise frappe.PermissionError("Configuration identity and revision are immutable")
        if not is_config_transition(before.status, self.status):
            raise frappe.PermissionError("Illegal configuration state transition")
        if before.status in FROZEN_STATUSES:
            if (before.definition_json != self.definition_json
                    or before.content_hash != self.content_hash
                    or before.review_actor != self.review_actor):
                raise frappe.PermissionError("Published or retired configuration is immutable")
            return
        # Content is mutable only while the revision remains a Draft.
        if not (before.status == "Draft" and self.status == "Draft"):
            if before.definition_json != self.definition_json or before.content_hash != self.content_hash:
                raise frappe.PermissionError("Configuration content is frozen once reviewed")
        if before.review_actor and before.review_actor != self.review_actor:
            raise frappe.PermissionError("Recorded review actor is immutable")

    def db_insert(self, *args, **kwargs):
        require_command(self.doctype)
        return super().db_insert(*args, **kwargs)

    def db_update(self, *args, **kwargs):
        require_command(self.doctype)
        return super().db_update(*args, **kwargs)

    def db_set(self, *args, **kwargs):
        raise frappe.PermissionError("Direct setters are not a placement mutation path")

    def before_rename(self, *args, **kwargs):
        raise frappe.PermissionError("Placement records cannot be renamed")

    def on_trash(self):
        raise frappe.PermissionError("Placement history cannot be deleted through CRUD")


class FrozenRecord(ProtectedRecord):
    """Allocation-era records (case/manifest/exposure/guard/response) are
    created exactly once by an authorized command and are immutable after.
    Attempt state advances only through AttemptRecord under command context,
    never through generic save."""

    def validate(self):
        super().validate()
        if self.get_doc_before_save():
            raise frappe.PermissionError("Placement allocation records are immutable after creation")


class AttemptRecord(ProtectedRecord):
    """Attempt identity is frozen at allocation; status moves only
    Allocated → Verified → In Progress → Sealed → Marking → Review →
    Finalized with a version CAS and one-way clock fields."""

    IDENTITY = (
        "case_name", "ordinal", "subject", "blueprint", "blueprint_version",
        "blueprint_hash", "policy", "policy_version", "policy_hash", "mode",
        "allocated_by",
    )
    CLOCKS = (
        "verified_by", "verified_at", "started_at", "deadline_at",
        "sealed_at", "seal_reason", "reviewed_by", "reviewed_at",
        "finalized_by", "finalized_at",
    )

    def validate(self):
        super().validate()
        before = self.get_doc_before_save()
        if not before:
            if self.status != "Allocated" or self.version != 1:
                raise frappe.ValidationError("New attempts start Allocated at version 1")
            if not self.allocated_by:
                raise frappe.ValidationError("Allocator is required")
            if any(self.get(field) for field in self.CLOCKS):
                raise frappe.ValidationError("New attempts have empty clocks")
            return
        for field in self.IDENTITY:
            if before.get(field) != self.get(field):
                raise frappe.PermissionError("Attempt identity is immutable")
        for field in self.CLOCKS:
            if before.get(field) and before.get(field) != self.get(field):
                raise frappe.PermissionError("Attempt clock and verification fields are immutable once set")
        if type(self.version) is not int or self.version != before.version + 1:
            raise frappe.ValidationError("Attempt version must advance by one")
        if before.status == self.status or (before.status, self.status) not in ATTEMPT_TRANSITIONS:
            raise frappe.PermissionError("Illegal attempt state transition")
        if self.status == "Verified" and not (self.verified_by and self.verified_at):
            raise frappe.ValidationError("Verification actor and time required")
        if self.status == "In Progress" and not (self.started_at and self.deadline_at):
            raise frappe.ValidationError("Session clock required")
        if self.status == "Sealed":
            if not (self.sealed_at and self.seal_reason):
                raise frappe.ValidationError("Seal time and reason required")
            if self.seal_reason not in ("Submitted", "Timeout"):
                raise frappe.ValidationError("Unsupported seal reason")
        if self.status == "Review" and not (self.reviewed_by and self.reviewed_at):
            raise frappe.ValidationError("Review actor and time required")
        if self.status == "Finalized" and not (self.finalized_by and self.finalized_at):
            raise frappe.ValidationError("Finalize actor and time required")


class ManifestRecord(FrozenRecord):
    """The form manifest additionally self-verifies its integrity at insert:
    the stored form_hash must bind the exact canonical form_json, the seed is
    bounded to 64 hex chars, the algorithm version must match the form and
    occurrences must be ordered 1..N. This holds even under
    ignore_permissions writes, because it lives in the controller."""

    def validate(self):
        super().validate()
        if not self.get_doc_before_save():
            try:
                form = json.loads(self.form_json)
            except ValueError as exc:
                raise frappe.ValidationError("Manifest form_json must be valid JSON") from exc
            if self.form_hash != digest(form):
                raise frappe.ValidationError("Manifest hash mismatch")
            if self.algorithm_version != form.get("algorithm"):
                raise frappe.ValidationError("Manifest algorithm mismatch")
            if not re.fullmatch(r"[0-9a-f]{64}", self.seed or ""):
                raise frappe.ValidationError("Manifest seed must be 64 hex characters")
            items = form.get("items")
            if not isinstance(items, list) or [i.get("order") for i in items] != list(range(1, len(items) + 1)):
                raise frappe.ValidationError("Manifest occurrences must be ordered 1..N")


class ScoreRecord(FrozenRecord):
    """Objective score rows are created exactly once per revision and
    self-verify that the stored hash binds a key-free projection."""

    def validate(self):
        super().validate()
        if not self.get_doc_before_save():
            try:
                result = json.loads(self.result_json)
            except ValueError as exc:
                raise frappe.ValidationError("Score result_json must be valid JSON") from exc
            if self.result_hash != digest(result):
                raise frappe.ValidationError("Score hash mismatch")
            if self.scorer_version != SCORER_VERSION or result.get("algorithm") != SCORER_VERSION:
                raise frappe.ValidationError("Unsupported scorer version")
            if type(self.revision) is not int or self.revision < 1:
                raise frappe.ValidationError("Score revision must be a positive integer")
            forbidden = ("seed", "answer", "item", "family", "option_id", "key")
            if any(field in result for field in forbidden):
                raise frappe.ValidationError("Score projection must not include keys or item identity")
            items = result.get("items")
            if not isinstance(items, list) or not items:
                raise frappe.ValidationError("Score items required")
            for entry in items:
                if not isinstance(entry, dict) or any(field in entry for field in forbidden):
                    raise frappe.ValidationError("Score projection must not include keys or item identity")
                if entry.get("outcome") not in ("correct", "incorrect", "missing"):
                    raise frappe.ValidationError("Unsupported score outcome")
            presented = result.get("presented")
            if type(presented) is not int or presented != (
                    result.get("correct", 0) + result.get("incorrect", 0) + result.get("missing", 0)):
                raise frappe.ValidationError("Score completeness mismatch")
            if type(result.get("missing")) is not int or result["missing"] < 0:
                raise frappe.ValidationError("Missing evidence must be an explicit non-negative count")


class DecisionRecord(FrozenRecord):
    """Released placement decisions are created exactly once and self-verify
    that the stored hash binds an internal course recommendation with no
    composite, CEFR or official TOEFL claim."""

    def validate(self):
        super().validate()
        if not self.get_doc_before_save():
            try:
                result = json.loads(self.result_json)
            except ValueError as exc:
                raise frappe.ValidationError("Decision result_json must be valid JSON") from exc
            if self.result_hash != digest(result):
                raise frappe.ValidationError("Decision hash mismatch")
            if self.status != "Released":
                raise frappe.ValidationError("Only released decisions are implemented in this increment")
            if type(self.revision) is not int or self.revision < 1:
                raise frappe.ValidationError("Decision revision must be a positive integer")
            if not (self.released_by and self.internal_level and self.course_code):
                raise frappe.ValidationError("Released decision requires actor, level and course")
            forbidden = ("percent", "cutoff", "cefr", "toefl", "composite", "seed", "answer")
            if any(field in result for field in forbidden):
                raise frappe.ValidationError("Decision must not include composite or external claims")
            if result.get("algorithm") != "course-map-v1":
                raise frappe.ValidationError("Unsupported decision algorithm")
            if result.get("internal_level") != self.internal_level or result.get("course_code") != self.course_code:
                raise frappe.ValidationError("Decision projection mismatch")


class AdmissionDecisionRecord(ProtectedRecord):
    """Owned institutional admission decision. Native Applicant/Student remain
    Education authorities. Status advances only through authorized commands;
    acceptance and native Student conversion do not enroll or bill."""

    IDENTITY = (
        "student_applicant", "program", "academic_year", "academic_term",
        "placement_decision", "existing_student", "drafted_by",
    )
    CLOCKS = (
        "reviewed_by", "reviewed_at", "decided_by", "decided_at",
        "outcome_reason", "conditions", "accepted_by", "accepted_at",
        "revoked_by", "revoked_at", "native_student", "converted_at",
    )

    def validate(self):
        super().validate()
        before = self.get_doc_before_save()
        if not before:
            if self.status != "Draft" or self.version != 1:
                raise frappe.ValidationError("New admission decisions start Draft at version 1")
            if not self.drafted_by:
                raise frappe.ValidationError("Drafting actor is required")
            if self.accepted or any(self.get(field) for field in self.CLOCKS):
                raise frappe.ValidationError("New admission decisions have empty clocks")
            return
        for field in self.IDENTITY:
            if before.get(field) != self.get(field):
                raise frappe.PermissionError("Admission identity is immutable")
        if type(self.version) is not int or self.version != before.version + 1:
            raise frappe.ValidationError("Admission version must advance by one")
        if before.status == self.status:
            self._validate_same_status(before)
            return
        if not is_admission_transition(before.status, self.status):
            raise frappe.PermissionError("Illegal admission state transition")
        for field in self.CLOCKS:
            if before.get(field) and before.get(field) != self.get(field):
                raise frappe.PermissionError("Admission clock fields are immutable once set")
        if before.accepted and not self.accepted:
            raise frappe.PermissionError("Offer acceptance cannot be reversed")
        if self.status == "Review" and not (self.reviewed_by and self.reviewed_at):
            raise frappe.ValidationError("Review actor and time required")
        if self.status in ADMISSION_OUTCOMES and not (self.decided_by and self.decided_at and self.outcome_reason):
            raise frappe.ValidationError("Decision actor, time and reason required")
        if self.status == "Conditional" and not self.conditions:
            raise frappe.ValidationError("Conditional admission requires recorded conditions")
        if self.status == "Approved" and self.conditions:
            raise frappe.ValidationError("Approved admission cannot carry unresolved conditions")
        if self.status == "Revoked" and not (self.revoked_by and self.revoked_at):
            raise frappe.ValidationError("Revocation actor and time required")
        if before.status in ("Approved", "Conditional") and before.native_student:
            raise frappe.PermissionError("Converted admission decisions are terminal for mutation")

    def _validate_same_status(self, before):
        if before.status not in ("Approved", "Conditional"):
            raise frappe.PermissionError("Illegal admission state transition")
        allowed = set()
        if not before.accepted and self.accepted:
            allowed.update(("accepted", "accepted_by", "accepted_at"))
            if not (self.accepted_by and self.accepted_at):
                raise frappe.ValidationError("Acceptance actor and time required")
        if before.status == "Approved" and not before.native_student and self.native_student:
            allowed.update(("native_student", "converted_at"))
            if not self.converted_at:
                raise frappe.ValidationError("Conversion time required")
            if not self.accepted:
                raise frappe.ValidationError("Native Student conversion requires an accepted Approved decision")
        if before.accepted and not self.accepted:
            raise frappe.PermissionError("Offer acceptance cannot be reversed")
        if before.native_student and before.native_student != self.native_student:
            raise frappe.PermissionError("Native Student pointer is immutable once set")
        for field in list(self.CLOCKS) + ["accepted"]:
            if field in allowed:
                continue
            if before.get(field) != self.get(field):
                raise frappe.PermissionError("Admission clock fields are immutable once set")
