"""Transactional order cancellation. Draft voids never post or reverse accounting."""
from uuid import uuid4

import frappe
from frappe import _


def assert_active_order(invoice):
    if invoice.docstatus == 0 and invoice.get("status") == "Cancelled":
        frappe.throw(_("This unpaid order was cancelled and cannot be edited or paid."))


def validate_order_state(doc, method=None):
    """Reject resurrection through direct REST/Desk saves as well as URY APIs."""
    stored = None
    if doc.name:
        stored = frappe.db.get_value("POS Invoice", doc.name,
            ["docstatus", "status"], as_dict=True)
    if stored and stored.docstatus == 0 and stored.status == "Cancelled":
        frappe.throw(_("This unpaid order was cancelled and cannot be edited or paid."))
    assert_active_order(doc)


def cancel_order_transaction(invoice_id, reason):
    from ury.ury.doctype.ury_order import ury_order as orders
    from ury.ury_pos.api import _require_ury_profile_access
    from ury.ury.api.invoice_item_extensions import run_order_guards

    if frappe.session.user == "Guest":
        frappe.throw(_("Login is required."), frappe.PermissionError)
    if not isinstance(invoice_id, str) or not invoice_id.strip() or len(invoice_id) > 140:
        frappe.throw(_("Invalid order reference."))
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 1000:
        frappe.throw(_("Enter a cancellation reason of up to 1000 characters."))
    reason = reason.strip()
    savepoint = "ury_cancel_" + uuid4().hex
    frappe.db.savepoint(savepoint)
    try:
        invoice = frappe.get_doc("POS Invoice", invoice_id, for_update=True)
        invoice.check_permission("read")
        if not frappe.has_permission("POS Invoice", "cancel", doc=invoice):
            frappe.throw(_("You do not have permission to cancel this invoice."), frappe.PermissionError)
        profile = _require_ury_profile_access(invoice.pos_profile)
        if invoice.company != profile.company or invoice.branch != profile.branch:
            frappe.throw(_("Order company and branch must match its POS Profile."), frappe.PermissionError)
        if frappe.session.user != "Administrator" and invoice.branch != orders.getBranch():
            frappe.throw(_("You are not allowed to cancel an invoice from another branch."), frappe.PermissionError)
        already_cancelled = invoice.docstatus == 2 or (invoice.docstatus == 0 and invoice.status == "Cancelled")
        orders._enforce_order_access(invoice, require_modify=not already_cancelled)
        if already_cancelled:
            return {"name": invoice.name, "status": "Cancelled", "already_cancelled": True}
        if invoice.docstatus not in (0, 1) or invoice.get("is_return") or invoice.get("consolidated_invoice"):
            frappe.throw(_("Use the controlled return workflow for returned or consolidated sales."))
        if invoice.get("custom_merged_pos_invoice") or frappe.db.exists("POS Invoice", {
            "custom_merged_pos_invoice": invoice.name, "docstatus": ["<", 2],
        }):
            frappe.throw(_("Unmerge the bills before cancelling this order."))
        run_order_guards("ury_before_order_cancel", invoice)
        if invoice.docstatus == 0:
            invoice.check_permission("write")
        # Do not silently ignore KOT failures and report a successful cancellation.
        orders.cancel_kot(invoice.name)
        if invoice.docstatus == 0:
            # Operational void only: retain the invoice/KOT identity and docstatus 0.
            invoice.db_set({"status": "Cancelled", "cancel_reason": reason})
        else:
            invoice.cancel_reason = reason
            invoice.cancel()  # Exactly once; ERPNext owns reversal of submitted sales.
        from frappe.utils import escape_html
        invoice.add_comment("Info", _("Order cancelled: {0}").format(escape_html(reason)))
        if invoice.restaurant_table:
            orders._free_tables_if_no_open_invoices(
                invoice.restaurant_table, invoice.get("custom_merged_tables"), commit=False)
        return {"name": invoice.name, "status": "Cancelled", "docstatus": invoice.docstatus}
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
