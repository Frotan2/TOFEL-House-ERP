"""Per-bill reasons for earlier GL postings, without changing old receipts.

Date bounds remain the governing Owner policy's responsibility. Validation
belongs inside the command's work function, after receipt replay, so a
completed same-day request can still be replayed on a later day.
"""
from datetime import date

from toefl_house.configuration.rules import validate_change_reason


def request_payload(payload, reason):
    """Keep the exact legacy payload when the optional argument is absent."""
    if reason is not None and reason != "":
        return dict(payload, backdate_reason=reason)
    return payload


def validate_backdate_reason(posting, today, reason):
    """Require a bounded human reason for every newly backdated bill."""
    earlier = date.fromisoformat(str(posting)) < date.fromisoformat(str(today))
    if not earlier and (reason is None or reason == ""):
        return ""
    return validate_change_reason(reason, "Backdated billing reason")


def set_native_remarks(doc, reason):
    """Copy the reason to a native remarks field when the schema has one."""
    meta = getattr(doc, "meta", None)
    if reason and meta and meta.has_field("remarks"):
        doc.remarks = "Backdated billing reason: " + reason


def receipt_and_audit(result, audit_values, reason):
    """Bind the reason to the immutable receipt and audit hash if supplied."""
    if reason:
        result["backdate_reason"] = reason
        return [*audit_values, {"backdate_reason": reason}]
    return audit_values
