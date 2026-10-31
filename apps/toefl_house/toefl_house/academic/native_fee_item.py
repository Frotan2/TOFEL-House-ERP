"""Allow native Education to maintain only its newly created fee service item."""
import frappe

from toefl_house.configuration import rules


class FeeItemPermissionMixin:
    def _is_owned_fee_item_request(self):
        scope = rules.active_fee_item()
        actor = frappe.session.user
        return bool(
            scope and rules.active_command() == "create_fee_type"
            and scope[0] == actor
            and self.item_code == scope[1]
            and self.name in (None, scope[1])
            and self.item_group == "Fee Component"
            and self.is_stock_item == 0
            and self.is_sales_item == 1
        )

    def validate(self):
        # The pinned Education FeeCategory.create_item() does not set the
        # mandatory Item stock_uom. A site built without the ERPNext setup
        # wizard therefore fails with MandatoryError before any Fee Category
        # can be saved. Fill this *standard non-stock service unit* only for
        # the exact request-local Owner fee-type Item; never touch ordinary
        # merchandise, other Items, or a caller-supplied nonempty UOM.
        if self._is_owned_fee_item_request() and not self.stock_uom:
            from toefl_house.configuration.audit import require_authority
            if require_authority("business_policy") == frappe.session.user:
                if not frappe.db.exists("UOM", "Nos"):
                    raise frappe.ValidationError(
                        "ERPNext's standard Nos unit of measure is missing; "
                        "finish the native accounting and stock setup first")
                self.stock_uom = "Nos"
        return super().validate()

    def has_permission(self, permtype="read", *, debug=False, user=None):
        actor = frappe.session.user
        if (self._is_owned_fee_item_request()
                and user in (None, actor)
                and permtype in ("create", "write")):
            from toefl_house.configuration.audit import require_authority
            if require_authority("business_policy") == actor:
                return True
        return super().has_permission(permtype, debug=debug, user=user)
