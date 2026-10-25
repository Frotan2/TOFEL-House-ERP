from frappe.model.document import Document
from toefl_house.operations.notifications import validate_dispatch_rule
class THNotificationDispatchRule(Document):
    def validate(self):
        # Build rule dict from fields and validate
        rule={
            "event_type": self.event_type,
            "enabled": bool(self.enabled),
            "recipients": [r.recipient for r in (self.recipients or [])],
            "severity": self.severity,
            "channel": self.channel,
            "timing_delay_minutes": self.timing_delay_minutes,
            "max_retries": self.max_retries,
            "retry_delay_minutes": self.retry_delay_minutes,
            "escalate_after_minutes": self.escalate_after_minutes,
            "escalation_recipients": [r.recipient for r in (self.escalation_recipients or [])],
        }
        validate_dispatch_rule(rule)
def validate(doc, method=None):
    doc.validate()
