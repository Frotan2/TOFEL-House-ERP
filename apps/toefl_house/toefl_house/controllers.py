"""Owned document invariants apply even when generic writes ignore permissions."""
import frappe
import json
import re
from frappe.model.document import Document
from toefl_house.policy import ATTEMPT_TRANSITIONS, FROZEN_STATUSES, digest, is_config_transition
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
    Allocated → Verified → In Progress → Sealed with a version CAS and
    one-way clock fields."""

    IDENTITY = (
        "case_name", "ordinal", "subject", "blueprint", "blueprint_version",
        "blueprint_hash", "policy", "policy_version", "policy_hash", "mode",
        "allocated_by",
    )
    CLOCKS = (
        "verified_by", "verified_at", "started_at", "deadline_at",
        "sealed_at", "seal_reason",
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
