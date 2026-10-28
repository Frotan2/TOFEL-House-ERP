"""Adversarial contracts for native book-sale and cash-refund evidence.

The receipt verifier must reject a forged financial trail even when the net
sum looks correct. These are synthetic records, never production transactions.
"""
import copy
import unittest

from tools.native.native_checks import validate_book_reconciliation


def make_valid_receipt():
    amount, quantity, value = 600.0, 2.0, 200.0
    accounts = {"cash": "Cash - SYN", "receivable": "Debtors - SYN",
                "income": "Book Revenue - SYN"}
    documents = {"sale": "SYN-SALE", "payment": "SYN-PAY",
                 "return": "SYN-RETURN", "refund": "SYN-REFUND"}
    baseline = {"cash": 1000.0, "customer": 0.0,
                "stock_qty": 10.0, "stock_value": 1000.0}
    stages = {"baseline": baseline,
              "sale": {"cash": 1000.0, "customer": amount,
                       "stock_qty": 8.0, "stock_value": 800.0},
              "payment": {"cash": 1600.0, "customer": 0.0,
                          "stock_qty": 8.0, "stock_value": 800.0},
              "return": {"cash": 1600.0, "customer": -amount,
                         "stock_qty": 10.0, "stock_value": 1000.0},
              "refund": dict(baseline)}

    def gl(kind, account, signed):
        return {"company": "Synthetic Company", "voucher_no": documents[kind],
                "voucher_type": "Sales Invoice" if kind in ("sale", "return") else "Payment Entry",
                "account": accounts[account],
                "party_type": "Customer" if account == "receivable" else None,
                "party": "SYN-CUSTOMER" if account == "receivable" else None,
                "debit": max(signed, 0), "credit": max(-signed, 0), "is_cancelled": 0}

    def stock(kind, signed_qty, signed_value):
        return {"voucher_no": documents[kind], "item_code": "SYN-BOOK",
                "warehouse": "Books - SYN", "actual_qty": signed_qty,
                "stock_value_difference": signed_value, "is_cancelled": 0}

    def payment(kind, direction, source, target, reference, allocation):
        return {"payment_type": direction, "party_type": "Customer",
                "party": "SYN-CUSTOMER", "paid_from": accounts[source],
                "paid_to": accounts[target], "paid_amount": amount,
                "received_amount": amount,
                "references": [{"reference_doctype": "Sales Invoice",
                                "reference_name": documents[reference],
                                "allocated_amount": allocation}]}

    return {
        "user": "synthetic-book-seller@example.test",
        "company": "Synthetic Company", "currency": "AFN",
        "customer": "SYN-CUSTOMER", "item": "SYN-BOOK",
        "warehouse": "Books - SYN", "amount": amount,
        "quantity": quantity, "unit_price": 300.0, "unit_cost": 100.0,
        "accounts": accounts, "documents": documents,
        "document_status": {name: 1 for name in documents},
        "invoice_totals": {"sale": amount, "return": -amount},
        "outstanding": {"sale": 0.0, "return": 0.0},
        "stages": stages,
        "gl_entries": {
            "sale": [gl("sale", "receivable", amount),
                     gl("sale", "income", -amount)],
            "payment": [gl("payment", "cash", amount),
                        gl("payment", "receivable", -amount)],
            "return": [gl("return", "income", amount),
                       gl("return", "receivable", -amount)],
            "refund": [gl("refund", "receivable", amount),
                       gl("refund", "cash", -amount)],
        },
        "stock_entries": {
            "sale": [stock("sale", -quantity, -value)],
            "return": [stock("return", quantity, value)],
        },
        "payment_details": {
            "payment": payment("payment", "Receive", "receivable", "cash",
                               "sale", amount),
            "refund": payment("refund", "Pay", "cash", "receivable",
                              "return", -amount),
        },
    }


class BookLedgerEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.receipt = make_valid_receipt()

    def expect_rejected(self, mutated):
        with self.assertRaisesRegex(ValueError, "Invalid book accounting reconciliation"):
            validate_book_reconciliation(mutated)

    def test_valid_sale_payment_return_and_cash_refund(self):
        self.assertIsNone(validate_book_reconciliation(self.receipt))

    def test_double_sided_gl_row_rejected_even_if_net_amount_matches(self):
        forged = copy.deepcopy(self.receipt)
        receivable = forged["gl_entries"]["sale"][0]
        receivable["debit"] = 900.0
        receivable["credit"] = 300.0
        self.expect_rejected(forged)

    def test_negative_gl_amounts_rejected_even_if_net_matches(self):
        forged = copy.deepcopy(self.receipt)
        receivable = forged["gl_entries"]["sale"][0]
        receivable["debit"] = -100.0
        receivable["credit"] = -700.0
        self.expect_rejected(forged)

    def test_split_gl_reversal_cannot_hide_inside_correct_net_balance(self):
        forged = copy.deepcopy(self.receipt)
        receivable = forged["gl_entries"]["sale"][0]
        receivable["debit"] = 700.0
        offset = copy.deepcopy(receivable)
        offset["debit"] = 0.0
        offset["credit"] = 100.0
        forged["gl_entries"]["sale"].append(offset)
        self.expect_rejected(forged)

    def test_offsetting_stock_movements_cannot_hide_inside_correct_net(self):
        forged = copy.deepcopy(self.receipt)
        sale_stock = forged["stock_entries"]["sale"][0]
        sale_stock["actual_qty"] = -3.0
        sale_stock["stock_value_difference"] = -300.0
        fake_receipt = copy.deepcopy(sale_stock)
        fake_receipt["actual_qty"] = 1.0
        fake_receipt["stock_value_difference"] = 100.0
        forged["stock_entries"]["sale"].append(fake_receipt)
        self.expect_rejected(forged)

    def test_mismatched_stock_valuation_direction_rejected(self):
        forged = copy.deepcopy(self.receipt)
        sale_stock = forged["stock_entries"]["sale"][0]
        sale_stock["actual_qty"] = -1.0
        sale_stock["stock_value_difference"] = 100.0
        forged["stock_entries"]["sale"].append({
            **sale_stock, "actual_qty": -1.0, "stock_value_difference": -300.0
        })
        # The exact value happens to match, but one SLE increased inventory value.
        self.expect_rejected(forged)


if __name__ == "__main__":
    unittest.main()
