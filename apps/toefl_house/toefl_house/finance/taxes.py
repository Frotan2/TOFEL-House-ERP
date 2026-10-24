"""Native tax application, verified — never invented.

Owner decision (FINANCE-POLICY-APPROVAL.md §1.2): TOEFL House issues documents
as *TOEFL House — Afghanistan — AFN*, the native Standard chart applies, and
**tax templates remain unconfigured until the owner supplies the applicable
tax policy**. This module implements exactly that boundary:

- the owner configures taxes the native way (a native ``Sales Taxes and
  Charges Template`` made default for the company, and/or native
  ``Item Tax Template`` rows on the item), which is the only place a rate,
  account, exemption or jurisdiction can enter the system;
- every submitted ``Sales Invoice`` is checked against that native
  configuration before it posts: each tax line must exist in a configured
  template, be one-sided and non-negative, name a real non-group account of
  the company, and the tax total must equal the native ``grand_total -
  net_total``;
- a cashier cannot add an ad-hoc tax line through the ordinary invoice form,
  because the line would not be backed by any owner configuration;
- with no template configured, the only permitted tax state is *no tax
  lines* — the explicit absence the owner decision records, not a zero rate
  this code invented.

No tax law, percentage, exemption, threshold or holiday is encoded here.
"""
import frappe

TEMPLATE = "Sales Taxes and Charges Template"
TEMPLATE_ROW = "Sales Taxes and Charges"
ITEM_TAX_TEMPLATE = "Item Tax Template"
ITEM_TAX_ROW = "Item Tax Template Detail"
ITEM_TAX = "Item Tax"
INVOICE = "Sales Invoice"
TOLERANCE = 0.005

# The native charge-type vocabulary of Sales Taxes and Charges. Nothing else
# can be a tax line; the list is ERPNext's own, not a business invention.
NATIVE_CHARGE_TYPES = (
    "Actual",
    "On Net Total",
    "On Previous Row Amount",
    "On Previous Row Total",
    "On Item Quantity",
)


def _flt(value):
    return round(float(value or 0), 6)


def _template_rows(template_name):
    """Tax rows of one configured native template, as plain dicts."""
    rows = frappe.db.get_all(
        TEMPLATE_ROW,
        filters={"parent": template_name, "parenttype": TEMPLATE},
        fields=["charge_type", "account_head", "rate", "description", "cost_center"],
        order_by="idx asc",
    )
    return [dict(row) for row in (rows or [])]


def default_templates(company):
    """Native default selling tax templates configured for a company."""
    rows = frappe.db.get_all(
        TEMPLATE,
        filters={"company": company, "is_default": 1, "docstatus": 0},
        fields=["name", "title", "company"],
        order_by="name asc",
        limit_page_length=20,
    )
    return [dict(row) for row in (rows or [])]


def item_tax_templates(item_codes):
    """Native Item Tax Template names bound to the given items."""
    if not item_codes:
        return []
    codes = sorted(set(item_codes))
    rows = frappe.db.get_all(
        ITEM_TAX,
        filters={"parent": ["in", codes], "parenttype": "Item"},
        fields=["parent", "item_tax_template"],
        limit_page_length=200,
    )
    names = sorted({row.get("item_tax_template") for row in (rows or [])
                    if row.get("item_tax_template")})
    return names


def _item_template_rows(template_name):
    rows = frappe.db.get_all(
        ITEM_TAX_ROW,
        filters={"parent": template_name, "parenttype": ITEM_TAX_TEMPLATE},
        fields=["tax_type", "tax_rate"],
        order_by="idx asc",
    )
    # An item tax template states an account + rate; ERPNext applies it as
    # an "On Net Total" row for that account. That mapping is the native
    # behaviour, not a rule added here.
    return [{"charge_type": "On Net Total", "account_head": row.get("tax_type"),
             "rate": row.get("tax_rate"), "description": "", "cost_center": None}
            for row in (rows or [])]


def allowed_tax_rows(company, item_codes=()):
    """Every native tax line this company/item combination may legitimately carry.

    Union of the company's default selling template(s) and every item tax
    template bound to the invoice's items. Empty means *no tax configuration*,
    which is the owner-declared state, not an error.
    """
    allowed = []
    for template in default_templates(company):
        allowed.extend(_template_rows(template["name"]))
    for name in item_tax_templates(item_codes):
        allowed.extend(_item_template_rows(name))
    return allowed


def _matches(row, allowed):
    """Whether one invoice tax line is backed by a configured template row."""
    if row.get("charge_type") not in NATIVE_CHARGE_TYPES:
        return False
    account = row.get("account_head")
    if not account:
        return False
    for candidate in allowed:
        if candidate.get("account_head") != account:
            continue
        if candidate.get("charge_type") != row.get("charge_type"):
            continue
        # A rate-based template fixes the rate; an "Actual" template fixes
        # the amount instead (its `rate` column carries the amount).
        if candidate.get("rate") not in (None, ""):
            if abs(_flt(candidate.get("rate")) - _flt(row.get("rate"))) > 1e-6:
                continue
        return True
    return False


def verify_tax_rows(taxes, allowed, *, net_total, grand_total, is_return=False):
    """Judge one invoice's tax lines against the native configuration.

    Pure: takes the invoice rows, the template rows and the native totals.
    Raises ``ValueError`` with the business reason. Returns the verified rows.
    """
    rows = [dict(row) for row in (taxes or [])]
    # Native totals carry the document's own sign: a credit note's net and
    # grand totals are negative, so their difference is negative too. The tax
    # lines must follow that direction rather than a convention invented here.
    expected = _flt(grand_total) - _flt(net_total)
    if is_return and expected > TOLERANCE:
        raise ValueError(
            "A credit note's tax total cannot be positive; check the native totals")
    if not is_return and expected < -TOLERANCE:
        raise ValueError(
            "A sales invoice cannot carry a negative tax total; check the native totals")
    if not rows:
        if allowed and abs(expected) > TOLERANCE:
            raise ValueError(
                "A native tax template applies to this invoice but it carries "
                "no tax line; the configured tax must be applied before posting")
        return []
    if not allowed:
        raise ValueError(
            "This invoice carries tax lines but no native tax template is "
            "configured; TOEFL House applies only owner-configured native taxes")
    total = 0.0
    for row in rows:
        if not _matches(row, allowed):
            raise ValueError(
                "Tax line " + str(row.get("account_head") or "")
                + " is not part of a configured native tax template")
        amount = _flt(row.get("tax_amount"))
        if expected < 0 and amount > TOLERANCE:
            raise ValueError("A credit note cannot carry a positive tax amount")
        if expected >= 0 and amount < -TOLERANCE:
            raise ValueError("A sales invoice cannot carry a negative tax amount")
        total += amount
    if abs(total - expected) > TOLERANCE:
        raise ValueError(
            "Tax lines do not add up to the native invoice tax total")
    return rows


def _account_is_postable(company, account):
    if not account:
        return False
    row = frappe.db.get_value("Account", account,
                              ["company", "is_group", "disabled"], as_dict=True)
    return bool(row) and row.company == company and not int(row.is_group or 0) \
        and not int(row.disabled or 0)


def verify_document_taxes(doc, method=None):
    """``Sales Invoice`` before_submit seam: refuse unbacked tax lines.

    Runs after the native controller has computed taxes and totals, and
    before any GL or stock posting exists, so a refused invoice leaves no
    accounting history behind.
    """
    company = getattr(doc, "company", None)
    if not company:
        raise frappe.ValidationError("A tax-checked invoice requires a company")
    items = [row.get("item_code") for row in (doc.get("items") or [])]
    allowed = [row for row in allowed_tax_rows(company, items)
               if _account_is_postable(company, row.get("account_head"))
               or not row.get("account_head")]
    try:
        verify_tax_rows(
            [row.as_dict() if hasattr(row, "as_dict") else row
             for row in (doc.get("taxes") or [])],
            allowed,
            net_total=getattr(doc, "net_total", 0),
            grand_total=getattr(doc, "grand_total", 0),
            is_return=int(getattr(doc, "is_return", 0) or 0) == 1,
        )
    except ValueError as exc:
        raise frappe.ValidationError(str(exc)) from exc


def supplied_taxes_permitted(company, item_codes, taxes):
    """Guard-side check used before an invoice is saved.

    Same rule as the submit seam, against whatever tax lines the request
    already carries. A native form with the owner's configured template
    passes; a hand-added line does not.
    """
    if not taxes:
        return True
    allowed = allowed_tax_rows(company, item_codes)
    if not allowed:
        return False
    try:
        for row in taxes:
            payload = row.as_dict() if hasattr(row, "as_dict") else dict(row)
            if not _matches(payload, allowed):
                return False
    except (TypeError, ValueError):
        return False
    return True


def describe_tax_configuration(company=None):
    """Owner-facing readiness facts about native tax configuration.

    Read-only; used by the finance desk and the acceptance procedure so the
    operator can see *what the system will apply* without guessing. It
    reports configuration state only — it never asserts a jurisdiction,
    rate or exemption.
    """
    companies = [company] if company else [
        row.get("name") for row in
        (frappe.db.get_all("Company", fields=["name"], limit_page_length=50) or [])]
    out = {"companies": []}
    for name in companies:
        templates = default_templates(name)
        rows = allowed_tax_rows(name)
        out["companies"].append({
            "company": name,
            "default_selling_templates": [row["name"] for row in templates],
            "configured_tax_lines": len(rows),
            "state": "Configured" if templates else "No native tax configured",
        })
    if len(out["companies"]) == 1:
        out.update(out["companies"][0])
    return out


@frappe.whitelist(methods=["GET", "POST"])
def tax_configuration(company=None):
    """Read-only tax readiness for the finance workspace."""
    from toefl_house.security import require_operational
    require_operational()
    roles = set(frappe.get_roles(frappe.session.user))
    if not roles & {"Finance Officer", "Finance Manager", "Finance Auditor",
                    "Course Owner"}:
        raise frappe.PermissionError("Tax configuration is finance-readable only")
    return describe_tax_configuration(company)
