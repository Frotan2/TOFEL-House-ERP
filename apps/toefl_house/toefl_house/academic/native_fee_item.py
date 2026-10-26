"""Allow native Education to maintain only its newly created fee service item."""
import frappe

from toefl_house.configuration import rules


class FeeItemPermissionMixin:
    def has_permission(self, permtype="read", *, debug=False, user=None):
        scope = rules.active_fee_item()
        actor = frappe.session.user
        if (scope and rules.active_command() == "create_fee_type"
                and scope[0] == actor and user in (None, actor)
                and permtype in ("create", "write")
                and self.item_code == scope[1]
                and self.name in (None, scope[1])
                and self.item_group == "Fee Component"
                and self.is_stock_item == 0
                and self.is_sales_item == 1):
            from toefl_house.configuration.audit import require_authority
            if require_authority("business_policy") == actor:
                return True
        return super().has_permission(permtype, debug=debug, user=user)
