"""Fresh canonical resource authorization for the app's realtime delivery guard."""
import frappe
from foundation_security.guards import validate_student_scope


@frappe.whitelist()
def authorize(kind: str, resource: str, name: str = "") -> bool:
    validate_student_scope()
    user = frappe.session.user
    if user in (None, "Guest") or not all(isinstance(v,str) and len(v)<=512 for v in (kind,resource,name)):
        return False
    if kind == "user":
        return resource == user
    if kind == "document" and resource and name:
        return bool(frappe.has_permission(resource, doc=name, ptype="read"))
    if kind == "doctype" and resource:
        return bool(frappe.has_permission(resource, ptype="read"))
    if kind == "task" and resource:
        from rq.job import Job
        from rq.exceptions import NoSuchJobError
        from frappe.utils.background_jobs import get_redis_conn
        try:
            job = Job.fetch(resource, connection=get_redis_conn())
        except NoSuchJobError:
            return False
        return job.kwargs.get("site") == frappe.local.site and job.kwargs.get("user") == user
    # Broad site/website/doctype rooms and unknown resources have no adequate
    # per-record authorization contract. Do not infer one from a role or ID.
    return False
